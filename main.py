#!/usr/bin/env python3

import datetime
import json
import logging
import os
from time import sleep

import consul
import requests
import six

from wework_robot import WeworkRobot, Message


class ConsulAlertManager(object):

    def __init__(self, consul_host='127.0.0.1', consul_port=8500, key='', log_path='', log_file=''):
        self.interval_time = 5
        self.consul_scheme = 'http'
        self.consul_host = consul_host
        self.consul_port = consul_port

        self.alert_manager_key_prefix = 'alert-manager'
        if key:
            self.robot = WeworkRobot(key)
        else:
            self.robot = None

        self.log_path = log_path
        self.log_file = log_file

        # Alerting for the next states
        self.processing_states = ['warning', 'critical']

        self.datacenters = []
        self.consul = None
        self.logger = logging.getLogger()

        self.init_logger()

    def init_logger(self):

        self.logger.setLevel(logging.INFO)
        log_formatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_formatter)
        self.logger.addHandler(console_handler)

        if self.log_path and self.log_file:
            file_handler = logging.FileHandler("{0}/{1}".format(self.log_path, self.log_file))
            file_handler.setFormatter(log_formatter)
            self.logger.addHandler(file_handler)

    @staticmethod
    def ensure_unicode(s):
        if isinstance(s, six.binary_type):
            return s.decode('utf-8')
        else:
            return s

    @staticmethod
    def ensure_byte(s):
        if isinstance(s, six.text_type):
            return s.encode('utf-8')
        else:
            return s

    def get_kv_value(self, k):
        assert k != ''
        _, v = self.consul.kv.get(k)
        if v is not None:
            v = self.ensure_unicode(v['Value'])
        return v

    def delete_key(self, k):
        assert k != ''
        if self.consul.kv.delete(k, recurse=True):
            self.logger.info('Deleted key: ' + k)
            return True
        return False

    def send_notify(self, header, dc='', node='', service='', check_id='', state='', output=''):
        try:

            if header == 'Resolved':
                header = '<font color="info">{}</font>已恢复。'.format(service if service else node)
            elif header == 'Problem':
                header = '<font color="warning">{}</font>出现异常，请相关同事注意。'.format(service if service else node)
            else:
                header = '<font color="warning">{}</font>出现崩溃，请相关同事注意。'.format(service if service else node)

            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if state == 'passing':
                color = 'info'
            else:
                color = 'warning'

            content = ('{header}\n'
                       '>Time: <font color="comment">{time}</font>\n'
                       '>DC: {dc}\n'
                       '>Node: {node}\n'
                       '>Service: {service}\n'
                       '>State: <font color="{color}">{state}</font>\n'
                       '>CheckID: {check_id}\n'
                       '>Output:\n\n{output}').format(
                header=header, time=now,
                dc='<font color="comment">{dc}</font>'.format(dc=dc) if dc else '',
                node='<font color="comment">{node}</font>'.format(node=node) if node else '',
                service=service,
                color=color,
                state=state,
                check_id='<font color="comment">{check_id}</font>'.format(check_id=check_id) if check_id else '',
                output=output)

            if self.robot:
                message = Message()
                message.set_markdown(content)
                result = self.robot.send(message)
                if result['errcode'] == 1:
                    self.logger.info('send notify success')
                else:
                    self.logger.error('send notify fail, message = {}'.format(result['errmessage']))
            else:
                self.logger.info(content)
        except Exception as e:
            self.logger.exception(e)
            self.logger.error("Notify not sent")

    def get_output_by_check_id(self, dc, node, check_id):
        _, services = self.consul.health.node(node, dc=dc)
        for n in services:
            if n['CheckID'] == check_id:
                return n['Output']

    def is_check_resolved(self, dc, node, check_id, target_state):
        _, services = self.consul.health.node(node, dc=dc)
        for n in services:
            if (n['CheckID'] == check_id) and (n['Status'] == target_state):
                return True

        return False

    def is_check_present(self, dc, node, check_id):
        _, services = self.consul.health.node(node, dc=dc)
        for n in services:
            if n['CheckID'] == check_id:
                return True

        return False

    def handle_saved_states(self, saved_states):
        for state in saved_states:
            _, keys = self.consul.kv.get(self.alert_manager_key_prefix + '/' + state, keys=True)
            if keys is not None:
                for k in keys:
                    data = k.split('/')
                    dc, node, check_id = data[2], data[3], data[4]

                    target_state = 'passing'

                    if not self.is_check_present(dc, node, check_id):
                        self.logger.info('Previously saved checkid ' + check_id + ' is absent')
                        self.delete_key(k)
                        continue

                    if self.is_check_resolved(dc, node, check_id, target_state):
                        service, output = '', ''
                        if len(data) > 5:
                            service = data[5]
                            output = self.get_output_by_check_id(dc, node, check_id)

                        self.logger.info('Found ' + target_state + ' state: ' + check_id)

                        if self.delete_key(k):
                            self.send_notify('Resolved', dc, node, service, check_id, target_state, output)

    def handle_novel_states(self, states):
        """
        处理异常状态
        :param states:
        :type states:
        :return:
        :rtype:
        """
        for dc in self.datacenters:
            for state in states:
                _, services = self.consul.health.state(state, dc=dc)
                for s in services:
                    node, service, output, check_id = s['Node'], s['ServiceName'], s['Output'], s['CheckID']
                    k = "{0}/{1}/{2}/{3}/{4}/{5}".format(self.alert_manager_key_prefix, state, dc, node, check_id,
                                                         service).rstrip('/')

                    _, v = self.consul.kv.get(k)
                    if v is None:
                        if self.consul.kv.put(k, self.ensure_byte(output)):
                            self.logger.warning('Found ' + state + ' state. Saved state key: ' + k)
                            self.send_notify('Problem', dc, node, service, check_id, state, output)

    def handle_exited_services(self):
        for dc in self.datacenters:
            _, services = self.consul.catalog.services(dc=dc)

            k = "{0}/{1}".format(self.alert_manager_key_prefix, dc).rstrip('/')

            _, v = self.consul.kv.get(k)
            if v is not None:
                old_services = json.loads(v['Value'])
                exited_services = set(old_services).difference(set(services))
                if exited_services:
                    # 取消退出告警
                    # self.send_notify('Problem', dc, service=str(exited_services), state='exited')
                    self.logger.info('Exited services {}'.format(exited_services))

            new_value = self.ensure_byte(json.dumps(services))
            if not v or v['Value'] != new_value:
                if self.consul.kv.put(k, new_value):
                    self.logger.info('Found services {}. Saved state key: {}'.format(services, k))

    def wait_for_connection(self):
        try:
            consul.Consul(host=self.consul_host, port=self.consul_port, scheme=self.consul_scheme).catalog.datacenters()
            self.logger.info('Connection restored. Consul Alert Manager is ready')
        except requests.exceptions.ConnectionError:
            sleep(self.interval_time)
            self.wait_for_connection()

    def run(self):
        self.logger.info('Consul Alert Manager is started')

        while True:
            try:
                self.consul = consul.Consul(self.consul_host, self.consul_port, self.consul_scheme)

                # Get datacenters list
                self.datacenters = self.consul.catalog.datacenters()
                self.handle_exited_services()
                self.handle_saved_states(self.processing_states)
                self.handle_novel_states(self.processing_states)
            except requests.exceptions.ConnectionError:
                self.logger.error(
                    'Connection error with Consul on ' + self.consul_scheme + '://' + self.consul_host + ':' + str(
                        self.consul_port) + '. Reconnecting...')
                self.wait_for_connection()
            except Exception as e:
                self.logger.exception(e)
                self.send_notify('Crashed', service='Consul Alert Manager', state='crashed', output=str(e))
                raise

            sleep(self.interval_time)


if __name__ == '__main__':
    consul_alert_manager = ConsulAlertManager(
        consul_host=os.getenv('CONSUL_HOST', '127.0.0.1'),
        consul_port=int(os.getenv('CONSUL_PORT', '8500')),
        key=os.getenv('KEY', ''),
        log_path=os.getenv('LOG_PATH', ''),
        log_file=os.getenv('LOG_FILE', ''),
    )
    consul_alert_manager.run()
