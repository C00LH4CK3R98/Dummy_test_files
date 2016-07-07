#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function

import os
import sys
import time
import argparse
import logging
import logging.config
import logging.handlers
import subprocess
from ConfigParser import *

from util import *
from monotonic import monotonic
import compat

__all__ = ['Config']

class Config(object):
    __metaclass__ = Singleton

    _WB = "/sbin/wb"
    _TEAMD_PATH = "/usr/bin/teamd"
    _TEAMDCTL_PATH = "/usr/bin/teamdctl"
    _CONFIG_PATH = "/opt/omneon/config/network"
    _DEFAULT_SYSTEM_CONFIG_FILE = "/etc/nminet.conf"
    _SETAUTONEG_PATH = "/opt/omneon/sbin/setautoneg.sh"
    _DHCLIENT_PATH = "/usr/sbin/dhclient"
    _ETHTOOL_PATH = "/usr/sbin/ethtool"

    _RUNTIME_DIR = "/var/lib/nminet"
    _AUTONEG_DB = "{}/autoneg.db".format(_RUNTIME_DIR)

    DEFAULT_NMIEVENT_SH = "/opt/omneon/sbin/nmievent.sh"
    DEFAULT_CONFIG_FILE = "{}/nminet.conf".format(_CONFIG_PATH)
    DEFAULT_SETTINGS_XML_FILE = "{}/nminet.settings.xml".format(_CONFIG_PATH)
    DEFAULT_ROUTES_JSON_FILE = "{}/nminet.routes.json".format(_CONFIG_PATH)
    DEFAULT_BRIDGED = True
    DEFAULT_LINK_WATCH_TIMEOUT = 10
    DEFAULT_LINK_WATCH_TRIES = 3
    DEFAULT_LINK_DOWN_ETHS = True
    DEFAULT_DOWN_LOWER_ONLY = True

    DEFAULT_PID_FILE = "/var/run/nminet.pid"

    MANAGEMENT_PORT_IDS = [1, 2]
    APPLICATION_PORT_IDS = [3, 4]

    DEFAULT_AR_DELAY_UP = 30000

    def __init__(self, args=None):

        self._startup_time = monotonic()

        parser = argparse.ArgumentParser(description='NMI Networking utilities')

        parser.add_argument('-p', '--pid', metavar='pid', type=str,
                            default=self.DEFAULT_PID_FILE,
                            help='PID file path (default: "{}")'.format(self.DEFAULT_PID_FILE))

        parser.add_argument('-c', '--config', metavar='config', type=str,
                            default=self.DEFAULT_CONFIG_FILE,
                            help='config file path (default: "{}")'.format(self.DEFAULT_CONFIG_FILE))

        parser.add_argument('-v', '--verbose', action='count',
                            default=0,
                            help='Increase verbosity level')

        parser.add_argument('-s', '--syslog', action='store_true',
                            default=0,
                            help='Log to syslog')

        parser.add_argument('--bootp', action='store_true',
                            default=False,
                            help='Enable BOOTP mode')

        if args is None:
            args = []
        self._args = parser.parse_args(args=args)

        self._setup_logging()

        self._load_config()

        self._prepare_helpers()

        self.settings_xml = self.get("global", "settings_xml", self.DEFAULT_SETTINGS_XML_FILE)
        self.routes_json = self.get("global", "routes_json", self.DEFAULT_ROUTES_JSON_FILE)
        self.nmievent_sh = self.get("global", "nmievent_sh", self.DEFAULT_NMIEVENT_SH)
        self.teamd_path = self.get("global", "teamd_path", self._TEAMD_PATH)
        self.teamdctl_path = self.get("global", "teamdctl_path", self._TEAMDCTL_PATH)
        self.setautoneg_path = self.get("global", "setautoneg_path", self._SETAUTONEG_PATH)
        self.dhclient_path = self.get("global", "dhclient_path", self._DHCLIENT_PATH)
        self.ethtool_path = self.get("global", "ethtool_path", self._ETHTOOL_PATH)
        self.autoneg_db = self.get("global", "autoneg_db", self._AUTONEG_DB)
        self.bridged = self.getboolean("global", "bridged", self.DEFAULT_BRIDGED)
        self.link_watch_timeout = self.getint("global", "link_watch_timeout", self.DEFAULT_LINK_WATCH_TIMEOUT)
        self.link_watch_tries = self.getint("global", "link_watch_tries", self.DEFAULT_LINK_WATCH_TRIES)
        self.ar_delay_up = self.getint("global", "ar_delay_up", self.DEFAULT_AR_DELAY_UP)
        self.link_down_eths = self.getboolean("global", "link_down_eths", self.DEFAULT_LINK_DOWN_ETHS)
        self.down_lower_only = self.getboolean("global", "down_lower_only", self.DEFAULT_DOWN_LOWER_ONLY)

        self.chassis = self.get("global", "chassis", "Ch.1")

        self.management_ports = list(self.MANAGEMENT_PORT_IDS)
        self.bootp_ports = list(self.MANAGEMENT_PORT_IDS)
        self.application_ports = list(self.APPLICATION_PORT_IDS)

        # whatami -p
        #self.product = "pml_acp"
        self.product = "pmo"

        self._legacy_net_config = None
        self._legacy_net_config_ready = False

        self._legacy_net_routes = None
        self._legacy_net_routes_ready = False

        try:
            os.makedirs(self._RUNTIME_DIR, 0750)
            os.makedirs(self._CONFIG_PATH, 0755)
        except:
            pass

    @property
    def startup_time(self):
        return self._startup_time

    def get_team_name_by_nmiid(self, iid):
        if self.bridged:
            return "nteam{}".format(iid)
        else:
            return "net{}".format(iid)

    def get_br_name_by_nmiid(self, iid):
        if self.bridged:
            return self.get_l3int_name_by_nmiid(iid)
        return None

    def get_l3int_name_by_nmiid(self, iid):
        return "net{}".format(iid)

    def _setup_logging(self):

        if self.verbose:
            level = logging.DEBUG
        else:
            level = logging.INFO

        if self.args.syslog:
            handlers = ['sys-logger']
        else:
            handlers = ['stdout']

        logconfig = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'fmt-file': {
                    'format': '%(asctime)s nminet[%(process)d]: %(levelname)s(%(name)s) - %(message)s',
                },
                'fmt-syslog': {
                    'format': 'nminet[%(process)d]: %(asctime)s.%(msecs).03d %(levelname)s(%(name)s) - %(message)s',
                    'datefmt': '%H:%M:%S',
                },
            },
            'handlers': {
                'stdout': {
                    'class': 'logging.StreamHandler',
                    'stream': sys.stdout,
                    'formatter': 'fmt-file',
                },
                'sys-logger': {
                    'class': 'logging.handlers.SysLogHandler',
                    'address': '/dev/log',
                    'facility': "daemon",
                    'formatter': 'fmt-syslog',
                },
            },
            'root': {
                'handlers': handlers,
                'level': level,
            },
            'loggers': {
                'perf': {
                    'level': level if self.verbose > 1 else logging.INFO,
                },
                #'alarm': {
                #    'level': level if self.verbose > 1 else logging.INFO,
                #},
            }
        }

        logging.config.dictConfig(logconfig)

    def _get_system_eth_interfaces(self):
        devs = []
        with open('/proc/net/dev', 'r') as f:
            for line in f.readlines():
                if ':' not in line:
                    continue
                dev, rest = line.split(':', 2)
                dev = dev.strip()
                if dev.startswith("eth"):
                    try:
                        num = int(dev[3:])
                    except ValueError:
                        continue
                    devs.append((num+1, dev))

        return devs

    def _prepare_helpers(self):
        self._prepare_helpers_interface()

    def _prepare_helpers_interface(self):
        interf_nmi_to_name = {}
        interf_name_to_nmi = {}

        defaultnet = self._get_system_eth_interfaces()
        valid_interfaces = [name for i, name in defaultnet]

        for nmi_id, name in self.items('interfaces', default=defaultnet):
            if name not in valid_interfaces:
                continue
            nmi_id = int(nmi_id)
            interf_nmi_to_name[nmi_id] = name
            interf_name_to_nmi[name] = nmi_id

        self.interf_nmi_to_name = interf_nmi_to_name
        self.interf_name_to_nmi = interf_name_to_nmi

    def get_legacy_routes(self):
        if self._legacy_net_routes_ready:
            return self._legacy_net_routes

        try:
            cr = compat.CompatRoutes()
            cr.load()
            self._legacy_net_routes = cr.get_json_string()
        except:
            self._legacy_net_routes = None

        self._legacy_net_routes_ready = True
        return self._legacy_net_routes

    def get_legacy_config(self):
        if self._legacy_net_config_ready:
            return self._legacy_net_config

        try:
            cs = compat.CompatSetting()
            cs.load()
            obj = cs.get_xmlobj()
            self._legacy_net_config = obj.to_xml()
        except:
            self._legacy_net_config = None

        self._legacy_net_config_ready = True
        return self._legacy_net_config

    def wb(self, filename):

        try:
            proc = subprocess.Popen([self._WB, filename],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            close_fds=True)

            stdoutdata, stderrdata = proc.communicate()
        except:
            # XXX
            pass

    def get_interf_platf_objid(self, iid):
        # XXX TODO put into config
        return "{}.C.{}.P.{}".format(self.chassis, ((iid - 1) / 4) + 1, ((iid - 1) % 4) + 1)

    def get_interf_description(self, iid):
        # XXX TODO put into config
        n = int(iid)
        if n == 1 or n == 2:
            return "Management {:02d}".format(n)
        return "GbE {:02d}".format(n)

    @property
    def args(self):
        return self._args

    @property
    def verbose(self):
        return self._args.verbose

    def _load_config(self):
        self.config = RawConfigParser()

        self.config.read([self._DEFAULT_SYSTEM_CONFIG_FILE, self.args.config])

    def _get(self, getop, section, option, default):
        if not self.config.has_option(section, option):
            return default
        return getop(section, option)

    def get(self, section, option, default=None):
        return self._get(self.config.get, section, option, default)

    def getint(self, section, option, default=None):
        return self._get(self.config.getint, section, option, default)

    def getfloat(self, section, option, default=None):
        return self._get(self.config.getfloat, section, option, default)

    def getboolean(self, section, option, default=None):
        return self._get(self.config.getboolean, section, option, default)

    def items(self, section, default=None):
        if not self.config.has_section(section):
            return default
        return self.config.items(section)
