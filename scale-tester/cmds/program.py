import logging
import pprint
from collections import deque

LOG = logging.getLogger("scale_tester")

class Resources:
    """
    This class encapsulates the data structures used for storing program
    created resources such as tenants, users, networks, etc
    """

    def __init__(self):
        """
        constructor.  resource objects are keyed by their uuids
        """
        self.tenants = {}
        self.users = {}
        self.tenant_users = {}

    def add_tenant(self,tenant):
        """
        Register a created tenant
        
        """
        if(tenant is not None):
            self.tenants[tenant.id] = tenant
            LOG.debug(pprint.pformat(tenant))
            
            # create initial placeholder for mapping tenant users to a
            # tenant_id
            self.tenant_users[tenant.id] = []
    
    def get_tenant(self,tenant_id):
        """
        Getter for retrieving a particular tenant (based on its unique id)
        """
        if tenant_id in self.tenants:
            return self.tenants[tenant_id]

    def add_user(self,user):
        """
        register a newly created user (based on its unique id)
        The user object is expected to be of the same type as created /
        returned by the keystone api
        """
        
        if (user is not None):
            self.users[user.id] = user
            LOG.debug(pprint.pformat(user))
            
            # associate user with tenant mapping
            if (user.tenantId in self.tenant_users):
                tenant_users = self.tenant_users[user.tenantId]
                tenant_users.append(user)

            pu.db 

    def get_user(self,user_id):
        """
        Getter for retrieving a particular user (based on its unique id)
        """
        if (user_id in self.users):
            return self.users[user_id]
    
    def get_tenant_users(self, tenant_id):
        """
        A generator for iterating through all the users for a tenant
        """
        pass

class Program(object):
    """
    This class represents a collection of parsed commands to be executed by the
    programm runner

    Preallocated context keys

    "program.resources" -> Resources object
    
    """

    def __init__(self):
        """
        attributes
        commands represents the list of commands in the program
        context represents program wide scope for state that's accessible
        to all commands
        """
        self.commands = deque()
        self.context = {}
        self.name = None
        
        # tracks created openstack resource objects
        resources = Resources()
        self.context["program.resources"] = resources

    def add_command(self,cmd):
        """appends a cmd to the commands list"""
        self.commands.append(cmd)

class ProgramRunner(object):
    """
    This class represents the execution engine for a program
    """

    def __init__(self):
        """
        constructor
        """
        self.execution_queue= deque()
        self.program = None
        self.completed_commands = deque() 

        # self.is_test_mode = True

    def set_program(self,program):
        self.program = program
        
        # pop the first command from the program
        cmd = self.program.commands.popleft()

        self.execution_queue.append(cmd)

    def run(self):
        LOG.debug("ProgramRunner run started")
        while(True):
            
            if len(self.execution_queue) > 0:
                LOG.debug("popping next command from the execution queue ")
                cmd = self.execution_queue.popleft()
               
                # wrap each command step in a function so that exception
                # handling is easier to deal with

                # we can add status checks after each call to check
                # whether the next step should be invoked or not
                cmd.init()
                cmd.execute()

                # if a cmd.done() indicates that it's not done, appendleft
                # the current cmd
                cmd.done()
                
                self.completed_commands.append(cmd)

            elif len(self.program.commands) > 0: 
                LOG.debug("popping next cmd from the program commands queue ")
                cmd = self.program.commands.popleft()
                self.execution_queue.append(cmd)
            else:
                LOG.debug("No more commands")
                break

        # Clean up the results of a program/test run
        while (len(self.completed_commands)>0):
            executed_cmd = self.completed_commands.popleft()
            executed_cmd.undo()






