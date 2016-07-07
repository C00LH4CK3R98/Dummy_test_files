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
import subprocess

import schema
import sysfs
from defs import *
from config import *
from util import *

__all__ = ['DHCPClientHnd']

class DHCPClientHnd(object):

    DHCLIENT_EXEC_TIMEOUT = 5

    def __init__(self):
        self.config = Config()
        self.log = logging.getLogger("dhcp")

    def force_renew(self, ifname):
        pid = self.get_dhclient_pid(ifname)
        if pid is None or not is_process_running(pid):
            self.log.warning("Renew requested but DHCP client for {} is not running".format(ifname))
            # XXX restart
            pass
        else:
            self.log.info("Sending HUP signal to DHCP client for {}".format(ifname))
            try:
                os.kill(pid, signal.SIGHUP)
            except OSError:
                ## XXX restart dhcp?
                self.log.exception("Exception while sending HUP to DHCP on {}".format(ifname))

    def set_interf_dhcp(self, ifname, enable_dhcp, renew=False):

        if enable_dhcp:
            if not self.is_dhclient_running(ifname):
                self.log.info("Startind DHCP client for {}".format(ifname))
                self._dhclient_start(ifname)
            elif renew:
                self.force_renew(ifname)

        else:
            if self.is_dhclient_running(ifname):
                self.log.info("Stopping DHCP client for {}".format(ifname))
                self._dhclient_exit(ifname)

    def dhclient_pid_filename(self, ifname):
        return "/var/run/dhclient.{}.pid".format(ifname)

    def get_dhclient_pid(self, ifname):
        pidf = self.dhclient_pid_filename(ifname)
        try:
            # XXX TODO: check process name too ?

            with open(pidf, 'r') as f:
                pid = f.read()
            pid = int(pid.strip())

            if pid > 1:
                return pid

        except IOError:
            pass
        except ValueError:
            pass

        return None

    def is_dhclient_running(self, ifname):
        pid = self.get_dhclient_pid(ifname)

        if pid is not None:
            return is_process_running(pid)

        return False

    def _dhclient_start(self, ifname):
        # Start dhcp client in background.
        pidf = self.dhclient_pid_filename(ifname)
        leasesf = "/tmp/dhclient.{}.leases".format(ifname)

        return self._dhclient_exec(['-pf', pidf, '-lf', leasesf, '-nw', ifname])

    def _dhclient_exit(self, ifname):
        # Release lease and exit.
        # Note that this call blocks and waits dhclient to exit
        # PID file is deleted by dhclient automatically.
        pidf = self.dhclient_pid_filename(ifname)
        return self._dhclient_exec(['-pf', pidf, '-r', ifname])

    def _dhclient_exec(self, args):
        self.log.debug("Running DHCP client command: {}".format(args))
        return exec_checkcode(self.config.dhclient_path, args, log=self.log, timeout=self.DHCLIENT_EXEC_TIMEOUT)
