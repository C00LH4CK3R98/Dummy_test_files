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
from enum import Enum
import cStringIO

import sysfs
from defs import *
from config import *
from util import *

__all__ = ['NICTuning']


class EthtoolException(Exception):
    pass


class HWInterface(object):
    def __init__(self, ifname):
        self.config = Config()
        self.ifname = ifname
        self.driver = None
        self.version = None
        self._load()

    def _load(self):
        out = cStringIO.StringIO()
        exec_checkcode(self.config.ethtool_path, ['-i', self.ifname], fstdout=out)
        out = out.getvalue()

        if not out:
            raise EthtoolException("can not get interface '{}' data".format(self.ifname))

        def getval(l):
            vals = l.split(":", 2)
            if len(vals) == 2:
                return vals[1].strip()
            raise EthtoolException("unexpected line format: '{}'".format(l))

        for line in out.split("\n"):
            if line.startswith("driver:"):
                self.driver = getval(line)
            elif line.startswith("version:"):
                self.version = getval(line)

        if self.driver is None or self.version is None:
            raise EthtoolException("can not get interface '{}' driver and version".format(self.ifname))


    def ethtool(self, template_args):
        fmt = {
            "dev": self.ifname
        }

        args = [arg.format(**fmt) for arg in template_args]

        return exec_checkcode(self.config.ethtool_path, args)


class HWTune(object):
    TUNE_TABLE = {
        "vmxnet3": {
            "ethtool": [
                ["-G", "{dev}", "rx", "4096"],
            ],
        },
        "igb": {
            "ethtool": [
                ["-G", "{dev}", "rx", "4096"],
            ],
        },
        "ixgbe": {
            "ethtool": [
                ["-G", "{dev}", "rx", "4096"],
            ],
        },
        "e1000": {
            "ethtool": [
                ["-G", "{dev}", "rx", "4096"],
            ],
        },

    }

    def __init__(self, hwif):
        self.log = logging.getLogger("tuning")
        self.hwif = hwif

    def tune(self):
        tune = self.TUNE_TABLE.get(self.hwif.driver)
        if not tune:
            return

        for cmd in tune["ethtool"]:
            self.log.debug("Tuning inteface '{}': ethtool {}".format(self.hwif.ifname, str(cmd)))
            self.hwif.ethtool(cmd)


class NICTuning(object):

    def __init__(self):
        self.config = Config()
        self.log = logging.getLogger("tuning")

    def run_initial(self):

        interfaces = sorted(self.config.interf_name_to_nmi.keys())

        for ifname in interfaces:
            try:
                hw = HWInterface(ifname)

                self.log.debug("Interface '{}' driver: {}, version: {}".format(hw.ifname, hw.driver, hw.version))

                HWTune(hw).tune()

            except EthtoolException:
                self.log.exception("Exception while tuning interface '{}'".format(ifname))
            except:
                self.log.exception("Exception while tuning interface '{}'".format(ifname))
