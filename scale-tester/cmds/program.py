import logging
import pprint
import re
from collections import deque
import tenants
import stack
import importlib
import threading
import traceback
import delete

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
        self.traffic_results = {}
        self.tenants_stacks = {}
        self.tenant_failed_ips = {}

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

def parse_program(test_configuration):
    """
    This function accepts the dictionary form of a json test program,
    parses it, and creates the corresponding program instance.
    """
    LOG.debug(pprint.pformat(test_configuration))
    
    module_class_regex = "(?P<module_path>.*)\.(?P<class_name>.*Cmd)"
    

    program_context = test_configuration['program']['context']
    LOG.debug("program context")
    LOG.debug(pprint.pformat(program_context))

    commands = test_configuration['program']['commands']
    LOG.debug("program commands")


    program = Program()
    program.context = program_context
    resources = Resources()
    program.context['program.resources'] = resources

    for command_dict in commands:
        cmd_name = command_dict['command_name']
        LOG.debug(cmd_name)
        
        match_results = re.match(module_class_regex, cmd_name)

        LOG.debug("module_path=%s" % (match_results.group('module_path')))
        LOG.debug("class name = %s " % (match_results.group('class_name')))
        
        module = importlib.import_module(match_results.group('module_path'))
        class_obj = getattr(module,match_results.group('class_name'))

        # LOG.debug("class object name = %s" % (class_obj.__name__))
        cmd_context = command_dict['context']
        LOG.debug(pprint.pformat(cmd_context))

        obj = class_obj(cmd_context, program)

        program.add_command(obj)
        
    return program

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
        self.failed = False
        
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
        """
        Associates a program with the ProgramRunner.

        enqueue the first program command into the execution queue
        """
        self.program = program
        
        # make sure the program has a reference back to the program runner
        self.program.context['program_runner'] = self
        
        # pop the first command from the program
        if program.is_delete:
            cmd = delete.DeleteStacksCmd(None, self.program)
            program.commands = deque() # ignore other commands
        else:
            cmd = self.program.commands.popleft()

        self.execution_queue.append(cmd)
    
    def enqueue_command(self, cmd):
        self.execution_queue.append(cmd)
        LOG.debug("enqueued cmd %s in program_runner for execution" %
                  (cmd.name))

    def run(self):
        LOG.debug("ProgramRunner run started")

        pending_threads = []

        # max thread window size
        # -1 == unlimited
        max_threads = -1

        if "max_threads" in self.program.context['global_test_parameters']:
            max_threads = self.program.context['global_test_parameters']['max_threads']
        
        LOG.debug("max threads = %d" % (max_threads))

        try:
            while(True):
            
                if len(self.execution_queue) > 0:
                    LOG.debug("popping next command from the execution queue ")
                    cmd = self.execution_queue.popleft()
               
                    # wrap each command step in a function so that exception
                    # handling is easier to deal with

                    # we can add status checks after each call to check
                    # whether the next step should be invoked or not
                    cmd.init()

                    if cmd.threaded is True:
                        LOG.debug("Starting thread...")
                        cmd_thread = threading.Thread(target=cmd.execute)
                        cmd_thread.start()
                        pending_threads.append(cmd_thread)
                        
                        LOG.debug("number of pending threads = %d" % \
                                  (len(pending_threads)))

                        # wait for the window of threads to finish before
                        # proceeding
                        # after the threads are done, clear the pending_threads
                        # list
                        if max_threads > 0 and len(pending_threads) >= max_threads:
                            LOG.debug("max thread window (%d) reached, joining on pending threads" % \
                                      (max_threads))
                            for pending_thread in pending_threads:
                                pending_thread.join()
                                LOG.debug("thread joined")

                            pending_threads = []
                            
                            
                    else:
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
        except:
            LOG.error("Caught unexpected exception")
            LOG.error(traceback.format_exc())

        # wait for threads to join
        LOG.debug("joining on pending threads (%d)" % len(pending_threads))
        for pending_thread in pending_threads:
            pending_thread.join()
            LOG.debug("thread joined")

        # Clean up the results of a program/test run
        while (len(self.completed_commands)>0):
            executed_cmd = self.completed_commands.pop()
            executed_cmd.undo()






