"""Run fixed patch actions as the inventory agent through noninteractive sudo."""

from pathlib import Path

from cmdb.interface.SSH import SSH


class SSHPatch:
    def run(self, address, action):
        if action not in ('probe', 'patch', 'reboot', 'verify'):
            raise ValueError('Invalid patch action.')
        ssh = SSH()
        timeout = 7200 if action == 'patch' else 60
        script = (Path(__file__).parent / 'scripts/patch-host.sh').read_text()
        result = ssh.run(address, f'sudo -n timeout --kill-after=10 {timeout} /bin/sh -s -- {action}',
                         input=script, timeout=timeout + 30)
        return result.stdout
