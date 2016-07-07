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
import Queue
import select
import errno
import subprocess
import json
queue = Queue # python 3
from enum import Enum

from util import *
from message import *
from config import *
from defs import *

__all__ = ['PerfStatThread']


class NetStatEntry(object):
    def __init__(self, name):
        self.name = name
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.speed = 0


class PerfStatThread(threading.Thread):

    STAT_FILE = "/var/nmi/stats.net"
    UPDATE_INTERVAL = 1
    MAX_INTERFACES = 1000

    def __init__(self):
        super(PerfStatThread, self).__init__()
        self.log = logging.getLogger("psint")
        self.queue = queue.Queue()
        self.terminate = False
        self.config = Config()

        self.stat = {}
        self.warncnt = 0

    def get_max_util(self, iflist):
        util = []

        # locking is required here to be completely accurate,
        # but it seems like even partially updated data
        # is acceptable here (except for special care for 'speed')

        stat = self.stat

        for name in iflist:
            entry = stat.get(name)

            if entry is None:
                continue

            speed = entry.speed

            if speed <= 0:
                continue

            ifutil = 100.0 * (max(entry.rx_bytes, entry.tx_bytes) * (8e-6)) / speed       # bytes to megabits
            ifutil = min(max(0, ifutil), 100)
            util.append(int(ifutil))

        if len(util) > 0:
            return max(util)

        return None

    def _del_stat_entry(self, name):
        if name in self.stat:
            del self.stat[name]

    def _get_stat_entry(self, name):
        if name not in self.stat:
            self.stat[name] = NetStatEntry(name)
        return self.stat[name]

    def _read_stats(self):
        try:
            # flush stats if too much entries
            if len(self.stat) > self.MAX_INTERFACES:
                if (self.warncnt % 300) == 0:
                    self.log.warning("Dropping stats, too many entries")
                self.warncnt += 1
                self.stat = {}
            else:
                self.warncnt = 0

            with open(self.STAT_FILE, "r") as f:
                for line in f.readlines():
                    data = line.strip().split()
                    if len(data) < 4:
                        # bad entry
                        continue
                    name = data[0]
                    try:
                        rx_b = int(data[1])
                        tx_b = int(data[2])
                        speed = int(data[3])
                    except ValueError:
                        self._del_stat_entry(name)
                        continue

                    entry = self._get_stat_entry(name)
                    entry.rx_bytes = rx_b
                    entry.tx_bytes = tx_b
                    entry.speed = speed if speed != 65535 else 0

        except IOError:
            # destroy last statistics
            self.stat = {}
        except:
            self.log.exception("Exception while loading stats")

    def run(self):

        while not self.terminate:

            self._read_stats()

            try:
                msg = self.queue.get(timeout=self.UPDATE_INTERVAL)
            except queue.Empty:
                # timeout occured, ignore
                continue

            try:
                if isinstance(msg, MessageStop):
                    self.terminate = True
                else:
                    self.log.error("Internal error, unexpected message class")

            except:
                self.log.exception("Uncaught exception")
                msg.failure()
            finally:
                msg = None      # if msg has value from previos iteration, free it before blocking
                self.queue.task_done()

    def shutdown(self):
        if not self.terminate:
            self.terminate = True
            MessageStop(self.queue).request()

