#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import sys
sys.path.append('../src')
import unittest

import os
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

from defs import *
from hnd_ethtune import HWTune, HWInterface, EthtoolException


class Tests(unittest.TestCase):

    def test_nointerf(self):
        with self.assertRaises(EthtoolException):
            HWInterface("xxx42")

        hw = HWInterface("eth0")
        self.assertIsNotNone(hw.driver)
        self.assertNotEqual(hw.driver, "")

        self.assertIsNotNone(hw.version)
        self.assertNotEqual(hw.version, "")

    def test_tune1(self):

        class myHWInterface(object):
            def __init__(self, ifname, dr, ver):
                self.ifname = ifname
                self.driver = dr
                self.version = ver
                self.out = ""

            def ethtool(self, cmd):
                self.out += " ".join(cmd)

        hw = myHWInterface("eth1", "vmxnet3", "1.0")
        HWTune(hw).tune()
        self.assertEqual(hw.out, '-G {dev} rx 4096')

        hw = myHWInterface("eth3", "unknown!!!123", "1.0")
        HWTune(hw).tune()
        self.assertEqual(hw.out, '')

if __name__ == '__main__':
    unittest.main()
