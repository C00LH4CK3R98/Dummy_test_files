#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 Harmonic Corporation, all rights reserved
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
import subprocess

import schema
import sysfs
from monotonic import monotonic
from defs import *
from config import *
from util import *
from message import *

__all__ = ['DelayedRevertHnd']


class FSMState(Enum):
    INIT = 0
    DISABLE = 1
    ENABLE = 2
    BOTH_FIRST = 3
    PORT2_FIRST = 4
    PORT1_FIRST = 5
    PORT1_SECOND = 6
    END = 7


class RevertFSM(object):
    """
        disabled -> enabled
        enabled -> timeout : end
        enabled -> port 2 up
        enabled -> port 1 up : end
        enabled -> 1 and 2 up : revert
        port 2 up -> port 1 up : revert
        port 2 up -> timeout : end
    """

    RUN_STEPS_LIMIT = 10

    def __init__(self, revert_handler, timeout=10.0):
        self.timeout = timeout
        self.log = logging.getLogger("revert")
        self.revert_handler = revert_handler
        self.reset()

    def reset(self):
        self.state = FSMState.INIT
        self.start_time = 0

    def check_revert(self, primary, group):

        if primary.redundancy_status != RedundancyStatus.ACTIVE:
            #self.log.debug("######################## revert")
            self.revert_handler(primary, group)

    def handle_one(self, primary, group):

        secondary = group[1] if len(group)>1 else primary

        def go(new):
            #self.log.debug("######################## fsm {} -> {}".format(self.state, new))
            self.state = new
            go.updated = True
        go.updated = False


        if self.state == FSMState.INIT:

            if not primary.enabled:
                go(FSMState.DISABLE)

        elif self.state == FSMState.DISABLE:

            if primary.enabled:
                self.start_time = monotonic()
                go(FSMState.ENABLE)

        elif self.state == FSMState.ENABLE:

            if not primary.enabled:
                go(FSMState.DISABLE)
            elif primary.status == PortStatus.CONNECTED and primary.status == PortStatus.CONNECTED:
                go(FSMState.BOTH_FIRST)
            elif primary.status == PortStatus.CONNECTED:
                go(FSMState.PORT1_FIRST)
            elif secondary.status == PortStatus.CONNECTED:
                go(FSMState.PORT2_FIRST)

        elif self.state == FSMState.BOTH_FIRST:

            self.check_revert(primary, group)
            go(FSMState.END)

        elif self.state == FSMState.PORT2_FIRST:

            if not primary.enabled:
                go(FSMState.DISABLE)
            elif secondary.status == PortStatus.CONNECTED and primary.status == PortStatus.CONNECTED:
                go(FSMState.PORT1_SECOND)
            elif secondary.status != PortStatus.CONNECTED:
                go(FSMState.ENABLE)

        elif self.state == FSMState.PORT1_FIRST:

            go(FSMState.END)

        elif self.state == FSMState.PORT1_SECOND:

            self.check_revert(primary, group)
            go(FSMState.END)

        elif self.state == FSMState.END:

            # restart
            self.start_time = 0
            go(FSMState.INIT)

        else:
            self.log.error("Bad revert fsm state {}".format(self.state))
            self.start_time = 0
            go(FSMState.INIT)

        #if not go.updated:
        #    self.log.debug("######################## fsm {}".format(self.state))

        return go.updated

    def handle(self, primary, group):

        prev_state = self.state

        if self.start_time > 0:
            if monotonic() >= self.start_time + self.timeout:
                self.log.debug("Revert fsm {}: timeout".format(primary.nmi_id))
                self.reset()
                return

        cnt = self.RUN_STEPS_LIMIT
        while True:
            if not self.handle_one(primary, group):
                #self.log.debug("######################## fsm iters left {}".format(cnt))
                break
            cnt -= 1
            if cnt <= 0:
                self.log.warning("Revert fsm: too many steps")
                self.reset()
                break

        if prev_state != self.state:
            self.log.debug("Revert fsm {}: {} -> {}".format(primary.nmi_id, prev_state, self.state))


class DelayedRevertHnd(object):

    REVERT_DELAY = 2
    FSM_TIMEOUT = 5

    def __init__(self, queue):
        self.queue = queue
        self.log = logging.getLogger("revert")
        self.states = {}

    def handler_do_revert(self, primary, group):
        self.log.info("Executing revert for {}".format(primary.nmi_id))
        MessageRevertInterface(self.queue, data=[primary.nmi_id]).request()

    def reset_group(self, primary, group):
        for interf in group:
            if interf.nmi_id in self.states:
                self.log.debug("Revert handler {}/{} reset".format(primary.nmi_id, interf.nmi_id))
                del self.states[interf.nmi_id]

    def process_group(self, primary, group):

        if primary.nmi_id not in self.states:
            fsm = RevertFSM(self.handler_do_revert, timeout=self.FSM_TIMEOUT)
            self.states[primary.nmi_id] = fsm
        else:
            fsm = self.states[primary.nmi_id]

        fsm.handle(primary, group)

    def interfaces_updated(self, net_data):

        groups = net_info_group_by_redundancy(net_data)

        try:
            handled = []
            for group in groups.itervalues():
                if group in handled:
                    continue

                handled.append(group)

                primary = group[0]

                # Need redundancy enabled and in Automatic mode
                if primary.redundancy_type == RedundancyType.NONE:
                    self.reset_group(primary, group)
                    continue
                if primary.redundancy_mode != RedundancyMode.AUTOMATIC:
                    self.reset_group(primary, group)
                    continue

                self.process_group(primary, group)

        except:
            self.log.exception("Exception while handling revert")
            # reset
            self.states = {}

