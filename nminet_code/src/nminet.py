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
import traceback
import argparse
import socket
import logging
import signal
import Queue
import errno
queue = Queue   # python 3
from enum import Enum
import json
from copy import deepcopy

import schema
import sysfs
import icmp
from config import *
from xmlrpc import *
from ip import *
from teaming import *
from netmng import *
from alarm import *
from perfstat import *
from hnd_bootp import *
from hnd_ethtune import *
from hnd_revert import *
from util import exec_checkcode
from monotonic import monotonic


def xmlrpc_handler(req_type, disable_on_bootp=False):
    def decor(func):
        func.xmlrpc_req_type = req_type
        func.disable_on_bootp = disable_on_bootp
        return func

    return decor


class XmlrpcHandlers(object):
    def __init__(self):
        self.xmlrpc_handlers = None
        self.current_xml_config = None
        self.init_xmlrpc_handlers()

    def init_xmlrpc_handlers(self):
        hnd = {}
        for n in dir(self):
            if n.startswith("_"):
                continue
            member = getattr(self, n)
            if callable(member) and hasattr(member, 'xmlrpc_req_type'):
                hnd[member.xmlrpc_req_type] = member
        self.xmlrpc_handlers = hnd

    def handle_xmlrpc(self, msg):

        if msg.rtype not in self.xmlrpc_handlers:
            msg = "Internal error, unexpected message type"
            self.log.error(msg)
            raise Exception(msg)

        handler = self.xmlrpc_handlers[msg.rtype]

        if handler.disable_on_bootp and self.bootp.enable:
            msg = "BOOTP is in progress, can't execute operation"
            self.log.warning(msg)
            raise Exception(msg)

        data = handler(msg.data)

        # can't pass None via XML-RPC
        if data is None:
            data = ""

        msg.reply(data)


    @xmlrpc_handler(MessageXMLRPCRequest.REQ_GET_NETWORK_INFO)
    def net_get_info(self, data):
        res = self.mng.get_net_info()
        return res

    def do_revert_to_primary(self, ids=None):
        self.mng.revert_to_primary(ids)

        # We're altering configuration, so current_xml_config
        # can be different now. Clear the value, as it's for
        # cache only.
        self.current_xml_config = None

    @xmlrpc_handler(MessageXMLRPCRequest.REQ_REVERT_TO_PRIMARY)
    def revert_to_primary(self, data=None):
        self.log.info("Requested to revert to primary")

        try:
            self.do_revert_to_primary()
        except:
            self.log.exception("Exception while reverting to primary")
            return False
        return True

    @xmlrpc_handler(MessageXMLRPCRequest.REQ_BOOTP_FINISHED, disable_on_bootp=False)
    def finalize_bootp(self, data=None):

        try:
            self.net_load_settings(force_save=True, preconfig=self.make_configure_port_func(data))
        except:
            self.log.exception("Exception applying BOOTP results, aborting")
            self.terminate = True

    @xmlrpc_handler(MessageXMLRPCRequest.REQ_DHCP_CALLBACK)
    def process_dhcp_client_data(self, data=None):
        self.log.debug("Callback data from DHCP: {}".format(data))

        # {'proto': '4', 'ip': '192.168.30.106', 'mask': '255.255.255.0', 'bound': True, 'dev': 'net7', 'expire': False, 'gateway': ''}

        ifname = data.get("dev")
        family = socket.AF_INET if data.get("proto") == "4" else None
        ip = data.get("ip")
        mask = data.get("mask")
        gw = data.get("gateway", "")
        expire = data.get("expire")
        bound = data.get("bound")

        if family != socket.AF_INET:
            self.log.warning("Not supported protocol for DHCP configuration on interface {}".format(ifname))
            return

        if (not expire and not bound) or (expire and bound):
            self.log.warning("Unknown action for DHCP update on interface {}".format(ifname))
            return

        if bound and (not ip or not mask):
            self.log.warning("Bound but missing IP or mask configuration for interface {}".format(ifname))
            return

        ipaddr = None
        gateway = None

        if ip:
            ipaddr = EthernetIP("{}/{}".format(ip, mask), addr_type=IPOrigin.DHCP)
            if not ipaddr.is_valid_interface_ip():
                self.log.warning("Bad DHCP IP address '{}/{}' for interface {}".format(ip, mask, ifname))
                return

        if ipaddr and gw:
            gateway = EthernetIP(gw, addr_type=IPOrigin.DHCP)
            if not gateway.is_valid_interface_ip():
                self.log.warning("Bad DHCP gateway address '{}' for interface {}".format(gw, ifname))
                return

        res = self.bootp.dhcp_callback(family, ifname, ip=ipaddr, gateway=gateway, expire=expire)

        if res is None:
            res = self.mng.configure_dhcp(family, ifname, ip=ipaddr, gateway=gateway, expire=expire)
            if res:
                self.log.debug("DHCP config for Port {} updated".format(ifname))
                self.notify_new_config()
                self.recalc_alarms()

    @xmlrpc_handler(MessageXMLRPCRequest.REQ_SET_MNG_IP, disable_on_bootp=True)
    def set_mng_ip(self, req):

        ip = str(req.get('ip'))
        mask = str(req.get('mask'))
        gw = str(req.get('gateway'))
        dhcp = bool(req.get('dhcp'))

        ip = EthernetIP("{}/{}".format(ip, mask)) if ip and mask else None
        gw = EthernetIP(gw) if gw else None

        # enable teaming for management interfaces 1 and 2
        # and set ip/dhcp setting
        config = {}
        for iid in self.config.management_ports:
            config[iid] = self.PortConfigData(dhcp, ip, gw, True, AutoNegotiate.AUTO_NEGOTIATE, enabled=True)

        modfunc = self.make_configure_port_func(config)

        try:
            self.net_load_settings(force_save=True, preconfig=modfunc)
        except:
            self.log.exception("Exception while changing management IP")
            return False
        return True

    @xmlrpc_handler(MessageXMLRPCRequest.REQ_GET_NETWORK_SETTINGS, disable_on_bootp=True)
    def net_get_settings(self, _data):

        xmldata = None

        legacy, xmldata = self.load_xml_configs()

        if xmldata:
            xmlobj, xmltag = schema.parse_string(xmldata)
        else:
            # empty default setting
            xmlobj = schema.model_.PlatformNetworkModel(
                EthernetPortConfigModels=[
                    schema.model_.EthernetPortConfigModelsType()
                ]
            )

        eth_cfg = self.mng.get_configuration()

        xmlobj.EthernetPortConfigModels[0].EthernetPortConfigModel = eth_cfg

        return xmlobj.to_xml()

    def load_xml_configs(self):
        xmldata = None
        legacy = False

        if self.current_xml_config is not None:
            return False, self.current_xml_config

        try:
            with open(self.config.settings_xml, "r") as f:
                xmldata = f.read()
        except IOError, e:
            self.log.warning("Can not load network settings: '{}'".format(e))
            if e.errno == errno.ENOENT:
                self.log.info("Trying to read legacy configuration data")
                xmldata = self.config.get_legacy_config()
                legacy = True

        return legacy, xmldata

    def net_load_settings(self, force_save=False, preconfig=None):
        legacy, xmldata = self.load_xml_configs()

        save = force_save or (legacy and xmldata is not None)

        if self.bootp.enable:
            # Do not save config file if it's modified by BOOTP process
            # to avoid overwriting valid configuration on the disk.
            # In case of crash/reboot etc. confuguration may be lost.
            save = False

        if xmldata:
            self.net_set_settings(xmldata, save=save, preconfig=preconfig)

    def check_conf_updated(self, new):
        if not self.current_xml_config or not new:
            return True

        def prepare_cfg_obj(o):
            for p in o:
                p.PortStatus = None
                p.RedundancyStatus = None
                p.LinkSpeed = None
                p.Utilization = None
            return schema.model_.EthernetPortConfigModelsType(EthernetPortConfigModel=o)

        try:
            xmlobj, xmltag = schema.parse_string(self.current_xml_config)
            old = xmlobj.EthernetPortConfigModels[0].EthernetPortConfigModel

            new = prepare_cfg_obj(deepcopy(new))
            old = prepare_cfg_obj(old)

            newxml = new.to_xml()
            oldxml = old.to_xml()

            #self.log.debug("<<<<<<<<<<<<<<<<<")
            #self.log.debug(oldxml)
            #self.log.debug("----------------------------------------------")
            #self.log.debug(newxml)
            #self.log.debug(">>>>>>>>>>>>>>>>> {}".format(newxml == oldxml))

            if newxml == oldxml:
                return False

        except:
            self.log.exception("Exception while comparing configurations")

        return True


    @xmlrpc_handler(MessageXMLRPCRequest.REQ_SET_NETWORK_SETTINGS, disable_on_bootp=True)
    def net_set_settings(self, xmldata, save=True, preconfig=None, norecover=False):

        xmlobj, xmltag = schema.parse_string(xmldata)
        eth_cfg = xmlobj.EthernetPortConfigModels[0].EthernetPortConfigModel

        if preconfig:
            eth_cfg = preconfig(eth_cfg)
            if not eth_cfg:
                self.log.error("Internal error: preconfig() returned no data")
                return
            xmlobj.EthernetPortConfigModels[0].EthernetPortConfigModel = eth_cfg
            xmldata = xmlobj.to_xml()

        if not preconfig and not self.check_conf_updated(eth_cfg):
            self.log.info("New configuration is the same, doing nothing.")
            return

        try:
            self.mng.configure(eth_cfg)
        except:
            legacy, prev_xmldata = self.load_xml_configs()
            if prev_xmldata != xmldata and not norecover:
                # try to load last good config
                self.log.exception("Exception while applying new network configuration")
                self.log.info("Reverting to previous configuration")
                return self.net_set_settings(prev_xmldata, save, norecover=True)
            raise

        self.notify_new_config()
        self.recalc_alarms()

        self.current_xml_config = xmldata

        if save:
            # XXX tmp+rename ?
            with open(self.config.settings_xml, "w") as f:
                f.write(xmldata)
            self.config.wb(self.config.settings_xml)

    def net_load_routes(self):

        try:
            legacy = False
            with open(self.config.routes_json, "r") as f:
                routes_data = f.read()
        except IOError, e:
            self.log.warning("Can not load route settings: '{}'".format(e))
            if e.errno == errno.ENOENT:
                self.log.info("Trying to read legacy routes data")
                routes_data = self.config.get_legacy_routes()
                legacy = True

        if routes_data:
            try:
                conf = json.loads(routes_data)
                for origin, routes in conf.iteritems():
                    self.log.debug("Restoring routes configuration for '{}'".format(origin))
                    try:
                        self.mng.configure_routes("set", origin, routes)
                    except:
                        self.log.exception("Exception while loading routes for '{}'".format(origin))
            except:
                self.log.exception("Exception while decoding saved routes")

            if legacy:
                # save config in new format
                self.routes_save_config()

    @xmlrpc_handler(MessageXMLRPCRequest.REQ_ROUTES_LIST)
    def routes_list(self, data):
        res = {}
        res["routes"] = self.mng.get_route_configuration(data['origin'])
        return res;

    def routes_save_config(self):
        routes = self.mng.get_route_configuration_full()
        text = json.dumps(routes, indent=4, sort_keys=True)

        # XXX tmp+rename ?
        with open(self.config.routes_json, "w") as f:
            f.write(text)
        self.config.wb(self.config.routes_json)

    @xmlrpc_handler(MessageXMLRPCRequest.REQ_ROUTES_UPDATE)
    def routes_update(self, data):
        oper = data['oper']
        origin = data['origin']
        bak_routes = self.mng.get_route_configuration(origin)

        try:
            self.log.debug("Updating routes: '{}' on '{}': {}".format(oper, origin, data['routes']))

            self.mng.configure_routes(oper, origin, data['routes'])
        except:
            # try to restore previous routes
            self.log.exception("Got Exception while configuring routes, trying to restore previous configuration")
            self.mng.configure_routes("set", origin, bak_routes)
            raise
        else:
            self.routes_save_config()

        return True

    @xmlrpc_handler(MessageXMLRPCRequest.REQ_ROUTES_FLUSH)
    def routes_flush(self, data):

        origin = data['origin']
        iids = data['iids']
        if iids is not None:
            iids = [int(i) for i in iids]

        if iids is None:
            self.log.debug("Flushing all routes on '{}'".format(origin))
        else:
            self.log.debug("Flushing routes on '{}': {}".format(origin, str(iids)))

        self.mng.configure_flush_routes(origin, iids)
        self.routes_save_config()

        return True


class PortConfigHelper(object):

    class PortConfigData(object):
        def __init__(self, dhcp=None, ip=None, gw=None, redundancy=None, autoneg=None, enabled=None):
            self.dhcp = dhcp
            self.ip = ip
            self.gw = gw
            self.redundancy = redundancy
            self.autoneg = autoneg
            self.enabled = enabled

    class ReplaceConfigData(object):
        def __init__(self, conf):
            self.conf = conf

    def make_configure_port_func(self, config):

        model_ = schema.model_

        def change_config_model(ports):
            new_ports = []
            for port in ports:
                if port.PortIdentifier in config:
                    new = config[port.PortIdentifier]

                    # check if we have a full port config
                    if isinstance(new, self.ReplaceConfigData):
                        port = new.conf

                    elif isinstance(new, self.PortConfigData):
                        if not new.ip and not new.dhcp:
                            self.log.warning("Requested to change managent IP ignored: no IP, disable DHCP for port {}".format(port.PortIdentifier))
                            continue

                        if new.redundancy is not None:
                            port.EnableRedundancy = True
                            port.RedundantPortType = RedundancyType.ACTIVE_STANDBY.name
                            port.RedundancyMode = RedundancyMode.AUTOMATIC.name
                        if new.autoneg is not None:
                            port.AutoNegotiate = new.autoneg.name

                        if new.enabled is not None:
                            port.EnableInterface = new.enabled

                        port.EnableDHCP = new.dhcp

                        models = []
                        if new.ip:
                            models.append(model_.IPAddressModelType(IPAddress=new.ip.prefix, AddressOrigin=IPOrigin.Manual.name))
                        port.IPAddressModels = model_.IPAddressModelsType(IPAddressModel=models)

                        models = []
                        if new.gw:
                            models.append(model_.GatewayModelType(GatewayAddress=new.gw.ipaddr, GatewayOrigin=IPOrigin.Manual.name))
                        port.GatewayModels = model_.GatewayModelsType(GatewayModel=models)

                        # legacy
                        port.IPAddress = '0.0.0.0'
                        port.NetworkMask = '0.0.0.0'
                        port.Gateway = '0.0.0.0'

                new_ports.append(port)

            return new_ports

        return change_config_model


class EthtoolLinkRestart(object):

    MAX_PING_PACKETS = 3

    def __init__(self, ifname, ping_addr, cb_done):
        self.config = Config()
        self.log = logging.getLogger("main")

        self.ifname = ifname
        self.cb_done = cb_done
        self.ping_addr = ping_addr

        thread = threading.Thread(target=self.ethtool_do)
        thread.daemon = True
        thread.start()

    def ethtool_do(self):
        try:
            self.log.info("Forcing re-negotiation on {}...".format(self.ifname))
            exec_checkcode(self.config.ethtool_path, ["-r", self.ifname], log=self.log, timeout=10)

            # wait link to settle
            waittime = float(self.config.link_watch_timeout) / 2

            if self.ping_addr:
                pings = int(min(self.MAX_PING_PACKETS, waittime))
                try:
                    self.log.debug("Trying to ping '{}'...".format(self.ping_addr))
                    icmp.ping(self.ping_addr, pings)
                    waittime -= pings
                except:
                    self.log.exception("Exception while pinging '{}'".format(self.ping_addr))

            if waittime > 0:
                time.sleep(waittime)

        finally:
            self.cb_done(self.ifname)


class Main(XmlrpcHandlers, PortConfigHelper):

    def __init__(self):
        super(Main, self).__init__()

        self.mng = None

        self.config = Config(args=sys.argv[1:])
        self.log = logging.getLogger("main")
        self.terminate = False
        self.queue = queue.Queue()
        self.alarm = None
        self.team = None
        self.xmlrpc = None
        self.bootp = BootPHandler(self, self.queue)
        self.revert_mon = DelayedRevertHnd(self.queue)

        self.llock = threading.Lock()
        self.link_restart_counter = 0

        signal.signal(signal.SIGTERM, self.signalterm)
        signal.signal(signal.SIGINT, self.signalterm)
        signal.signal(signal.SIGHUP, self.signalhup)
        signal.signal(signal.SIGUSR1, self.signalusr1)

        sysfs.helper.init()

    def signalusr1(self, signum, frame):
        id2name = dict([(th.ident, th.name) for th in threading.enumerate()])
        code = []
        for threadId, stack in sys._current_frames().items():
            self.log.info("# Thread: {}({})".format(id2name.get(threadId,""), threadId))
            for filename, lineno, name, line in traceback.extract_stack(stack):
                self.log.info('File: "{}", line {}, in {}'.format(filename, lineno, name))
                if line:
                    self.log.info("  {}".format(line.strip()))

    def signalterm(self, signum, frame):
        self.log.info("Signal received, terminating")
        self.terminate = True

    def signalhup(self, signum, frame):
        self.log.info("Signal received, ignoring HUP")

    def recalc_alarms(self):
        # We're about to get all status and update alarms,
        # all already pending notifications are redundant
        self.team.flush_planned_notify()
        net_info = self.mng.get_net_info(as_obj=True, nocache=True)

        # ACP-4817
        # produce a net_info for xmlrpc server to return
        # while we're still blocked by processing this event
        info = {}
        for iid, eth in net_info.iteritems():
            # xml-rpc requires keys to be strings
            info[str(iid)] = eth.get_dict()

        # set up cache first
        self.xmlrpc.update_cached_net_info(info)
        # send alarms after that to avoid blocking when
        # alarms send and processed and cache is not
        # updated yet, forcing a synchronous operation

        with self.llock:
            if self.link_restart_counter > 0:
                # If ethtool link restarts are in progress, do not
                # update alarms. Alarms will be updated when all
                # restarts finish
                return

        self.alarm.process_alarm_data_async(net_info)
        self.revert_mon.interfaces_updated(net_info)

    def handle_team_change(self, msg):
        self.recalc_alarms()
        self.mng.team_status_changed()

    def notify_new_config(self):
        self.alarm.new_configuration_event_async()

    def start_link_restart(self, ifname, ping_addr):
        with self.llock:
            if not self.link_restart_counter:
                self.log.debug("Suppression of alarm processing started")
            self.link_restart_counter += 1
        EthtoolLinkRestart(ifname, ping_addr, self.done_link_restart)

    def done_link_restart(self, ifname):
        # called from another thread
        update_alarms = False

        MessageSuspectInterfaceFail(self.queue, MessageSuspectInterfaceFail.INTERF_DONE, data={'ifname':ifname}).request()

        with self.llock:
            self.link_restart_counter -= 1
            if self.link_restart_counter <= 0:
                self.log.debug("Suppression of alarm processing ended")
                self.link_restart_counter = 0
                update_alarms = True

        if update_alarms:
            MessageSuspectInterfaceFail(self.queue, MessageSuspectInterfaceFail.DONE, data={'ifname':ifname}).request()

    def handle_interf_fail(self, msg):
        if msg.rtype == MessageSuspectInterfaceFail.INTERF_DONE:
            ifname = msg.data.get("ifname") if msg.data else None
            if ifname in self.config.interf_name_to_nmi:
                nmiid = self.config.interf_name_to_nmi[ifname]
                self.do_revert_to_primary([nmiid])
        elif msg.rtype == MessageSuspectInterfaceFail.DONE:
            self.recalc_alarms()
            self.notify_new_config() # notify controller that config may have changed
        elif msg.rtype == MessageSuspectInterfaceFail.REPORT:
            if (monotonic() - self.config.startup_time) > 60:
                # workaround is enabled only for the first minute of
                # running time
                return

            ifname = msg.data["ifname"]
            iid = self.mng.get_iid_by_eth(ifname)

            if iid and iid not in self.config.management_ports:
                self.log.warning("Detected possible port {}({}) fail".format(iid, ifname))
                gws = self.mng.get_port_default_gateways(iid)
                ping_addr = gws[0] if gws else None
                self.start_link_restart(ifname, ping_addr)
        else:
            self.log.error("unknown message type {}".format(msg.rtype))

    def handle_revert_interface(self, msg):
        ids = msg.data

        if not ids:
            return

        self.do_revert_to_primary(ids)

    def flush_queue(self):
        while True:
            try:
                msg = self.queue.get_nowait()
            except queue.Empty:
                return
            try:
                msg.failure()
            finally:
                self.queue.task_done()

    def main_loop(self):

        self.log.info("Ready")
        if self.bootp.enable:
            self.log.info("BOOTP is still running, some requests are disabled")

        while not self.terminate:

            try:
                msg = self.queue.get(timeout=0.5)
            except queue.Empty:
                # timeout occured, ignore
                continue

            try:
                if isinstance(msg, MessageXMLRPCRequest):
                    self.handle_xmlrpc(msg)
                elif isinstance(msg, MessageTeamNewState):
                    self.handle_team_change(msg)
                elif isinstance(msg, MessageSuspectInterfaceFail):
                    self.handle_interf_fail(msg)
                elif isinstance(msg, MessageRevertInterface):
                    self.handle_revert_interface(msg)
                else:
                    self.log.error("Internal error, unexpected message class")

                # remove cached data
                self.xmlrpc.update_cached_net_info(None)

            except:
                self.log.exception("Uncaught exception in main loop")
                msg.failure()
            finally:
                msg = None      # if msg has value from previos iteration, free it before blocking
                self.queue.task_done()

    def run(self):

        self.log.debug("Command line arguments: {}".format(str(self.config.args)))

        threads = []

        try:
            xmlrpc = XMLRPCThread(self.queue)
            threads.append(xmlrpc)
            self.xmlrpc = xmlrpc

            ip = IPRoute(self.queue)
            threads.append(ip)

            team = TeamThread(self.queue)
            threads.append(team)
            self.team = team

            self.alarm = AlarmProcThread()
            threads.append(self.alarm)

            stat = PerfStatThread()
            threads.append(stat)

            for t in threads:
                t.start()

            team.start_teamds()

            self.mng = NetManager(ip, team, stat)
            try:
                self.mng.setup()
            except:
                self.log.exception("Exception while doing initial network setup, will try again")
                time.sleep(1)
                self.mng.setup()

            tune = NICTuning()
            tune.run_initial()

            self.net_load_settings(preconfig=self.bootp.mangle_config)
            self.net_load_routes()

            self.main_loop()

            self.mng.shutdown()
        finally:
            for t in reversed(threads):
                t.shutdown()

            time.sleep(0.1)
            self.flush_queue()

            for t in threads:
                try:
                    t.join()
                except:
                    self.log.exception("Exception on thread join() on exit")


if __name__ == "__main__":
    main = Main()
    main.run()
