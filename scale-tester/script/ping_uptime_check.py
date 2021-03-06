import time
import subprocess
import signal
import sys
import re
import neutronclient.v2_0.client as neutron_client

#dst_ip_list = ["5.5.2.100",
#                "5.5.2.99",
#                "5.5.2.98",
#                "5.5.2.97"]

#dst_ip_list = ["10.1.10.188",
#               "10.1.10.63"]
dst_ip_list = []

open_process_list = []
results_dict = {}

NEUTRON_FIP_LIST_REGEX = ".*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}).*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}).*"
OSTK_AUTH_URL = "http://10.1.10.63:5000/v2.0/"

def get_floating_ips():
    auth_url = OSTK_AUTH_URL
    neutron_session = neutron_client.Client(auth_url=auth_url,
                                            username="admin2",
                                            password="admin2",
                                            tenant_name="admin")

    tenant_floating_ip_objs = neutron_session.list_floatingips()
    tenant_floating_ip_objs = tenant_floating_ip_objs['floatingips']
    for fip_dict in tenant_floating_ip_objs:
        dst_ip_list.append(fip_dict['floating_ip_address'])
    dst_ip_list.sort()

def proc_cleanup():
    for process in open_process_list:
            process.kill()
    parse_results()

def signal_handler(signal, frame):
    print('You pressed Ctrl+C!')
    proc_cleanup()
    sys.exit(0)

PING_CMD_STR = "ping -ODn -W 0.9 -i 1 %s > /tmp/ping_check/%s.out"
PING_SUCCESS_REGEX = ".*bytes from (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}).*icmp_seq=(\d+).*"
PING_DUP_REGEX = ".*DUP.*"
PING_FAIL_REGEX = ".*no answer.*icmp_seq=(\d+).*"

def start_pings():
    get_floating_ips()
    for dst_ip in dst_ip_list:
        cmd_str = PING_CMD_STR % (dst_ip, dst_ip)
        print("Launching cmd: %s" % cmd_str)
        proc = subprocess.Popen(cmd_str, shell=True)
        open_process_list.append(proc)

    time.sleep(3600) # sleep for 1 hour
    proc_cleanup()
    sys.exit(0)

def parse_results():
    global_max_gap_size = 0
    for dst_ip in dst_ip_list:
        gap_start_seq = 0
        gap_start_line = 0
        max_gap_size = 0
        max_gap_start_line = ""
        cur_seq = 0
        in_gap = False
        results_file = open("/tmp/ping_check/%s.out" % dst_ip)
        skipped_first = False
        first_success_seen = False

        for line in results_file:
            #if not skipped_first:
            #    skipped_first = True
            #    continue

            # ignore duplicate packets
            if re.match(PING_DUP_REGEX, line):
                continue

            match_obj = re.match(PING_SUCCESS_REGEX, line)
            if match_obj is None:
                line_valid = False
            else:
                line_ip, seq_no = match_obj.group(1,2)
                if line_ip != dst_ip:
                    line_valid = False
                else:
                    line_valid = True

            if line_valid:
                first_success_seen = True
                if in_gap == False:
                    pass
                else:
                    in_gap = False
                    gap_size = cur_seq - gap_start_seq
                    if gap_size > max_gap_size:
                        max_gap_size = gap_size
                        max_gap_start_line = gap_start_line

                cur_seq += 1
            else:
                match_obj = re.match(PING_FAIL_REGEX, line)
                if match_obj:
                    seq_no = match_obj.group(1)

                    if not first_success_seen:
                        continue

                    if in_gap == False:
                        gap_start_seq = cur_seq
                        gap_start_line = line
                        in_gap = True
                    else:
                        pass
                    
                    cur_seq += 1

        results_dict[dst_ip] = {"max_gap_size": max_gap_size,
                                "max_gap_start_line": max_gap_start_line,
                                "first_success_seen": first_success_seen}

        if max_gap_size > global_max_gap_size:
            global_max_gap_size = max_gap_size
    
    for dst_ip, result in sorted(results_dict.iteritems(), key=lambda (k,v): k):
        print("Dest IP: %s" % dst_ip)
        if not result['first_success_seen']:
            print("    ERROR: No pings succeeded.")
        else:
            print("    max gap size: %s" % result['max_gap_size'])
            print("    max gap start line: %s" % result['max_gap_start_line'])

    print("Global max gap size: %s" % global_max_gap_size)

if __name__=='__main__':
    signal.signal(signal.SIGINT, signal_handler)
    print('Press Ctrl+C to stop.')
    #signal.pause()
    start_pings()
