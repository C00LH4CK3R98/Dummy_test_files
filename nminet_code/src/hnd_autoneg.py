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
import csv
import tempfile

import schema
import sysfs
from defs import *
from config import *
from util import *

__all__ = ['AutoNegParamHnd']

class AutoNegParamHnd(object):

    CMD_AUTONEG = {
        AutoNegotiate.AUTO_NEGOTIATE: "autoneg",
        AutoNegotiate.FORCE_TENG_FULL: "10gfull",
        AutoNegotiate.FORCE_ONEG_FULL: "1gfull",
        AutoNegotiate.FORCE_HUNDM_FULL: "100mfull",
    }

    def __init__(self):
        self.config = Config()
        self.log = logging.getLogger("autoneg")
        self.db = None

    def get_interf_caps(self, ifname):
        return [
            AutoNegotiate.AUTO_NEGOTIATE,
            AutoNegotiate.FORCE_TENG_FULL,
            AutoNegotiate.FORCE_ONEG_FULL,
            AutoNegotiate.FORCE_HUNDM_FULL
        ]

    def _save_db(self):

        try:
            dir = os.path.dirname(self.config.autoneg_db)
            tmpfd, tmpname = tempfile.mkstemp(dir=dir)
            with os.fdopen(tmpfd, 'w') as tmpf:
                db = csv.writer(tmpf)
                for ifname, mode in self.db.iteritems():
                    db.writerow([ifname, mode])
                del db
        except:
            self.log.exception("Exception while saving autoneg db")
            try:
                os.unlink(self.config.autoneg_db)
            except:
                pass

            try:
                os.unlink(tmpname)
            except:
                pass
        else:
            os.rename(tmpname, self.config.autoneg_db)

    def _load_db(self):
        try:
            newdb = {}

            with open(self.config.autoneg_db, 'r') as f:
                db = csv.reader(f)
                for row in db:
                    if len(row) != 2:
                        continue
                    ifname = row[0]
                    mode = row[1]
                    newdb[ifname] = mode

            self.db = newdb
        except IOError:
            self.log.debug("Failed to read autoneg database")
            self.db = {}
        except:
            self.log.exception("Exception while reading autoneg database")
            self.db = {}

    def _set_interf_mode(self, ifname, mode):
        if self.db is None:
            self._load_db()

        self.db[ifname] = mode
        self._save_db()

    def _get_interf_mode(self, ifname):
        if self.db is None:
            self._load_db()

        return self.db.get(ifname, self.CMD_AUTONEG[AutoNegotiate.AUTO_NEGOTIATE])

    def set_interf_mode(self, ifname, autoneg, force=False):
        mode = self.CMD_AUTONEG.get(autoneg)
        if mode is None:
            self.log.error("Trying to set unexpected autoneg for interface {}: {}".format(ifname, autoneg))
            return

        curmode = self._get_interf_mode(ifname)

        if force or mode != curmode:
            self.log.info("Changing autoneg for interface {}: {}".format(ifname, mode))
            self._setautoneg_exec([ifname, mode])
            # check exec status ???
            self._set_interf_mode(ifname, mode)

    def _exec(self, cmd, args):
        try:
            proc = subprocess.Popen([cmd] + args,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            close_fds=True)

            stdoutdata, stderrdata = proc.communicate()

            if proc.returncode != 0:
                self.log.error("{} returned an error code {}: '{}', '{}'".format(
                                cmd, proc.returncode, stdoutdata, stderrdata))
                return False

        except:
            self.log.exception("Exception while executing '{}' '{}''".format(cmd, args))
            return False

        return True

    def _setautoneg_exec(self, args):
        return self._exec(self.config.setautoneg_path, args)
