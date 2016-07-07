#!/usr/bin/env python
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function
import os
import sys
import time
import threading
import argparse
import socket
import logging
import xmlrpclib


class CmdException(Exception):
    pass


class Config(object):
    def __init__(self):

        parser = argparse.ArgumentParser(description='NMInet control tool.')

        parser.add_argument('-H', '--host', metavar='host', type=str,
                        default="localhost",
                        help='Host IP to receive events (default: localhost)')

        parser.add_argument('-v', '--verbose', action='count',
                        default=0,
                        help='Increase verbosity level')


        subparsers = parser.add_subparsers(dest='cmd', help='sub-commands')

        subp = subparsers.add_parser('configip', help='Configure management interface')
        subp.add_argument('--ip', type=str, help='IP address')
        subp.add_argument('--mask', type=str, help='IP mask or prefix length')
        subp.add_argument('--gateway', type=str, help='Gateway')
        subp.add_argument('--dhcp', action='store_true',
                        help='Enable DHCP (overrides manual config)')

        subp = subparsers.add_parser('status', help='Retrieve current status')
        subp.add_argument('-d', '--dump', action='store_true', help='Show configuration and status')
        subp.add_argument('-c', '--config', action='store_true', help='Show raw XML configuration')

        subp = subparsers.add_parser('redundancy', help='Manage interface redundancy')
        subp.add_argument('-r', '--revert', action='store_true', help='Revert redundant interfaces to primary')

        subp = subparsers.add_parser('dhcp', help='DHCP client callbacks')
        subp.add_argument('--bound', action='store_true', help='Address acquired')
        subp.add_argument('--expire', action='store_true', help='Address expired or failed')
        subp.add_argument('--proto', type=str, help='IP protocol version', default="4")
        subp.add_argument('--dev', type=str, help='Interface name', default="")
        subp.add_argument('--ip', type=str, help='IP address', default="")
        subp.add_argument('--mask', type=str, help='IP mask or prefix length', default="")
        subp.add_argument('--gateway', type=str, help='Gateway', default="")

        self._args = parser.parse_args()

        if self.verbose:
            level = logging.DEBUG
        else:
            level = logging.INFO

        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=level)

        self.rpc_uri = "http://{}:8910/RPC2".format(self.args.host)

    @property
    def args(self):
        return self._args

    @property
    def verbose(self):
        return self._args.verbose


class App(object):

    def __init__(self):
        self.config = Config()
        self.log = logging.getLogger("main")
        self.log.debug("Command line arguments: {}".format(str(self.config.args)))

    def get_rpc(self):
        return xmlrpclib.ServerProxy(self.config.rpc_uri)

    def result_get_data(self, res):

        if not isinstance(res, dict):
            raise CmdException("RPC call error: bad result type")

        code = res.get('CODE')
        if code != 1:
            raise CmdException("RPC call error: unexpected result code '{}'".format(code))

        data = res.get('DATA')
        if data is None:
            raise CmdException("RPC call error: no data")

        return data

    def run_status(self):
        rpc = self.get_rpc()

        if not self.config.args.config and not self.config.args.dump:
            self.config.args.dump = True

        if self.config.args.config:
            res = rpc.getInstance("PlatformNetworkModel_PART")

            data = self.result_get_data(res)
            print(data)

        if self.config.args.dump:

            res = rpc.getNetworkInterfaceInfo()
            data = self.result_get_data(res)

            for p in sorted(data.keys()):
                v = data[p]
                print("{}:".format(p))
                for k in sorted(v.keys()):
                    v2 = v[k]
                    if k in ['all_ips', 'ips', 'all_gateways']:
                        v2 = []
                        for ip in v[k]:
                            tag = "" if ip.get('valid', True) else " Invalid"
                            v2.append("{}/{} ({}{})".format(ip.get('addr'), ip.get('plen'), ip.get('method'), tag))
                        v2 = ", ".join(v2)
                    elif k in ['teammembers']:
                        v2 = ", ".join(map(str, v2))
                    elif k in ['routes']:
                        v2 = []
                        for r in v[k]:
                            v2.append("{} via {} ({})".format(r.get('prefix'), r.get('gateway'), r.get('origin')))
                        v2 = ", ".join(v2)

                    print("    {:20s}: {}".format(k, v2))

    def run_configip(self):
        rpc = self.get_rpc()

        if self.config.args.ip and self.config.args.mask:
            if self.config.args.dhcp:
                raise CmdException("DHCP enabled, can not set manual IP address")
        elif not self.config.args.dhcp:
            raise CmdException("Argument missing, need either DHCP enabled or manual IP address")

        ip = self.config.args.ip
        mask = self.config.args.mask
        gw = self.config.args.gateway

        configip = {
            'ip': ip if ip else "",
            'mask': mask if mask else "",
            'gateway': gw if gw else "",
            'dhcp': self.config.args.dhcp,
        }

        self.log.debug("Setting management IP: {}".format(str(configip)))

        res = rpc.setManagementIP(configip)
        data = self.result_get_data(res)

        if data:
            print("Management ports configured successfully")
        else:
            print("Failed to configure Management ports. See logs.", file=sys.stderr)

    def run_redundancy(self):
        rpc = self.get_rpc()

        if not self.config.args.revert:
            raise CmdException("Unknown operation")

        self.log.debug("Executing Redundancy Revert command")

        res = rpc.revertToPrimaryInterfaces()
        data = self.result_get_data(res)

        if data:
            print("Success")
        else:
            print("Operation failed. See logs.", file=sys.stderr)


    def run_dhcp(self):
        rpc = self.get_rpc()

        if not any([self.config.args.bound, self.config.args.expire]):
            raise CmdException("Unknown operation")

        if any([self.config.args.bound, self.config.args.expire]) and not self.config.args.dev:
            raise CmdException("Device name required")

        self.log.debug("Executing DHCP callback command")

        params = {
            "bound": bool(self.config.args.bound),
            "expire": bool(self.config.args.expire),

            "dev": self.config.args.dev,
            "proto": self.config.args.proto,
            "ip": self.config.args.ip,
            "mask": self.config.args.mask,
            "gateway": self.config.args.gateway,
        }

        res = rpc.DHCPClientCallback(params)
        data = self.result_get_data(res)

        if self.config.verbose:
            if data:
                print("Success")
            else:
                print("Operation failed. See logs.", file=sys.stderr)


    def run(self):
        method = getattr(self, "run_{}".format(self.config.args.cmd), None)
        if method:
            return method()

        raise CmdException("Command handler not found")


if __name__ == "__main__" :
    app = App()
    try:
        res = app.run()
        if res is None:
            res = 0
    except Exception, e:
        print("Error: {}".format(e), file=sys.stderr)
        res = -1
    sys.exit(res)
