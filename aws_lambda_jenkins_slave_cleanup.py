###
# Author: Artur Sitarski
#
# Script used as a source of AWS Lambda
# It's used to deregister jenkins slave from master when
# its instance was terminated. Instances are in ASG.
# Lambda is triggered by CloudWatch rule based on instance termination.
# Every Jenkins slave has its instance ID injected into its configuration
# as separate label.
###

import jenkins
import untangle
import socket
import os

JENKINS_SERVER_PORT=8080

class Jenkins:
    jenkins_server = ''

    def __init__(self, jenkins_server_host, jenkins_server_port):
        self.jenkins_server_host = jenkins_server_host
        self.jenkins_server_port = jenkins_server_port

    def authorize(self, username, token):
        jenkins_server_url = 'http://' + self.jenkins_server_host + ':' + str(self.jenkins_server_port)

        try:
            self.jenkins_server = jenkins.Jenkins(jenkins_server_url, username=username, password=token)
        except JenkinsException as err:
            print('Something went wrong with authorization: {}'.format(err))
            exit(1)

    def delete_node(self, instance_id):
        nodes = self.__get_nodes_names()
        node_to_delete = self.__find_node_to_delete(nodes, instance_id)

        if node_to_delete is None:
            print('Could not find jenkins slave with instance id: {}'.format(instance_id))
            exit(1)
        else:
            self.jenkins_server.delete_node(node_to_delete)

    def __get_nodes_names(self):
        nodes = self.jenkins_server.get_nodes()

        return nodes

    def __find_node_to_delete(self, nodes, instance_id):
        for node in nodes:
            if node['name'] == 'master':
                continue

            node_config_raw = self.jenkins_server.get_node_config(node['name'])
            node_config = untangle.parse(node_config_raw)
            node_labels = node_config.slave.label.cdata.encode('UTF-8').split(' ')

            for label in node_labels:
                if label == instance_id:
                    return node_config.slave.name.cdata.encode('UTF-8')


def handler(event, context):
    jenkins_server_fqdn = os.environ.get('jenkins_name')
    jenkins_api_user = os.environ.get('jenkins_api_user')
    jenkins_api_pass = os.environ.get('jenkins_api_pass')

    if 'EC2InstanceId' in event['detail']:
        instance_id = event['detail']['EC2InstanceId']
    else:
        raise Exception('Cannot find instance ID in event payload: {}'.format(event))

    jenkins_server_ip = socket.gethostbyname(jenkins_server_fqdn)
    jenkins_server = Jenkins(jenkins_server_ip, JENKINS_SERVER_PORT)
    jenkins_server.authorize(jenkins_api_user, jenkins_api_pass)
    jenkins_server.delete_node(instance_id)
