###
# Author: Artur Sitarski
#
# Script used as a source of AWS Lambda
# It's used to disable/remove jenkins slave node from jenkins master
# before node termination triggered by ASG.
# It checks if there are ongoing builds on terminated node.
# Script is triggered by ASG lifecycle hook event sent to CloudWatch
###

import jenkins
import untangle
import socket
import os
import boto3

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

    def disable_node(self, node_name):
        self.jenkins_server.disable_node(node_name)

    def is_node_ok_to_terminate(self, node_name):
        running_builds = self.jenkins_server.get_running_builds()

        for build in running_builds:
            if build['node'] == node_name:
                return False

        return True

    def get_node_name_by_id(self, instance_id):
        nodes = self.jenkins_server.get_nodes()

        for node in nodes:
            if node['name'] == 'master':
                continue

            node_config_raw = self.jenkins_server.get_node_config(node['name'])
            node_config = untangle.parse(node_config_raw)
            node_labels = node_config.slave.label.cdata.split(' ')

            for label in node_labels:
                if label == instance_id:
                    return node_config.slave.name.cdata


class AWS:
    aws_client = ''

    def __init__(self, aws_service, aws_region='us-west-2'):
        try:
            self.aws_client = boto3.client(aws_service, region_name=aws_region)
        except botocore.exceptions.ClientError as err:
            print('Something went wrong with connection to AWS: {}'.format(err))
            exit(1)

    def continue_node_termination(self, asg_name, lc_hook_name, lc_action_token):
        try:
            self.aws_client.complete_lifecycle_action(
                AutoScalingGroupName = asg_name,
                LifecycleActionResult = 'CONTINUE',
                LifecycleActionToken = lc_action_token,
                LifecycleHookName = lc_hook_name)
        except botocore.exceptions.ClientError as err:
            print('Something went wrong with complete_lifecycle action (ASG):'.format(err))
            exit(1)


def handler(event, context):
    jenkins_server_name = os.environ.get('jenkins_name')
    jenkins_api_user = os.environ.get('jenkins_api_user')
    jenkins_api_pass = os.environ.get('jenkins_api_pass')

    instance_id = event['detail']['EC2InstanceId']
    lifecycle_action_token = event['detail']['LifecycleActionToken']
    lifecycle_hook_name = event['detail']['LifecycleHookName']
    asg_name = event['detail']['AutoScalingGroupName']

    jenkins_server_ip = socket.gethostbyname(jenkins_server_name)
    jenkins_server = Jenkins(jenkins_server_ip, JENKINS_SERVER_PORT)
    jenkins_server.authorize(jenkins_api_user, jenkins_api_pass)
    node_name = jenkins_server.get_node_name_by_id(instance_id)

    # disabling node won't break ongoing builds but exclude node from queuing
    jenkins_server.disable_node(node_name)

    # try lucky shot, otherwise is will be terminated by ASG when
    # lifecycle hook TTL will be reached
    if jenkins_server.is_node_ok_to_terminate(node_name):
        aws = AWS('autoscaling')
        aws.continue_node_termination(asg_name, lifecycle_hook_name, lifecycle_action_token)
