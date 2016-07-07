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

from alarm_types import *
from util import *
from defs import *
from config import *

__all__ = ['AlarmHandlerSingle', 'AlarmHandlerActiveStandby']


class EventRedundancyPortState(Enum):
    NOT_ENABLED = 0     # used when redundancy initially configured or deconfigured
    DISABLED = 1        # never actually used
    ACTIVE = 2          # port is active
    INACTIVE = 3        # standby or disconnected


class AlarmHandlerBase(object):
    def __init__(self, alarm_proc):
        self.alarm_proc = alarm_proc
        self.event_proc = alarm_proc.event_proc
        self.config = Config()
        self.link_speed_counter = 0

    def check_interfaces(self, iflist):
        # group alarms are handled
        return True

    @property
    def log(self):
        return self.alarm_proc.log

    def link_speed_alarm(self, interf):
        # ACP-8134
        # Need to add an alarm for the case when network port change between 100Mbps and 1GBps

        # if previous state of link speed changed 3 times for last 10 seconds throw an alarm
        # DON"T know when to remit it though.

        prev = self.alarm_proc.get_prev_data(interf, same_mode=True)

        # New state
        current_link_speed = self.config.link_speed #??????

        # Counter for alarm emitting
        if prev != current_link_speed:
            self.link_speed_counter++  # add +1 to counter
            if timer not goes:
                timer start
            if self.link_speed_counter >= 10 && timer >= 100:
                evt = Harmonic_LinkSpeedChanged(ethernetPortNum=interf.nmi_id, NICTeamingName=interf.interface_name_l3,
                                            PreviousState=prev.name,
                                            CurrentState=current_link_speed.name)
                self.event_proc.alarm(evt, status)
                self.link_speed_counter = 0
                timer stop and 0

    def voip_down_alarm(self, interf, down=False, badaddr=False, dhcp_fail=False):

        if interf.nmi_id in self.config.management_ports:
            return

        # Harmonic_VideoOverIPPortDown
        if down:
            if interf.redundancy_status == RedundancyStatus.INACTIVE:
                evt = Harmonic_VideoOverIPPortDown_Inactive(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                                                            PlatformObjectID=interf.platform_object_id)
            else:
                evt = Harmonic_VideoOverIPPortDown_Interface(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                                                             PlatformObjectID=interf.platform_object_id)
            voip_status = True
        elif badaddr:
            evt = Harmonic_VideoOverIPPortDown_Address(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                PlatformObjectID=interf.platform_object_id)
            voip_status = True
        elif dhcp_fail:
            evt = Harmonic_VideoOverIPPortDown_DHCP(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                PlatformObjectID=interf.platform_object_id)
            voip_status = True
        else:   # default - for remit
            evt = Harmonic_VideoOverIPPortDown(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                PlatformObjectID=interf.platform_object_id)
            voip_status = False

        self.event_proc.alarm(evt, voip_status)
        return voip_status

    def address_fail_alarm(self, interf, badaddr=False, dhcp_fail=False):

        # Harmonic_NetworkAddressFailIndication
        if badaddr:
            evt = Harmonic_NetworkAddressFailIndication(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                PlatformObjectID=interf.platform_object_id)
            status = True
        elif dhcp_fail:
            evt = Harmonic_NetworkAddressFailIndication_DHCP(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                PlatformObjectID=interf.platform_object_id)
            status = True
        else:   # default - for remit
            evt = Harmonic_NetworkAddressFailIndication(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                PlatformObjectID=interf.platform_object_id)
            status = False

        self.event_proc.alarm(evt, status)
        return status

    def storage_port_down_alarm(self, interf, status):
        if interf.nmi_id not in self.config.application_ports:
            return

        evt = Harmonic_StoragePortDown(None, PlatformObjectID=self.config.chassis)
        self.event_proc.alarm(evt, status)

    _REDUNDANCY_STATE_TO_EVENT_MAP = {
        RedundancyStatus.NOT_ENABLED: EventRedundancyPortState.NOT_ENABLED,
        RedundancyStatus.ACTIVE: EventRedundancyPortState.ACTIVE,
        RedundancyStatus.INACTIVE: EventRedundancyPortState.INACTIVE,
        RedundancyStatus.DISCONNECTED: EventRedundancyPortState.INACTIVE,
        RedundancyStatus.ACTIVE_DUAL: EventRedundancyPortState.ACTIVE,
    }

    def _redundancy_state_to_event(self, state):

        ret = self._REDUNDANCY_STATE_TO_EVENT_MAP.get(state)
        if ret is not None:
            return ret

        return EventRedundancyPortState.NOT_ENABLED

    def _fire_team_change_event(self, interf, state_from, state_to):
        if state_from != state_to:
            self.event_proc.event(Harmonic_NICTeamingPortStateChanged(ethernetPortNum=interf.nmi_id,
                NICTeamingName=interf.interface_name_l3, PreviousState=state_from.name, CurrentState=state_to.name))

    def redundancy_event(self, interf):

        # ACP-4956
        # When redundancy configuration changed, emit events for "transitional"
        # state "NOT_ENABLED" to send new state to NMX for both ports.

        prev = self.alarm_proc.get_prev_data(interf, same_mode=True)

        if prev is None:
            # probably mode has changed, transition throught NOT_ENABLED state

            prev = self.alarm_proc.get_prev_data(interf)
            if prev is not None:
                prev_status = self._redundancy_state_to_event(prev.redundancy_status)
                redundancy_status = EventRedundancyPortState.NOT_ENABLED

                self._fire_team_change_event(interf, prev_status, redundancy_status)

            prev_status = EventRedundancyPortState.NOT_ENABLED

        else:
            # Same redundancy configuration, pickup previous state
            prev_status = self._redundancy_state_to_event(prev.redundancy_status)

        # New state
        redundancy_status = self._redundancy_state_to_event(interf.redundancy_status)

        # Harmonic_NICTeamingPortStateChanged
        self._fire_team_change_event(interf, prev_status, redundancy_status)

    def interf_badaddr(self, interf):
        return len([ip for ip in interf.all_ips if not ip.valid]) > 0

    def interf_dhcp_fail(self, interf):
        return (interf.enabled and
                interf.enable_dhcp and
                interf.status == PortStatus.CONNECTED and
                interf.dhcp_status == DHCPStatus.FAIL)


class AlarmHandlerSingle(AlarmHandlerBase):

    def check_interfaces(self, iflist):
        interf = iflist[0]

        interf_down = interf.enabled and interf.status == PortStatus.MEDIA_DISCONNECTED

        interf_badaddr = interf.enabled and self.interf_badaddr(interf)
        dhcp_fail = self.interf_dhcp_fail(interf)

        # Harmonic_NetworkIFDownIndication
        evt = Harmonic_NetworkIFDownIndication(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
            isTeamingPort=False, PlatformObjectID=interf.platform_object_id)

        self.event_proc.alarm(evt, interf_down)

        self.address_fail_alarm(interf, interf_badaddr, dhcp_fail)

        # Harmonic_VideoOverIPPortDown
        self.voip_down_alarm(interf, interf_down, interf_badaddr, dhcp_fail)

        # Harmonic_StoragePortDown
        self.storage_port_down_alarm(interf, interf_down or interf_badaddr or dhcp_fail)

        # Harmonic_NICTeamingPortStateChanged
        # send event about redundancy change if redundant pair was deconfigured
        self.redundancy_event(interf)

        return True


class AlarmHandlerActiveStandby(AlarmHandlerBase):

    TEAMED_INTERF_OBJ_BASE = 2119

    def check_interfaces(self, iflist):
        master = iflist[0]
        slaves = iflist[1:]
        slave = slaves[0] if len(slaves)>0 else master

        # assume all ports are same
        enabled = master.enabled

        team_badaddrs = []
        team_dhcp_fails = []

        def is_primary(i):
            return i.primary_port

        # Harmonic_NICTeamingPortStateChanged
        for interf in iflist:
            # send event about redundancy change, if needed
            self.redundancy_event(interf)

        # Harmonic_NICTeamingSlaveChannelActivated
        for interf in iflist:
            # ACP-4957 - need alarm for all modes except Dual if backup port activated

            slave_act_status = (not is_primary(interf) and
                interf.redundancy_status == RedundancyStatus.ACTIVE and
                enabled)

            evt = Harmonic_NICTeamingSlaveChannelActivated(interf.nmi_id,
                ethernetPortNum=interf.nmi_id, NICTeamingName=interf.interface_name_l3, PlatformObjectID=interf.platform_object_id)

            self.event_proc.alarm(evt, slave_act_status)


        for interf in iflist:
            interf_down = interf.enabled and interf.status == PortStatus.MEDIA_DISCONNECTED
            interf_badaddr = interf.enabled and self.interf_badaddr(interf)
            interf_dhcp_fail = self.interf_dhcp_fail(interf)

            # Harmonic_NetworkIFDownIndication
            evt = Harmonic_NetworkIFDownIndication(interf.nmi_id, NetworkIFNumber=interf.nmi_id,
                isTeamingPort=True, PlatformObjectID=interf.platform_object_id)
            self.event_proc.alarm(evt, interf_down)

            self.address_fail_alarm(interf, interf_badaddr, interf_dhcp_fail)

            team_badaddrs.append(interf_badaddr)
            team_dhcp_fails.append(interf_dhcp_fail)

        # Harmonic_NICTeamingDown
        team_down = enabled
        if team_down:
            for interf in iflist:
                if interf.redundancy_status in [RedundancyStatus.ACTIVE, RedundancyStatus.ACTIVE_DUAL]:
                    team_down = False
                    break

        for interf in iflist:
            if interf.redundancy_type == RedundancyType.ACTIVE_ACTIVE:
                alarm_klass = Harmonic_NICTeamingDown_PortRedundancy
            else:
                alarm_klass = Harmonic_NICTeamingDown
            evt = alarm_klass(self.TEAMED_INTERF_OBJ_BASE + interf.nmi_id,
                    AssetingPortNum=interf.nmi_id,
                    NICTeamingName=master.interface_name_l3,
                    FirstPortNum=master.nmi_id,
                    SecondPortNum=slave.nmi_id,
                    EnforcePortPriority=(master.redundancy_mode not in [RedundancyMode.AUTOMATIC, RedundancyMode.DUAL]))
            self.event_proc.alarm(evt, team_down)

        # XXX TODO?
        # DHCP fail and Bad IP Address condition does not currently trigger redundancy failover -
        # any such failure can bring video down, so raise an alarm in any redundancy mode
        team_badaddr = any(team_badaddrs)
        team_dhcp_fail = any(team_dhcp_fails)

        # Harmonic_VideoOverIPPortDown
        # NMX wants alarm for master port but for compatibility emit alarm
        # for all slaves too
        for interf in iflist:
            self.voip_down_alarm(interf, team_down, team_badaddr, team_dhcp_fail)

        # Harmonic_StoragePortDown
        self.storage_port_down_alarm(master, team_down or team_badaddr or team_dhcp_fail)

        return True

