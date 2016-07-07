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
import Queue
queue = Queue # python 3

from util import *

#__all__ = []

class MessageBase(object):
    REQ_NOOP = -1

    def __init__(self, reqqueue=None, reqtype=REQ_NOOP, data=None):
        self._data = data
        self._request_type = reqtype
        self._request_queue = reqqueue
        self._reply_queue = queue.Queue()
        self._fail = False
        self._have_reply = False

    @property
    def data(self):
        return self._data

    @property
    def rtype(self):
        return self._request_type

    def request(self, **kw):
        if 'data' in kw:
            self._data = kw['data']

        queue = self._request_queue
        if 'queue' in kw:
            queue = kw['queue']

        queue.put(self)
        return self

    def reply(self, data):
        self._reply_queue.put(data)
        self._have_reply = True
        return self

    def is_failed(self):
        return self._fail

    def failure(self, data=None):
        self._fail = True
        if not self._have_reply:
            self._reply_queue.put(data)
        return self

    def wait_reply(self, block=True, timeout=None):
        rdata = self._reply_queue.get(block=block, timeout=timeout)
        if self.is_failed():
            raise Exception("IPC Failed: {}".format(rdata))
        return rdata


class Message(MessageBase):
    pass

class MessageStop(MessageBase):
    pass

class MessageXMLRPCRequest(MessageBase):
    REQ_SET_NETWORK_SETTINGS = 1        # NMI setInstance
    REQ_GET_NETWORK_SETTINGS = 2        # NMI getInstance
    REQ_GET_NETWORK_INFO = 3            # NMI NetworkInterface.enumerate
    REQ_SET_MNG_IP = 4                  # Command line helper tool 'configip'
    REQ_REVERT_TO_PRIMARY = 5           # Revert interfaces with redundancy to primary
    REQ_DHCP_CALLBACK = 6               # Callback data from DHCP client
    REQ_BOOTP_FINISHED = 7              # BOOTP execution result callback
    REQ_ROUTES_LIST = 8                 # List Routes
    REQ_ROUTES_UPDATE = 9               # Add/del/set routes
    REQ_ROUTES_FLUSH = 10               # Flush routes

class MessageTeamNewState(MessageBase):
    pass

class MessageSuspectInterfaceFail(MessageBase):
    REPORT = 1                          # Problem detected
    INTERF_DONE = 2                     # Finished executing workaround on interface
    DONE = 3                            # Finished

class MessageUpdateAlarms(MessageBase):
    pass

class MessageNewConfiguration(MessageBase):
    pass

class MessageRevertInterface(MessageBase):
    pass
