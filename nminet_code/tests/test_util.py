#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import sys
sys.path.append('../src')
import unittest

import logging
import socket
import struct
import time
import cStringIO

from util import *


class Tests(unittest.TestCase):

    def test_singleton(self):
        class A(object):
            __metaclass__ = Singleton
            def __init__(self):
                self.a = 1

        a1 = A()
        a2 = A()
        a3 = A()


        a2.a = 2

        self.assertEqual(a1.a, 2)

        self.assertEqual(a1, a2)
        self.assertEqual(a2, a3)

    def test_ip_mask_to_prefix_len(self):
        self.assertEqual(ip_mask_to_prefix_len("0.0.0.0"), 0)
        self.assertEqual(ip_mask_to_prefix_len("240.0.0.0"), 4)
        self.assertEqual(ip_mask_to_prefix_len("255.0.0.0"), 8)
        self.assertEqual(ip_mask_to_prefix_len("255.255.255.0"), 24)
        self.assertEqual(ip_mask_to_prefix_len("255.255.255.255"), 32)

        self.assertEqual(ip_mask_to_prefix_len("::"), 0)
        self.assertEqual(ip_mask_to_prefix_len("ffff::"), 16)
        self.assertEqual(ip_mask_to_prefix_len("ffff:ffff::"), 32)
        self.assertEqual(ip_mask_to_prefix_len("ffff:ffff:ff00::"), 40)
        self.assertEqual(ip_mask_to_prefix_len("ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"), 128)

    def test_ip_prefix_len_to_mask(self):
        self.assertEqual(ip_prefix_len_to_mask(0), "0.0.0.0")
        self.assertEqual(ip_prefix_len_to_mask(4), "240.0.0.0")
        self.assertEqual(ip_prefix_len_to_mask(16), "255.255.0.0")
        self.assertEqual(ip_prefix_len_to_mask(32), "255.255.255.255")

        self.assertEqual(ip_prefix_len_to_mask(0, socket.AF_INET6), "::")
        self.assertEqual(ip_prefix_len_to_mask(16, socket.AF_INET6), "ffff::")
        self.assertEqual(ip_prefix_len_to_mask(40, socket.AF_INET6), "ffff:ffff:ff00::")
        self.assertEqual(ip_prefix_len_to_mask(64, socket.AF_INET6), "ffff:ffff:ffff:ffff::")
        self.assertEqual(ip_prefix_len_to_mask(128, socket.AF_INET6), "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff")

    def test_ip_to_long(self):
        self.assertEqual(ip_to_long('0.0.0.255'), 0xff)
        self.assertEqual(ip_to_long('0.0.255.255'), 0xffff)
        self.assertEqual(ip_to_long('128.0.0.0'), 0x80000000)

        self.assertEqual(ip_to_long('::ff', socket.AF_INET6), 0xff)
        self.assertEqual(ip_to_long('fe80::', socket.AF_INET6), 0xfe800000000000000000000000000000)
        self.assertEqual(ip_to_long('80:1::', socket.AF_INET6), 0x00800001000000000000000000000000)

    def test_long_to_ip(self):
        self.assertEqual(long_to_ip(0xff), '0.0.0.255')
        self.assertEqual(long_to_ip(0xffff), '0.0.255.255')
        self.assertEqual(long_to_ip(0x80000000), '128.0.0.0')

        self.assertEqual(long_to_ip(0xff, socket.AF_INET6), '::ff')
        self.assertEqual(long_to_ip(0xfe800000000000000000000000000000, socket.AF_INET6), 'fe80::')
        self.assertEqual(long_to_ip(0x00800001000000000000000000000000, socket.AF_INET6), '80:1::')

    def test_portmodes(self):


        def lw(x, du=0):
            for item in x.itervalues():
                item['link_watch'] = {'delay_down': 0, 'delay_up': du, 'name': 'ethtool'}
            return x


        # SINGLE
        c = get_teamed_config(TeamModes.SINGLE, ['eth0'])
        self.assertEqual(c, lw({'eth0': {'prio':0}}))

        # AUTOMATIC
        for mode in [TeamModes.AUTOMATIC, RedundancyMode.AUTOMATIC]:
            c = get_teamed_config(mode, ['eth0','eth1'])
            self.assertEqual(c, lw({'eth0': {'prio':10,'sticky':True},'eth1': {'prio':0,'sticky':True}}))
            c = get_teamed_config(mode, ['eth0','eth1','eth2'])
            self.assertEqual(c, lw({'eth0': {'prio':20,'sticky':True},'eth1': {'prio':10,'sticky':True},'eth2': {'prio':0,'sticky':True}}))

        # AUTOMATIC_REVERT
        for mode in [TeamModes.AUTOMATIC_REVERT, RedundancyMode.AUTOMATIC_REVERT]:
            c = get_teamed_config(mode, ['eth0','eth1'])
            self.assertEqual(c, lw({'eth0': {'prio':10,'sticky':True},'eth1': {'prio':0}}))
            c = get_teamed_config(mode, ['eth1','eth0'])
            self.assertEqual(c, lw({'eth0': {'prio':0},'eth1': {'prio':10,'sticky':True}}))

        # MANUAL
        for mode in [TeamModes.MANUAL, RedundancyMode.MANUAL_NOFAILOVER]:
            c = get_teamed_config(mode, ['eth0','eth1'])
            self.assertEqual(c, lw({'eth0': {'prio':10,'sticky':True,'final':True},'eth1': {'prio':0,'sticky':True,'final':True}}))

        # MANUAL_REVERT
        for mode in [TeamModes.MANUAL_REVERT, RedundancyMode.MANUAL]:
            c = get_teamed_config(mode, ['eth0','eth1'])
            self.assertEqual(c, lw({'eth0': {'prio':10,'sticky':True},'eth1': {'prio':0,'sticky':True,'final':True}}))
            c = get_teamed_config(mode, ['eth1','eth0'])
            self.assertEqual(c, lw({'eth1': {'prio':10,'sticky':True},'eth0': {'prio':0,'sticky':True,'final':True}}))

        # DELAYED, AUTOMATIC
        for mode in [TeamModes.AUTOMATIC, RedundancyMode.AUTOMATIC]:
            c = get_teamed_config(mode, ['eth0','eth1'], delay_up=10)
            self.assertEqual(c, lw({'eth0': {'prio':10,'sticky':True},'eth1': {'prio':0,'sticky':True}}, du=10))

        # DUAL
        with self.assertRaises(Exception):
            c = get_teamed_config(TeamModes.DUAL, ['eth0','eth1'])

        # other
        with self.assertRaises(Exception):
            c = get_teamed_config("whatever", ['eth0','eth1'])

    def test_find_primary_selected(self):
        class P(object):
            def __init__(self, n, p, s):
                self.n = n
                self.manual_primary = p
                self.select_port = s

        ports = [
            P(1, False, False),
            P(2, False, False),
            P(3, False, False),
            P(4, False, False),
        ]
        res = find_primary_selected(ports[-1], ports, lambda p: p.n)
        self.assertEqual(res, ([4, 1, 2, 3], None))

        ports = [
            P(1, False, False),
            P(2, False, False),
            P(3, True, False),
            P(4, False, False),
        ]
        res = find_primary_selected(ports[-1], ports, lambda p: p.n)
        self.assertEqual(res, ([4, 1, 2, 3], None))

        ports = [
            P(1, False, False),
            P(2, False, True),
            P(3, True, False),
            P(4, False, False),
        ]
        res = find_primary_selected(ports[-1], ports, lambda p: p.n)
        self.assertEqual(res, ([4, 1, 2, 3], ports[1]))

    def test_exec_checkcode(self):

        # def exec_getcode(self, cmd, args, log=None, timeout=None):

        self.assertTrue(exec_checkcode("/bin/true"))
        self.assertFalse(exec_checkcode("/bin/false"))

        t1 = time.time()
        self.assertTrue(exec_checkcode("/bin/sh", ['-c', 'sleep 1']))
        t2 = time.time()

        self.assertLess(1, t2-t1)

        t1 = time.time()
        self.assertTrue(exec_checkcode("/bin/sh", ['-c', 'sleep 1'], timeout=2))
        t2 = time.time()

        self.assertLess(t2-t1, 2)

        t1 = time.time()
        self.assertFalse(exec_checkcode("/bin/sh", ['-c', 'sleep 5'], timeout=2))
        t2 = time.time()

        self.assertLess(t2-t1, 3)

    def test_exec_checkcode_io(self):

        out = cStringIO.StringIO()
        err = cStringIO.StringIO()
        self.assertTrue(exec_checkcode("/bin/sh", ['-c', 'echo "test123-321 zzz"'], fstdout=out, fstderr=err))
        self.assertEqual(out.getvalue(),"test123-321 zzz\n")
        self.assertEqual(err.getvalue(),"")

        out = cStringIO.StringIO()
        err = cStringIO.StringIO()
        self.assertTrue(exec_checkcode("/bin/sh", ['-c', 'echo "test1233211111" >&2'], fstdout=out, fstderr=err))
        self.assertEqual(out.getvalue(),"")
        self.assertEqual(err.getvalue(),"test1233211111\n")

        out = cStringIO.StringIO()
        err = cStringIO.StringIO()
        self.assertTrue(exec_checkcode("/bin/sh", ['-c', 'echo -n "err" >&2 ; echo -n out'], fstdout=out, fstderr=err))
        self.assertEqual(out.getvalue(),"out")
        self.assertEqual(err.getvalue(),"err")

        out = cStringIO.StringIO()
        self.assertTrue(exec_checkcode("/bin/sh", ['-c', 'echo -n "err2" >&2 ; echo -n out2'], fstdout=out))
        self.assertEqual(out.getvalue(),"out2")


    def test_net_info_group_by_redundancy(self):

        class _IfItem(object):
            def __init__(self, teammembers, is_primary_port):
                self.teammembers = teammembers
                self.primary_port = is_primary_port

        net_info = {
            1: _IfItem([2], True),
            2: _IfItem([1], False),
            3: _IfItem([4], True),
            4: _IfItem([3], False),
            5: _IfItem([], True),
            6: _IfItem([], False),
        }

        grp = net_info_group_by_redundancy(net_info)

        self.assertEqual(grp, {
                "1": [net_info[1], net_info[2]],
                "2": [net_info[1], net_info[2]],
                "3": [net_info[3], net_info[4]],
                "4": [net_info[3], net_info[4]],
                "5": [net_info[5]],
                "6": [net_info[6]],
            })

        self.assertIs(grp["1"], grp["2"])
        self.assertIs(grp["3"], grp["4"])
        self.assertIsNot(grp["5"], grp["6"])

if __name__ == '__main__':
    unittest.main()
