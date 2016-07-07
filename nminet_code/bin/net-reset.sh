#!/bin/bash

TEAMD=`which teamd`
IP=`which ip`

rmmod bonding

$TEAMD -k -t nteam1
$TEAMD -k -t nteam2
$TEAMD -k -t nteam3
$TEAMD -k -t nteam4
$TEAMD -k -t nteam5
$TEAMD -k -t nteam6
$TEAMD -k -t nteam7
$TEAMD -k -t nteam8

$IP l del nteam1
$IP l del nteam2
$IP l del nteam3
$IP l del nteam4
$IP l del nteam5
$IP l del nteam6
$IP l del nteam7
$IP l del nteam8

$IP l del net1
$IP l del net2
$IP l del net3
$IP l del net4
$IP l del net5
$IP l del net6
$IP l del net7
$IP l del net8

#$IP l set down dev eth0
$IP l set down dev eth1
$IP l set down dev eth2
$IP l set down dev eth3
$IP l set down dev eth4
$IP l set down dev eth5
$IP l set down dev eth6
$IP l set down dev eth7
