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
import pyroute2
from pyroute2 import IPDB
from pyroute2.netlink.rtnl.ifinfmsg import IFF_UP, IFF_ALLMULTI
from pyroute2.netlink.rtnl import rtypes
import Queue
queue = Queue   # python 3

from util import *
from message import *

__all__ = ['IPRoute', 'EthernetIP', 'RouteUnreachable', 'IFF_UP', 'IFF_ALLMULTI']


class RouteUnreachable(object):
    pass


class EthernetIP(object):
    def __init__(self, prefix, plen=None, addr_type=None):
        if plen is None:
            self._prefix = prefix
        else:
            self._prefix = "{}/{}".format(prefix, plen)
        self.normalize()
        self.addr_type = addr_type

    def get_network(self):
        family = self.family
        plen = self.plen
        mask = ip_to_long(ip_prefix_len_to_mask(plen, family), family)
        addr = self.ipaddr

        new_addr = ip_to_long(addr, family) & mask

        return EthernetIP(long_to_ip(new_addr, family), plen=plen)

    def normalize(self):
        if self._prefix:
            self._prefix = "{}/{}".format(self.ipaddr, self.plen)

    @property
    def prefix(self):
        return self._prefix

    @property
    def ipaddr(self):
        return self._prefix.split('/')[0] # TODO/FIXME a hack

    @property
    def plen(self):
        spl = self._prefix.split('/')
        if len(spl) < 2:
            if self.family == socket.AF_INET6:
                return 128
            else:
                return 32
        else:
            mask = spl[1]
            try:
                plen = int(mask)
            except ValueError:
                # assume 1.1.1.1/255.0.0.0 format
                plen = ip_mask_to_prefix_len(mask)
            return plen

    @property
    def ipmask(self):
        spl = self._prefix.split('/')
        if len(spl) < 2:
            if self.family == socket.AF_INET6:
                return "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
            else:
                return "255.255.255.255"
        else:
            mask = spl[1]
            try:
                plen = int(mask)
                mask = ip_prefix_len_to_mask(plen, self.family)
            except ValueError:
                # assume 1.1.1.1/255.0.0.0 format
                pass
            return mask

    @property
    def family(self):
        if ":" in self._prefix: # FIXME, not a best method
            return socket.AF_INET6
        return socket.AF_INET

    def is_link_local(self):
        plen = self.plen
        addr = self.ipaddr
        family = self.family
        if family == socket.AF_INET6:
            # IPv6: fe80::/10
            if plen < 10:
                return False

            ll_net = 0xfe80 << 112
            ll_mask = 0xffc0 << 112
            ip_long = ip_to_long(addr, family)
        else:
            # IPv4: 169.254.0.0/16
            if plen < 16:
                return False

            ll_net = 0xa9fe0000
            ll_mask = 0xffff0000
            ip_long = ip_to_long(addr, family)

        return ip_long & ll_mask == ll_net

    def is_valid_interface_ip(self):
        family = self.family
        addr = ip_to_long(self.ipaddr, family)
        plen = self.plen

        if addr == 0:
            return False

        if family == socket.AF_INET6:
            if plen < 0 or plen > 128:
                return False
            # other restrictions ?
        else:
            if plen < 0 or plen > 32:
                return False

        return True

    def __repr__(self):
        return "<{}: {}, {}>".format(self.__class__.__name__, self._prefix, self.addr_type)

    def __str__(self):
        return repr(self)

    # compare address and mask, not addr_type
    def __eq__(self, other):
        if not isinstance(other, EthernetIP):
            return False
        family = self.family
        return (family == other.family and
                ip_to_long(self.ipaddr, family) == ip_to_long(other.ipaddr, family) and
                self.plen == other.plen)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        res = 0
        family = self.family
        res ^= family
        res ^= ip_to_long(self.ipaddr, family)
        res ^= self.plen
        return res


class SysRoute(object):
    def __init__(self, dst, plen, gw, oif, metric, realm, rtype):
        self.dst = dst
        self.plen = plen
        self.gw = gw
        self.oif = oif
        self.metric = metric
        self.realm = realm
        self.rtype = rtype


class IPRoute(object):
    UNREACH_BASE = 180
    MAIN = 254

    PROTO = 32

    DEFAULTS = {
        socket.AF_INET: "0.0.0.0",
        socket.AF_INET6: "::",
    }

    class Entry(object):
        def __init__(self, prefix, gateway, metric=None):
            self.prefix = prefix
            self.gateway = gateway
            self.metric = metric
            if self.prefix is None and self.gateway is not None:
                self.prefix = EthernetIP(IPRoute.DEFAULTS[self.gateway.family], plen=0)

        @property
        def family(self):
            return self.prefix.family

        @property
        def dst(self):
            return self.prefix.ipaddr

        @property
        def dst_len(self):
            return self.prefix.plen

        @property
        def gw(self):
            if self.gateway is None:
                return "255.255.255.255"
            return self.gateway.ipaddr

        def get_metric(self, default=10):
            return self.metric if self.metric is not None else default

        def __hash__(self):
            return (11 * hash(self.prefix)) ^ (7 * self.metric) ^ hash(self.gateway)

        def __eq__(self, other):
            return (self.prefix == other.prefix and
                    (self.gateway == other.gateway or (self.gateway is None and other.gateway is None)) and
                    self.metric == other.metric)

        def __neq__(self, other):
            return not self.__eq__(other)


    def __init__(self, rqqueue):
        super(IPRoute, self).__init__()
        self.queue = rqqueue
        self.ip = None
        self.ready = False
        self.log = logging.getLogger("iproute")

    def barrier(self):
        # this is from iproute2
        time.sleep(0.2)

    def create_unreach_rules(self, iids):

        targets = [(self.UNREACH_BASE + iid, 10000 + iid) for iid in iids]

        nl = self.ip.nl
        rules = nl.get_rules()
        # {'family': 2, 'dst_len': 0, 'proto': 0, 'tos': 0, 'event': 'RTM_NEWRULE', 'flags': 0, 'attrs': [['RTA_TABLE', 241], ['RTA_PRIORITY', 241]], 'table': 241, 'src_len': 0, 'type': 1, 'scope': 0}

        for rule in rules:
            target = (rule.get_attr('RTA_TABLE'), rule.get_attr('RTA_PRIORITY'))
            if target in targets:
                targets.remove(target)

        for table, prio in targets:
            try:
                nl.rule('add', table, prio, family=socket.AF_INET)
                nl.rule('add', table, prio, family=socket.AF_INET6)
            except:
                pass

    def set_interface_routes(self, ifname, routes, default_metric=10, table=None):
        rttable = self.MAIN if table is None else table
        # use iproute netlink api, and not IPDB
        # IPDB is broken if multiple routes for
        # same destination required (e.g. multiple
        # defaults with different metric)
        nl = self.ip.nl

        ifidx = self.ip.interfaces[ifname].index

        for family in [socket.AF_INET]:
            rawroutes = nl.get_routes(family=family, table=rttable)

            delete = []
            seen = []
            for r in rawroutes:
                proto = r.get('proto')

                if proto != self.PROTO:
                    continue

                oif = r.get_attr('RTA_OIF')
                if oif is not None and oif != ifidx :
                    continue

                dst = r.get_attr('RTA_DST')
                if dst:
                    plen = r.get('dst_len')
                else:
                    dst = self.DEFAULTS[family]
                    plen = 0

                gateway = r.get_attr('RTA_GATEWAY')
                metric = r.get_attr('RTA_PRIORITY')
                realm = r.get_attr('RTA_FLOW')
                rtype = r.get('type')

                # check if route is installed already
                # and remember matches
                if rtype == rtypes['RTN_UNREACHABLE']:
                    egateway = RouteUnreachable
                else:
                    egateway = EthernetIP(gateway) if gateway is not None else EthernetIP(self.DEFAULTS[family])
                thisroute = self.Entry(EthernetIP(dst, plen=plen), egateway, metric)
                if thisroute in routes:
                    seen.append(thisroute)
                else:
                    sr = SysRoute(dst, plen, gateway, oif, metric, realm, rtype)
                    delete.append(sr)

            # delete extra routes
            for sr in delete:
                rtinfo = {
                    'table': rttable,
                    'rtproto': self.PROTO,
                    'family': family,

                    'dst': sr.dst,
                    'dst_len': sr.plen,

                    'rtype': sr.rtype,
                }
                if sr.metric is not None:
                    rtinfo['RTA_PRIORITY'] = sr.metric
                if sr.realm is not None:
                    rtinfo['RTA_FLOW'] = sr.realm
                if sr.gw:
                    rtinfo['gateway'] = sr.gw
                if sr.oif:
                    rtinfo['oif'] = sr.oif
                try:
                    self.log.debug("Removing route {}".format(rtinfo))
                    nl.route('del', **rtinfo)
                except pyroute2.netlink.NetlinkError, e:
                    self.log.error("Can not remove route {}: {}".format(rtinfo, e))

            # install routes that are missing
            for route in routes:
                if route in seen:
                    continue
                rtinfo = {
                    'table': rttable,
                    'rtproto': self.PROTO,
                    'family': family,

                    'dst': route.dst,
                    'dst_len': route.dst_len,

                    #'prefsrc': ,

                    'RTA_PRIORITY': route.get_metric(default_metric),
                    #'RTA_FLOW': ,
                }
                if route.gateway is RouteUnreachable:
                    # unreachable destination
                    rtinfo['rtype'] = "RTN_UNREACHABLE"
                elif route.gateway is not None:
                    if ip_to_long(route.gw, family=route.family) == 0: # '0.0.0.0' or '::'
                        # link route
                        pass
                    else:
                        # usual route
                        rtinfo['gateway'] = route.gw
                    rtinfo['oif'] = ifidx
                    rtinfo['rtype'] = "RTN_UNICAST"
                else:
                    # invalid route, bad gateway
                    continue

                try:
                    self.log.debug("Adding route {}".format(rtinfo))
                    nl.route('add', **rtinfo)
                except pyroute2.netlink.NetlinkError, e:
                    self.log.error("Can not install route {}: {}".format(rtinfo, e))

    def start(self):
        self.ip = IPDB()
#        self.ip.register_callback(self.ipcallback)

    def ipcallback(self, ipdb, msg, action):
        print("cb ", action, msg)

    def run(self):
        pass

    def join(self, timeout=None):
        pass

    def shutdown(self):
        if self.ip:
            self.ip.release()
            self.ip = None

