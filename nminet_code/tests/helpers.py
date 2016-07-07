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


def mk_eth_info(data):
    class IPInfo(object):
        def __init__(self, d):
            self.addr = d["addr"]
            self.plen = d["plen"]
            self.method = IPOrigin[d["method"]]
            self.valid = True

    class EthInfo(object):
        def __init__(self, d):
            self.nmi_id = d["nmi_id"]
            self.teammembers = d["teammembers"]
            self.status = PortStatus[d["status"]]
            self.redundancy_type = RedundancyType[d["redundancy_type"]]
            self.redundancy_mode = RedundancyMode[d["redundancy_mode"]]
            self.redundancy_status = RedundancyStatus[d["redundancy_status"]]
            self.interface_name_l2 = d["interface_name_l2"]
            self.interface_name_l3 = d["interface_name_l3"]
            self.enabled = d["enabled"]
            self.enable_dhcp = d["enable_dhcp"]
            self.mac_address = d["mac_address"]
            self.pci_id = d["pci_id"]
            self.link_speed = d["link_speed"]
            self.link_mode = AutoNegotiate[d["link_mode"]]
            self.primary_port = d["primary_port"]
            self.manual_primary_port = d["manual_primary_port"]
            self.description = d["description"]
            self.platform_object_id = d["platform_object_id"]

            self.all_ips = self._get_iplist(d["all_ips"])
            self.all_gateways = self._get_iplist(d["all_gateways"])
            self.ips = self._get_iplist(d["ips"])

        def _get_iplist(self, d):
            res = []
            for item in d:
                res.append(IPInfo(item))
            return res

        def get_dict(self):
            return self._get_rpc_dict(self)

        @classmethod
        def _get_rpc_dict(kls, obj):

            if type(obj) in [str, unicode, int, long, bool]:
                return obj
            elif isinstance(obj, Enum):
                return obj.name
            elif isinstance(obj, list):
                lst = []
                for v in obj:
                    lst.append(kls._get_rpc_dict(v))
                return lst
            else:
                res = {}
                for n in dir(obj):
                    if n.startswith('_'):
                        continue
                    v = getattr(obj, n)
                    if callable(v):
                        continue

                    res[n] = kls._get_rpc_dict(v)

                return res


    return EthInfo(data)


