"""One-time removal of legacy remote cmdb accounts and their homes."""

import argparse
import os
from pathlib import Path
import pwd
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.SSH import SSH


REMOVE_ACCOUNT = r'''
set -eu
[ "$(id -u)" = 0 ]
if [ -r /etc/machine-id ] && [ "$(cat /etc/machine-id)" = "$1" ]; then
    printf 'Refusing to remove the local service account\n' >&2
    exit 1
fi
if ! entry=$(getent passwd cmdb); then
    printf 'cmdb account already absent\n'
    exit 0
fi
uid=$(printf '%s\n' "$entry" | cut -d: -f3)
home=$(printf '%s\n' "$entry" | cut -d: -f6)
[ "$uid" != 0 ]
case "$home" in /home/cmdb|/var/lib/cmdb) ;; *)
    printf 'Refusing unexpected cmdb home: %s\n' "$home" >&2
    exit 1 ;;
esac
[ ! -L "$home" ]
userdel --remove cmdb
printf 'Removed cmdb account and home\n'
'''


def cleanup(addresses: list[str], local_identity: str) -> int:
    ssh = SSH()
    failed = False
    for address in dict.fromkeys(addresses):
        if ssh.is_local(address):
            print(f'{address}: skipped local machine', flush=True)
            continue
        try:
            result = ssh.run(address, 'sh -s -- ' + shlex.quote(local_identity), user='root',
                             input=REMOVE_ACCOUNT, timeout=DCmdb.SSH_COMMAND_TIMEOUT_SECONDS,
                             connect_timeout=DCmdb.SSH_CONNECT_TIMEOUT_SECONDS)
            print(f'{address}: {result.stdout.strip()}', flush=True)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            failed = True
            detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
            print(f'{address}: FAILED: {detail}', file=sys.stderr, flush=True)
    return int(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo using the installed CMDB virtualenv Python.')
    local_identity = Path('/etc/machine-id').read_text().strip()
    if not local_identity:
        raise SystemExit('Local machine identity is empty; cleanup stopped.')
    values = DatabaseEnvironment.read(Path(DCmdb.DATABASE_ENV))
    os.environ.update(values)
    db = DbMgr()
    try:
        addresses = [machine.ipAddress for machine in MachineDb(db).list_machines()]
    finally:
        db.close()
        for name in values:
            os.environ.pop(name, None)
    account = pwd.getpwnam(DCmdb.SERVICE_USER)
    os.initgroups(account.pw_name, account.pw_gid)
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    return cleanup(addresses, local_identity)


if __name__ == '__main__':
    sys.exit(main())
