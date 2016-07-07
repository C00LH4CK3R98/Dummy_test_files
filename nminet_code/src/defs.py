#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2015 Harmonic Corporation, all rights reserved
#

from __future__ import print_function

import logging
import socket
import struct
from enum import Enum


class TeamModes(Enum):
    SINGLE = 1
    AUTOMATIC = 2
    AUTOMATIC_REVERT = 3
    MANUAL = 4
    MANUAL_REVERT = 5
    DUAL = 6


class PortStatus(Enum):
    CONNECTED = 0
    DISABLED = 1
    MEDIA_DISCONNECTED = 2


class RedundancyType(Enum):
    NONE = 0
    ACTIVE_STANDBY = 1
    ACTIVE_ACTIVE = 2


class RedundancyMode(Enum):
    AUTOMATIC = 0               # Automatic
    AUTOMATIC_REVERT = 1        # Automatic Revert
    MANUAL = 2                  # Manual Revert
    MANUAL_NOFAILOVER = 3       # Manual
    DUAL = 4                    # Dual


class RedundancyStatus(Enum):
    NOT_ENABLED = 0
    ACTIVE = 1
    INACTIVE = 2
    DISCONNECTED = 3
    ACTIVE_DUAL = 4


class AutoNegotiate(Enum):
    AUTO_NEGOTIATE = 0
    FORCE_TENG_FULL = 1
    FORCE_ONEG_FULL = 2
    FORCE_HUNDM_FULL = 3
    OTHER = 4


class IPOrigin(Enum):
    Unknown = 0
    Manual = 1
    DHCP = 2
    LinkLocal = 3
    RouterAdvertisement = 4


class DHCPStatus(Enum):
    UNKNOWN = 0
    OK = 1
    FAIL = 2


class RouteStatus(Enum):
    ACTIVE = 0
    INACTIVE = 1
    BLOCKED = 2


class PortRole(Enum):
    DATA = 0
    MANAGEMENT = 1
    APPLICATION = 2


