#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function

import os
import sys
import time
import threading
import argparse
import socket
import logging
import signal
import fnmatch
import json

import schema
from util import ip_prefix_len_to_mask
#from config import *

DIR = "/opt/omneon/config/network/"

class CfgBase(object):
    AUTONEG_MAP = {
        'autoneg': 'AUTO_NEGOTIATE',
        '10gfull': 'FORCE_TENG_FULL',
        '1gfull': 'FORCE_ONEG_FULL',
        '100mfull': 'FORCE_HUNDM_FULL',
    }
    AUTONEG_MAP_UNKNOWN = 'AUTO_NEGOTIATE'

    def get_autoneg(self, autoneg):
        if autoneg in self.AUTONEG_MAP:
            return self.AUTONEG_MAP[autoneg]
        return self.AUTONEG_MAP_UNKNOWN

    def __str__(self):
        return str(self.data)

class CfgBond(CfgBase):
    """
BONDPORT=bond1
SLAVE1=eth2
SLAVE2=eth3
MODE=any
AUTONEG1=autoneg
AUTONEG2=autoneg
ISDHCP=no
STATIC_IP_ADDR=2.1.1.2
STATIC_PREFIX=24
STATIC_GW=2.1.1.1
DISABLED=no
IPV6_METHOD=auto
IPV6_MANUAL_IP=
IPV6_MANUAL_GW=
    """

    def __init__(self, fn):

        self.data = {
            'disabled': 'yes',
            'bondport': 'bondX',
            'slave1': 'ethX',
            'slave2': 'ethY',
            'mode': 'any',
            'isdhcp': 'yes',
            'static_ip_addr': '0.0.0.0',
            'static_gw': '0.0.0.0',
            'static_prefix': '0',
            'ipv6_method': 'auto',
            'ipv6_manual_ip': '',
            'ipv6_manual_gw': '',
            'autoneg1': 'autoneg',
            'autoneg2': 'autoneg'
        }

        self.load(fn)


    def load(self, fn):
        with open(fn, "r") as f:
            lines = f.readlines()
            for l in lines:
                l = l.strip()
                if l.startswith("#") or l.startswith(";") or len(l) == 0:
                    continue

                key, val = l.split('=', 2)
                key = key.strip().lower()
                val = val.strip()
                self.data[key] = val

        iid = self.data['slave1']
        iid = int(iid[3:])+1
        self.iid = iid


    def get_xmlobj(self, n):

        model_ = schema.model_
        x = model_.EthernetPortConfigModel()

        x.PortIdentifier = self.iid + (n - 1)

        x.EnableInterface = self.data['disabled'].lower() != 'yes'
        x.EnableDHCP = self.data['isdhcp'] != 'no'

        x.RedundantPortType = 'ACTIVE_STANDBY'
        x.EnableRedundancy = True
        x.AutoNegotiate = self.get_autoneg(self.data['autoneg'+str(n)])

        if n == 1:
            x.FollowerKeys.append(model_.FollowerKeysType(string=self.iid+1))

        legacy_ip = None
        if not x.EnableDHCP:
            legacy_ip = (self.data['static_ip_addr'], self.data['static_prefix'])
            legacy_gw = self.data['static_gw']

        # set legacy fields for SAG
        if legacy_ip:
            x.IPAddress = legacy_ip[0]
            x.NetworkMask = ip_prefix_len_to_mask(int(legacy_ip[1]))
            if legacy_gw:
                x.Gateway = legacy_gw
            else:
                x.Gateway = '0.0.0.0'
        else:
            x.IPAddress = '0.0.0.0'
            x.NetworkMask = '0.0.0.0'
            x.Gateway = '0.0.0.0'

        return x



class CfgInterf(CfgBase):
    """
auto eth3
iface eth3 inet static
    address 192.168.31.82
    netmask 255.255.255.0
    gateway 192.168.31.2
    autoneg autoneg
    """

    def __init__(self, fn):

        self.data = {
            'disabled': 'yes',
            'port': 'ethX',
            'isdhcp': 'yes',
            'static_ip_addr': '0.0.0.0',
            'static_gw': '0.0.0.0',
            'static_prefix': '0',
            'autoneg': 'autoneg',
        }

        self.load(fn)


    def load(self, fn):
        with open(fn, "r") as f:
            lines = f.readlines()
            family = ""
            for l in lines:
                l = l.strip()
                if l.startswith("#") or l.startswith(";") or len(l) == 0:
                    continue

                words = l.split()
                if words[0] == 'auto':
                    self.data['port'] = words[1]
                    self.data['disabled'] = 'no'

                if words[0] == 'iface':
                    self.data['port'] = words[1]
                    family = words[2]
                    if words[3] == 'static':
                        self.data['isdhcp'] = 'no'
                    else:
                        self.data['isdhcp'] = 'yes'

                if family == "inet":
                    if words[0] == 'address':
                        self.data['static_ip_addr'] = words[1]
                    if words[0] == 'netmask':
                        self.data['static_prefix'] = words[1]
                    if words[0] == 'gateway':
                        self.data['static_gw'] = words[1]
                    if words[0] == 'autoneg':
                        self.data['autoneg'] = words[1]

        iid = self.data['port']
        iid = int(iid[3:])+1
        self.iid = iid


    def get_xmlobj(self):

        model_ = schema.model_
        x = model_.EthernetPortConfigModel()

        x.PortIdentifier = self.iid

        x.EnableInterface = self.data['disabled'].lower() != 'yes'
        x.EnableDHCP = self.data['isdhcp'] != 'no'

        x.RedundantPortType = None
        x.EnableRedundancy = False
        x.AutoNegotiate = self.get_autoneg(self.data['autoneg'])


        legacy_ip = None
        if not x.EnableDHCP:
            legacy_ip = (self.data['static_ip_addr'], self.data['static_prefix'])
            legacy_gw = self.data['static_gw']

        # set legacy fields for SAG
        if legacy_ip:
            x.IPAddress = legacy_ip[0]
            x.NetworkMask = legacy_ip[1]
            if legacy_gw:
                x.Gateway = legacy_gw
            else:
                x.Gateway = '0.0.0.0'
        else:
            x.IPAddress = '0.0.0.0'
            x.NetworkMask = '0.0.0.0'
            x.Gateway = '0.0.0.0'

        return x


class CompatSetting(object):

    def __init__(self):
        self.log = logging.getLogger("compat")

    def load(self):

        interfaces = []
        conf = []

        for fn in os.listdir(DIR):
            if fnmatch.fnmatch(fn, 'config.bond*'):
                try:
                    cfg = CfgBond(DIR+'/'+fn)
                    conf.append(cfg)
                    interfaces.append(cfg.data['slave1'])
                    interfaces.append(cfg.data['slave2'])

                    self.log.info("Loaded {}: {}".format(fn, str(cfg)))
                except:
                    self.log.exception("Exception while loading {}".format(fn))

        for fn in os.listdir(DIR):
            if fnmatch.fnmatch(fn, 'interfaces.eth*'):
                try:
                    cfg = CfgInterf(DIR+'/'+fn)
                    if cfg.data['port'] not in interfaces:
                        conf.append(cfg)
                        interfaces.append(cfg.data['port'])
                        self.log.info("Loaded {}: {}".format(fn, str(cfg)))
                    else:
                        self.log.info("Skipping {}".format(fn))
                except:
                    self.log.exception("Exception while loading {}".format(fn))

        self.conf = conf

    def get_xmlobj(self):

        l = []
        for c in self.conf:
            if isinstance(c, CfgBond):
                for n in [1, 2]:
                    obj = c.get_xmlobj(n)
                    l.append(obj)
            else:
                obj = c.get_xmlobj()
                l.append(obj)

        xmlobj = schema.model_.PlatformNetworkModel(
            EthernetPortConfigModels=[
                schema.model_.EthernetPortConfigModelsType(
                    EthernetPortConfigModel=l
                )
            ]
        )

        return xmlobj


class CompatRoutes(object):

    def __init__(self):
        self.log = logging.getLogger("compat")
        self.routes = {}

    def load(self):

        result = {}

        f = file(DIR+"configured_routes", "r")

        for line in f.readlines():
            line = line.strip()
            if line.startswith("#"):
                continue

            line = line.split(" # ", 2)
            if len(line) < 2:
                continue

            params = line[1].split(",")
            if len(params) != 5:
                continue

            origin = params[4].lower()
            if origin not in ["user", "controller"]:
                continue

            entry = {
                "prefix": params[0],
                "gateway": params[1],
                "portid": params[3],
            }

            oroutes = result.setdefault(origin, [])
            oroutes.append(entry)

        self.routes = result

    def get_json_string(self):
        return json.dumps(self.routes)


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    app = CompatSetting()
    app.load()

    o = app.get_xmlobj()
    print(o.to_xml())

    app = CompatRoutes()
    app.load()
    print(app.get_json_string())
