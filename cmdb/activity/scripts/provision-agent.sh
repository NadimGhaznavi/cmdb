#!/bin/sh
# Executed remotely through an authenticated root SSH session.
set -eu
umask 077
account=$1
public_key=$2
[ "$(id -u)" = 0 ] || exit 1
command -v getent >/dev/null
command -v usermod >/dev/null

if ! getent passwd "$account" >/dev/null; then
    # An unusable password enables key-only access without an account-lock marker.
    useradd --create-home --shell /bin/sh --password '*NP*' "$account"
fi
entry=$(getent passwd "$account")
home=$(printf '%s\n' "$entry" | cut -d: -f6)
login_shell=$(printf '%s\n' "$entry" | cut -d: -f7)
case "$home" in
    ''|/|/nonexistent)
        home=/home/$account
        usermod --home "$home" "$account"
        ;;
    /*) ;;
    *) exit 1 ;;
esac
case "$login_shell" in
    ''|*/nologin|*/false) usermod --shell /bin/sh "$account" ;;
esac
# Permit key authentication for an existing locked service account without
# enabling a password. Existing usable password hashes are left alone.
password=$(getent shadow "$account" | cut -d: -f2)
case "$password" in
    '!'*|'*') usermod --password '*NP*' "$account" ;;
esac

[ ! -L "$home" ] && [ ! -L "$home/.ssh" ] && [ ! -L "$home/.ssh/authorized_keys" ] || exit 1
mkdir -p "$home/.ssh"
touch "$home/.ssh/authorized_keys"
if ! grep -Fqx -- "$public_key" "$home/.ssh/authorized_keys"; then
    printf '\n%s\n' "$public_key" >> "$home/.ssh/authorized_keys"
fi
owner=$(id -u "$account"):$(id -g "$account")
chown "$owner" "$home" "$home/.ssh" "$home/.ssh/authorized_keys"
chmod go-w "$home"
chmod 700 "$home/.ssh"
chmod 600 "$home/.ssh/authorized_keys"
