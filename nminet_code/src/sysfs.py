#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import time
import threading
import socket
import logging
import re
import os

from util import *

#__all__ = []

class SysFSHelper(object):

    @classmethod
    def init(klass):
        klass.log = logging.getLogger("sysfs")

    RE_PCIID = re.compile(r'.*([0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]\.[0-9a-f]+)', flags=re.IGNORECASE)

    @classmethod
    def get_net_interface_pci_id(klass, interf):
        try:
            link = os.readlink("/sys/class/net/{}/device".format(interf))
            m = klass.RE_PCIID.match(link)
            if m:
                return m.group(1)
            return "unknown"
        except OSError:
            # link not found
            return ""

    @classmethod
    def get_net_interface_param(klass, interf, param):
        try:
            with open("/sys/class/net/{}/{}".format(interf, param), "r") as f:
                s = f.read()

                if param == "speed":
                    try:
                        speed = int(s.strip())
                        if speed < 0 or speed > 1000000: # 1Pbps
                            speed = 0
                        return speed
                    except ValueError:
                        return 0

                return s
        except:
            klass.log.exception("Exception while getting interface '{}' parameter '{}'".format(interf, param))

    @classmethod
    def set_net_bridge_params(klass, interf, params, silent_errors):
        for k, v in params:
            try:
                with open("/sys/class/net/{}/bridge/{}".format(interf, k), "w") as f:
                    f.write(v)
            except Exception, e:
                #klass.log.exception("Exception while setting bridge '{}' parameter '{}' to '{}'".format(interf, k, v))
                if not silent_errors:
                    klass.log.warning("Error while setting bridge '{}' parameter '{}' to '{}': {}".format(interf, k, v, e))

    @classmethod
    def disable_interface_ipv6(klass, interf):
        v = "1"

        for k in ["disable_ipv6"]:
            try:
                with open("/proc/sys/net/ipv6/conf/{}/{}".format(interf, k), "w") as f:
                    f.write(v)
            except Exception, e:
                klass.log.warning("Error while setting procfs '{}' ipv6 parameter '{}' to '{}': {}".format(interf, k, v, e))

helper = SysFSHelper
