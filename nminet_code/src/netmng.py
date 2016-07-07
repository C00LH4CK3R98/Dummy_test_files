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
import socket
import logging
import re
import Queue
queue = Queue # python 3
from enum import Enum
from copy import deepcopy

from teaming import TeamModes, CurrentDefaultDelay
from monotonic import monotonic
import schema
import sysfs
from util import *
from message import *
from config import *
from defs import *
from ip import EthernetIP, RouteUnreachable, IFF_UP, IFF_ALLMULTI
from hnd_redundancy import *
from hnd_autoneg import *
from hnd_dhcp import *

#__all__ = []


class IPAddressInfo(object):
    def __init__(self, ip=None, addr=None, plen=None, method=None, valid=None):

        if ip:
            self.addr = ip.ipaddr
            self.plen = ip.plen
            self.method = ip.addr_type
            self.valid = ip.is_valid_interface_ip()
        else:
            assert(addr is not None)
            assert(plen is not None)
            assert(method is not None)
            assert(valid is not None)
            self.addr = addr
            self.plen = plen
            self.method = method
            self.valid = valid


class IPRouteInfo(object):
    def __init__(self, origin=None, route=None):
        self.prefix = route.prefix.prefix if route.prefix else "default"
        if route.gateway == RouteUnreachable:
            self.gateway = "unreachable"
        else:
            self.gateway = route.gateway.ipaddr if route.gateway else "link"
        self.origin = origin if origin is not None else route.origin
        if self.origin is None:
            self.origin = "unknown"


class NetworkInterfaceInfo(object):
    def __init__(self):
        # Legacy CPI fields

        # NMI port Id
        self.nmi_id = 0
        # list of ip,mask pairs
        # contains at lease one v4 address (0.0.0.0 as a fallback)
        # does not contain link-local addresses
        self.ips = []
        # Port IDs of NIC team members (excluding current interface)
        self.teammembers = []
        # Port status
        self.status = PortStatus.MEDIA_DISCONNECTED

        # New fields

        self.redundancy_type = RedundancyType.NONE
        self.redundancy_mode = RedundancyMode.AUTOMATIC
        self.redundancy_status = RedundancyStatus.ACTIVE

        self.interface_name_l2 = ""     # eth0, eth1...
        self.interface_name_l3 = ""     # net1...

        self.all_ips = []
        self.all_gateways = []

        self.enabled = False
        self.enable_dhcp = False
        self.mac_address = "00-00-00-00-00-00"
        self.pci_id = ""
        self.link_speed = "(Offline)"
        self.link_mode = AutoNegotiate.AUTO_NEGOTIATE
        self.primary_port = False
        self.manual_primary_port = False
        self.description = ""
        self.platform_object_id = ""

        self.routes_status = RouteStatus.INACTIVE

    def init_from_ethernet_interface(self, eth):
        self.nmi_id = eth.iid
        self.status = eth.status

        master = eth.master if eth.master is not None else eth

        self.all_ips = []
        self.ips = []
        hasv4 = False
        for ip in master.ip_addresses + master.auto_ip_addresses:
            cpiip = IPAddressInfo(ip)

            self.all_ips.append(cpiip)

            if not ip.is_link_local():
                self.ips.append(cpiip)
                if not hasv4 and ip.family == socket.AF_INET:
                    hasv4 = True

        if not hasv4:
            self.ips.insert(0, IPAddressInfo(addr='0.0.0.0', plen=0, method=IPOrigin.Unknown, valid=False))

        for gw in master.gateways:
            cpigw = IPAddressInfo(gw)
            self.all_gateways.append(cpigw)

        self.teammembers = list(eth.peers)
        self.primary_port = len(eth.follower_keys) > 0 # and eth.redundancy_type != none ?
        if master.redundancy_mode in [RedundancyMode.MANUAL, RedundancyMode.MANUAL_NOFAILOVER]:
            self.manual_primary_port = eth.manual_primary
        else:
            self.manual_primary_port = self.primary_port

        # New fields

        self.redundancy_type = master.redundancy_type
        self.redundancy_mode = master.redundancy_mode
        self.redundancy_status = eth.redundancy_status

        self.interface_name_l2 = eth.eth_port_name
        self.interface_name_l3 = master.l3int_name
        self.dhcp_status = master.dhcp_status

        self.routes_status = master.routes.last_status
        self.routes = []
        for origin, routes in eth.routes.get_all().iteritems():
            for route in routes:
                self.routes.append(IPRouteInfo(origin, route))

        # fields for enumerate() call
        self.enabled = master.enabled
        self.enable_dhcp = master.enable_dhcp
        self.mac_address = eth.mac_address
        self.pci_id = eth.pci_id
        self.link_speed = eth.link_speed
        self.link_mode = eth.link_mode
        self.description = eth.description
        self.platform_object_id = eth.platform_object_id

    def get_dict(self):
        return self._get_rpc_dict(self)

    @classmethod
    def _get_rpc_dict(kls, obj):

        if type(obj) in [str, unicode, int, long, bool]:
            return obj
        elif isinstance(obj, Enum):
            return obj.name
        elif isinstance(obj, list):
            lst = []
            for v in obj:
                lst.append(kls._get_rpc_dict(v))
            return lst
        else:
            res = {}
            for n in dir(obj):
                if n.startswith('_'):
                    continue
                v = getattr(obj, n)
                if callable(v):
                    continue

                res[n] = kls._get_rpc_dict(v)

            return res


class InterfaceState(object):

    STATE_CACHE_TIME = 1.0

    def __init__(self, interface):
        self.interf = interface
        self._last_update = 0
        self._reset()

    def _reset(self):
        self._link_speed = "(N/A)"
        self._mac_address = "00-00-00-00-00-00"
        self._have_carrier = False
        self._active = False
        self._last_update = 0
        self._last_change = monotonic()

    @property
    def log(self):
        return self.interf.log

    @property
    def eth_port_name(self):
        return self.interf.eth_port_name

    @property
    def team(self):
        return self.interf._netmng.team

    def update(self, force=False):

        ip = self.interf._netmng.ip

        try:
            eth = ip.interfaces[self.eth_port_name]
        except:
            self._reset()
            return True

        # avoid too frequent updates
        now = monotonic()
        if not force:
            if (now - self._last_update) < self.STATE_CACHE_TIME:
                return False

        # collect data

        have_carrier = self.team.port_has_link(self.eth_port_name)
        active = self.team.is_port_active(self.eth_port_name)

        mac_address = eth.address.replace(":", "-")

        if have_carrier:
            link_speed = sysfs.helper.get_net_interface_param(self.eth_port_name, "speed")
        else:
            link_speed = self._link_speed

        # check if anything changed
        updated = (
            (self._have_carrier != have_carrier) or
            (self._mac_address != mac_address) or
            (self._link_speed != link_speed) or
            (self._active != active))

        # semi-"atomic" update
        self._link_speed = link_speed
        self._mac_address = mac_address
        self._have_carrier = have_carrier
        self._active = active
        self._last_update = now

        if updated:
            self._last_change = now
            self.log.debug("Interface {} new state: {}".format(self.eth_port_name, str(self)))

        return updated

    @property
    def link_speed(self):
        self.update()
        return self._link_speed

    @property
    def mac_address(self):
        self.update()
        return self._mac_address

    @property
    def have_carrier(self):
        self.update()
        return self._have_carrier

    @property
    def active(self):
        self.update()
        return self._active

    @property
    def last_change(self):
        return self._last_change

    def __str__(self):
        return "<InterfaceState {}: mac:{} link:{} active:{} speed:{} changed:{}>".format(self.eth_port_name,
            self._mac_address, self._have_carrier, self._active, self._link_speed,
            self._last_change)


class IfRoute(object):
    def __init__(self, origin, prefix, gateway, iid):
        self.prefix = prefix
        self.gateway = gateway
        self.iid = iid
        self.origin = origin

    def to_dict(self):
        res = {}

        if self.prefix is not None:
            res["prefix"] = self.prefix.prefix
        if self.gateway is not None:
            res["gateway"] = self.gateway.ipaddr
        if self.iid > 0:
            res["portid"] = str(self.iid)

        return res

    @classmethod
    def from_dict(klass, origin, d):
        prefix = EthernetIP(d.get("prefix"))
        gateway = d.get("gateway")
        if gateway is not None:
            gateway = EthernetIP(gateway)
        iid = d.get("portid")
        iid = 0 if iid is None else int(iid)

        return klass(origin, prefix, gateway, iid)

    def __hash__(self):
        return hash((self.prefix, self.gateway))

    def __eq__(self, other):
        return (self.prefix == other.prefix and
                self.gateway == other.gateway)

    def __neq__(self, other):
        return not self.__eq__(other)



class InterfaceRoutes(object):

    _MOD_OPS = ["set", "add", "remove"]

    def __init__(self, interf):
        self.interf = interf
        self.iid = interf.iid
        self.last_status = RouteStatus.INACTIVE
        self.routes = {}

    def get_all(self):
        return self.routes

    def get(self, origin):
        if origin in self.routes:
            return self.routes[origin]
        return []

    def get_route_list(self):

        routes = []
        for rlist in self.routes.itervalues():
            routes.extend(rlist)

        return routes

    def flush(self, origin=None):
        if origin is None:
            self.routes = {}
        elif origin in self.routes:
            del self.routes[origin]

    def set(self, new_routes, origin=None):
        # XXX if origin is none, use route's origin
        self.routes[origin] = new_routes

    def add(self, routes, origin=None):
        # XXX if origin is none, use route's origin
        existing = self.routes.setdefault(origin, [])
        for r in routes:
            if r not in existing:
                existing.append(r)

    def remove(self, routes, origin=None):
        # XXX if origin is none, use route's origin
        existing = self.routes.setdefault(origin, [])
        for r in routes:
            if r in existing:
                existing.remove(r)

    def update(self, oper, routes, origin):
        if oper not in self._MOD_OPS:
            raise Exception("Unknown route modify operation: {}".format(oper))

        func = getattr(self, oper)
        return func(routes, origin)


class EthernetInterface(object):

    _NO_LEGACY_GW = "0.0.0.0"
    _DEFAULT_REDUNDANCY_HANDLER = RedundancyHandlerNOOP()

    def __init__(self, netmng, iid):

        self._netmng = netmng
        self.redundancy_handler = self._DEFAULT_REDUNDANCY_HANDLER
        self.redundancy_data = None
        self.redundancy_data_prev = None

        self.state = InterfaceState(self)

        # read-only/info fields
        self.iid = int(iid)
        self.key = None
        self.follower_keys = []
        self.pci_id = None
        self.description = None
        self.platform_object_id = None
        self.available_redundancy = None
        self.available_dhcp = None
        self.roles = []

        # settable
        self.enabled = self.is_port_role(PortRole.MANAGEMENT) # enable management only as a default

        self.enable_redundancy = False
        self.redundancy_type = RedundancyType.NONE
        self.redundancy_mode = RedundancyMode.AUTOMATIC
        self.select_port = False
        self.manual_primary = False

        self.link_mode = AutoNegotiate.AUTO_NEGOTIATE

        self.enable_dhcp = True
        # manually configured addresses
        self.ip_addresses = []
        self.gateways = []

        # link-local, dhcp addresses, etc
        self.auto_ip_addresses = []
        self.auto_gateways = []

        # platform
        self.eth_port_name = None
        self.team_name = None
        self.l3int_name = None
        self.dhcp_status = DHCPStatus.UNKNOWN

        # list of interface ids which are slaves of a team kernel driver
        self.ifslaves = []
        # list of interface ids which are a logical nmi slaves
        self.slaves = []
        # list of ids of other interfaces in a logical nmi redundancy port
        self.peers = []

        # master port (in sense of 'ifslave')
        self.master = None
        # master port (in sense of 'slaves')
        self.primary = None

        self.init_defaults()

        self.pci_id = sysfs.helper.get_net_interface_pci_id(self.eth_port_name)
        self.routes = InterfaceRoutes(self)

    def set_redundancy_handler(self, hnd):
        hnd.init_interf(self)

    def force_update_redundancy(self):
        self.redundancy_handler.update(self)

    def is_port_role(self, role):
        if role == PortRole.MANAGEMENT:
            return (self.iid in self._netmng.config.management_ports)
        if role == PortRole.APPLICATION:
            return (self.iid in self._netmng.config.application_ports)
        return role == PortRole.DATA

    @property
    def log(self):
        return self._netmng.log

    def find_port_by_id(self, iid):
        return self._netmng.find_port_by_id(iid)

    def init_defaults(self):
        iid = self.iid
        self.key = iid

        if self.key & 1:
            self.follower_keys = [self.key + 1]
            self.available_redundancy = True
        else:
            self.available_redundancy = False

        self.available_dhcp = True

        self.description = self._netmng.config.get_interf_description(self.iid)
        self.platform_object_id = self._netmng.config.get_interf_platf_objid(self.iid)

        self.pci_id = "00:00.0"

        self.eth_port_name = self._netmng.config.interf_nmi_to_name[self.iid]
        self.team_name = self._netmng.config.get_team_name_by_nmiid(self.iid)
        self.l3int_name = self._netmng.config.get_l3int_name_by_nmiid(self.iid)

    def update(self):
        return self.state.update(force=True)

    @property
    def utilization(self):
        util = self._netmng.perfstat.get_max_util([self.eth_port_name])
        if util is None:
            return "unknown"
        return str(util)

    @property
    def link_speed(self):
        if self.state.have_carrier:
            link_speed = "{}Mb/s".format(self.state.link_speed)
        else:
            link_speed = "(Offline)"

        return link_speed

    @property
    def mac_address(self):
        return self.state.mac_address

    @property
    def is_active(self):
        return self.redundancy_handler.is_interf_active(self)

    @property
    def have_carrier(self):
        return self.state.have_carrier

    @property
    def status(self):
        if not self.enabled:
            return PortStatus.DISABLED
        elif self.have_carrier:
            return PortStatus.CONNECTED
        else:
            return PortStatus.MEDIA_DISCONNECTED


    @property
    def redundancy_status(self):
        if not self.enabled or self.redundancy_type == RedundancyType.NONE:
            return RedundancyStatus.NOT_ENABLED
        elif not self.have_carrier:
            return RedundancyStatus.DISCONNECTED

        is_active = self.is_active
        if is_active and self.redundancy_mode == RedundancyMode.DUAL:
            return RedundancyStatus.ACTIVE_DUAL
        elif is_active:
            return RedundancyStatus.ACTIVE

        return RedundancyStatus.INACTIVE

    @property
    def redundancy_status_soap(self):
        # SOAP doesn't support ACTIVE_DUAL, so convert it to ACTIVE
        redundancy_status = self.redundancy_status
        if redundancy_status == RedundancyStatus.ACTIVE_DUAL:
            redundancy_status = RedundancyStatus.ACTIVE
        return redundancy_status

    def reload_system_ips(self):
        ip = self._netmng.ip
        eth = ip.interfaces[self.l3int_name]

        ips = []
        for ipaddr, ipmask in eth.ipaddr:
            eip = EthernetIP(ipaddr, plen=ipmask)
            if eip not in self.ip_addresses:
                if eip.family == socket.AF_INET6 and eip.is_link_local():
                    eip.addr_type = IPOrigin.LinkLocal
                else:
                    eip.addr_type = IPOrigin.Unknown
                ips.append(eip)

        self.auto_ip_addresses = ips

    def update_dhcp_addr(self, dhcp_status, family, ip, gw):
        updated = False

        if family != socket.AF_INET:
            return updated

        if ip and ip.family != family:
            self.log.warning("IP address family mismatch: {} for {}".format(family, ip))
            return updated

        if ip and ip in self.ip_addresses:
            # update entry (e.g. stored addr_type)
            self.ip_addresses.remove(ip)
            self.ip_addresses.append(ip)
        elif ip:
            self.ip_addresses.append(ip)
            updated = True

        if gw:
            if len(self.gateways) != 1 or self.gateways[0] != gw:
                self.gateways = [gw]
                updated = True
        else:
            if len(self.gateways) != 0:
                self.gateways = []
                updated = True

        rmlist = []
        for cur in self.ip_addresses:
            if cur.addr_type == IPOrigin.DHCP and cur.family == family and (ip is None or cur != ip):
                rmlist.append(cur)

        for rm in rmlist:
            self.ip_addresses.remove(rm)

        if self.dhcp_status != dhcp_status:
            self.dhcp_status = dhcp_status
            updated = True

        return updated

    def load_from_xmlobj(self, obj):

        def get(p, default):
            v = getattr(obj, p, default)
            if v is None:
                v = default
            return v

        self.enabled = get('EnableInterface', False)

        self.enable_redundancy = get('EnableRedundancy', False)
        self.redundancy_type = RedundancyType[get('RedundantPortType', 'NONE')]
        self.redundancy_mode = RedundancyMode[get('RedundancyMode', 'AUTOMATIC')]

        if not self.enable_redundancy:
            # EnableRedundancy is a primary field, all other matter only if
            # redundancy is enabled
            self.redundancy_type = RedundancyType.NONE
            self.redundancy_mode = RedundancyMode.AUTOMATIC
        elif self.enable_redundancy and self.redundancy_type == RedundancyType.NONE:
            # compatibility mode, if redundancy is enabled, ACTIVE_STANDBY is the default
            self.redundancy_type = RedundancyType.ACTIVE_STANDBY

        self.select_port = False    # this is handled later when configuration is loaded
        if self.redundancy_mode in [RedundancyMode.MANUAL, RedundancyMode.MANUAL_NOFAILOVER]:
            self.manual_primary = get('IsManualPrimaryPort', False)
        else:
            self.manual_primary = False

        self.link_mode = AutoNegotiate[get('AutoNegotiate', 'AUTO_NEGOTIATE')]

        self.enable_dhcp = get('EnableDHCP', False)

        self.ip_addresses = []
        if obj.IPAddressModels:
            # new-style
            for ip in obj.IPAddressModels.IPAddressModel:
                eth_ip = EthernetIP(ip.IPAddress, addr_type=IPOrigin[ip.AddressOrigin])
                if eth_ip.is_link_local():
                    self.log.debug("Ignoring link-local IP {}/{} for interface id {}".format(eth_ip.ipaddr, eth_ip.plen, self.iid))
                else:
                    self.ip_addresses.append(eth_ip)
        else:
            # legacy
            if not self.enable_dhcp and obj.IPAddress and obj.NetworkMask:
                plen = ip_mask_to_prefix_len(obj.NetworkMask)
                if plen > 0:
                    self.ip_addresses.append(EthernetIP(obj.IPAddress, plen=plen, addr_type=IPOrigin.Manual))

        self.gateways = []
        if obj.GatewayModels:
            # new-style
            for gw in obj.GatewayModels.GatewayModel:
                ### XXX ignore automatic gateways?
                self.gateways.append(EthernetIP(gw.GatewayAddress, addr_type=IPOrigin[gw.GatewayOrigin]))
        else:
            # legacy
            if not self.enable_dhcp and obj.Gateway and obj.Gateway != self._NO_LEGACY_GW:
                self.gateways.append(EthernetIP(obj.Gateway, addr_type=IPOrigin.Manual))

        if self.redundancy_type == RedundancyType.ACTIVE_STANDBY:
            self.ifslaves = list(self.follower_keys)

        if self.redundancy_type != RedundancyType.NONE:
            self.slaves = list(self.follower_keys)

    def get_xmlobj(self):
        model_ = schema.model_
        x = model_.EthernetPortConfigModel()

        master = self.master if self.master is not None else self

        #
        # NOTE: NMX requires that all relevant tags will be present in XML, no matter
        # if the value makes sense in this configuration mode or not.
        #
        # In other words, all tags should be initialized to a non-None value.
        #
        # If None is used anywhere, NMX may generate incorrect XML on a
        # subsequent reconfiguration calls.
        #
        # See NMX-47674, ACP-4969
        #

        x.PortIdentifier = self.iid

        x.ModelKey = self.key
        for fk in self.follower_keys:
            x.FollowerKeys.append(model_.FollowerKeysType(string=fk))

        x.PCIDeviceLocation = self.pci_id
        x.Name = self.description
        x.PortStatus = self.status.name
        x.RedundancyStatus = self.redundancy_status_soap.name
        x.ActiveMAC = self.mac_address
        x.PlatformObjectID = self.platform_object_id
        x.LinkSpeed = self.link_speed
        x.Utilization = self.utilization
        x.CanEnableRedundancy = self.available_redundancy
        x.EnableDHCPMethod = self.available_dhcp

        if self.is_port_role(PortRole.MANAGEMENT):
            role = model_.InterfaceRoleModel(InterfaceRole="Management")
            roles = model_.InterfaceRolesType()
            roles.InterfaceRoleModel.append(role)
            x.InterfaceRoles.append(roles)

        x.EnableInterface = master.enabled
        x.EnableDHCP = master.enable_dhcp

        if master.redundancy_type == RedundancyType.NONE:
            # Default value for RedundantPortType, to force tag be present in XML
            x.RedundantPortType = RedundancyType.ACTIVE_STANDBY.name
            x.EnableRedundancy = False
        else:
            x.EnableRedundancy = True
            x.RedundantPortType = master.redundancy_type.name
        x.RedundancyMode = master.redundancy_mode.name
        x.AutoNegotiate = master.link_mode.name


        legacy_ip = None
        legacy_gw = None

        models = []
        for ip in master.ip_addresses + master.auto_ip_addresses:
            if self._select_legacy_addr(legacy_ip, ip):
                legacy_ip = ip
            model = model_.IPAddressModelType(IPAddress=ip.prefix, AddressOrigin=ip.addr_type.name)
            models.append(model)
        x.IPAddressModels = model_.IPAddressModelsType(IPAddressModel=models)

        models = []
        for gw in master.gateways:
            if self._select_legacy_addr(legacy_gw, gw):
                legacy_gw = gw
            model = model_.GatewayModelType(GatewayAddress=gw.ipaddr, GatewayOrigin=gw.addr_type.name)
            models.append(model)
        x.GatewayModels = model_.GatewayModelsType(GatewayModel=models)


        if master.redundancy_mode in [RedundancyMode.MANUAL, RedundancyMode.MANUAL_NOFAILOVER]:
            # represents selected primary port
            x.IsManualPrimaryPort = self.manual_primary
        else:
            x.IsManualPrimaryPort = bool(self.slaves)


        # set legacy fields for SAG
        if legacy_ip:
            x.IPAddress = legacy_ip.ipaddr
            x.NetworkMask = legacy_ip.ipmask
            if legacy_gw:
                x.Gateway = legacy_gw.ipaddr
            else:
                x.Gateway = '0.0.0.0'
        else:
            x.IPAddress = '0.0.0.0'
            x.NetworkMask = '0.0.0.0'
            x.Gateway = '0.0.0.0'

        return x

    def _select_legacy_addr(self, prev, new):
        if new.family != socket.AF_INET:
            return False

        if new.addr_type == IPOrigin.DHCP:
            # Assume there's only one DHCP address. DHCP address has highest preference.
            # DHCP address overrides any previously selected address, including Static.
            return True
        elif new.addr_type == IPOrigin.Manual:
            # Select statically configured address only if there were no other address
            # selected. Static address will not override previously selected DHCP address
            if prev is None:
                return True

        return False

    def __str__(self):
        l = []
        l.append("<EthernetInterface: {}".format(self.iid))

        for f in dir(self):
            v = getattr(self, f)
            if f.startswith("_") or callable(v):
                continue
            if f in ['primary', 'master']:
                l.append("\t{}: {}".format(f, repr(v)))
            else:
                l.append("\t{}: {}".format(f, str(v)))

        l.append(">")
        return "\n".join(l)


class NetManager(object):

    def __init__(self, ipthread, teamthread, perfstat):
        self.ipthread = ipthread
        self.team = teamthread
        self.perfstat = perfstat
        self.log = logging.getLogger("netmng")
        self.config = Config()
        self.ports = {}
        self.autoneg = AutoNegParamHnd()
        self.dhcp = DHCPClientHnd()
        self.revert_called = False

    def join(self, timeout=None):
        pass

    def shutdown(self):
        pass

    @property
    def ip(self):
        return self.ipthread.ip

    def configure_bridge_params(self, name, silent_errors=False):
        sysfs_data = [
            ("stp_state", "0"),                 # disable STP
            ("forward_delay", "0"),             # set STP forward delay after port gets activated
            ("multicast_querier", "0"),         # do not become IGMP querier
            ("multicast_snooping", "0"),        # disable IGMP snooping completely
            ("multicast_router", "2"),          # ports will always receive all multicast traffic
        ]

        sysfs.helper.set_net_bridge_params(name, sysfs_data, silent_errors)

    def find_port_by_id(self, iid):
        return self.ports.get(iid)

    def find_master_port_by_l3int(self, ifname):
        ports = self.get_ports_by_l3int(ifname)

        if len(ports) == 1:
            return ports[0]

        for port in ports:
            if port.master is None:
                return port
            if port.master:
                return port.master

        if len(ports) > 0:
            self.log.warning("master port not found, using fallback")
            return ports[0]

        return None

    def get_ports_by_l3int(self, ifname):
        if not self.ports:
            self.log.error("internal failure: ports is empty (called at init?)")
            return []

        ports = []
        for port in self.ports.itervalues():
            master = port.master if port.master else port
            if master.l3int_name == ifname:
                ports.append(port)
        return ports

    def get_iids_by_l3int(self, ifname):
        return [p.iid for p in self.get_ports_by_l3int(ifname)]

    def get_iid_by_eth(self, ifname):
        ports = [p.iid for p in self.ports.itervalues() if p.eth_port_name == ifname]
        if ports:
            return min(ports)
        return None

    def get_port_default_gateways(self, iid):
        port = self.find_port_by_id(iid)
        if not port:
            return []

        return [gw.ipaddr for gw in port.gateways]

    def guess_interface_type(self, interf):
        name = interf.ifname

        if self.team.is_managed_team(name):
            return 'team'

        if name in self.config.interf_name_to_nmi:
            return 'eth'

        #if name.startswith('net'):
        #    return 'bridge'

        return interf.kind

    def setup(self):

        changed = False
        self.ports = {}

        for iid, name in self.config.interf_nmi_to_name.iteritems():
            teamname = self.config.get_team_name_by_nmiid(iid)

            brname = self.config.get_br_name_by_nmiid(iid)

            if brname is None:
                # no bridge for this interface
                pass
            elif brname in self.ip.interfaces:
                # check setup is correct
                if self.ip.interfaces[teamname].index not in self.ip.interfaces[brname].ports:
                    with self.ip.interfaces[brname].nobarrier() as i:
                        self.log.info("Adding '{}' to '{}'".format(teamname, brname))
                        i.add_port(self.ip.interfaces[teamname])
                        changed = True
            else:
                self.log.info("Creating bridge '{}'".format(brname))
                with self.ip.create(kind='bridge', ifname=brname).nobarrier() as i:
                    self.log.info("Adding '{}' to '{}'".format(teamname, brname))
                    i.add_port(self.ip.interfaces[teamname])
                    changed = True

            # always set parameters at startup, but setting some parameters
            # may fail, we ignore all errors here because parameters will
            # be set again when interface will be up
            if brname is not None:
                self.configure_bridge_params(brname, silent_errors=True)

            port = EthernetInterface(self, iid)
            self.ports[iid] = port

            # Disable Link-Local address generation, RA receive and
            # probably other high-level IPv6 protocol handling
            # on underlying interfaces. IPv6 should be handled by
            # top-level net* interfaces only
            sysfs.helper.disable_interface_ipv6(name)
            if brname is not None:
                sysfs.helper.disable_interface_ipv6(teamname)

        # create ip rules for tables with unrechable routes
        self.ipthread.create_unreach_rules(self.ports.keys())

        if changed:
            self.ipthread.barrier()


    def check_setup(self):
        # Network setup sanity check.
        # Check that bridges are there and have teams as their interfaces
        #
        # Sometimes bridge loses its team port when bringing team interface
        # down (not sure), so re-add it after reconfiguration and log a warning
        #

        # small delay to sync and update pyroute status
        self.ipthread.barrier()
        changed = False

        for iid, name in self.config.interf_nmi_to_name.iteritems():
            teamname = self.config.get_team_name_by_nmiid(iid)
            brname = self.config.get_br_name_by_nmiid(iid)

            if brname is None:
                # no bridge for this interface
                pass
            elif brname in self.ip.interfaces:
                # check setup is correct
                try:
                    if self.ip.interfaces[teamname].index not in self.ip.interfaces[brname].ports:
                        with self.ip.interfaces[brname].nobarrier() as i:
                            self.log.warning("Re-adding '{}' to '{}'".format(teamname, brname))
                            i.add_port(self.ip.interfaces[teamname])
                            changed = True
                except:
                    self.log.exception("Exception while trying to fix network config for {}".format(brname))
            else:
                self.log.error("Bridge {} disappeared ?".format(brname))
                # XXX TODO quit ?

        if changed:
            self.ipthread.barrier()

    def update_delay_up(self, iids=None):

        if iids is None:
            iids = self.ports.keys()

        for iid in iids:
            if iid in self.ports:
                port = self.ports[iid]

                if (port.redundancy_type != RedundancyType.NONE and
                    port.redundancy_mode == RedundancyMode.AUTOMATIC_REVERT and
                    len(port.follower_keys) > 0):
                    # check if there's any port with link up

                    teamports = [port] + [self.ports[s] for s in port.slaves]

                    have_carrier = any([p.have_carrier for p in teamports])

                    teamnames = set([p.team_name for p in teamports])

                    if have_carrier:
                        delay_up = CurrentDefaultDelay
                        self.log.info("Enabling delay_up for {}".format(teamnames))
                    else:
                        delay_up = 0
                        self.log.info("Disabling delay_up for {}".format(teamnames))

                    for teamname in teamnames:
                        self.team.set_delay_up(teamname, delay_up=delay_up)


    def team_status_changed(self):
        self.refresh_interface_routes()
        self.update_delay_up()

    def get_net_info(self, as_obj=False, nocache=False):
        for iid, port in self.ports.iteritems():
            port.reload_system_ips()

        # NOTE: caching is broken because to redundancy
        # work as expected all slave interfaces should be
        # updated at the same time. This is needed to avoid
        # the following situation:
        #  - interface 1 has same state, redundancy state is same
        #    too because it's not known yet if interface 2 needs
        #    to be updated or not and treated as one with actual
        #    data;
        #  - when on a next iteration it is known that interface 2 state
        #    has changed, redundancy recalc is triggered,
        #    but data returned for interface 1 won't be changed so
        #    state of both ports will be inconsistent
        #
        # Always do updates for now.

        if True or nocache:
            # update all ports status first, and redundancy
            # after that because it depends on other ports state

            updated = False
            for port in self.ports.itervalues():
                port_upd = port.update()
                updated = updated or port_upd
            if updated:
                for port in self.ports.itervalues():
                    port.force_update_redundancy()

        res = {}
        for iid, port in self.ports.iteritems():
            cpi_eth = NetworkInterfaceInfo()
            cpi_eth.init_from_ethernet_interface(port)

            if as_obj:
                res[iid] = cpi_eth
            else:
                # xml-rpc requires keys to be strings
                res[str(iid)] = cpi_eth.get_dict()

        return res

    def get_configuration(self):

        for iid, port in self.ports.iteritems():
            port.reload_system_ips()

        res = []
        for iid, port in self.ports.iteritems():
            res.append(port.get_xmlobj())

        return res

    def configure(self, xmlobj):
        try:
            self.team.prioritize_important_events(False)
            return self.configure_ethernet_model(xmlobj)
        finally:
            self.team.prioritize_important_events(True)
            self.revert_called = False

    def configure_dhcp(self, family, ifname, ip=None, gateway=None, expire=False):

        if family != socket.AF_INET:
            self.log.warning("Not supported protocol '{}' for DHCP configuration on port {}".format(proto, ifname))
            return False

        port = self.find_master_port_by_l3int(ifname)
        if port is None:
            self.log.warning("Interface name {} not found in current configuration".format(ifname))
            return False

        if not port.enable_dhcp:
            self.log.warning("DHCP is disabled on interface {}, ignoring callback")
            return False

        if expire:
            dhcp_status = DHCPStatus.FAIL
        elif ip:
            dhcp_status = DHCPStatus.OK
        else:
            dhcp_status = DHCPStatus.UNKNOWN

        updated = port.update_dhcp_addr(dhcp_status, family, ip, gateway)

        if updated:
            self.interface_l3setup(port)
            self.interface_route_setup(port)

        return updated

    def revert_to_primary(self, ids=None):

        ports = self.ports

        if ids is None:
            ids = ports.keys()

        select_ports = {}

        for iid in ids:
            port = ports.get(iid)

            # port is enabled and has slaves
            if not port or not port.enabled or not port.slaves:
                continue

            # check port status and configuration
            if port.redundancy_status != RedundancyStatus.INACTIVE:
                continue
            # revert only in Automatic mode, NMX does not expect
            # device-driven reverts in Manual Revert modes
            if port.redundancy_mode != RedundancyMode.AUTOMATIC:
                continue

            port_list = select_ports.setdefault(port.redundancy_type, [])
            port_list.append(port)

        if RedundancyType.ACTIVE_STANDBY in select_ports:
            for port in select_ports[RedundancyType.ACTIVE_STANDBY]:
                self.revert_called = True
                self.team_select_port(port)

        if RedundancyType.ACTIVE_ACTIVE in select_ports:
            for port in select_ports[RedundancyType.ACTIVE_ACTIVE]:
                self.revert_called = True
                self.redundancy_hnd_select_port(port)

    def port_select_and_redundancy_change(self, ports_old, ports_new):

        for iid in ports_new.keys():
            old = ports_old.get(iid)
            new = ports_new.get(iid)

            if not new:
                continue

            if (new.redundancy_type == old.redundancy_type and new.redundancy_mode == old.redundancy_mode and
                new.enabled and old.enabled):
                # IsManualPrimaryPort selects port only if its value
                # has changed
                old_manual_primary = old.manual_primary if old else None
                if new.manual_primary and (old_manual_primary is None or not old_manual_primary or self.revert_called):
                    new.select_port = True

                # Try to keep redundancy_data across reconfiguration to e.g. avoid
                # unnecessary redundancy switch events
                new.redundancy_data_prev = old.redundancy_data
            else:
                new.select_port = new.manual_primary

    def preserve_routes(self, ports_old, ports_new):

        for iid in ports_new.keys():
            old = ports_old.get(iid)
            new = ports_new.get(iid)

            if not new:
                continue

            new.routes = old.routes

    def configure_ethernet_model(self, conf):
        ports = {}

        configured = []
        for portcfg in conf:
            iid = portcfg.PortIdentifier

            if iid not in self.config.interf_nmi_to_name:
                self.log.warning("ignoring interface {}".format(iid))
                continue

            if iid in configured:
                self.log.warning("ignoring non-uniqe interface {}".format(iid))
                continue

            port = EthernetInterface(self, iid)
            port.load_from_xmlobj(portcfg)

            ports[iid] = port
            configured.append(iid)

        # keep other ports as is
        for port_iid in self.ports.keys():
            if port_iid not in configured:
                ports[port_iid] = self.ports[port_iid]

        self.port_select_and_redundancy_change(self.ports, ports)
        self.preserve_routes(self.ports, ports)

        try:
            self.configure_ports(ports)
            self.ports = ports
        finally:
            self.check_setup()

    def _remove_missing_ports(self, ports):

        def rmmissing(iids):

            missing = []
            for iid in iids:
                if iid not in ports:
                    missing.append(iid)

            if missing:
                self.log.warning("Found references to missing ports {}".format(missing))
                res = list(iids)
                for iid in missing:
                    res.remove(iid)
                return res

            # nothing changed
            return iids

        for port in ports.itervalues():
            port.ifslaves = rmmissing(port.ifslaves)
            port.slaves = rmmissing(port.slaves)

    def _setup_ports_hierarchy(self, ports, hard_slaves=True):
        """
        This function has side-effects on @ports - sets hierarchy-related
        propertries: port.master or port.primary
        """
        class _Team:
            def __init__(self, port):
                self._team_name = port.team_name
                self.port = port
                self.slaves = [port]

            if hard_slaves:
                @property
                def teamname(self):
                    return self._team_name
            else:
                @property
                def teamname(self):
                    raise Exception()

        if hard_slaves:
            def get_slaves(_port):
                return _port.ifslaves

            def set_primary(_slave, _port):
                _slave.master = _port
        else:
            def get_slaves(_port):
                return _port.slaves

            def set_primary(_slave, _port):
                _slave.primary = _port


        teams = {}
        all_teams = []

        # wrap all ports into _Team() class
        for iid, p in ports.iteritems():
            team = _Team(p)
            all_teams.append(team)
            teams[iid] = team

        # move slave ports to appropriate masters/primaries
        for iid in list(teams.keys()):
            if iid not in teams:
                continue

            for slave_iid in get_slaves(teams[iid].port):
                slave = teams[slave_iid].port
                set_primary(slave, teams[iid].port)
                teams[iid].slaves.append(slave)
                del teams[slave_iid]


        return all_teams, teams

    def propagate_from_primary(self, master, ports):
        # Copy some propetries from master to slave ports
        # Caled for every logical group (teamed and not)
        for port in ports:
            if port == master:
                continue
            port.enabled = master.enabled
            port.redundancy_type = master.redundancy_type
            port.redundancy_mode = master.redundancy_mode

    def redundancy_hnd_select_port(self, port):
        self.log.info("Selecting port '{}' as active".format(port.l3int_name))
        port.redundancy_handler.set_active(port)
        self.team.handle_new_team_status()

    def team_select_port(self, port):
        name = port.eth_port_name
        self.log.info("Selecting port '{}' as active".format(name))
        self.team.set_port_active(name)
        time.sleep(0.1)
        self.team.port_signal_update(name)

    def configure_ports(self, ports):

        self._remove_missing_ports(ports)

        # get logical hierarchy and set 'primary'
        log_orphaned, log_teams = self._setup_ports_hierarchy(ports, hard_slaves=False)
        del log_orphaned

        # set peers property
        for team in log_teams.itervalues():
            for interf in team.slaves:
                interf.peers = [p.iid for p in team.slaves if p != interf]

        # set redundancy handler for active-active type
        for team in log_teams.itervalues():
            if team.port.redundancy_type == RedundancyType.ACTIVE_ACTIVE:
                for interf in team.slaves:
                    interf.set_redundancy_handler(RedundancyHandlerActAct())
            self.propagate_from_primary(team.port, team.slaves)

        # get hierarchy and set 'master'
        orphaned, teams = self._setup_ports_hierarchy(ports, hard_slaves=True)

        # (re)enslave interfaces as needed
        for team in teams.itervalues():
            orphaned.remove(team)

            redundancy_type = team.port.redundancy_type
            team_ifidx = self.ip.interfaces[team.teamname].index

            enslave_ifs = []
            for interf in team.slaves:
                eth_interf = self.ip.interfaces[interf.eth_port_name]
                if 'master' not in eth_interf or eth_interf.master != team_ifidx:
                    self.interface_clear_free(eth_interf)
                    enslave_ifs.append((team.teamname, interf.eth_port_name))

            if enslave_ifs:
                # wait for interfaces go go down after cleanup
                time.sleep(0.5)
                for tname, ename in enslave_ifs:
                    self.log.info("Adding interface {} to team {}".format(ename, tname))
                    self.team.add_port(tname, ename)
                # and wait for teamd to process netlink events
                time.sleep(0.5)

            portnames, new_active = find_primary_selected(team.port,
                list(team.slaves), lambda p: p.eth_port_name)

            mode = None
            delay_up = 0
            if redundancy_type == RedundancyType.ACTIVE_STANDBY:
                mode = team.port.redundancy_mode
                if mode == RedundancyMode.DUAL:
                    # invalid mode
                    mode = None
                if mode == RedundancyMode.AUTOMATIC_REVERT:
                    delay_up = self.config.ar_delay_up
            elif redundancy_type == RedundancyType.ACTIVE_ACTIVE:
                # Every port configured like a single
                mode = TeamModes.SINGLE
                if team.port.redundancy_mode == RedundancyMode.AUTOMATIC_REVERT:
                    delay_up = self.config.ar_delay_up
            else:
                # no redundancy
                mode = TeamModes.SINGLE

            if mode is None:
                self.log.error("Unexpected redundancy type/mode {}/{}".format(team.port.redundancy_type, team.port.redundancy_mode))
                mode = TeamModes.SINGLE

            #self.log.debug("Configuring team {} ({}): {}".format(team.teamname, portnames, mode))
            self.team.configure_ports_mode(team.teamname, portnames, mode, delay_up=delay_up)

            # set active, if requested, and trigger failover selection
            if team.port.enabled and new_active and redundancy_type == RedundancyType.ACTIVE_STANDBY:
                self.team_select_port(new_active)


        # setup IP addresses
        for team in teams.itervalues():
            if team.port.enabled:
                for interf in team.slaves:
                    self.autoneg.set_interf_mode(interf.eth_port_name, interf.link_mode)

                # need at least bring interfaces up even if DHCP is enabled
                self.interface_l3setup(team.port)
                self.interface_route_setup(team.port, ports=ports)

                self.dhcp.set_interf_dhcp(team.port.l3int_name, team.port.enable_dhcp, renew=True)

                # sometimes lower interfaces aren't brought up automatically,
                # so check they're enabled
                for interf in team.slaves:
                    down_to_up = False
                    with self.ip.interfaces[interf.eth_port_name].nobarrier() as i:
                        if not (i.flags & IFF_UP):
                            down_to_up = True
                        self._interface_updown(i, up=True)

                    if self.config.bridged:
                        # For some reason the link-up action done above gets lost when
                        # flags are changed too under the same "with" section.
                        with self.ip.interfaces[interf.eth_port_name].nobarrier() as i:
                            # Set ALLMULTICAST flag on underlaying eth* interfaces.
                            #
                            # This is a workaround for receiving multicast streams, looks
                            # like that for some reason multicast membership does not
                            # propagate its filters from bridges to underlaying interfaces
                            i.flags |= IFF_ALLMULTI

                    # if there are multiple slave interfaces that are believed to be down,
                    # then insert a small delay to sequence interface link up except
                    # for the last interface in the list
                    if down_to_up and interf != team.slaves[-1]:
                        time.sleep(0.3)

            elif self.config.down_lower_only:
                # Workaround for ACP, don't ifdown net* interfaces and leave assigned static IPs.
                # Disable eth* interfaces and remove routes.
                self.log.info("Disabling port {} lower layer".format(team.port.iid))

                self.dhcp.set_interf_dhcp(team.port.l3int_name, False)

                for slave in team.slaves:
                    self.interface_disable(slave, skipl3=True)
                for p in [team.port] + team.slaves:
                    self.interface_route_setup(p, ports=ports)

            else:
                self.log.info("Disabling port {}".format(team.port.iid))
                self.dhcp.set_interf_dhcp(team.port.l3int_name, False)
                self.interface_disable(team.port)
                for slave in team.slaves:
                    self.interface_disable(slave)
                for p in [team.port] + team.slaves:
                    self.interface_route_setup(p, ports=ports)

        for team in teams.itervalues():
            self.team.set_delay_up(team.teamname, delay_up=CurrentDefaultDelay)

        #print("orphaned: ", orphaned)
        # cleanup other interfaces
        for team in orphaned:
            self.log.info("Disabling orphaned port {}".format(team.port.iid))
            self.dhcp.set_interf_dhcp(team.port.l3int_name, False)
            # L2 interface may be teamed with other port, leave it alone
            self.interface_disable(team.port, skipl2=True)
        for team in orphaned:
            self.interface_route_setup(team.port, ports=ports)

        self.ipthread.barrier()

    def refresh_interface_routes(self, iids=None):
        if iids is None:
            iids = self.ports.iterkeys()

        for iid in sorted(iids):
            if iid in self.ports:
                self.interface_route_setup(self.ports[iid])

    @classmethod
    def _get_as_redundant_ports_list(klass, ports, port):
        master = port.master if port.master else port
        res = [master]
        for iid in master.ifslaves:
            res.append(ports[iid])
        return res

    @classmethod
    def _get_route_status(klass, ports, port):

        if port.is_port_role(PortRole.MANAGEMENT):
            # Managent port routes are always active
            status = RouteStatus.ACTIVE
            return status

        if port.redundancy_type == RedundancyType.ACTIVE_STANDBY:
            # for teamed redundancy use redundancy status of all intrerfaces
            # and check if at least one of them is active
            carrier = False
            for p in klass._get_as_redundant_ports_list(ports, port):
                if p.redundancy_status in [RedundancyStatus.ACTIVE, RedundancyStatus.ACTIVE_DUAL]:
                    carrier = True
                    break
        else:
            carrier = port.have_carrier

        # remove routes if down, default
        status = RouteStatus.INACTIVE

        if carrier and port.enabled:
            status = RouteStatus.ACTIVE
        elif port.is_port_role(PortRole.APPLICATION):
            # block traffic if ports are down
            status = RouteStatus.BLOCKED

        return status

    @classmethod
    def _get_port_routes(klass, ports, port):
        # for teamed redundancy collect routes from
        # all teamed interfaces

        if port.redundancy_type == RedundancyType.ACTIVE_STANDBY:
            routes = []
            for p in klass._get_as_redundant_ports_list(ports, port):
                routes.extend(p.routes.get_route_list())
            return routes
        else:
            return port.routes.get_route_list()

    def interface_route_setup(self, port, ports=None):
        default_metric = 7000
        origin_metric_base = {
            "gateway": 5000,
            "user": 3000,
            "controller": 1000,
        }

        def calc_metric(origin):
            metric_base = origin_metric_base.get(origin, default_metric)
            return metric_base + port.iid * 10

        if port.master:
            # skip team slaves
            return

        if ports is None:
            ports = self.ports

        self.log.info("Updating routes on interface {}".format(port.l3int_name))

        routes = [self.ipthread.Entry(None, gw, calc_metric("gateway")) for gw in port.gateways]

        # unreachable routes go to other routing tables AND they dont have destination
        # interface associated with them, so set_interface_routes() on any interface
        # will "see" unreachable routes and, most likely, will remove them.
        unreachables = []

        route_status = self._get_route_status(ports, port)
        port.routes.last_status = route_status

        if route_status == RouteStatus.ACTIVE:
            for r in self._get_port_routes(ports, port):
                routes.append(self.ipthread.Entry(r.prefix.get_network(), r.gateway, calc_metric(r.origin)))
        elif route_status == RouteStatus.BLOCKED:
            for r in self._get_port_routes(ports, port):
                unreachables.append(self.ipthread.Entry(r.prefix.get_network(), RouteUnreachable, calc_metric(r.origin)))

            for prefix in port.ip_addresses:
                if not prefix.is_link_local():
                    unreachables.append(self.ipthread.Entry(prefix.get_network(), RouteUnreachable, calc_metric("default")))
        else: # RouteStatus.INACTIVE:
            pass

        self.ipthread.set_interface_routes(port.l3int_name, routes, default_metric)

        unreach_table = self.ipthread.UNREACH_BASE + port.iid
        self.ipthread.set_interface_routes(port.l3int_name, unreachables, default_metric, table=unreach_table)

    def configure_flush_routes(self, origin, iids=None):

        if iids is None:
            iids = self.ports.keys()

        for iid in iids:
            if iid in self.ports:
                self.ports[iid].routes.flush(origin)

        self.refresh_interface_routes(iids)

    def _find_gateway_for_route(self, route):
        if route.prefix is None:
            return None

        port = self.ports.get(route.iid)
        if port is None:
            return None

        family = route.prefix.family

        for gw in port.gateways:
            if gw.family == family:
                return EthernetIP(gw.ipaddr)

        return EthernetIP("0.0.0.0")

    def _find_port_with_route_prefix(self, origin, robj):
        for iid in sorted(self.ports.iterkeys()):
            for route in self.ports[iid].routes.get(origin):
                if route.prefix == robj.prefix:
                    if robj.gateway is not None and route.gateway != robj.gateway:
                        continue
                    elif robj.gateway is None:
                        robj.gateway = deepcopy(route.gateway)
                    robj.iid = iid
                    return True
        return False

    def configure_routes(self, oper, origin, dict_routes):

        auto_interface = (oper == "remove")

        routes = {}
        for r in dict_routes:
            robj = IfRoute.from_dict(origin, r)
            if robj.gateway is None:
                # find some gateway or fallback to link-local
                robj.gateway = self._find_gateway_for_route(robj)

            if robj.iid == 0 and auto_interface:
                # port_id 0 is for routes without iid specified, e.g.
                # only prefix can be set. Try to find matching route
                # at all ports
                if not self._find_port_with_route_prefix(origin, robj):
                    continue

            rlist = routes.setdefault(robj.iid, [])
            rlist.append(robj)

        updated = []
        for iid, rlist in routes.iteritems():
            if not iid in self.ports:
                continue
            self.ports[iid].routes.update(oper, rlist, origin=origin)
            updated.append(iid)

        # clear routes on other interfaces
        if oper == "set":
            for iid in self.ports.iterkeys():
                if iid not in updated:
                    self.ports[iid].routes.flush(origin)

        self.refresh_interface_routes()

    def get_route_configuration_full(self):
        conf = {}
        for iid, port in self.ports.iteritems():
            for origin, routes in port.routes.get_all().iteritems():
                oroutes = conf.setdefault(origin, [])
                oroutes.extend([r.to_dict() for r in routes])
        return conf

    def get_route_configuration(self, origin):
        routes = []
        for iid, port in self.ports.iteritems():
            for r in port.routes.get(origin):
                routes.append(r.to_dict())
        return routes

    def interface_disable(self, port, skipl2=None, skipl3=False):
        if skipl2 is None:
            skipl2 = not self.config.link_down_eths

        if not skipl3:
            self.interface_flush(self.ip.interfaces[port.l3int_name])

        if port.l3int_name != port.team_name:
            self.interface_flush(self.ip.interfaces[port.team_name])
        if not skipl2 and port.l3int_name != port.eth_port_name:
            self.interface_flush(self.ip.interfaces[port.eth_port_name])

    def interface_flush(self, ipinterf, do_down=True):
        with ipinterf.nobarrier() as i:
            if do_down:
                self._interface_updown(i, down=True)

            for ipmask in list(i.ipaddr):
                if self.is_ipaddr_link_local(ipmask[0], ipmask[1]):
                    continue
                self.log.info("Removing IP {}/{} from interface {}".format(ipmask[0], ipmask[1], ipinterf.ifname))
                i.del_ip(ipmask[0], mask=ipmask[1])

    def interface_clear_free(self, interf):
        if 'master' not in interf or interf.master is None:
            self.log.info("Removing interface {} not teamed {}".format(interf.ifname, interf)) ## XXX debug
            return self.interface_flush(interf)

        master = self.ip.by_index[interf.master]
        kind = self.guess_interface_type(master)

        if kind == 'team':
            teamname = master.ifname
            self.log.info("Removing interface {} from team {}".format(interf.ifname, teamname))
            self.team.remove_port(teamname, interf.ifname)
            self.interface_flush(interf)
        elif kind == 'eth':
            self.log.error("Invalid interface {} master {} kind: {}".format(interf.ifname, master.ifname, master.kind))
        else:
            raise Exception("unknown interface {} master {} kind: {}".format(interf.ifname, master.ifname, master.kind))

    def is_ipaddr_link_local(self, addr, plen):
        eip = EthernetIP(addr, plen)
        return eip.is_link_local()

    def _interface_updown(self, interf, down=False, up=False):
        # pyroute2, being asyncronous, presumably may miss or delay
        # its internal interface status, resulting in incorrect
        # behavior here. For example. if interface is UP, but
        # pyroute2's flags show that interface is DOWN, down()
        # will not be called here, and the next interface enslave
        # to team interface will fail becase it can add interface
        # only in DOWN state.
        #
        # One possible way to avoid repeating down()s and up()s is
        # to use ioctl() synchronous call to determine interface
        # state, but the same problem of mismatched states may
        # raise elsewhere, so just force required interface state
        # independently of the state interface may appear to be in.

        assert(down or up)

        def strstate(f):
            return "up" if f else "down"

        cached_state = interf.flags & IFF_UP

        if down:
            interf.down()
            is_up = False

        if up:
            interf.up()
            is_up = True

        self.log.info("Bringing interface {} {} (likely was: {})".format(interf.ifname, strstate(is_up), strstate(cached_state)))

    def interface_l3setup(self, port):
        interf = self.ip.interfaces[port.l3int_name]

        # XXX fixme: can't really compare IPv6 addresses as a strings
        # because of possible different representation
        add = [(i.ipaddr, i.plen) for i in port.ip_addresses if i.is_valid_interface_ip()]
        remove = []

        for ipmask in interf.ipaddr:
            if ipmask in add:
                add.remove(ipmask)
            elif self.is_ipaddr_link_local(ipmask[0], ipmask[1]):
                self.log.debug("Ignoring link-local IP {}/{} on interface {}".format(ipmask[0], ipmask[1], port.l3int_name))
            else:
                # remove any non-link-local addresses
                remove.append(ipmask)

        with interf.nobarrier() as i:
            for ip in add:
                self.log.info("Adding IP {}/{} to interface {}".format(ip[0], ip[1], port.l3int_name))
                i.add_ip(ip[0], mask=ip[1])
            for ip in remove:
                self.log.info("Removing IP {}/{} from interface {}".format(ip[0], ip[1], port.l3int_name))
                i.del_ip(ip[0], mask=ip[1])

            self._interface_updown(i, up=True)

        # some parameters can be changed if interface is up
        brname = self.config.get_br_name_by_nmiid(port.iid)
        if brname:
            self.configure_bridge_params(brname)

        with self.ip.interfaces[port.team_name].nobarrier() as i:
            self._interface_updown(i, up=True)

