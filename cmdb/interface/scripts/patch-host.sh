#!/bin/sh
# Fixed actions only; executed as root through the inventory agent's sudo access.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
. /etc/os-release
case "$ID" in
    debian|fedora) ;;
    *) echo 'Host is not Debian or Fedora.' >&2; exit 1 ;;
esac

verify_packages() {
    if [ "$ID" = debian ]; then
        audit=$(dpkg --audit)
        [ -z "$audit" ] || { printf '%s\n' "$audit" >&2; exit 1; }
        apt-get check </dev/null
    else
        dnf check </dev/null
    fi
}

case "${1:-}" in
    probe) cat /proc/sys/kernel/random/boot_id ;;
    patch-kernel|patch-other)
        if [ "$ID" = debian ]; then
            export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
            timeout --kill-after=10 3500 apt-get -o APT::Update::Error-Mode=any update </dev/null
            if [ "$1" = patch-kernel ]; then
                installed=$(dpkg-query -W -f '${db:Status-Status} ${binary:Package}\n')
                packages=$(printf '%s\n' "$installed" | awk '$1 == "installed" && $2 ~ /^linux-(image|headers|modules|kbuild|compiler)-/ {print $2}')
                if [ -n "$packages" ]; then
                    # Package names come from dpkg, and splitting the list is intentional.
                    set -f
                    timeout --kill-after=10 3500 apt-get -y --only-upgrade --no-remove \
                        -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold \
                        install $packages </dev/null
                fi
                # APT's default retention keeps the current kernel and one fallback.
                timeout --kill-after=10 3500 apt-get -y \
                    -o APT::Get::AutomaticRemove=false \
                    -o APT::Get::AutomaticRemove::Kernels=true install </dev/null
            else
                # Add a per-command pin without changing holds or administrator preferences.
                preferences=$(mktemp)
                trap 'rm -f "$preferences"' EXIT
                trap 'exit 1' HUP INT TERM
                printf 'Package: linux-image-* linux-headers-* linux-modules-* linux-kbuild-* linux-compiler-*\nPin: version *\nPin-Priority: -1\n\n' > "$preferences"
                configuration=$(apt-config shell original_preferences Dir::Etc::preferences/f)
                eval "$configuration"
                if [ -f "$original_preferences" ]; then
                    cat "$original_preferences" >> "$preferences"
                fi
                timeout --kill-after=10 3500 apt-get -y --with-new-pkgs --no-remove \
                    -o "Dir::Etc::preferences=$preferences" \
                    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade </dev/null
            fi
        elif [ "$1" = patch-kernel ]; then
            timeout --kill-after=10 7000 dnf -y --refresh --setopt=installonly_limit=2 upgrade 'kernel*' </dev/null
        else
            timeout --kill-after=10 7000 dnf -y --refresh --exclude='kernel*' upgrade </dev/null
        fi
        verify_packages
        ;;
    reboot) shutdown -r +1 'CMDB kernel patch job completed; rebooting.' ;;
    verify)
        state=$(systemctl is-system-running --wait) || true
        [ "$state" = running ] || { printf 'System state: %s\n' "$state" >&2; exit 1; }
        verify_packages
        ;;
    verify-packages) verify_packages ;;
    *) echo 'Invalid patch action.' >&2; exit 2 ;;
esac
