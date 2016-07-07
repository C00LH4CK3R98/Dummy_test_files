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
import Queue
import select
import errno
import subprocess
import json
queue = Queue # python 3
from enum import Enum

#__all__ = []

class NMIEventBase(object):
    order = 1000
    source = "Platform"
    is_event = False
    merge = False
    defobj = None

    def __init__(self, obj=None, **params):
        self.obj = obj if obj is not None else self.defobj
        self.params = params

    def __str__(self):
        return "<NMIEvent {}: '{}' '{}' obj:{} params:{}>".format(self.name, self.title, self.desc, self.obj,
            str(self.params))


class Harmonic_NetworkIFDownIndication(NMIEventBase):
    order = 100
    name = "Harmonic_NetworkIFDownIndication"
    title = "Network Interface Link Down"
    desc = "Network interface %NetworkIFNumber is down"
    level = "CRIT"
    need = ('NetworkIFNumber', 'isTeamingPort', 'PlatformObjectID')


class Harmonic_VideoOverIPPortDown(NMIEventBase):
    order = 200
    name = "Harmonic_VideoOverIPPortDown"
    title = "Video Over IP Port Down"
    desc = "Video Over IP Port Down"
    level = "CRIT"


class Harmonic_VideoOverIPPortDown_Inactive(NMIEventBase):
    order = 200
    name = "Harmonic_VideoOverIPPortDown"
    title = "Video Over IP Port Down"
    desc = "Video Over IP Port Down. Network interface %NetworkIFNumber is inactive"
    level = "CRIT"


class Harmonic_VideoOverIPPortDown_Interface(NMIEventBase):
    order = 200
    name = "Harmonic_VideoOverIPPortDown"
    title = "Video Over IP Port Down"
    desc = "Video Over IP Port Down. Network interface %NetworkIFNumber is down"
    level = "CRIT"


class Harmonic_VideoOverIPPortDown_Address(NMIEventBase):
    order = 200
    name = "Harmonic_VideoOverIPPortDown"
    title = "Video Over IP Port Down"
    desc = "Video Over IP Port Down. Invalid address configured on interface %NetworkIFNumber"
    level = "CRIT"


class Harmonic_VideoOverIPPortDown_DHCP(NMIEventBase):
    order = 200
    name = "Harmonic_VideoOverIPPortDown"
    title = "Video Over IP Port Down"
    desc = "Video Over IP Port Down. DHCP failed on interface %NetworkIFNumber"
    level = "CRIT"


class Harmonic_NetworkAddressFailIndication(NMIEventBase):
    name = "Harmonic_NetworkAddressFailIndication"
    title = "Failed to set IP address"
    desc = "Failed to set IP address on interface %NetworkIFNumber"
    level = "CRIT"
    need = ('NetworkIFNumber', 'PlatformObjectID')


class Harmonic_NetworkAddressFailIndication_DHCP(NMIEventBase):
    name = "Harmonic_NetworkAddressFailIndication"
    title = "Failed to acquire IP address"
    desc = "Failed to acquire IP address on port %NetworkIFNumber"
    level = "CRIT"
    need = ('NetworkIFNumber', 'PlatformObjectID')


class Harmonic_NICTeamingSlaveChannelActivated(NMIEventBase):
    name = "Harmonic_NICTeamingSlaveChannelActivated"
    title = "NIC Teaming Slave Port Activated"
    desc = "Backup network interface %NICTeamingName port %ethernetPortNum is activated"
    level = "WARN"
    need = ('ethernetPortNum', 'NICTeamingName', 'PlatformObjectID')


class Harmonic_NICTeamingDown(NMIEventBase):
    name = "Harmonic_NICTeamingDown"
    title = "NIC Teaming Down"
    desc = "Teamed interface %NICTeamingName is down"
    level = "CRIT"
    need = ('AssetingPortNum', 'NICTeamingName', 'FirstPortNum', 'SecondPortNum', 'EnforcePortPriority')


class Harmonic_NICTeamingDown_PortRedundancy(NMIEventBase):
    name = "Harmonic_NICTeamingDown"
    title = "NIC Redundant Down"
    desc = "Redundant port interface %NICTeamingName is down"
    level = "CRIT"
    need = ('AssetingPortNum', 'NICTeamingName', 'FirstPortNum', 'SecondPortNum', 'EnforcePortPriority')


class Harmonic_NICTeamingPortStateChanged(NMIEventBase):
    name = "Harmonic_NICTeamingPortStateChanged"
    title = "NIC Teaming Port State Changed"
    desc = "Teamed interface %NICTeamingName port %ethernetPortNum state changed from %PreviousState to %CurrentState"
    level = "WARN"
    need = ('ethernetPortNum', 'NICTeamingName', 'PreviousState', 'CurrentState')
    is_event = True


class Harmonic_StoragePortDown(NMIEventBase):
    name = "Harmonic_StoragePortDown"
    title = "Storage Port Down"
    desc = "All active storage ports are down"
    level = "CRIT"
    merge = True


class Harmonic_LinkSpeedChanged(NMIEventBase):
    name = "Harmonic_LinkSpeedChanged"
    title = "Link Speed Changed"
    desc = "Interface %NICTeamingName port %ethernetPortNum speed changed from %PreviousState to %CurrentState"
    level = "WARN"
    need = ('ethernetPortNum', 'NICTeamingName', 'PreviousState', 'CurrentState')


class Harmonic_Internal_IPConfigurationChanged(NMIEventBase):
    # This event is special and handled separately from others.
    # Event should be dispatched right after reconfiguration
    # independent of alarms, etc.
    name = "Harmonic_Internal_IPConfigurationChanged"
    title = "IP configuration changed"
    desc = "IP configuration changed"
    level = "MAJOR"
    source = "NMI"
    defobj = "NMI"
    is_event = True
