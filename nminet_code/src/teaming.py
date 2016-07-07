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
import argparse
import socket
import logging
import Queue
import select
import errno
import subprocess
import json
queue = Queue # python 3
from enum import Enum
from monotonic import monotonic
from copy import deepcopy

import sysfs
from util import *
from message import *
from config import *
from defs import *
import team

__all__ = ['TeamThread', 'CurrentDefaultDelay']

class CurrentDefaultDelay(object):
    pass

class NoStatsException(Exception):
    pass


class IfStat(object):
    def __init__(self, ifname):
        self.ifname = ifname
        self.rx_packets = None
        self.get()

    def get(self):

        def ck(val):
            if val is None:
                raise NoStatsException("interface {} stats not available".format(ifname))
            return val

        self.rx_packets = ck(sysfs.helper.get_net_interface_param(self.ifname, "statistics/rx_packets"))

    def __eq__(self, other):
        return self.rx_packets == other.rx_packets

    def __ne__(self, other):
        return not self.__eq__(other)


class LinkCheck(object):
    def __init__(self, ifname, callback):
        self.ifname = ifname
        self.start_stat = IfStat(ifname)
        self.callback = callback

    def timer(self):
        try:
            end_stat = IfStat(self.ifname)
        except NoStatsException:
            self.callback(self.ifname, None)
            return

        res = (self.start_stat != end_stat)
        self.callback(self.ifname, res)


class LinkWatchdog(object):

    class WatchState(object):

        def __init__(self, max_fails):
            self.active = False
            self.count = 0
            self.max_fails = max_fails

        def disable(self):
            self.count = self.max_fails

        def enabled(self):
            return self.count < self.max_fails

        def run(self):
            if not self.active:
                self.count += 1
            self.active = True

        def cancel(self):
            if self.active and self.count > 0:
                self.count -= 1
            self.active = False

        def stop(self):
            self.active = False


    def __init__(self, manager, wd_delay):
        self.manager = manager
        self.wd_delay = wd_delay

        self.lock = threading.Lock()
        self.timers = {}
        self.ifstatus = {}

    @property
    def log(self):
        return self.manager.log

    def port_up(self, ifname):
        # must be called with lock held

        checker = LinkCheck(ifname, self.result_data)

        timer = threading.Timer(self.wd_delay, checker.timer)
        self.timers[ifname] = timer

        self.log.debug("link_wd: monitoring {}".format(ifname))
        timer.start()

    def result_data(self, ifname, is_ok):
        self.log.debug("link_wd: result {}: {}".format(ifname, is_ok))

        with self.lock:
            state = self.get_state(ifname)
            state.stop()
            self.timers.pop(ifname, None)
            # disable workaround after first success
            if is_ok:
                state.disable()

        if is_ok == False: # is_ok can be None
            self.manager.send_interface_fail(ifname)
            # It is possible that during renegotiation
            # link-down event will be missed by
            # network driver and this will not trigger
            # another linkwatch cycle.
            #
            # So start it manually here
            self.port_changed(ifname, True)

    def cancel_iftimers(self, ifname):
        # must be called with lock held
        timer = self.timers.pop(ifname, None)
        if timer:
            self.log.debug("link_wd: cancel for {}".format(ifname))
            timer.cancel()
            self.get_state(ifname).cancel()

    def get_state(self, ifname):
        # must be called with lock held
        if ifname not in self.ifstatus:
            self.ifstatus[ifname] = self.WatchState(self.manager.config.link_watch_tries)
        return self.ifstatus[ifname]

    def port_changed(self, ifname, linkup):

        if self.wd_delay <= 0:
            # disabled
            return

        with self.lock:
            self.cancel_iftimers(ifname)

            state = self.get_state(ifname)

            if linkup and state.enabled():
                state.run()
                try:
                    self.port_up(ifname)
                except NoStatsException:
                    # ignore port
                    pass


class TeamMon(object):
    def __init__(self, manager, rqqueue, link_wd, teamname):
        self.manager = manager
        self.link_wd = link_wd
        self.queue = rqqueue
        self.teamname = teamname
        self._ports_count = 0
        self.team = team.Team(teamname)

        hnd = team.TeamChangeHandler(self.port_change_handler, None,
                                    team.TEAM_PORT_CHANGE)
        self.team.change_handler_register(hnd)

        hnd = team.TeamChangeHandler(self.option_change_handler, None,
                                    team.TEAM_OPTION_CHANGE)
        self.team.change_handler_register(hnd)

    @property
    def monitor_fd(self):
        return self.team.get_event_fd()

    def process_event(self):
        self.team.handle_events()

    def get_port_priority(self, port_id):
        return self.team.get_port_priority(port_id)

    def set_port_priority(self, port_id, prio):
        return self.team.set_port_priority(port_id, prio)

    def port_change_handler(self, param):
        updated = False
        t = self.team
        cnt = 0
        for port in t.port_list():
            self.manager.log.debug("Port change %s: ifname %s, linkup %d, changed %d, speed %d, duplex %d, removed %d" %
                            (self.teamname, port.ifname, port.linkup, port.changed,
                             port.speed, port.duplex, port.removed))

            if port.changed:
                updated = True
                if not port.removed:
                    try:
                        self.link_wd.port_changed(port.ifname, port.linkup)
                    except:
                        self.manager.log.exception("unhandled exception")

            if not port.removed:
                cnt += 1

        self._ports_count = cnt

        if updated:
            self.manager.handle_new_team_status(self)

        return 0

    def option_change_handler(self, param):
        t = self.team
        updated = False
        important = False

        for option in sorted(t.option_list(), key=lambda x: x.name):
            if option.changed:
                self.manager.log.debug("Option change %s: %s = %s (changed %d)" % (self.teamname, option.name, option.value,
                                                   option.changed))
                # ignore priority option updates - we're not interested in them and
                # they're used to notify teamd to update its port configuration
                if "priority" in option.name:
                    continue
                updated = True

                if important:
                    # no more checks necessary
                    pass
                elif self._ports_count == 1:
                    # team has only one port, catch slave link down events
                    if "user_linkup" in option.name and not option.value:
                        important = True
                elif self._ports_count > 1:
                    # multiple ports, catch activeport changes
                    if "activeport" in option.name:
                        important = True

        if updated:
            self.manager.handle_new_team_status(self, important)

        return 0

    def get_port_carrier(self, portname):
        # This left here for reference.
        # p.linkup is actual link status of the port,
        # but user_linkup option is delayed link-up
        #
        #for p in self.team.port_list():
        #    #print (p.ifname, p.linkup, p.removed)
        #    if not p.removed and p.ifname == portname:
        #        return p.linkup
        #self.manager.log.error("Trying to get carrier for unknown port {}".format(portname))
        #return None

        opt = "{}:user_linkup".format(portname)

        for p in self.team.option_list():
            if p.name == opt:
                return p.value

        self.manager.log.error("Trying to get carrier for unknown port {}".format(portname))
        return None


    def set_active_port(self, portname):
        # not supported, doesn't set internal teamd state
        raise Exception()
        try:
            self.team.set_active_port(portname)
        except team.TeamLibError:
            self.manager.log.exception("set_active_port exception")
            return False
        return True

    def get_active_port(self):

        activeport = None
        for p in self.team.option_list():
            if p.name == "activeport":
                activeport = p.value

        if activeport is not None:
            for p in self.team.port_list():
                if p.ifindex == activeport:
                    if p.removed or not p.linkup:
                        activeport = None
                    else:
                        activeport = p.ifname
                    break

        #print("Active", activeport)
        return activeport

    def get_ports_list(self):
        res = []
        for p in self.team.port_list():
            if not p.removed:
                res.append(p.ifname)

        self._ports_count = len(res)
        return res

    def get_enabled_ports(self):

        res = []
        for p in self.team.option_list():
            if ":" in p.name:   # e.g. eth4:enabled
                ifname, opt = p.name.split(":", 2)
                if opt == "enabled":
                    res.append(ifname)

        #print (res)
        return res


class TeamThread(threading.Thread):

    BURST_DELAY = 0.1
    BASE_SELECT_WAIT = 0.5

    def __init__(self, rqqueue):
        super(TeamThread, self).__init__()
        self.log = logging.getLogger("team")
        self.queue = rqqueue
        self.server = None
        self.terminate = False
        self.config = Config()

        self.link_wd = LinkWatchdog(self, self.config.link_watch_timeout)

        self.evt_time = 0
        self.evt_updated = False
        self.prioritize_important = True

        self.teams = {}
        self.fds = None

        self.team_port_configs = {}
        self.team_default_delay_up = {}

        self.port_to_team_name_map = {}

    def _rebuild_fds(self):
        fds = {}
        for t in self.teams.values():
            fds[t.monitor_fd] = t
        self.fds = fds
        return fds

    def _exec(self, cmd, args):

        proc = subprocess.Popen([cmd]+args,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        close_fds=True)

        stdoutdata, stderrdata = proc.communicate()

        if proc.returncode != 0:
            self.log.error("{} returned an error code {}: '{}', '{}'".format(
                                cmd, proc.returncode, stdoutdata, stderrdata))
            return False

        return True

    def _teamd_exec(self, args):
        return self._exec(self.config.teamd_path, args)

    def _teamdctl_exec(self, args):
        return self._exec(self.config.teamdctl_path, args)

    def _teamd_stop(self, teamname):
        return self._teamd_exec(['-t', teamname, '-k'])

    def _teamd_check(self, teamname):
        return self._teamd_exec(['-t', teamname, '-e'])

    def _teamd_start(self, teamname, config, noports=False):
        args = ['-N', '-o', '-U', '-d']

        if noports:
            args.append('-n')

        return self._teamd_exec(args+['-t', teamname, '-c', config])

    def is_managed_team(self, name):
        return name in self.teams

    def start_teamds(self):

        any_started = False
        add_teams = []

        for iid, name in self.config.interf_nmi_to_name.iteritems():
            teamname = self.config.get_team_name_by_nmiid(iid)

            # default config for single port mode
            cfg = {
                "device": teamname,
                "mcast_rejoin": {
                    "count": 3,
                    "interval": 25,
                },
                "notify_peers": {
                    "count": 3,
                    "interval": 25,
                },
                "runner": {
                    "name": "activebackup",
                    "hwaddr_policy": "same_all"
                },
                "link_watch": {
                    "name": "ethtool"
                },
                #"ports": get_teamed_config(TeamModes.SINGLE, [name]),
            }

            if self._teamd_start(teamname, config=json.dumps(cfg), noports=True):
                any_started = True

            # if teamd is running alredy, execution will fail,
            # so check if it's running anyway

            res = self._teamd_check(teamname)
            if res:
                add_teams.append(teamname)
            else:
                self.log.error("teamd not running for interface {}".format(teamname))

        if any_started:
            # wait for teamds to finish startup
            time.sleep(1)

        for teamname in add_teams:
            self._add_team(teamname)

    def _team_port_config(self, teamname, portname, add=False, remove=False, config=None):

        if add:
            return self._teamdctl_exec([teamname, "port", "add", portname])
        if remove:
            return self._teamdctl_exec([teamname, "port", "remove", portname])
        if config is not None:
            return self._teamdctl_exec([teamname, "port", "config", "update", portname, config])

    def remove_port(self, teamname, portname):
        if portname in self.port_to_team_name_map:
            del self.port_to_team_name_map[portname]
            return self._team_port_config(teamname, portname, remove=True)

        self.log.error("Removing non-existing port {} from {}".format(portname, teamname))
        return False

    def add_port(self, teamname, portname):
        if portname in self.port_to_team_name_map:
            self.log.warning("Moving busy port {} from {} to {}".format(portname, self.port_to_team_name_map[portname], teamname))

        self.port_to_team_name_map[portname] = teamname
        res = self._team_port_config(teamname, portname, add=True)
        if not res:
            self.log.warning("Error adding port {} to {}, trying again".format(portname, teamname))
            time.sleep(1)
            res = self._team_port_config(teamname, portname, add=True)

        if not res:
            self.log.error("Failed to add port {} to {}".format(portname, teamname))

        return res

    def configure_port(self, teamname, portname, config, force=False):
        if isinstance(config, dict):
            strconfig = json.dumps(config)
        else:
            raise Exception("invalid config, need dict")

        # check if port config is the same
        ports = self.team_port_configs.setdefault(teamname, {})
        if portname in ports:
            old_config = ports[portname]
        else:
            old_config = {}

        if old_config == config and not force:
            self.log.debug("Not changing team {} port {} config".format(portname, teamname))
            return True

        self.log.debug("Updating team {} port {} config: {}".format(teamname, portname, strconfig))

        ports[portname] = dict(config)


        res = self._team_port_config(teamname, portname, config=strconfig)

        self.team_port_signal_update(teamname, portname, prio=config['prio'])
        return res

    def port_signal_update(self, portname):
        teamname = self.port_to_team_name_map.get(portname)
        if teamname is None:
            self.log.error("Trying to signal update for unknown port {}".format(portname))
            return None

        return self.team_port_signal_update(teamname, portname)

    def team_port_signal_update(self, teamname, portname, prio=None):

        # At the time of writing, updating json port config in teamd
        # actually does nothing but uptates config that is shown to a
        # user, all running ports are not updated. Port needs to be
        # re-added for changes to take effect.
        #
        # Specially modified version of teamd reloads config
        # when it receives notification from kernel that
        # port priority has changed.
        #
        # This event also triggers active port recalculation

        orig_prio = prio

        try:
            orig_prio = self.teams[teamname].get_port_priority(portname)
        except team.TeamLibError:
            # teamd not synced yet? Wait and try again
            self.log.warning("Error getting team {} port {} priority, trying again".format(teamname, portname))
            time.sleep(0.5)
            try:
                orig_prio = self.teams[teamname].get_port_priority(portname)
            except team.TeamLibError:
                self.log.exception("Error getting team {} port {} priority".format(teamname, portname))

        if prio is None:
            prio = orig_prio

        if prio is None:
            self.log.error("Can not signal team update for {}/{}".format(teamname, portname))
            return False

        # Change priority to signal option change.
        # Choose new priority as follows: LSB is flipped every priority change,
        # all other bits stay as a desired priority

        new_prio = ((orig_prio & 1) ^ 1) | (prio & ~1)

        try:
            self.teams[teamname].set_port_priority(portname, new_prio)
        except team.TeamLibError:
            self.log.exception("Error setting team {} port {} priority".format(teamname, portname))
            return False

        return True

    def set_delay_up(self, teamname, delay_up=None):

        if delay_up == CurrentDefaultDelay:
            if teamname not in self.team_default_delay_up:
                return
            delay_up = self.team_default_delay_up[teamname]

        if delay_up is None or delay_up < 0:
            return

        ports = self.team_port_configs[teamname]
        portnames = sorted(ports.keys())

        for portname in portnames:
            config = deepcopy(ports[portname])
            if "link_watch" in config:
                lw = config["link_watch"]
                if "delay_up" in lw and lw["delay_up"] == delay_up:
                    # delay not changed
                    continue
                lw["name"] = "ethtool"
                lw["delay_up"] = delay_up
                lw["delay_down"] = 0
            else:
                if delay_up == 0:
                    # 0 is default (if no global config set)
                    continue
                config["link_watch"] = {
                    "name": "ethtool",
                    "delay_up": delay_up,
                    "delay_down": 0,
                }
            self.configure_port(teamname, portname, config)

    def configure_ports_mode(self, teamname, portnames, mode, delay_up):
        # Can not set delay_up here because newly added ports end up
        # in a delayed state ringht from the start. Delays should be set
        # after interfaces were added.

        if len(portnames) == 1:
            if mode in [TeamModes.SINGLE, TeamModes.DUAL,
                        RedundancyMode.DUAL]:
                cfg = get_teamed_config(TeamModes.SINGLE, portnames)   # same config
            else:
                self.log.error("Unexpected mode {} for interfaces: {}".format(mode, portnames))
                return False

        elif len(portnames) > 1:
            if mode in [TeamModes.AUTOMATIC, TeamModes.AUTOMATIC_REVERT, TeamModes.MANUAL, TeamModes.MANUAL_REVERT,
                    RedundancyMode.AUTOMATIC, RedundancyMode.AUTOMATIC_REVERT, RedundancyMode.MANUAL,
                    RedundancyMode.MANUAL_NOFAILOVER]:
                cfg = get_teamed_config(mode, portnames)
            else:
                self.log.error("Unexpected mode {} for interfaces: {}".format(mode, portnames))
                return False

        else:
            self.log.error("Unexpected list of interfaces: {}".format(portnames))
            return False

        self.team_default_delay_up[teamname] = delay_up

        for port in portnames:
            if not self.configure_port(teamname, port, cfg[port]):
                self.log.warning("Error updating team {} port {} config: {}".format(teamname, port, cfg[port]))

        return True

    def _add_team(self, teamname):
        if teamname in self.teams:
            raise Exception()

        t = TeamMon(self, self.queue, self.link_wd, teamname)

        self.teams[teamname] = t
        self.fds = None

        for p in t.get_ports_list():
            self.port_to_team_name_map[p] = teamname

    def is_port_active(self, portname):
        #print( self.port_to_team_name_map)
        teamname = self.port_to_team_name_map.get(portname)
        if teamname is None:
            self.log.error("Trying to get active status for unknown port {}".format(portname))
            return None

        return self.teams[teamname].get_active_port() == portname

    def set_port_active(self, portname):
        #print( self.port_to_team_name_map)
        teamname = self.port_to_team_name_map.get(portname)
        if teamname is None:
            self.log.error("Trying to set active status for unknown port {}".format(portname))
            return None

        # use teamdctl to set internal teamd state
        # according to our selection

        return self._teamdctl_exec([teamname,
            'state', 'item', 'set', 'runner.active_port', portname])
        #return self.teams[teamname].set_active_port(portname)

    def port_has_link(self, portname):
        teamname = self.port_to_team_name_map.get(portname)
        if teamname is None:
            self.log.error("Trying to get link status for unknown port {}".format(portname))
            return None

        return self.teams[teamname].get_port_carrier(portname)

    def prioritize_important_events(self, value):
        # Under some conditions, e.g. reconfiguration, there will be
        # a lot of events generated and many of them may be marked as
        # important. This is used to suppress expected "important event storms"
        self.prioritize_important = value

    def handle_new_team_status(self, team=None, important=False):
        # notifications always come in a batch, delay and filter

        if important and self.prioritize_important:
            # force immediate update
            self.evt_time = 0
            self.evt_updated = True
        elif not self.evt_updated:
            self.evt_time = monotonic()
            self.evt_updated = True

    def flush_planned_notify(self):
        # Caller is about to start capturing interface status.
        # All previously planned notification are considered
        # redundant.
        self.evt_updated = False

    def send_updated_notify(self):
        # reply not needed
        MessageTeamNewState(self.queue).request()

    def send_interface_fail(self, ifname):
        MessageSuspectInterfaceFail(self.queue, MessageSuspectInterfaceFail.REPORT, data={'ifname':ifname}).request()

    def run(self):

        wait = self.BASE_SELECT_WAIT

        while not self.terminate:

            fds = self.fds

            if fds is None:
                fds = self._rebuild_fds()

            if not fds:
                time.sleep(0.5)
                continue

            try:

                rfd, wfd, efd = select.select(fds, [], [], wait)

                for fd in rfd:
                    if fd in fds:
                        fds[fd].process_event()

                wait = self.BASE_SELECT_WAIT

                if self.evt_updated:
                    now = monotonic()
                    delayleft = self.BURST_DELAY - (now - self.evt_time)
                    if delayleft <= 0:
                        self.evt_updated = False
                        self.send_updated_notify()
                    else:
                        wait = min(self.BASE_SELECT_WAIT, delayleft)

            except KeyboardInterrupt:
                continue
            except select.error as e:
                if e[0] == errno.EINTR or e[0] == errno.EAGAIN:
                    continue
                raise


    def shutdown(self):
        self.terminate = True


