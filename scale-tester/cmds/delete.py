import cmd
import pprint
import logging
import keystoneclient.v2_0.client as keystone_client
#import novaclient.v1_1.client as nova_client
from novaclient.client import Client as NovaClient
import neutronclient.v2_0.client as neutron_client
import heatclient.v1.client as heat_client
import time
import re
import stack as stack_module
import pudb

LOG = logging.getLogger("scale_tester")

TENANT_NAME_REGEX = "tenant-test-.*"

class TenantCleanupCmd(cmd.Command):
    """
    Deletes instances, floating IPs, routers, and networks
    that belong to a deleted tenant.
    """

    def __init__(self, cmd_context, program):
        super(TenantCleanupCmd,self).__init__()
        self.context = cmd_context
        self.program = program

    def init(self):
        return cmd.SUCCESS

    def execute(self):
        openstack_conf = self.program.context["openstack_conf"]
        auth_url = openstack_conf["openstack_auth_url"]
        admin_username = openstack_conf['openstack_user']
        admin_password = openstack_conf['openstack_password']

        admin_keystone_c = cmd.get_keystone_client(self.program)

        # Get list of valid tenant IDs
        tenant_list = admin_keystone_c.tenants.list()
        tenant_id_list = []
        for tenant in tenant_list:
            tenant_id_list.append(tenant.id)
        
        print("VALID TENANT IDs: %s" % tenant_id_list)

        # Delete instances with invalid project_id
        nova_c = NovaClient("1.1", admin_username, admin_password,
                            "admin", auth_url)

        search_opts = {"all_tenants": True}
        server_list = nova_c.servers.list(search_opts=search_opts)
        #print("NOVA SERVERS: %s" % server_list)
        for server in server_list:
            #print("SERVER: %s" % pprint.pformat(server.__dict__))
            print("SERVER, tenant_id: %s  name: %s" % (server.tenant_id,
                                                       server.name))
            if server.tenant_id not in tenant_id_list:
                server.delete()
                
        neutron_c = neutron_client.Client(auth_url=auth_url,
                                          username=admin_username,
                                          password=admin_password,
                                          tenant_name="admin")

        # Delete floating IPs with invalid tenant_id
        fips = neutron_c.list_floatingips()
        fips = fips["floatingips"]
        for fip in fips:
            print("FLOATING IP: %s" % fip)
            if fip['tenant_id'] not in tenant_id_list:
                neutron_c.delete_floatingip(fip['id'])
        
        # Delete routers with invalid tenant_id
        routers = neutron_c.list_routers()
        routers = routers["routers"]
        for router in routers:
            print("ROUTER: %s" % router)
            if router['tenant_id'] not in tenant_id_list:
                if router['name'] != "PHYSICAL_GLOBAL_ROUTER_ID":
                    router_ports = neutron_c.list_ports(device_id=router['id'],
                                                        device_owner="network:router_interface")['ports']
                    router_gw = neutron_c.list_ports(device_id=router['id'],
                                                        device_owner="network:router_gateway")['ports']
                    print("router ports: %s" % router_ports)
                    print("router_gw :%s" % router_gw)
                    for router_port in router_ports:
                        neutron_c.remove_interface_router(router['id'],
                                                          {'port_id': router_port['id']})
                    if len(router_gw) > 0:
                        neutron_c.remove_gateway_router(router['id'])
                                                        
                    neutron_c.delete_router(router['id'])

        # Delete networks with invalid tenant_id
        networks = neutron_c.list_networks()
        networks = networks["networks"]
        for network in networks:
            print("NETWORK: %s" % network)
            if network['tenant_id'] not in tenant_id_list:                
                network_ports = neutron_c.list_ports(network_id=network['id'])['ports']
                print("network ports: %s" % network_ports)
                for network_port in network_ports:
                    neutron_c.delete_port(network_port['id'])
                neutron_c.delete_network(network['id'])

        return cmd.SUCCESS

    def undo(self):
        return cmd.SUCCESS

class DeleteStacksCmd(cmd.Command):
    """
    This is a factory cmd that walks resource data structures (tenants and
    users) and creates invidual CreateStackCmd for each tenant. 
    """
    
    def __init__(self, cmd_context, program):
        super(DeleteStacksCmd,self).__init__()
        self.context = cmd_context
        self.program = program

    def init(self):
        #if ("program.resources" in self.program.context):
        #    return cmd.SUCCESS
        #else:
        #    return cmd.FAILURE_HALT
        
        # make sure that self.program.context['program_runner'] exists
        return cmd.SUCCESS

    def execute(self):
        
        openstack_conf = self.program.context["openstack_conf"]
        auth_url = openstack_conf["openstack_auth_url"]
        heat_url = openstack_conf['openstack_heat_url']

        admin_keystone_c = cmd.get_keystone_client(self.program)
        tenant_list = admin_keystone_c.tenants.list()

        for tenant in tenant_list:

            if re.match(TENANT_NAME_REGEX,tenant.name) != None:
                LOG.info("DELETE TENANT: %s" % (tenant))

                user_list = admin_keystone_c.tenants.list_users(tenant)
                username = None
                for user in user_list:
                    if user.name != "admin":
                        LOG.info("    DELETE USER: %s" % (user))
                        username = user.name

                if username == None:
                    continue

                user_keystone_c = keystone_client.Client(auth_url=auth_url,
                                                         username=username,
                                                         password=username,
                                                         tenant_name=tenant.name)

                user_heat_url = heat_url % (user_keystone_c.auth_tenant_id)
                
                LOG.info("user_heat_url = %s" % (user_heat_url)) 
                
                user_heat_c = heat_client.Client(user_heat_url,
                                                 token=user_keystone_c.auth_token)
                
                stack_list = user_heat_c.stacks.list()
                for stack in stack_list:
                    LOG.info("    DELETE STACK: %s" % stack)
                    
                    try:
                        user_heat_c.stacks.delete(stack.id)
                        LOG.info("tenant stack (id=%s) deleted" % (stack.id))
                    except Exception:
                        LOG.error("Exception while deleting stack %s" % stack.id)
                
                    time_limit = 60
                    start_time = time.time()
                    cur_time = time.time()
                    while cur_time - start_time < time_limit:
                        time.sleep(5)
                        cur_time = time.time()
                        
                        stack_status = _get_stack(user_heat_c, stack.stack_name)
                        if stack_status == None:
                            break
                            LOG.info("        FINISHED DELETING STACK %s" % stack)
                        else:
                            LOG.info("        STACK STATUS: %s" % stack_status)
                        
                
                for user in user_list:
                    if user.name != "admin":
                        admin_keystone_c.users.delete(user)
                        LOG.info("deleted user %s",str(user))

                admin_keystone_c.tenants.delete(tenant)
                LOG.info("deleted tenant %s" % tenant)
                    
        return cmd.SUCCESS

    def undo(self):
        return cmd.SUCCESS


def _get_stack(heat_session, stack_name):
    filter = {"name": stack_name}
    stack_list = heat_session.stacks.list(filters=filter)
    for stack_item in stack_list:
        LOG.debug("stack status: %s" % stack_item)
        LOG.debug("   stack_id: %s" % stack_item.id)
        return stack_item
