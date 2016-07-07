#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import sys
sys.path.append('../src')
import unittest
from cksum import *


class Tests(unittest.TestCase):

    def test_1(self):
        self.assertEqual(cksum("test"), 3076352578)

    def test_2(self):
        self.assertEqual(cksum("A"*1048576), 2683235781)

    def test_3(self):
        self.assertEqual(cksum(""), 4294967295)

if __name__ == '__main__':
    unittest.main()
