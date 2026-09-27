---
title: "/opt/prod/xmr/xmr-mode.sh"
date: 2024-09-24
markdown: GFM
category:
  - Cryptocurrency
  - Monero
  - XMRig
---
# Introduction and Scope

This page documents the `/opt/prod/xmrrig/xmrig-mode.sh` script.

The `xmrig-mode.sh` script is used to switch XMRig configurations with a simple command. The idea is that sometimes you want to run XMRig full throttle, using all the cores that are available on the machine. Other times you want to leave one or more CPU threads free, because you are running some other tasks and otherwise those tasks stutter or take forever.

```
#!/bin/bash

# Base directory
BASE_DIR=/opt/prod/xmrig

# Config filename
CONFIG=config.json

# Full throttle configuration
FULL_THROTTLE=config.json-fullthrottle

# User mode, reduced CPU usage
USER_MODE=config.json-usermode

# Check that this script is being run by root
LOGIN_NAME=$(whoami)
if [ $LOGIN_NAME != "root" ]; then
	echo "ERROR: You must run this script as root, exiting"
	exit 1
fi

# Check that an arg was passed in
ARG=$1
if [ -z $ARG ]; then
	echo "ERROR: Missing mandatory argument [usermode|fullthrottle]"
	exit 1
fi

# Check that the arg is a valid value
if [ $ARG != "usermode" -a $ARG != "fullthrottle" ]; then
	echo "ERROR: Invalid argument ($ARG). Valid values are \"usermode\" or \"fullthrottle\", exiting"
	exit 1
fi

if [ "$ARG" == "fullthrottle" ]; then
	echo -n "Changing xmrig mode to full throttle: "
	cd ${BASE_DIR}
	rm -f ${BASE_DIR}/${CONFIG}
	ln -s ${BASE_DIR}/${FULL_THROTTLE} ${BASE_DIR}/${CONFIG}
	systemctl stop xmrig
	systemctl start xmrig
elif [ "$ARG" == "usermode" ]; then
	echo -n "Changing xmrig mode to user mode: "
	cd ${BASE_DIR}
	rm -f ${BASE_DIR}/${CONFIG}
	ln -s ${BASE_DIR}/${USER_MODE} ${BASE_DIR}/${CONFIG}
	systemctl stop xmrig
	systemctl start xmrig
fi
echo "DONE"
```
