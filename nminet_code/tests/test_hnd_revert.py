#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import sys
sys.path.append('../src')
import unittest

import os
import time
import threading
import argparse
import socket
import logging
import Queue
import select
import errno
import subprocess
import json
queue = Queue # python 3
from enum import Enum

from defs import *
from message import MessageRevertInterface
from hnd_revert import RevertFSM, DelayedRevertHnd

import helpers

class Tests(unittest.TestCase):

    def test_revert1(self):
        SEQ = [
            # both disabled, redundancy mode automatic
            {
                7: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': False, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': False, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, both disconnected
            {
                7: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, 7 disconnected, 8 connected, 8 active
            {
                7: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, 7 connected, 8 connected, 8 active
            {
                7: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'INACTIVE', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

        ]

        q = queue.Queue()
        self.do_test(q, SEQ)

        res = q.get_nowait()
        self.assertIsInstance(res, MessageRevertInterface)

    def test_revert2(self):
        SEQ = [
            # both disabled, redundancy mode automatic
            {
                7: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': False, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': False, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, 7 connected, 8 connected, 8 active
            {
                7: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'INACTIVE', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

        ]

        q = queue.Queue()
        self.do_test(q, SEQ)

        res = q.get_nowait()
        self.assertIsInstance(res, MessageRevertInterface)

    def test_norevert1(self):
        SEQ = [
            # both disabled, redundancy mode automatic
            {
                7: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': False, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': False, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, both disconnected
            {
                7: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, 8 disconnected, 7 connected, 7 active
            {
                7: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, 7 connected, 8 connected, 7 active
            {
                7: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'INACTIVE', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

        ]

        q = queue.Queue()
        self.do_test(q, SEQ)

        self.assertTrue(q.empty())

    def test_norevert2(self):
        SEQ = [
            # both disabled, redundancy mode automatic
            {
                7: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': False, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': False, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, 7 connected, 8 connected, 7 active
            {
                7: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'INACTIVE', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

        ]

        q = queue.Queue()
        self.do_test(q, SEQ)

        self.assertTrue(q.empty())

    def test_norevert3(self):
        SEQ1 = [
            # both disabled, redundancy mode automatic
            {
                7: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': False, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'DISABLED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': False, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, both disconnected
            {
                7: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },

            # enabled, 7 disconnected, 8 connected, 8 active
            {
                7: {'status': 'MEDIA_DISCONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'DISCONNECTED', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },
        ]

        SEQ2 = [
            # enabled, 7 connected, 8 connected, 8 active
            {
                7: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth6', 'primary_port': True, 'interface_name_l3': 'net7', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-be-c4-8d', 'enabled': True, 'pci_id': '00:11.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.18.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'INACTIVE', 'manual_primary_port': True, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.3', 'nmi_id': 7, 'teammembers': [8], 'description': 'GbE 07'},
                8: {'status': 'CONNECTED', 'all_ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'redundancy_type': 'ACTIVE_ACTIVE', 'all_gateways': [], 'enable_dhcp': False, 'interface_name_l2': 'eth7', 'primary_port': False, 'interface_name_l3': 'net8', 'redundancy_mode': 'AUTOMATIC', 'mac_address': '08-00-27-97-71-66', 'enabled': True, 'pci_id': '00:13.0', 'ips': [{'plen': 24, 'valid': True, 'addr': '192.168.19.51', 'method': 'Manual'}], 'link_speed': '(Offline)', 'redundancy_status': 'ACTIVE', 'manual_primary_port': False, 'link_mode': 'AUTO_NEGOTIATE', 'platform_object_id': 'Ch.1.C.2.P.4', 'nmi_id': 8, 'teammembers': [7], 'description': 'GbE 08'},
            },
        ]

        q = queue.Queue()
        hnd = self.do_test(q, SEQ1)
        time.sleep(12)
        self.do_test(q, SEQ2, hnd)

        self.assertTrue(q.empty())


    def do_test(self, q, data, hnd=None):
        if hnd is None:
            hnd = DelayedRevertHnd(q)

        for evt in data:
            info = {}
            for k, v in evt.iteritems():
                info[k] = helpers.mk_eth_info(v)

            hnd.interfaces_updated(info)

        return hnd

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
    unittest.main()
