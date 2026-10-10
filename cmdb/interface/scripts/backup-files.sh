#!/bin/sh
# Executed on the application host as cmdbagent. stdout is reserved for metadata.
set -eu
umask 077
base=$1
relative=$2
source=$3

source=$(realpath -e -- "$source")
[ -d "$source" ] && [ "$source" != / ] || { echo 'Select an existing application directory.' >&2; exit 1; }
cd -- "$base"
base=$(pwd -P)
# Refuse to archive the backup destination recursively.
case "$base/" in "$source/"*) echo 'Backup directory is inside the source directory.' >&2; exit 1 ;; esac
directory=${relative%/*}
mkdir -p -- "$directory"
lock=$(printf '%s' "$source" | sha256sum)
lock=${lock%% *}
exec 9>"$directory/.$lock.lock"
flock -n 9 || { echo 'A backup of this directory is already running.' >&2; exit 1; }
temporary=$(mktemp "$directory/.backup-XXXXXXXX.part")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
tar -czf "$temporary" -C "${source%/*}/" -- "${source##*/}"
size=$(stat -c %s -- "$temporary")
checksum=$(sha256sum < "$temporary")
checksum=${checksum%% *}
ln -- "$temporary" "$relative"
printf '%s %s\n' "$size" "$checksum"
