"""Run the same fixed patch actions locally or over administrative SSH."""

from pathlib import Path
import subprocess

from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.SSH import SSH


class SSHPatch:
    def run(self, address, action):
        if action not in ('probe', 'patch', 'reboot', 'verify'):
            raise ValueError('Invalid patch action.')
        ssh = SSH()
        timeout = 7200 if action == 'patch' else 60
        if ssh.is_local(address):
            script = str(Path(DCmdb.BASE_DIR) / 'cmdb/interface/scripts/patch-host.sh')
            result = subprocess.run(['/usr/bin/sudo', '-n', '/bin/sh', script, action],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                    timeout=timeout, check=True)
        else:
            script = (Path(__file__).parent / 'scripts/patch-host.sh').read_text()
            result = ssh.run(address, f'timeout --kill-after=10 {timeout} sh -s -- {action}',
                             user='root', input=script, timeout=timeout + 30)
        return result.stdout
