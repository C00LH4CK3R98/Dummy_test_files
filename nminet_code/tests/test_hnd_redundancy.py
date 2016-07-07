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
import re
import Queue
queue = Queue # python 3
from enum import Enum

#import schema
#import sysfs
#from util import *
#from message import *
#from config import *
from defs import *
from hnd_redundancy import *



class TestRedundancyHandlerActAct_Base(unittest.TestCase):
    REDUNDANCY_MODE = None
    OUT_NAME = None

    EXPECT = []

    def setUp(self):

        ports = {}

        class InterfState(object):
            def __init__(self, interface):
                self.interf = interface
                self.have_carrier = False
                self.active = False
                self._upd()

            def _upd(self):
                self.last_update = time.time()
                self.last_change = self.last_update

            def up(self):
                self.have_carrier = True
                self.active = True
                self._upd()

            def down(self):
                self.have_carrier = False
                self.active = False
                self._upd()

        class Interf(object):
            def __init__(self, iid, mode=self.REDUNDANCY_MODE):
                self.iid = iid
                self.state = InterfState(self)
                self.enable_redundancy = True
                self.redundancy_type = RedundancyType.ACTIVE_ACTIVE
                self.redundancy_mode = mode
                self.redundancy_data = None
                self.redundancy_data_prev = None
                self.manual_primary = False
                self.select_port = False

            def find_port_by_id(self, iid):
                return ports[iid]

        p = Interf(1)
        p.ifslaves = []
        p.slaves = [2]
        p.peers = [2]
        p.master = None
        p.primary = None
        ports[1] = p

        p = Interf(2)
        p.ifslaves = []
        p.slaves = [1]
        p.peers = [1]
        p.master = None
        p.primary = ports[1]
        ports[2] = p

        self.ports = ports
        self.r = RedundancyHandlerActAct()

    def _test_base(self):

        ports = self.ports
        r = self.r

        def get():
            return [r.is_interf_active(ports[1]), r.is_interf_active(ports[2])]


        import itertools

        def reset(st):
            master = [p.primary for p in ports.itervalues() if p.primary is not None][0]
            cfg = master.redundancy_data
            cfg.active_id = st
            cfg.last_update = 0

        def go(pl):
            for i in xrange(len(pl)):
                if pl[i]:
                    ports[i+1].state.up()
                else:
                    ports[i+1].state.down()
            # if ran in a batch mode, some status updates
            # may be lost due to same timestamps of events
            time.sleep(0.0002)

        def transition_label(frm, to):
            s = []
            if not any(to):
                s.append("all disconnect")
            elif all(to):
                s.append("all connect")
            else:
                for p in xrange(len(frm)):
                    if frm[p] and to[p]:
                        pass
                    if not frm[p] and to[p]:
                        s.append("port {} connect".format(p+1))
                    if frm[p] and not to[p]:
                        s.append("port {} disconnect".format(p+1))
                    if not frm[p] and not to[p]:
                        pass


            return ",".join(s)

        def node_label(stat, conn):
            if all(stat):
                s = ["all active"]
            elif not any(stat):
                s = ["none active"]
            elif len([p for p in stat if p]) == 1:
                s = ["port {} active".format(list(stat).index(True)+1)]
            elif len([p for p in stat if p]) > 1:
                s = ["??? {}".format(stat)]

            for i in xrange(len(conn)):
                if conn[i]:
                    s.append("{} connected".format(i+1))

            return "\\n".join(s)


        def have_active_connected(act, conn):
            for i in xrange(min(len(act), len(conn))):
                if act[i] == True and conn[i] == True:
                    return True
            return False

        states = list(itertools.product((True,False), repeat=2))

        # init internal redundancy structs
        get()

        transitions = []
        nodes = []

        for init in [None, 1, 2]:
            for start in states:
                reset(init)

                go(start)
                active_start = get()
                node_start = node_label(active_start, start)

                if not have_active_connected(active_start, start):
                    nodes.append('"{}" [color=red];'.format(node_start))

                for end in states:
                    go(end)
                    active_end = get()
                    node_end = node_label(active_end, end)

                    label = transition_label(start, end)
                    self._check_transition(label, node_start, node_end)
                    transitions.append('"{}" -> "{}" [label="{}"];'.format(node_start, node_end, label))

                    if not have_active_connected(active_end, end):
                        nodes.append('"{}" [color=red];'.format(node_end))


        graphviz = [
            'digraph finite_state_machine {',
            '    rankdir=LR;',
            '    size="20,20"',
            '    node [shape = circle];',
            '',
        ]

        for t in sorted(set(nodes)):
            graphviz.append("    " + t)
        for t in sorted(set(transitions)):
            graphviz.append("    " + t)

        graphviz.append('}')

        self._save_graphviz("\n".join(graphviz))

    def _save_graphviz(self, text):
        if self.OUT_NAME:
            open(self.OUT_NAME, "w").write(text)

    def _check_transition(self, label, node_start, node_end):
        #print("        ({},{},{}),".format(repr(node_start), repr(label), repr(node_end)))
        key = node_start, label, node_end
        value = self.EXPECT.pop(0)
        self.assertEqual(key, value)


class TestRedundancyHandlerActAct_Auto(TestRedundancyHandlerActAct_Base):
    REDUNDANCY_MODE = RedundancyMode.AUTOMATIC
    OUT_NAME = "out_hnd_redundancy_aa_auto.gv"

    EXPECT = [
        # NOTE: generated, check
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 1 active'),
        ('port 2 active\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 1 active'),
        ('port 2 active\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active','all disconnect','port 1 active'),
        ('port 2 active\\n1 connected\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 2 active\\n1 connected\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 1 active'),
        ('port 2 active\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active','all disconnect','port 1 active'),
    ]

    def test_redundancy_aa_auto(self):
        self._test_base()


class TestRedundancyHandlerActAct_AutoRevert(TestRedundancyHandlerActAct_Base):
    REDUNDANCY_MODE = RedundancyMode.AUTOMATIC_REVERT
    OUT_NAME = "out_hnd_redundancy_aa_autorevert.gv"

    EXPECT = [
        # NOTE: generated, check
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 1 active'),
        ('port 2 active\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 1 active'),
        ('port 2 active\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 1 active'),
        ('port 2 active\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active','all disconnect','port 1 active'),
    ]

    def test_redundancy_aa_auto_revert(self):
        self._test_base()


class TestRedundancyHandlerActAct_ManualRevert(TestRedundancyHandlerActAct_Base):
    REDUNDANCY_MODE = RedundancyMode.MANUAL
    OUT_NAME = "out_hnd_redundancy_aa_manualrevert.gv"

    EXPECT = [
        # NOTE: generated, check
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 2 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 2 active'),
        ('port 2 active\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 2 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 2 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active','all disconnect','port 2 active'),
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 2 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 2 active'),
        ('port 2 active\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 2 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 2 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active','all disconnect','port 2 active'),
        ('port 2 active\\n1 connected\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n1 connected\\n2 connected','port 2 disconnect','port 2 active\\n1 connected'),
        ('port 2 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 2 active\\n1 connected\\n2 connected','all disconnect','port 2 active'),
        ('port 2 active\\n1 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n1 connected','','port 2 active\\n1 connected'),
        ('port 2 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 2 active\\n1 connected','all disconnect','port 2 active'),
        ('port 2 active\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 2 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 2 active'),
        ('port 2 active','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active','port 1 connect','port 2 active\\n1 connected'),
        ('port 2 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 2 active','all disconnect','port 2 active'),
    ]

    def test_redundancy_aa_manual_revert(self):
        self._test_base()


class TestRedundancyHandlerActAct_Manual(TestRedundancyHandlerActAct_Base):
    REDUNDANCY_MODE = RedundancyMode.MANUAL_NOFAILOVER
    OUT_NAME = "out_hnd_redundancy_aa_manual.gv"

    EXPECT = [
        # NOTE: generated, check
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 1 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 1 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 1 active'),
        ('port 2 active\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 2 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 2 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 1 active\\n2 connected'),
        ('port 1 active','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected\\n2 connected','port 1 disconnect','port 1 active\\n2 connected'),
        ('port 1 active\\n1 connected\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active\\n1 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 1 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','port 1 active'),
        ('port 1 active\\n2 connected','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 1 active\\n2 connected','','port 1 active\\n2 connected'),
        ('port 1 active\\n2 connected','all disconnect','port 1 active'),
        ('port 1 active','all connect','port 1 active\\n1 connected\\n2 connected'),
        ('port 1 active','port 1 connect','port 1 active\\n1 connected'),
        ('port 1 active','port 2 connect','port 1 active\\n2 connected'),
        ('port 1 active','all disconnect','port 1 active'),
        ('port 2 active\\n1 connected\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n1 connected\\n2 connected','port 2 disconnect','port 2 active\\n1 connected'),
        ('port 2 active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('port 2 active\\n1 connected\\n2 connected','all disconnect','port 2 active'),
        ('port 2 active\\n1 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n1 connected','','port 2 active\\n1 connected'),
        ('port 2 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 2 active\\n1 connected','all disconnect','port 2 active'),
        ('port 2 active\\n2 connected','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 2 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','port 2 active'),
        ('port 2 active','all connect','port 2 active\\n1 connected\\n2 connected'),
        ('port 2 active','port 1 connect','port 2 active\\n1 connected'),
        ('port 2 active','port 2 connect','port 2 active\\n2 connected'),
        ('port 2 active','all disconnect','port 2 active'),
    ]

    def test_redundancy_aa_manual(self):
        self._test_base()


class TestRedundancyHandlerActAct_Dual(TestRedundancyHandlerActAct_Base):
    REDUNDANCY_MODE = RedundancyMode.DUAL
    OUT_NAME = "out_hnd_redundancy_aa_dual.gv"

    EXPECT = [
        # NOTE: generated, check
        ('all active\\n1 connected\\n2 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('all active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('all active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('all active\\n1 connected\\n2 connected','all disconnect','none active'),
        ('port 1 active\\n1 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','none active'),
        ('port 2 active\\n2 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','none active'),
        ('none active','all connect','all active\\n1 connected\\n2 connected'),
        ('none active','port 1 connect','port 1 active\\n1 connected'),
        ('none active','port 2 connect','port 2 active\\n2 connected'),
        ('none active','all disconnect','none active'),
        ('all active\\n1 connected\\n2 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('all active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('all active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('all active\\n1 connected\\n2 connected','all disconnect','none active'),
        ('port 1 active\\n1 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','none active'),
        ('port 2 active\\n2 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','none active'),
        ('none active','all connect','all active\\n1 connected\\n2 connected'),
        ('none active','port 1 connect','port 1 active\\n1 connected'),
        ('none active','port 2 connect','port 2 active\\n2 connected'),
        ('none active','all disconnect','none active'),
        ('all active\\n1 connected\\n2 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('all active\\n1 connected\\n2 connected','port 2 disconnect','port 1 active\\n1 connected'),
        ('all active\\n1 connected\\n2 connected','port 1 disconnect','port 2 active\\n2 connected'),
        ('all active\\n1 connected\\n2 connected','all disconnect','none active'),
        ('port 1 active\\n1 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('port 1 active\\n1 connected','','port 1 active\\n1 connected'),
        ('port 1 active\\n1 connected','port 1 disconnect,port 2 connect','port 2 active\\n2 connected'),
        ('port 1 active\\n1 connected','all disconnect','none active'),
        ('port 2 active\\n2 connected','all connect','all active\\n1 connected\\n2 connected'),
        ('port 2 active\\n2 connected','port 1 connect,port 2 disconnect','port 1 active\\n1 connected'),
        ('port 2 active\\n2 connected','','port 2 active\\n2 connected'),
        ('port 2 active\\n2 connected','all disconnect','none active'),
        ('none active','all connect','all active\\n1 connected\\n2 connected'),
        ('none active','port 1 connect','port 1 active\\n1 connected'),
        ('none active','port 2 connect','port 2 active\\n2 connected'),
        ('none active','all disconnect','none active'),
    ]

    def test_redundancy_aa_dual(self):
        self._test_base()


if __name__ == '__main__':
    unittest.main()
