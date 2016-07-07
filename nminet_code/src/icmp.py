#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import socket
import struct
import random
import time

__all__ = [ "ping" ]

IPPROTO_ICMP = 1
ICMP_ECHO_REQUEST = 8


def ip_checksum(msg):
    s = 0
    for i in range(0, len(msg) & ~1, 2):
        s = s + (msg[i] + (msg[i+1] << 8))
        s = (s & 0xffff) + (s >> 16)

    if len(msg) & 1:
        s = s + msg[-1]
        s = (s & 0xffff) + (s >> 16)

    return ~s & 0xffff

def echo_packet(eid, seq):

    header = [
        ICMP_ECHO_REQUEST,
        0,
        0, 0,
        (eid >> 8) & 0xff, eid & 0xff,
        (seq >> 8) & 0xff, seq & 0xff,
    ]

    packet = header + [(c & 0xff) for c in xrange(ord('0'), ord('0')+56)]

    cs = ip_checksum(packet)

    packet[2] = cs & 0xff
    packet[3] = (cs >> 8) & 0xff

    return "".join([chr(c) for c in packet])

def ping(ipaddr, cnt, wait=1.0):

    eid = random.randint(0, 0xffff)

    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, IPPROTO_ICMP)

    try:
        for i in xrange(cnt):
            data = echo_packet(eid, i + 1)
            s.sendto(data, (ipaddr, 1))
            time.sleep(wait)
    finally:
        s.close()

if __name__ == "__main__":
    import sys
    ping(sys.argv[1], int(sys.argv[2]))

