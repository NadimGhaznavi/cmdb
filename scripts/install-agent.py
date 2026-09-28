"""Provision the local inventory identity during install or upgrade."""

import os
from pathlib import Path
import pwd
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.SSHDb import provisioning_sql


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run through the root installer.")
    try:
        pwd.getpwnam(DCmdb.AGENT_USER)
    except KeyError:
        subprocess.run(['useradd', '--system', '--create-home', '--home-dir', DCmdb.AGENT_HOME,
                        '--shell', '/bin/sh', '--password', '*NP*', DCmdb.AGENT_USER], check=True)
    public_key = Path(DCmdb.SSH_KEY + '.pub').read_text().strip()
    script = Path(__file__).resolve().parents[1] / 'cmdb/activity/scripts/provision-agent.sh'
    subprocess.run(['/bin/sh', str(script), DCmdb.AGENT_USER, public_key], check=True)
    subprocess.run(['mariadb', '--no-defaults', '--protocol=socket', '--user=root', '--batch'],
                   input=provisioning_sql(), text=True, check=True)
    subprocess.run(['runuser', '-u', DCmdb.AGENT_USER, '--', 'mariadb', '--no-defaults',
                    '--protocol=socket', '--user=' + DCmdb.AGENT_USER, '--batch',
                    '-e', 'SELECT CURRENT_USER(); SHOW DATABASES;'], check=True,
                   stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
