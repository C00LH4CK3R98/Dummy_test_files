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
import Queue
import select
import errno
import subprocess
import json
queue = Queue # python 3
from enum import Enum
from collections import deque, namedtuple
from monotonic import monotonic

from cksum import cksum
from util import *
from message import *
from config import *
from defs import *
from alarm_handlers import *
from alarm_types import Harmonic_Internal_IPConfigurationChanged

__all__ = ['AlarmProcThread']


class NMIEventSender(object):
    PORT = 8514
    SEP = "#"

    def __init__(self):
        self.config = Config()
        self.log = logging.getLogger("nmievent")

    def _exec(self, cmd, args):

        proc = subprocess.Popen([cmd]+args,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        close_fds=True)

        stdoutdata, stderrdata = proc.communicate()

        if proc.returncode != 0:
            self.log.error("{} returned an error code {}: '{}', '{}'".format(
                                cmd, proc.returncode, stdoutdata, stderrdata))
            return False

        return True

    def nmievent_sh(self, action, event):
        args = [
            '-a', action,
            '-s', event.source,
            '-l', event.level,
            '-n', event.name,
            '-t', event.title,
            '-d', event.desc,
        ]

        if event.obj is not None:
            args.append('-o')
            args.append(str(event.obj))

        for key, val in event.params.iteritems():
            args.append('-k')
            if type(val) is bool:
                val = "true" if val else "false"
            args.append("{}={}".format(key, val))

        self._exec(self.config.nmievent_sh, args)

    def format_message(self, action, event):

        objid = str(event.obj) if event.obj is not None else ""

        opts = [
            ('ACTION', action),
            ('LEVEL', event.level),
            ('NAME', event.name),
            ('TITLE', event.title),
            ('OBJID', objid),
            ('SOURCE', event.source),
            ('DESC', event.desc),
        ]

        def unsep(s):
            if type(s) == str:
                return s.replace(self.SEP, '_')
            return s

        msg = []
        for name, value in opts:
            msg.append("{}={}".format(name, unsep(value)))

        for name, value in event.params.iteritems():
            msg.append("{}={}".format(unsep(name), unsep(value)))

        event = self.SEP + (self.SEP.join(msg)) + "\n"

        checksum = cksum(event)

        return "CKSUM={}{}".format(checksum, event)

    def nmievent_tcp(self, action, event):
        data = self.format_message(action, event)

        if len(data) > 2048:
            self.log.warning("NMI event message is too long: {}".format(len(data)))

        #self.log.info(data)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(0.25)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.connect(("127.0.0.1", self.PORT))
            s.send(data)
        finally:
            s.close()

    def send(self, action, event):
        try:
            return self.nmievent_tcp(action, event)
        except:
            self.log.exception("Exception while sending event using TCP")
            self.log.warning("Sending event using a script as a fallback (slow)")
            return self.nmievent_sh(action, event)


class EventDescriptor(object):
    def __init__(self, evt):
        self._name = evt.name
        self._obj = evt.obj
        self._source = evt.source
        self._desc = evt.desc

    @property
    def desc(self):
        return self._desc

    def __hash__(self):
        return hash(self._name) ^ hash(self._obj) ^ hash(self._source)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __eq__(self, other):
        return (self._name == other._name and
            self._obj == other._obj and
            self._source == other._source)

    def __str__(self):
        return "<EventDescriptor: {} {} {}>".format(self._source, self._name, self._obj)

    def __repr__(self):
        return self.__str__()


class EventStatus(object):
    def __init__(self, status, event):
        self._status = status
        self._event = event

    @property
    def event(self):
        return self._event

    @property
    def status(self):
        return self._status


class EventProcessor(object):

    EVENT_SENDER = NMIEventSender

    PlanItem = namedtuple('PlanItem', ['action', 'event', 'key'])

    def __init__(self, alarmproc):
        self.alarmproc = alarmproc
        self.alarmstatus = {}
        self.alarmstatus_start = {}
        self.seen_updates = []
        self.event_plan = []
        self.time_alarmproc = 0
        self.time_nmievent = 0
        self.sender = self.EVENT_SENDER()

    @property
    def log(self):
        return self.alarmproc.log


    def add_plan(self, action, event):
        key = EventDescriptor(event)
        if event.merge:
            prevs = [x for x in self.event_plan if x.key == key]
            for item in prevs:
                self.event_plan.remove(item)

        self.event_plan.append(self.PlanItem(action, event, key))

    def event(self, evt):
        if evt.is_event:
            self.log.debug("EVENT: {}".format(str(evt)))
            self.add_plan('EVENT', evt)
        else:
            self.log.error("cant send alarm as an event {}".format(str(evt)))

    def alarm(self, evt, is_on):
        if not evt.is_event:
            act = "ALARM_ON" if is_on else "ALARM_OFF"

            edescr = EventDescriptor(evt)
            do_update = True
            is_new_alarm = edescr not in self.alarmstatus

            if not is_new_alarm:
                if self.alarmstatus[edescr].status == act:
                    # same status, nothing to update
                    do_update = False
                elif evt.merge and not is_on and edescr in self.seen_updates:
                    # for merged alarms do not remit already
                    # emitted alarms in a single run
                    do_update = False

            # force alarm re-emit if alarm has new description
            if not do_update and is_on and (evt.desc != self.alarmstatus[edescr].event.desc):
                do_update = True

            self.seen_updates.append(edescr)

            if do_update or is_new_alarm:
                self.alarmstatus[edescr] = EventStatus(act, evt)

            if do_update and not (is_new_alarm and not is_on):
                self.log.debug("ALARM {}: {}".format(is_on, str(evt)))
                self.add_plan(act, evt)
        else:
            self.log.error("cant send event as an alarm {}".format(str(evt)))

    def simple_event(self, event):
        self.log.debug("EVENT: Simple {}".format(str(event)))
        self.sender.send('EVENT', event)

    def process_start(self):
        self.seen_updates = []
        self.event_plan = []
        self.time_alarmproc = monotonic()
        self.time_nmievent = 0
        self.alarmstatus_start = dict(self.alarmstatus)

    def process_end(self):
        orphaned_alarms = set(self.alarmstatus.keys())-set(self.seen_updates)

        for orphan in orphaned_alarms:
            desc = self.alarmstatus.pop(orphan)

            if desc.status == "ALARM_ON":
                self.log.info("Remitting orphaned alarm: {}".format(desc.event))
                self.add_plan("ALARM_OFF", desc.event)

        self.time_nmievent = monotonic()

        self.event_plan.sort(key=lambda item: item.event.order)

        for item in self.event_plan:
            if item.event.merge:
                skey = EventDescriptor(item.event)
                if skey in self.alarmstatus_start and self.alarmstatus_start[skey].status == item.action:
                    self.log.debug("Skipping event {} {}".format(item.action, item.event))
                    continue
            self.sender.send(item.action, item.event)

        t = monotonic()
        self.log.debug("stats: proc:{:.3f}s, nmi:{:.3f}s".format(self.time_nmievent-self.time_alarmproc, t-self.time_nmievent))

        # free memory
        self.seen_updates = []
        self.event_plan = []


class AlarmProcThread(threading.Thread):

    EVT_HIST_SIZE = 500

    def __init__(self, event_proc_klass=None):
        super(AlarmProcThread, self).__init__()
        self.log = logging.getLogger("alarm")
        self.queue = queue.Queue()
        self.terminate = False
        self.config = Config()
        self.event_history = deque(maxlen=self.EVT_HIST_SIZE)
        if event_proc_klass is not None:
            self.event_proc = event_proc_klass(self)
        else:
            self.event_proc = EventProcessor(self)

    def get_hist_data(self, index=0):
        try:
            return self.event_history[index]
        except IndexError:
            #self.log.debug("history event index {} not found".format(index))
            return None

    def interf_same_base_config(self, if1, if2):
        return (if1.redundancy_type == if2.redundancy_type and
                if1.redundancy_mode == if2.redundancy_mode and
                if1.enabled == if2.enabled and
                if1.manual_primary_port == if2.manual_primary_port and
                if1.teammembers == if2.teammembers)

    def get_prev_data(self, ifdata, same_mode=False):
        pdata = self.get_hist_data(-2)
        if pdata is None:
            return None

        prev_ifdata = pdata.get(ifdata.nmi_id)
        if prev_ifdata is None:
            return None

        if same_mode and not self.interf_same_base_config(ifdata, prev_ifdata):
            return None

        return prev_ifdata

    def handle_new_config(self, msg):
        self.log.debug("New configuration event")
        self.event_proc.simple_event(Harmonic_Internal_IPConfigurationChanged())

    def handle_upd_alarms(self, msg):
        self.log.debug("Updating alarms...")
        data = msg.data

        for iid in sorted(data.keys()):
            self.log.debug("Port {} state: {}".format(iid, data[iid].get_dict()))

        self.event_history.append(data)

        groups = net_info_group_by_redundancy(data)

        AlarmRedundancyHandlers = {
            (RedundancyType.ACTIVE_STANDBY, RedundancyMode.AUTOMATIC): AlarmHandlerActiveStandby,
            (RedundancyType.ACTIVE_STANDBY, RedundancyMode.AUTOMATIC_REVERT): AlarmHandlerActiveStandby,
            (RedundancyType.ACTIVE_STANDBY, RedundancyMode.MANUAL): AlarmHandlerActiveStandby,
            (RedundancyType.ACTIVE_STANDBY, RedundancyMode.MANUAL_NOFAILOVER): AlarmHandlerActiveStandby,

            (RedundancyType.ACTIVE_ACTIVE, RedundancyMode.AUTOMATIC): AlarmHandlerActiveStandby,
            (RedundancyType.ACTIVE_ACTIVE, RedundancyMode.AUTOMATIC_REVERT): AlarmHandlerActiveStandby,
            (RedundancyType.ACTIVE_ACTIVE, RedundancyMode.MANUAL): AlarmHandlerActiveStandby,
            (RedundancyType.ACTIVE_ACTIVE, RedundancyMode.MANUAL_NOFAILOVER): AlarmHandlerActiveStandby,
            (RedundancyType.ACTIVE_ACTIVE, RedundancyMode.DUAL): AlarmHandlerActiveStandby,
        }

        self.event_proc.process_start()
        try:
            handled = []
            for group in groups.itervalues():
                if group in handled:
                    continue

                primary = group[0]

                handlertype = None
                if primary.redundancy_type == RedundancyType.NONE:
                    handlertype = AlarmHandlerSingle
                else:
                    handlertype = AlarmRedundancyHandlers.get((primary.redundancy_type, primary.redundancy_mode))

                if not handlertype:
                    self.log.error("Can not find alarm handler for interface {} mode".format(primary.nmi_id))
                    continue

                handler = handlertype(self)

                res = handler.check_interfaces(group)
                if res:
                    handled.append(group)

        finally:
            self.event_proc.process_end()

    def run(self):

        while not self.terminate:

            try:
                msg = self.queue.get(timeout=1)
            except queue.Empty:
                # timeout occured, ignore
                continue

            try:
                if isinstance(msg, MessageUpdateAlarms):
                    self.handle_upd_alarms(msg)
                elif isinstance(msg, MessageNewConfiguration):
                    self.handle_new_config(msg)
                elif isinstance(msg, MessageStop):
                    self.terminate = True
                else:
                    self.log.error("Internal error, unexpected message class")

            except:
                self.log.exception("Uncaught exception")
                msg.failure()
            finally:
                msg = None      # if msg has value from previos iteration, free it before blocking
                self.queue.task_done()

    def process_alarm_data_async(self, data):
        if not self.terminate:
            MessageUpdateAlarms(self.queue, data=data).request()
            return True
        return False

    def new_configuration_event_async(self):
        if not self.terminate:
            MessageNewConfiguration(self.queue).request()
            return True
        return False

    def shutdown(self):
        if not self.terminate:
            self.terminate = True
            MessageStop(self.queue).request()

    def shutdown_when_done(self):
        # Do not use, for tests only
        MessageStop(self.queue).request()


