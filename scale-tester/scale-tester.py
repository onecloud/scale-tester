"""
This is the main driver for the scale-tester.

1. read test configuration file
2. create program
3. For each command in the template file, instantiate the cmd object and append
to the program
"""

import argparse
import json
import logging
import pudb
import pprint
import cmds.program as scale_tester_program

DESCRIPTION="Scale Tester"
EPILOG = "Copyright 2014 OneCloud, Inc.  All rights reserved."

LOG = logging.getLogger("scale_tester")

formatter = \
    logging.Formatter('%(asctime)s - %(module)s - %(funcName)s - (%(lineno)d) %(levelname)s \n %(message)s')

fh = logging.FileHandler("scale_tester.log")
fh.setFormatter(formatter)
LOG.addHandler(fh)
LOG.setLevel(logging.DEBUG)

def parse_args():
    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG)

    
    parser.add_argument("test_input_file",
                        help='file path for the test template file')
    
    results = parser.parse_args()

    return results    


def process_test_input_file(program_args):
    """
    This function returns a dictionary form of the json
    test configuration file.
    """
    test_input_file = program_args.test_input_file

    input_file_stream = open(test_input_file)

    test_configuration = json.load(input_file_stream)
    
    LOG.debug(pprint.pformat(test_configuration))
    return test_configuration

def main():
    
    parsed_args = parse_args()

    print(parsed_args.test_input_file)

    test_configuration = process_test_input_file(parsed_args)

    program = scale_tester_program.parse_program(test_configuration)


if __name__ == "__main__":
    main()
