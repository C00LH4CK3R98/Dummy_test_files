#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import xmlrpclib
import os
import sys
import time
import threading
import argparse
import socket
import logging
import Queue
queue = Queue # python 3
from enum import Enum
from monotonic import monotonic

import SocketServer
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler

from util import *
from message import *

__all__ = ['XMLRPCThread']

PERFMON = True

if PERFMON:
    def perfstat(func):
        log = logging.getLogger("perf")

        def f(*a, **kw):
            tstart = monotonic()
            try:
                return func(*a, **kw)
            finally:
                tend = monotonic()
                log.debug("XML-RPC Call '{}': {:.3f}s".format(func.__name__, tend-tstart))
        f.__name__ = func.__name__
        return f
else:
    def perfstat(func):
        return func


class XmlRpcHandlersBase(object):
    pass


class ResCode(Enum):
    OK_NODATA = 0
    OK = 1

    UNKNOWN_ERROR = -1
    NOT_SUPPORTED = -2
    BAD_ARGUMENTS = -3


class NMIInterface(XmlRpcHandlersBase):

    NET_INFO_CACHE_TTL = 1.0    # sec

    def __init__(self, inqueue):
        super(NMIInterface, self).__init__()
        self.queue = inqueue
        self.log = logging.getLogger("xmlrpcnmi")

        self.net_info_cached = None
        self.net_info_timestamp = 0
        self.net_info_lock = threading.Lock()

    def gen_result(self, code, data=None):

        if data is None and code == ResCode.OK:
            code = ResCode.OK_NODATA
        elif data is not None and code == ResCode.OK_NODATA:
            raise Exception("result should not have data")

        res = {
            'CODE': code.value,
        }

        if code == ResCode.OK:
            res['DATA'] = data
        elif data is not None and code != ResCode.OK_NODATA:
            # errors
            res['ERROR'] = data

        return res

    def update_cached_net_info(self, data):
        now = monotonic()
        with self.net_info_lock:
            self.net_info_cached = data
            self.net_info_timestamp = now

    def get_cached_net_info(self):
        now = monotonic()
        with self.net_info_lock:
            if self.net_info_cached and (now - self.net_info_timestamp <= self.NET_INFO_CACHE_TTL):
                return self.net_info_cached
        return None

    @perfstat
    @log_exception
    def revertToPrimaryInterfaces(self, data=None):

        try:
            res = MessageXMLRPCRequest(self.queue, MessageXMLRPCRequest.REQ_REVERT_TO_PRIMARY, data=data).request().wait_reply()
        except Exception, e:
            self.log.exception("Exception while processing revertToPrimaryInterfaces call")
            return self.gen_result(ResCode.UNKNOWN_ERROR, str(e))

        return self.gen_result(ResCode.OK, res)

    @perfstat
    @log_exception
    def setManagementIP(self, data=None):

        if not data or not isinstance(data, dict):
            return self.gen_result(ResCode.BAD_ARGUMENTS)

        try:
            res = MessageXMLRPCRequest(self.queue, MessageXMLRPCRequest.REQ_SET_MNG_IP, data=data).request().wait_reply()
        except Exception, e:
            self.log.exception("Exception while processing setManagementIP call")
            return self.gen_result(ResCode.UNKNOWN_ERROR, str(e))

        return self.gen_result(ResCode.OK, res)

    @perfstat
    @log_exception
    def DHCPClientCallback(self, data=None):

        if not data or not isinstance(data, dict):
            return self.gen_result(ResCode.BAD_ARGUMENTS)

        try:
            res = MessageXMLRPCRequest(self.queue, MessageXMLRPCRequest.REQ_DHCP_CALLBACK, data=data).request().wait_reply()
        except Exception, e:
            self.log.exception("Exception while processing DHCPClientCallback call")
            return self.gen_result(ResCode.UNKNOWN_ERROR, str(e))

        return self.gen_result(ResCode.OK, res)

    @perfstat
    @log_exception
    def setInstance(self, objname=None, xmlstring=None):

        if objname != "PlatformNetworkModel":
            return self.gen_result(ResCode.BAD_ARGUMENTS)

        try:
            MessageXMLRPCRequest(self.queue, MessageXMLRPCRequest.REQ_SET_NETWORK_SETTINGS, data=xmlstring).request().wait_reply()
        except Exception, e:
            self.log.exception("Exception while processing setInstance call")
            return self.gen_result(ResCode.UNKNOWN_ERROR, str(e))

        return self.gen_result(ResCode.OK)

    @perfstat
    @log_exception
    def getInstance(self, objname=None):

        if objname != "PlatformNetworkModel_PART":
            return self.gen_result(ResCode.BAD_ARGUMENTS)

        try:
            proc = MessageXMLRPCRequest(self.queue, MessageXMLRPCRequest.REQ_GET_NETWORK_SETTINGS).request().wait_reply()
        except Exception, e:
            self.log.exception("Exception while processing getInstance call")
            return self.gen_result(ResCode.UNKNOWN_ERROR, str(e))

        return self.gen_result(ResCode.OK, proc)

    @perfstat
    @log_exception
    def getNetworkInterfaceInfo(self, iid=None, serial=None):

        try:
            cached = self.get_cached_net_info()
            if cached:
                self.log.debug("getNetworkInterfaceInfo cache hit")
                data = cached
            else:
                data = MessageXMLRPCRequest(self.queue, MessageXMLRPCRequest.REQ_GET_NETWORK_INFO).request().wait_reply()
        except Exception, e:
            self.log.exception("Exception while processing getNetworkInterfaceInfo call")
            return self.gen_result(ResCode.UNKNOWN_ERROR, str(e))

        return self.gen_result(ResCode.OK, data)

    @perfstat
    @log_exception
    def updateRoutes(self, params={}):
        oper = params.get("oper")
        origin = params.get("origin")
        routes = params.get("routes")
        flush_iids = params.get("flush_iids")

        if origin is None:
            return self.gen_result(ResCode.BAD_ARGUMENTS)

        if oper == 'add' and routes:
            req_id = MessageXMLRPCRequest.REQ_ROUTES_UPDATE
            data = {
                'oper': "add",
                'routes': routes
            }
        elif oper == 'del' and routes is not None:
            req_id = MessageXMLRPCRequest.REQ_ROUTES_UPDATE
            data = {
                'oper': "remove",
                'routes': routes
            }
        elif oper == 'setall' and routes is not None:
            req_id = MessageXMLRPCRequest.REQ_ROUTES_UPDATE
            data = {
                'oper': "set",
                'routes': routes
            }
        elif oper == 'flush':
            req_id = MessageXMLRPCRequest.REQ_ROUTES_FLUSH
            data = {'iids': flush_iids}
        else:
            return self.gen_result(ResCode.BAD_ARGUMENTS)

        data['origin'] = origin

        try:
            data = MessageXMLRPCRequest(self.queue, req_id, data=data).request().wait_reply()
        except Exception, e:
            self.log.exception("Exception while processing updateRoutes call")
            return self.gen_result(ResCode.UNKNOWN_ERROR, str(e))

        return self.gen_result(ResCode.OK, data)

    @perfstat
    @log_exception
    def listRoutes(self, origin=None, filter_iid=None):

        if origin is None:
            return self.gen_result(ResCode.BAD_ARGUMENTS)

        data = {'origin': origin, 'iids': filter_iid}

        try:
            data = MessageXMLRPCRequest(self.queue, MessageXMLRPCRequest.REQ_ROUTES_LIST, data=data).request().wait_reply()
        except Exception, e:
            self.log.exception("Exception while processing updateRoutes call")
            return self.gen_result(ResCode.UNKNOWN_ERROR, str(e))

        return self.gen_result(ResCode.OK, data)


class RequestHandler(SimpleXMLRPCRequestHandler):
    #rpc_paths = ('/', '/RPC2',)
    encode_threshold = None # disable gzip


class XMLRPCServer(SocketServer.ThreadingMixIn, SimpleXMLRPCServer):

    def __init__(self, addr=None):
        SimpleXMLRPCServer.__init__(self, addr, requestHandler=RequestHandler, logRequests=False)


class XMLRPCThread(threading.Thread):

    def __init__(self, rqqueue):
        super(XMLRPCThread, self).__init__()
        self.queue = rqqueue
        self.server = None
        self.nmi_interface = None

    def run(self):

        self.server = XMLRPCServer(('127.0.0.1', 8910))
        #self.server = XMLRPCServer(('0.0.0.0', 8910))

        self.nmi_interface = NMIInterface(self.queue)
        self.server.register_instance(self.nmi_interface)

        self.server.serve_forever()

    def update_cached_net_info(self, data):
        self.nmi_interface.update_cached_net_info(data)

    def shutdown(self):
        if self.server:
            self.server.shutdown()
