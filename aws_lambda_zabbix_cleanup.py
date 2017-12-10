###
# Author: Artur Sitarski
#
# Script used as a source of AWS Lambda.
# It's used to disable zabbix nodes associated with terminated AWS instances.
# When AWS instance is being terminated CloudWatch rule executes this lambda.
# IMPORTANT: Every zabbix host should have its instance-id as asset_tag in its inventory.
# You can change action from just disabling host to removing -
# but remember that will lost history data for that host in zabbix.
# It works with termination from ASG and regular one.
###

from __future__ import print_function

import requests
import boto3
import json
import sys
import os


class Zabbix:
    zabbix_api_url = 'localhost'

    def __init__(self, api_url):
        self.zabbix_api_url = api_url

    def authenticate(self, login, password):
        payload = {
            'jsonrpc': '2.0',
            'method':'user.login',
            'params': {'user': login, 'password': password},
            'id':0 }

        headers = {'Content-Type': 'application/json-rpc'}
        response = self.__make_request(payload, headers)
        auth_token = response['result']

        return auth_token

    def get_host_id(self, auth_token, instance_id):
        payload = {
            'jsonrpc': '2.0',
            'method': 'host.get',
            'params': {'output': 'hostid', 'searchInventory': {'asset_tag': instance_id}},
            'auth': auth_token,
            'id':0 }

        headers = {'Content-Type': 'application/json-rpc'}
        response = self.__make_request(payload, headers)

        if response['result']:
            host_id = response['result'].pop()['hostid']
        else:
            print('No host in zabbix registered with {} asset tag. Nothing to do.'.format(instance_id))
            exit(0)

        return host_id

    def disable_host(self, auth_token, host_id):
        payload = {
            "jsonrpc": "2.0",
            "method": "host.update",
            "params": {'hostid': host_id, 'status': 1},
            "auth": auth_token,
            "id":0 }

        headers = { 'Content-Type': 'application/json-rpc' }
        response = self.__make_request(payload, headers)
        disabled_hosts = response['result']['hostids']

        if host_id not in disabled_hosts:
            raise Exception('Disabled hosts do not match requested ones. Requested ids: {}, Disabled ids: {}'. format(disabled_hosts, host_id))

    def __make_request(self, payload, headers=None):
        try:
            response = requests.post(self.zabbix_api_url, headers=headers, json=payload).json()
        except requests.exceptions.RequestException as err:
            print('There was a problem with network connection: {}'.format(err))
            sys.exit(1)
        except (ValueError, KeyError) as err:
            print('No valid JSON response can be find: {}'.format(err))
            sys.exit(1)
        except Exception as err:
            print('Something went wrong with request: {}'.format(err))
            sys.exit(1)

        if 'error' in response:
            raise Exception('API request failed! Payload: {}. API error message: {}. API error data: {}'.format(payload, response['error']['message'], response['error']['data']))

        return response


def handler(event, context):
    zbx_api_user = os.environ.get('zbx_api_user')
    zbx_api_pass = os.environ.get('zbx_api_pass')
    zbx_server_fqdn = os.environ.get('zbx_server_fqdn')

    if 'EC2InstanceId' in event['detail']:
        instance_id = event['detail']['EC2InstanceId']
    elif 'instance-id' in event['detail']:
        instance_id = event['detail']['instance-id']
    else:
        raise Exception('Cannot find instance ID in event payload: {}'.format(event))

    zabbix = Zabbix('https://' + zbx_server_fqdn + '/api_jsonrpc.php')
    zbx_auth_token = zabbix.authenticate(zbx_api_user, zbx_api_pass)
    zbx_host_id = zabbix.get_host_id(zbx_auth_token, instance_id)
    zabbix.disable_host(zbx_auth_token, zbx_host_id)
