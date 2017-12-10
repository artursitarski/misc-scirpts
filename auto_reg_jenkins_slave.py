#!/usr/bin/env python

###
# Author: Artur Sitarski
#
# This script is to add/register jenkins slave automatically to jenkins master;
# In my case it's executed by my SDDC tool.
# Slaves are created by AWS ASG; can be destroyed/created dynamically depends on you ASG actions.
# Slave will register itself and add its instance-id as separate label - 
# thanks to this, you will be able to find slave and destroy it when its server will be terminated.
# (see aws_lambda_jenkins_slave_cleanup.py)
###

import jenkins
import socket
import time
import datetime
import argparse
import os
import requests

JENKINS_SERVER_PORT=8080
JENKINS_SLAVE_CREDS_ID='jenkins'
JENKINS_SLAVE_PORT=22
JENKINS_SLAVE_FS='/var/lib/jenkins'
JENKINS_SLAVE_MAIN_LABEL='linux_slave'
JENKINS_SLAVE_CTRL_FILE='registration_date.txt'

class Jenkins:
    jenkins_server = ''

    def __init__(self, jenkins_server_host, jenkins_server_port):
        self.jenkins_server_host = jenkins_server_host
        self.jenkins_server_port = jenkins_server_port

    def authorize(self, username, token):
        jenkins_server_url = 'http://' + self.jenkins_server_host + ':' + str(self.jenkins_server_port)

        try:
            self.jenkins_server = jenkins.Jenkins(jenkins_server_url, username=username, password=token)
        except jenkins.JenkinsException as err:
            print('Something went wrong with authorization: {0}'.format(err))
            exit(1)

    def create_node(self, node_name, node_ip, instance_id, num_executors):
        if self.jenkins_server.node_exists(node_name):
            self.__write_status_file('Node was added manually.')
            return None

        node_params = {
            'port': JENKINS_SLAVE_PORT,
            'credentialsId': JENKINS_SLAVE_CREDS_ID,
            'host': node_ip
        }

        try:
            self.jenkins_server.create_node(node_name,
                numExecutors=num_executors,
                nodeDescription='Node dynamically created by ASG',
                remoteFS=JENKINS_SLAVE_FS,
                labels=JENKINS_SLAVE_MAIN_LABEL + ' ' + instance_id,
                launcher=jenkins.LAUNCHER_SSH,
                launcher_params=node_params)

            self.__write_status_file(str(datetime.datetime.now()))
        except jenkins.JenkinsException as err:
            print('Something went wrong with jenkins node creation: {}'.format(err))
            exit(1)

    def start_node(self, node_name):
        # little hack - jenkins needs few secs to initiate new node
        time.sleep(30)
        node_exists = self.jenkins_server.node_exists(node_name)

        if node_exists:
            self.jenkins_server.enable_node(node_name)
        else:
            print('Slave {} does not exists!'.format(node_name))
            exit(1)

    def delete_node(self, node_name):
        node_exists = self.jenkins_server.node_exists(node_name)

        if node_exists:
            self.jenkins_server.delete_node(node_name)

    def __write_status_file(self, status):
        """Write marker file after registration - skip registration on subsequent SDDC tool runs"""
        status_file = os.path.join(JENKINS_SLAVE_FS, JENKINS_SLAVE_CTRL_FILE)

        if not os.path.exists(status_file):
            with open(status_file, 'w') as f:
                f.write(status)


def __get_master_slave_ips(jenkins_server_fqdn):
    jenkins_server_ip = socket.gethostbyname(jenkins_server_fqdn)

    soc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    soc.connect((jenkins_server_ip, 0))
    my_ip = soc.getsockname()[0]

    return (jenkins_server_ip, my_ip)

def __get_my_instance_id():
  response = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
  instance_id = response.text.encode('UTF-8')

  return instance_id


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Dynamically create jenkins node.')

    parser.add_argument('-n','--jenkins-name', dest='jenkins_server_fqdn', help='Jenkins server name', required=True)
    parser.add_argument('-e','--executors', dest='num_executors', help='Number of executors on jenkins slave', required=False, default=1)
    parser.add_argument('-u','--jenkins-api-user', dest='jenkins_api_user', help='Jenkins API access user name', required=True)
    parser.add_argument('-p','--jenkins-api-pass', dest='jenkins_api_pass', help='Jenkins API access user token', required=True)
    parser.add_argument('-d','--delete-slave', dest='delete_slave', help='Jenkins API access user token', required=False, action='store_true', default=False)
    args = vars(parser.parse_args())

    jenkins_server_fqdn = args['jenkins_server_fqdn']
    jenkins_api_user = args['jenkins_api_user']
    jenkins_api_pass = args['jenkins_api_pass']
    slave_num_executors = args['num_executors']
    delete_slave = args['delete_slave']

    # AWS instance ID will be passed on creation as another label;
    # it will allow you to find particular jenkins slave to delete
    # when termination event occur
    my_instance_id = __get_my_instance_id()
    my_fqdn = socket.gethostname().split('.')

    # extracting server name from FQDN;
    # array range can be different in your case
    my_name = '.'.join(my_fqdn[:-4])

    jenkins_server_ip, my_ip = __get_master_slave_ips(jenkins_server_fqdn)
    # from fome reason, at least for me, jenkins lib don't want to resolve
    # passed jenkins domain, that's why I'm passing raw IP
    jenkins_server = Jenkins(jenkins_server_ip, JENKINS_SERVER_PORT)
    jenkins_server.authorize(jenkins_api_user, jenkins_api_pass)

    if delete_slave:
        jenkins_server.delete_node(my_name)
    else:
        jenkins_server.create_node(my_name, my_ip, my_instance_id, slave_num_executors)
        jenkins_server.start_node(my_name)
