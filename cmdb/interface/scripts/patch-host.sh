#!/bin/sh
# Fixed actions only; installed root-owned for local sudo and sent over root SSH remotely.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
. /etc/os-release
[ "$ID" = debian ] || { echo 'Host is not Debian.' >&2; exit 1; }
case "${1:-}" in
    probe) cat /proc/sys/kernel/random/boot_id ;;
    patch)
        export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
        timeout --kill-after=10 3500 apt-get -o APT::Update::Error-Mode=any update </dev/null
        timeout --kill-after=10 3500 apt-get -y --with-new-pkgs -o Dpkg::Options::=--force-confdef \
            -o Dpkg::Options::=--force-confold upgrade </dev/null
        timeout --kill-after=10 3500 apt-get -y autoremove </dev/null
        audit=$(dpkg --audit)
        [ -z "$audit" ] || { printf '%s\n' "$audit" >&2; exit 1; }
        ;;
    reboot) shutdown -r +1 'CMDB patch job completed; rebooting.' ;;
    verify)
        state=$(systemctl is-system-running --wait) || true
        [ "$state" = running ] || { printf 'System state: %s\n' "$state" >&2; exit 1; }
        audit=$(dpkg --audit)
        [ -z "$audit" ] || { printf '%s\n' "$audit" >&2; exit 1; }
        apt-get check </dev/null
        ;;
    *) echo 'Invalid patch action.' >&2; exit 2 ;;
esac
