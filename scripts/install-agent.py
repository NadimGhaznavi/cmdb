"""Provision the local inventory identity during install or upgrade."""

import os
from pathlib import Path
import pwd
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cmdb.constants.DCmdb import DCmdb


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


if __name__ == '__main__':
    main()
