#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import sys
import os
sys.path.append('../src')
import subprocess
import logging
import unittest

from ip import *


def run(cmd, args=None, check=False):

    if args is None:
        args = []

    proc = subprocess.Popen([cmd] + args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setpgrp,  # start a new process group
                    close_fds=True)

    stdoutdata, stderrdata = proc.communicate()

    if check and proc.returncode != 0:
        raise Exception("exec error")

    return proc.returncode, stdoutdata, stderrdata


class Tests(unittest.TestCase):

    IF1 = "ntest1"
    IF2 = "ntest2"
    LinkLocal = EthernetIP("0.0.0.0")


    @classmethod
    def setUpClass(cls):
        if os.getuid() != 0:
            return

        run("/bin/sh", ['-c', """
            ip link add dev ntest1 type veth peer name ptest1;
            ip link add dev ntest2 type veth peer name ptest2;

            ip link set up dev ntest1;
            ip link set up dev ntest2;

            ip link set up dev ptest1;
            ip link set up dev ptest2;

            ip addr add 172.31.10.1/24 dev ntest1;
            ip addr add 172.31.20.1/24 dev ntest2;

        """])

        # MORE LOGGING
        #logging.basicConfig(format='%(message)s', level=logging.DEBUG)


    @classmethod
    def tearDownClass(cls):


        if os.getuid() != 0:
            return

        #return

        run("/bin/sh", ['-c', """
            ip route flush dev ntest1;
            ip route flush dev ntest2;

            ip link del dev ntest1;
            ip link del dev ntest2;
        """])

    def setUp(self):
        r = IPRoute(None)
        r.start()
        self.r = r


    def tearDown(self):
        self.r.shutdown()
        del self.r

    def get_routes(self):
        code, outdata, errdata = run("/bin/sh", ['-c',
            'ip route list proto {}'.format(IPRoute.PROTO)])
        return sorted([l.strip() for l in outdata.split("\n") if l.strip()])

    @unittest.skipIf(os.getuid() != 0, "need to be root to run this test")
    def test_routes_types(self):

        ifname = self.IF1
        r = self.r
        metric = 1000

        def R(p, gw):
            return IPRoute.Entry(p, gw, metric)

        def noroutes():
            rr = [ ]
            r.set_interface_routes(ifname, rr, metric)
            self.assertEqual(self.get_routes(), [])

        noroutes()

        # LinkLocal
        rr = [
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
        ]
        r.set_interface_routes(ifname, rr, metric)
        routes = self.get_routes()
        self.assertEquals(len(routes), 1)
        self.assertIn("11.55.2.0/24", routes[0])
        self.assertNotIn("via", routes[0])

        noroutes()

        # Default
        rr = [
            R(None, EthernetIP("172.31.10.252")),
        ]
        r.set_interface_routes(ifname, rr, metric)
        routes = self.get_routes()
        self.assertEquals(len(routes), 1)
        self.assertIn("default", routes[0])
        self.assertIn("via 172.31.10.252", routes[0])

        noroutes()

        # Unreachable
        rr = [
            R(EthernetIP("22.1.2.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)
        routes = self.get_routes()
        self.assertEquals(len(routes), 1)
        self.assertIn("unreachable 22.1.2.0/24", routes[0])

        noroutes()

        # Unicast
        rr = [
            R(EthernetIP("11.22.55.0/27"), EthernetIP("172.31.10.253")),
        ]
        r.set_interface_routes(ifname, rr, metric)
        routes = self.get_routes()
        self.assertEquals(len(routes), 1)
        self.assertIn("11.22.55.0/27", routes[0])
        self.assertIn("via 172.31.10.253", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        noroutes()

        return

    @unittest.skipIf(os.getuid() != 0, "need to be root to run this test")
    def test_multiple_routes(self):

        ifname = self.IF1
        r = self.r
        metric = 1000

        def R(p, gw):
            return IPRoute.Entry(p, gw, metric)

        def noroutes():
            rr = [ ]
            r.set_interface_routes(ifname, rr, metric)
            self.assertEqual(self.get_routes(), [])

        noroutes()

        rr = [
            R(EthernetIP("11.22.55.0/27"), EthernetIP("172.31.10.253")),
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.2.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        '''
            '11.22.55.0/27 via 172.31.10.253 dev ntest1  metric 1000',
            '11.55.2.0/24 dev ntest1  metric 1000',
            'default via 172.31.10.252 dev ntest1  metric 1000',
            'unreachable 22.1.2.0/24  metric 1000'
        '''
        self.assertEquals(len(routes), 4)

        self.assertIn("11.22.55.0/27", routes[0])
        self.assertIn("via 172.31.10.253", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        self.assertIn("11.55.2.0/24", routes[1])
        self.assertNotIn("via", routes[1])

        self.assertIn("default", routes[2])
        self.assertIn("via 172.31.10.252", routes[2])

        self.assertIn("unreachable 22.1.2.0/24", routes[3])

        # update one
        rr = [
            R(EthernetIP("11.22.66.0/27"), EthernetIP("172.31.10.253")),
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.2.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 4)

        self.assertIn("11.22.66.0/27", routes[0])
        self.assertIn("via 172.31.10.253", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        self.assertIn("11.55.2.0/24", routes[1])
        self.assertNotIn("via", routes[1])

        self.assertIn("default", routes[2])
        self.assertIn("via 172.31.10.252", routes[2])

        self.assertIn("unreachable 22.1.2.0/24", routes[3])

        # update one
        rr = [
            R(EthernetIP("11.22.66.0/27"), EthernetIP("172.31.10.252")),
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.2.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 4)

        self.assertIn("11.22.66.0/27", routes[0])
        self.assertIn("via 172.31.10.252", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        self.assertIn("11.55.2.0/24", routes[1])
        self.assertNotIn("via", routes[1])

        self.assertIn("default", routes[2])
        self.assertIn("via 172.31.10.252", routes[2])

        self.assertIn("unreachable 22.1.2.0/24", routes[3])

        # update one
        rr = [
            R(EthernetIP("11.22.77.0/27"), EthernetIP("172.31.10.250")),
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.2.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 4)

        self.assertIn("11.22.77.0/27", routes[0])
        self.assertIn("via 172.31.10.250", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        self.assertIn("11.55.2.0/24", routes[1])
        self.assertNotIn("via", routes[1])

        self.assertIn("default", routes[2])
        self.assertIn("via 172.31.10.252", routes[2])

        self.assertIn("unreachable 22.1.2.0/24", routes[3])

        # update one
        rr = [
            R(EthernetIP("11.22.77.0/27"), EthernetIP("172.31.10.250")),
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.3.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 4)

        self.assertIn("11.22.77.0/27", routes[0])
        self.assertIn("via 172.31.10.250", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        self.assertIn("11.55.2.0/24", routes[1])
        self.assertNotIn("via", routes[1])

        self.assertIn("default", routes[2])
        self.assertIn("via 172.31.10.252", routes[2])

        self.assertIn("unreachable 22.1.3.0/24", routes[3])

        # remove one
        rr = [
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.2.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 3)

        self.assertIn("11.55.2.0/24", routes[0])
        self.assertNotIn("via", routes[0])

        self.assertIn("default", routes[1])
        self.assertIn("via 172.31.10.252", routes[1])

        self.assertIn("unreachable 22.1.2.0/24", routes[2])

        # remove one
        rr = [
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(EthernetIP("22.1.2.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 2)

        self.assertIn("11.55.2.0/24", routes[0])
        self.assertNotIn("via", routes[0])

        self.assertIn("unreachable 22.1.2.0/24", routes[1])

        # add two
        rr = [
            R(EthernetIP("11.22.77.0/27"), EthernetIP("172.31.10.250")),
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.3.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 4)

        self.assertIn("11.22.77.0/27", routes[0])
        self.assertIn("via 172.31.10.250", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        self.assertIn("11.55.2.0/24", routes[1])
        self.assertNotIn("via", routes[1])

        self.assertIn("default", routes[2])
        self.assertIn("via 172.31.10.252", routes[2])

        self.assertIn("unreachable 22.1.3.0/24", routes[3])

        # update two
        rr = [
            R(EthernetIP("11.22.88.0/27"), EthernetIP("172.31.10.251")),
            R(EthernetIP("11.55.3.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.3.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 4)

        self.assertIn("11.22.88.0/27", routes[0])
        self.assertIn("via 172.31.10.251", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        self.assertIn("11.55.3.0/24", routes[1])
        self.assertNotIn("via", routes[1])

        self.assertIn("default", routes[2])
        self.assertIn("via 172.31.10.252", routes[2])

        self.assertIn("unreachable 22.1.3.0/24", routes[3])

        # two three
        rr = [
            R(EthernetIP("11.22.77.0/27"), EthernetIP("172.31.10.250")),
            R(EthernetIP("11.33.77.0/27"), EthernetIP("172.31.10.253")),
            R(EthernetIP("11.55.2.0/24"), self.LinkLocal),
            R(EthernetIP("11.66.2.0/24"), self.LinkLocal),
            R(None, EthernetIP("172.31.10.252")),
            R(EthernetIP("22.1.3.0/24"), RouteUnreachable),
            R(EthernetIP("22.2.3.0/24"), RouteUnreachable),
        ]
        r.set_interface_routes(ifname, rr, metric)

        routes = self.get_routes()
        self.assertEquals(len(routes), 7)

        self.assertIn("11.22.77.0/27", routes[0])
        self.assertIn("via 172.31.10.250", routes[0])
        self.assertIn("dev {}".format(ifname), routes[0])

        self.assertIn("11.33.77.0/27", routes[1])
        self.assertIn("via 172.31.10.253", routes[1])
        self.assertIn("dev {}".format(ifname), routes[1])

        self.assertIn("11.55.2.0/24", routes[2])
        self.assertNotIn("via", routes[2])

        self.assertIn("11.66.2.0/24", routes[3])
        self.assertNotIn("via", routes[3])

        self.assertIn("default", routes[4])
        self.assertIn("via 172.31.10.252", routes[4])

        self.assertIn("unreachable 22.1.3.0/24", routes[5])

        self.assertIn("unreachable 22.2.3.0/24", routes[6])

        noroutes()

if __name__ == '__main__':
    unittest.main()
