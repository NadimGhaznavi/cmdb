"""Verify the FreeIPA inventory identity and provision its local MariaDB access."""

import os
from pathlib import Path
import pwd
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.SSHDb import provisioning_sql


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run through the root installer.")
    if any(line.partition(':')[0] == DCMDB.AGENT_USER
           for line in Path('/etc/passwd').read_text().splitlines()):
        raise SystemExit("Remove the local cmdbagent account before using the FreeIPA identity; see CHANGELOG.md.")
    try:
        pwd.getpwnam(DCMDB.AGENT_USER)
    except KeyError:
        raise SystemExit("FreeIPA cmdbagent must resolve on this host before installation; see CHANGELOG.md.") from None
    subprocess.run(['mariadb', '--no-defaults', '--protocol=socket', '--skip-ssl', '--user=root', '--batch'],
                   input=provisioning_sql(), text=True, check=True)
    subprocess.run(['runuser', '-u', DCMDB.AGENT_USER, '--', 'mariadb', '--no-defaults',
                    '--protocol=socket', '--skip-ssl', '--user=' + DCMDB.AGENT_USER, '--batch',
                    '-e', 'SELECT CURRENT_USER(); SHOW DATABASES;'], check=True,
                   stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
