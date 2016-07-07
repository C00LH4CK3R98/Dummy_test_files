#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import sys
sys.path.append('../src')
import unittest

import os
import time
import threading
import socket
import logging
import Queue
import select
import errno
import subprocess
import json
queue = Queue # python 3
from enum import Enum
from collections import deque, namedtuple

from config import *
from defs import *
from alarm import EventProcessor, AlarmProcThread
from alarm_handlers import *
from alarm_types import Harmonic_Internal_IPConfigurationChanged

import helpers

RECORDED_EVENTS = []


EventItem = namedtuple('EventItem', ['action', 'event', 'match'])
class EventItem(object):
    def __init__(self, action, event):
        self.action = action
        self.event = event
        self.match = False


EventCheck = namedtuple('EventCheck', ['action', 'name', 'obj', 'params'])
class EventCheckNot(EventCheck):
    pass


class MyNMIEventSender(object):

    def send(self, action, event):
        global RECORDED_EVENTS
        RECORDED_EVENTS.append(EventItem(action, event))


class MyEventProcessor(EventProcessor):
    EVENT_SENDER = MyNMIEventSender

    def process_end(self):
        super(MyEventProcessor, self).process_end()
        RECORDED_EVENTS.append(EventItem("COMMIT", None))


class Tests(unittest.TestCase):

    def setUp(self):
        global RECORDED_EVENTS
        RECORDED_EVENTS = []

    def test_same_alarm_desc_change(self):
        DATA = [
            # aa_auto
            {
                7: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # as_auto
            {
                7: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_STANDBY', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_STANDBY', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # aa_auto
            {
                7: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },
        ]

        REFERENCE = [
            EventCheck("ALARM_ON", "Harmonic_NetworkIFDownIndication", 7, {'NetworkIFNumber': 7, 'isTeamingPort': True}),
            EventCheck("ALARM_ON", "Harmonic_NetworkIFDownIndication", 8, {'NetworkIFNumber': 8, 'isTeamingPort': True}),
            EventCheck("ALARM_ON", "Harmonic_VideoOverIPPortDown_Interface", 7, {'NetworkIFNumber': 7}),
            EventCheck("ALARM_ON", "Harmonic_VideoOverIPPortDown_Interface", 8, {'NetworkIFNumber': 8}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net7', 'ethernetPortNum': 7, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net8', 'ethernetPortNum': 8, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingDown_PortRedundancy", 2126, {'NICTeamingName': 'net7', 'FirstPortNum': 7, 'SecondPortNum': 8, 'EnforcePortPriority': False, 'AssetingPortNum': 7}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingDown_PortRedundancy", 2127, {'NICTeamingName': 'net7', 'FirstPortNum': 7, 'SecondPortNum': 8, 'EnforcePortPriority': False, 'AssetingPortNum': 8}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net7', 'ethernetPortNum': 7, 'CurrentState': 'NOT_ENABLED', 'PreviousState': 'INACTIVE'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net7', 'ethernetPortNum': 7, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net7', 'ethernetPortNum': 8, 'CurrentState': 'NOT_ENABLED', 'PreviousState': 'INACTIVE'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net7', 'ethernetPortNum': 8, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingDown", 2126, {'NICTeamingName': 'net7', 'FirstPortNum': 7, 'SecondPortNum': 8, 'EnforcePortPriority': False, 'AssetingPortNum': 7}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingDown", 2127, {'NICTeamingName': 'net7', 'FirstPortNum': 7, 'SecondPortNum': 8, 'EnforcePortPriority': False, 'AssetingPortNum': 8}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net7', 'ethernetPortNum': 7, 'CurrentState': 'NOT_ENABLED', 'PreviousState': 'INACTIVE'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net7', 'ethernetPortNum': 7, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net8', 'ethernetPortNum': 8, 'CurrentState': 'NOT_ENABLED', 'PreviousState': 'INACTIVE'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net8', 'ethernetPortNum': 8, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingDown_PortRedundancy", 2126, {'NICTeamingName': 'net7', 'FirstPortNum': 7, 'SecondPortNum': 8, 'EnforcePortPriority': False, 'AssetingPortNum': 7}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingDown_PortRedundancy", 2127, {'NICTeamingName': 'net7', 'FirstPortNum': 7, 'SecondPortNum': 8, 'EnforcePortPriority': False, 'AssetingPortNum': 8}),
            EventCheck("COMMIT", None, None, None),
        ]

        self.run_test_and_compare(DATA, REFERENCE)

    def test_aa_manual_events_for_ACP_4956(self):
        DATA = [
            # manual mode, first active
            {
                5: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth4', 'primary_port': True, 'interface_name_l3': 'net5', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'ACTIVE', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 5, 'teammembers': [6], 'description': 'GbE 05'},
                6: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth5', 'primary_port': False, 'interface_name_l3': 'net6', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'INACTIVE', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 6, 'teammembers': [5], 'description': 'GbE 06'},
            },

            # select second
            {
                5: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth4', 'primary_port': True, 'interface_name_l3': 'net5', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'INACTIVE', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 5, 'teammembers': [6], 'description': 'GbE 05'},
                6: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth5', 'primary_port': False, 'interface_name_l3': 'net6', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'ACTIVE', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 6, 'teammembers': [5], 'description': 'GbE 06'},
            },

            # disconnect first
            {
                5: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth4', 'primary_port': True, 'interface_name_l3': 'net5', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 5, 'teammembers': [6], 'description': 'GbE 05'},
                6: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth5', 'primary_port': False, 'interface_name_l3': 'net6', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'ACTIVE', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 6, 'teammembers': [5], 'description': 'GbE 06'},
            },

            # activate first (disconnected)
            {
                5: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth4', 'primary_port': True, 'interface_name_l3': 'net5', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 5, 'teammembers': [6], 'description': 'GbE 05'},
                6: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth5', 'primary_port': False, 'interface_name_l3': 'net6', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'INACTIVE', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 6, 'teammembers': [5], 'description': 'GbE 06'},
            },

            # activate first (disconnected)
            {
                5: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth4', 'primary_port': True, 'interface_name_l3': 'net5', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 5, 'teammembers': [6], 'description': 'GbE 05'},
                6: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth5', 'primary_port': False, 'interface_name_l3': 'net6', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'INACTIVE', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 6, 'teammembers': [5], 'description': 'GbE 06'},
            },

            # connect first
            {
                5: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth4', 'primary_port': True, 'interface_name_l3': 'net5', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 5, 'teammembers': [6], 'description': 'GbE 05'},
                6: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth5', 'primary_port': False, 'interface_name_l3': 'net6', 'redundancy_mode': 'MANUAL_NOFAILOVER', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'INACTIVE', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 6, 'teammembers': [5], 'description': 'GbE 06'},
            },
        ]

        REFERENCE = [
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net5', 'ethernetPortNum': 5, 'CurrentState': 'ACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net6', 'ethernetPortNum': 6, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net5', 'ethernetPortNum': 5, 'CurrentState': 'NOT_ENABLED', 'PreviousState': 'ACTIVE'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net5', 'ethernetPortNum': 5, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net6', 'ethernetPortNum': 6, 'CurrentState': 'NOT_ENABLED', 'PreviousState': 'INACTIVE'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net6', 'ethernetPortNum': 6, 'CurrentState': 'ACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingSlaveChannelActivated", 6, {'NICTeamingName': 'net6', 'ethernetPortNum': 6}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_ON", "Harmonic_NetworkIFDownIndication", 5, {'NetworkIFNumber': 5, 'isTeamingPort': True}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_ON", "Harmonic_VideoOverIPPortDown_Interface", 5, {'NetworkIFNumber': 5}),
            EventCheck("ALARM_ON", "Harmonic_VideoOverIPPortDown_Inactive", 6, {'NetworkIFNumber': 6}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net5', 'ethernetPortNum': 5, 'CurrentState': 'NOT_ENABLED', 'PreviousState': 'INACTIVE'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net5', 'ethernetPortNum': 5, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net6', 'ethernetPortNum': 6, 'CurrentState': 'NOT_ENABLED', 'PreviousState': 'ACTIVE'}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net6', 'ethernetPortNum': 6, 'CurrentState': 'INACTIVE', 'PreviousState': 'NOT_ENABLED'}),
            EventCheck("ALARM_OFF", "Harmonic_NICTeamingSlaveChannelActivated", 6, {'NICTeamingName': 'net6', 'ethernetPortNum': 6}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingDown_PortRedundancy", 2124, {'NICTeamingName': 'net5', 'FirstPortNum': 5, 'SecondPortNum': 6, 'EnforcePortPriority': True, 'AssetingPortNum': 5}),
            EventCheck("ALARM_ON", "Harmonic_NICTeamingDown_PortRedundancy", 2125, {'NICTeamingName': 'net5', 'FirstPortNum': 5, 'SecondPortNum': 6, 'EnforcePortPriority': True, 'AssetingPortNum': 6}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_OFF", "Harmonic_NetworkIFDownIndication", 5, {'NetworkIFNumber': 5, 'isTeamingPort': True}),
            EventCheck("ALARM_OFF", "Harmonic_VideoOverIPPortDown", 5, {'NetworkIFNumber': 5}),
            EventCheck("ALARM_OFF", "Harmonic_VideoOverIPPortDown", 6, {'NetworkIFNumber': 6}),
            EventCheck("EVENT", "Harmonic_NICTeamingPortStateChanged", None, {'NICTeamingName': 'net5', 'ethernetPortNum': 5, 'CurrentState': 'ACTIVE', 'PreviousState': 'INACTIVE'}),
            EventCheck("ALARM_OFF", "Harmonic_NICTeamingDown_PortRedundancy", 2124, {'NICTeamingName': 'net5', 'FirstPortNum': 5, 'SecondPortNum': 6, 'EnforcePortPriority': True, 'AssetingPortNum': 5}),
            EventCheck("ALARM_OFF", "Harmonic_NICTeamingDown_PortRedundancy", 2125, {'NICTeamingName': 'net5', 'FirstPortNum': 5, 'SecondPortNum': 6, 'EnforcePortPriority': True, 'AssetingPortNum': 6}),
            EventCheck("COMMIT", None, None, None),
        ]

        self.run_test_and_compare(DATA, REFERENCE)


    def test_global_storage_alarm_for_ACP_5686(self):
        DATA = [
            # both connected, no teaming
            {
                3: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # 4 disconnected, no teaming
            {
                3: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # both connected, no teaming
            {
                3: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # 3 disconnected, no teaming
            {
                3: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # 4 disconnected, no teaming
            {
                3: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # both disconnected, no teaming
            {
                3: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },


            # both connected, no teaming
            {
                3: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # 4 disconnected, no teaming
            {
                3: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # both disconnected, no teaming
            {
                3: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # 3 disconnected, no teaming
            {
                3: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'NOT_ENABLED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # both disconnected, no teaming
            {
                3: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [], 'description': 'GbE 03'},
                4: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'NONE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [], 'description': 'GbE 04'},
            },
            # both disconnected, teaming
            {
                3: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_STANDBY', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [4], 'description': 'GbE 03'},
                4: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_STANDBY', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [3], 'description': 'GbE 04'},
            },
            # both connected, teaming
            {
                3: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e0', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_STANDBY', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth2', 'primary_port': True, 'interface_name_l3': 'net3', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e0', 'enabled': True, 'pci_id': '41:00.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.5.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'ACTIVE', 'manual_primary_port': True, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.1', 'nmi_id': 3, 'teammembers': [4], 'description': 'GbE 03'},
                4: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}, {'plen': 64, 'valid': True, 'addr': 'fe80::a236:9fff:fe11:36e1', 'method': 'LinkLocal'}], 'redundancy_type': 'ACTIVE_STANDBY', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth3', 'primary_port': False, 'interface_name_l3': 'net4', 'redundancy_mode': 'AUTOMATIC', 'mac_address': 'a0-36-9f-11-36-e1', 'enabled': True, 'pci_id': '41:00.1', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.6.197', 'method': 'Manual'}], 'link_speed': '1000Mb/s', 'redundancy_status': 'INACTIVE', 'manual_primary_port': False, 'link_mode': 'FORCE_ONEG_FULL', 'platform_object_id': 'Ch.1.C.2.P.2', 'nmi_id': 4, 'teammembers': [3], 'description': 'GbE 04'},
            },

        ]

        # correct
        REFERENCE = [
            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_OFF", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheckNot("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheckNot("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_OFF", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheckNot("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheckNot("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheckNot("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheckNot("ALARM_ON", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),

            EventCheck("ALARM_OFF", "Harmonic_StoragePortDown", None, {'PlatformObjectID': 'Ch.1'}),
            EventCheck("COMMIT", None, None, None),
        ]

        self.run_test_and_compare(DATA, REFERENCE)


    def run_test_and_compare(self, data, reference, dumponly=False):

        t = AlarmProcThread(MyEventProcessor)
        t.start()
        try:
            for cfg in data:
                status = {}
                for k, v in cfg.iteritems():
                    status[k] = helpers.mk_eth_info(v)
                t.process_alarm_data_async(status)
        finally:
            t.shutdown_when_done()
            t.join()

        if dumponly:
            self.dump_events()
        else:
            self.compare_events(reference, RECORDED_EVENTS)

    def dump_events(self):
        print("")
        indent = " "*12
        for item in RECORDED_EVENTS:
            a = item.action
            e = item.event
            #if a == "COMMIT":
            #    print("")
            #    continue
            #print("{:10s}: {}".format(a, e))

            if a == "COMMIT":
                print('{}EventCheck("{}", {}, {}, {}),'.format(indent, a, None, None, None))
                print('')
                continue
            #print('{}EventCheck("{}", "{}", {}, {}),'.format(indent, a, e.name, e.obj, e.params))
            print('{}EventCheck("{}", "{}", {}, {}),'.format(indent, a, e.__class__.__name__, e.obj, e.params))

    def split_events(self, evt):
        res = []

        cur = []
        for e in evt:
            if e.action == "COMMIT":
                res.append(cur)
                cur = []
                continue
            cur.append(e)

        if cur:
            res.append(cur)

        return res

    def compare_params(self, ref, params):
        for k, v in ref.iteritems():
            if k not in params:
                return False
            if params[k] != v:
                return False

        return True

    def event_is_in(self, evt, lst):

        match = []
        for item in lst:
            if (item.match == False and
                    evt.name == item.event.__class__.__name__ and
                    evt.obj == item.event.obj and
                    evt.action == item.action):
                match.append(item)

        for item in match:
            if self.compare_params(evt.params, item.event.params):
                item.match = True
                return True

        return False

    def compare_events(self, ref, result):

        ref = self.split_events(ref)
        result = self.split_events(result)

        if len(ref) != len(result):
            self.assertTrue(False, msg="Test cases count mismatch {} != {}".format(len(ref), len(result)))

        for i in xrange(len(ref)):
            i1 = ref[i]
            i2 = result[i]

            for j in xrange(len(i1)):
                if type(i1[j]) == EventCheckNot:
                    self.assertFalse(self.event_is_in(i1[j], i2), msg="Event {} found in case {}".format(i1[j], i))
                else:
                    self.assertTrue(self.event_is_in(i1[j], i2), msg="Event {} not found in case {}".format(i1[j], i))


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

    unittest.main()
