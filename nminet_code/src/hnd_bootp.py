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
import socket
import logging
from copy import deepcopy

from config import *
from defs import *
from util import *
from message import *

__all__ = ['BootPHandler']


class BootPHandler(object):
    BOOTP_TIMEOUT = 18
    BOOTP_MAXFAIL = 2

    def __init__(self, main, rqqueue):
        self.config = Config()
        self.main = main
        self.queue = rqqueue
        self.enable = self.config.args.bootp
        self.fails = {}
        self.iids = []
        self.original_config = {}
        self.log = logging.getLogger("bootp")
        self.timer = None
        self.lock = threading.RLock()

        self.results = {}

        if self.enable:
            self.timer = threading.Timer(self.BOOTP_TIMEOUT, self.timeout)
            self.timer.start()

    def finish(self, iids):
        for iid in iids:
            if iid in self.iids:
                self.iids.remove(iid)

        if len(self.iids) == 0:
            self.log.info("BOOTP finished")
            self.enable = False
            if self.timer:
                self.timer.cancel()

            MessageXMLRPCRequest(self.queue, MessageXMLRPCRequest.REQ_BOOTP_FINISHED, data=self.results).request()

            # cleanup
            self.fails = {}
            self.iids = []
            self.original_config = {}
            self.results = {}

    def mangle_config(self, ports):
        if not self.enable:
            return ports

        # enable DHCP on BOOTP ports
        config = {}
        for iid in self.config.bootp_ports:
            config[iid] = self.main.PortConfigData(dhcp=True, enabled=True)

        self.iids = []
        self.original_port_config = {}
        for port in ports:
            if port.PortIdentifier in config:
                iid = port.PortIdentifier
                self.iids.append(iid)
                self.original_port_config[iid] = deepcopy(port)

        self.log.info("Starting BOOTP on Ports {}".format(self.iids))

        modfunc = self.main.make_configure_port_func(config)

        return modfunc(ports)

    def get_iids_by_l3int(self, ifname):
        # Warning, this data is available at a callback time only.
        # When initial configuration is ran, mng.ports is empty
        return self.main.mng.get_iids_by_l3int(ifname)

    def bootp_success(self, iids, ifname, ip, gw):

        self.log.info("Got address via BOOTP on Ports {}, interface {}: ip: '{}', gw: '{}'".format(iids, ifname, ip, gw))

        try:
            # configure new address as static
            for iid in iids:
                self.results[iid] = self.main.PortConfigData(dhcp=False, ip=ip, gw=gw, enabled=True)
        finally:
            self.finish(iids)

    def bootp_fail(self, iids):

        self.log.info("BOOTP failed on Ports {}".format(iids))

        try:
            # restore original config
            for iid in iids:
                if iid in self.original_port_config:
                    self.results[iid] = self.main.ReplaceConfigData(self.original_port_config[iid])
        finally:
            self.finish(iids)


    def timeout(self):
        with self.lock:
            if self.enable and len(self.iids) > 0:
                self.log.info("BOOTP timeout")
                self.bootp_fail(list(self.iids))

    def dhcp_callback(self, family, ifname, ip=None, gateway=None, expire=False):
        with self.lock:
            return self._dhcp_callback(family, ifname, ip, gateway, expire)

    def _dhcp_callback(self, family, ifname, ip, gateway, expire):
        if not self.enable:
            return None

        if family != socket.AF_INET:
            return False

        iids = self.get_iids_by_l3int(ifname)
        if iids is None or not iids:
            return False

        fail = False
        success = False
        for iid in iids:
            if iid not in self.iids:
                return None

            if iid not in self.fails:
                self.fails[iid] = 0

            if expire:
                self.fails[iid] += 1

            if self.fails[iid] >= self.BOOTP_MAXFAIL:
                fail = True
                break
            elif not expire:
                success = True
                break

        if fail:
            self.bootp_fail(iids)
        elif success:
            self.bootp_success(iids, ifname, ip, gateway)

        return False

