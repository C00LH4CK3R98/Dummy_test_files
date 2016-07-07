#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function

import sys
import os
import logging
import socket
import struct
import threading
import subprocess
import signal
import traceback

from defs import *

# metaclass-based singleton implementation
class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


# decorator to log uncaught exceptions
def log_exception(func):
    def f(*a, **kw):
        try:
            return func(*a, **kw)
        except:
            logging.getLogger("oops").exception("uncaught exception")
            raise

    f.__name__ = func.__name__
    return f


def ip_prefix_len_to_mask(plen, family=socket.AF_INET):
    if ((plen < 0) or
            (family==socket.AF_INET and plen > 32) or
            (family==socket.AF_INET6 and plen > 128) or
            (family not in [socket.AF_INET, socket.AF_INET6])):
        raise Exception("invalid arguments")

    if family==socket.AF_INET:
        bits = 32
    elif family==socket.AF_INET6:
        bits = 128

    binmask = ((1 << plen) - 1) << (bits - plen)
    return long_to_ip(binmask, family)


def long_to_ip(n, family=socket.AF_INET):

    if family==socket.AF_INET:
        fmt = "!I"
        cnv = lambda x: [x]
    elif family==socket.AF_INET6:
        fmt = "!IIII"
        cnv = lambda x: [(x >> (128-32*(shf+1))) & 0xffffffff for shf in range(4)]

    data = struct.pack(fmt, *cnv(n))

    return socket.inet_ntop(family, data)


def ip_mask_to_prefix_len(mask):
    try:
        binary = socket.inet_pton(socket.AF_INET, mask)
        nums = struct.unpack("!I", binary)
    except socket.error:
        binary = socket.inet_pton(socket.AF_INET6, mask)
        nums = struct.unpack("!IIII", binary)

    plen = 32*len(nums)
    for n in range(plen):
        if nums[n / 32] & (1 << (31 - n % 32)) == 0:
            plen = n
            break

    return plen


def ip_to_long(ip, family=socket.AF_INET):
    if family==socket.AF_INET:
        fmt = "!I"
    elif family==socket.AF_INET6:
        fmt = "!IIII"

    binary = socket.inet_pton(family, ip)
    nums = struct.unpack(fmt, binary)

    res = long(0)
    for n in nums:
        res = (res << 32) + n
    return res


def get_teamed_config(mode, ifs, delay_up=None):

    if delay_up is None:
        delay_up = 0

    res = {}
    prio = 0
    for interf in reversed(ifs):
        res[interf] = {"prio": prio}
        # 2 is a minimum required priority step
        prio += 10
        res[interf]["link_watch"] = {
            "name": "ethtool",
            "delay_up": delay_up,
            "delay_down": 0,
        }

    if mode == TeamModes.AUTOMATIC or mode == RedundancyMode.AUTOMATIC:
        for val in res.values():
            val["sticky"] = True
    elif mode == TeamModes.AUTOMATIC_REVERT or mode == RedundancyMode.AUTOMATIC_REVERT:
        res[ifs[0]]["sticky"] = True
    elif mode == TeamModes.MANUAL or mode == RedundancyMode.MANUAL_NOFAILOVER:
        for val in res.values():
            val["sticky"] = True
            val["final"] = True
    elif mode == TeamModes.MANUAL_REVERT or mode == RedundancyMode.MANUAL:
        for val in res.values():
            val["sticky"] = True
            val["final"] = True
        del res[ifs[0]]["final"] # clear for first interface
    elif mode == TeamModes.SINGLE:
        pass
    else:
        raise Exception("bad mode")

    return res


def find_primary_selected(master, ports, func_pname):

    new_active = None

    # find new primary and selected
    for port in ports:
        if port.select_port:
            new_active = port

    portnames = [func_pname(p) for p in ports]
    primary_name = func_pname(master)

    # move "primary" port first
    portnames.remove(primary_name)
    portnames.insert(0, primary_name)

    return portnames, new_active


def exec_checkcode(cmd, args=None, log=None, timeout=None, fstdout=None, fstderr=None):

    if args is None:
        args = []

    try:
        proc = subprocess.Popen([cmd] + args,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        preexec_fn=os.setpgrp,  # start a new process group
                        close_fds=True)

        if timeout is not None:
            def kill_proc(p):
                if p.pid > 1:                           # avoid pids 0 and 1
                    os.kill(-p.pid, signal.SIGKILL)     # send to a process group

            timer = threading.Timer(timeout, kill_proc, [proc])
            timer.start()

        stdoutdata, stderrdata = proc.communicate()

        if timeout is not None:
            timer.cancel()

        if fstdout is not None:
            fstdout.write(stdoutdata)

        if fstderr is not None:
            fstderr.write(stderrdata)

        if proc.returncode != 0:
            msg = "{} returned an error code {}: '{}', '{}'".format(
                            cmd, proc.returncode, stdoutdata, stderrdata)
            if log:
                log.error(msg)
            else:
                print(msg, file=sys.stderr)
            return False

    except:
        msg = "Exception while executing '{}' '{}''".format(cmd, args)
        if log is not None:
            log.exception(msg)
        else:
            print(msg, file=sys.stderr)
            traceback.print_exc()
        return False

    return True


def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def net_info_group_by_redundancy(net_info):
    # Prepare interface logical groups like this:
    # groups = {
    #   1: [1,2]
    #   2: [1,2]
    #   3: [3,4]
    #   4: [3,4]
    #   5: [5]
    #   6: [6]
    # }
    # and groups[1] == groups[2] (points to the same object).
    #
    # Primary Master interfaces are put first in a lists.
    #
    groups = {}
    for iid, info in net_info.iteritems():
        iid = str(iid)

        found = False
        for tm in info.teammembers:
            tm = str(tm)
            if tm in groups:
                found = True
                if info.primary_port:
                    groups[tm].insert(0, info)
                else:
                    groups[tm].append(info)
                groups[iid] = groups[tm]
                break

        if not found:
            groups[iid] = [info]

    return groups
