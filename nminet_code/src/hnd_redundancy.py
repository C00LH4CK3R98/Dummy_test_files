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
import re
import Queue
queue = Queue # python 3
from enum import Enum

import schema
import sysfs
from defs import *
from util import *

__all__ = ['RedundancyHandlerNOOP', 'RedundancyHandlerActAct']

class RedundancyHandlerBase(object):

    def init_interf(self, interf):
        interf.redundancy_handler = self

    def is_interf_active(self, interf):
        pass

    def set_active(self, interf):
        pass

    def update(self, interf):
        pass


class RedundancyHandlerNOOP(RedundancyHandlerBase):
    def is_interf_active(self, interf):
        return interf.state.active


class RedundancyHandlerActAct(RedundancyHandlerBase):

    class PortState(object):
        def __init__(self):
            self.sticky = False
            self.final = False
            self.prio = 0


    class RConfig(object):
        def __init__(self, prev=None):
            self.slave_state = {}
            if prev:
                self.active_id = prev.active_id
            else:
                self.active_id = None
            self.last_update = 0


    def _apply_port_config(self, cfg, rconf):
        for iid, data in rconf.iteritems():
            cfg.slave_state[iid].sticky = data['sticky'] if 'sticky' in data else False
            cfg.slave_state[iid].final = data['final'] if 'final' in data else False
            cfg.slave_state[iid].prio = data['prio'] if 'prio' in data else 0

    def _recalc_redundancy(self, master, cfg, primary, ports):

        # check if port configuration changed
        if cfg.slave_state.keys() != ports.keys():
            for iid, port in ports.iteritems():
                if iid not in cfg.slave_state:
                    cfg.slave_state[iid] = self.PortState()

            for iid in list(cfg.slave_state.keys()):
                if iid not in ports:
                    del cfg.slave_state[iid]

            if cfg.active_id not in ports:
                cfg.active_id = None

            portnames, new_active = find_primary_selected(master,
                list(ports.itervalues()), lambda p: p.iid)

            # recalc priorities, etc.
            portconf = get_teamed_config(master.redundancy_mode, portnames)
            self._apply_port_config(cfg, portconf)

            # ???
            if new_active:
                cfg.active_id = new_active.iid

        if cfg.active_id is not None:
            current = ports[cfg.active_id]
        else:
            current = None

        active_ports = [p for p in ports.itervalues() if p.state.have_carrier]
        if active_ports:
            best = max(active_ports, key=lambda p: cfg.slave_state[p.iid].prio)
        else:
            # best = current
            # 'master' results in better state diagrams
            best = master

        # select new active port
        if current is None:
            if best:
                cfg.active_id = best.iid
            return

        # final port, no failover even if it fails
        if cfg.slave_state[current.iid].final:
            return

        # check if there's better port if non-sticky or failed
        if not cfg.slave_state[current.iid].sticky:
            if cfg.slave_state[best.iid].prio > cfg.slave_state[current.iid].prio:
                cfg.active_id = best.iid
                return

        if not current.state.have_carrier:
            if best.iid != current.iid:
                cfg.active_id = best.iid
                return

    def is_interf_active(self, interf):
        master = interf.primary if interf.primary else interf

        if master.redundancy_data is None:
            master.redundancy_data = self.RConfig(master.redundancy_data_prev)

        # no special handling in dual mode
        if master.redundancy_mode == RedundancyMode.DUAL:
            return interf.state.active

        cfg = master.redundancy_data

        # if there are new interfaces in redundant set,
        # new interface will have updated timestamp,
        # so check timestamps only

        # check when redundant interfaces state was updated
        # last time
        ports = {interf.iid: interf}
        newstate = interf.state.last_change
        for iid in interf.peers:
            eth = interf.find_port_by_id(iid)
            ports[iid] = eth
            if eth.state.last_change > newstate:
                newstate = eth.state.last_change

        if cfg.last_update < newstate:
            self._recalc_redundancy(master, cfg, interf, ports)
            cfg.last_update = newstate

        return cfg.active_id == interf.iid

    def set_active(self, interf):
        master = interf.primary if interf.primary else interf

        if master.redundancy_data is not None:
            cfg = master.redundancy_data
            cfg.active_id = interf.iid
            # force update on next status check
            cfg.last_update = 0

    def update(self, interf):
        master = interf.primary if interf.primary else interf

        if master.redundancy_data is not None:
            cfg = master.redundancy_data
            # force update on next status check
            cfg.last_update = 0

