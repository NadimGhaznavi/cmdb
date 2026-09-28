#!/bin/sh
# Executed on the database host as cmdbagent. stdout is reserved for metadata.
set -eu
umask 077
base=$1
relative=$2
database=$3
agent=$4

# Access the destination, triggering autofs where configured.
cd -- "$base"
directory=${relative%/*}
mkdir -p -- "$directory"
# Keep the lock on the shared filesystem, including across server restarts.
lock=$(printf '%s' "$database" | sha256sum)
lock=${lock%% *}
exec 9>"$directory/.$lock.lock"
flock -n 9 || { echo 'A backup of this database is already running.' >&2; exit 1; }
temporary=$(mktemp "$directory/.backup-XXXXXXXX.part")
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
mariadb-dump --no-defaults --protocol=socket --skip-ssl --user="$agent" \
    --single-transaction --quick --routines --events --triggers --hex-blob \
    --databases -- "$database" > "$temporary"
size=$(stat -c %s -- "$temporary")
checksum=$(sha256sum < "$temporary")
checksum=${checksum%% *}
# A hard link publishes the complete file without overwriting an existing dump.
ln -- "$temporary" "$relative"
printf '%s %s\n' "$size" "$checksum"
