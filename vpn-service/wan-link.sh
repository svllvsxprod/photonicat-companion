#!/bin/sh
# Reapply the owner's explicit UCI speed after the Ethernet PHY is available.
# Keep autonegotiation enabled for 1000BASE-T; advertise only the chosen speed.
device=$(uci -q get network.pcat_wan_link.name) || exit 0
speed=$(uci -q get network.pcat_wan_link.speed) || exit 0
[ "$device" = eth0 ] || exit 1
case "$speed" in 10|100|1000) ;; *) exit 1 ;; esac
/usr/sbin/ethtool -s "$device" speed "$speed" duplex full autoneg on
