"""Provision MariaDB inventory access through the host's SSH command interface."""

from pathlib import Path
import re
import shlex
import subprocess
from threading import Event

from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.SSH import SSH


def provisioning_sql() -> str:
    if re.fullmatch(r'[a-z_][a-z0-9_]*', DCmdb.AGENT_USER) is None:
        raise ValueError('Invalid database agent name.')
    return (Path(__file__).resolve().parents[2] / 'schema/cmdbagent.sql').read_text().replace(
        '@AGENT@', DCmdb.AGENT_USER)


class SSHDb:
    def __init__(self, ssh: SSH, stop_requested: Event) -> None:
        self._ssh = ssh
        self._stop_requested = stop_requested

    def _run(self, host: str, command: str, **options):
        if self._stop_requested.is_set():
            raise InterruptedError('Database provisioning stopped.')
        return self._ssh.run(host, command, timeout=DCmdb.SSH_COMMAND_TIMEOUT_SECONDS,
                             connect_timeout=DCmdb.SSH_CONNECT_TIMEOUT_SECONDS, **options)

    def _ready(self, host: str) -> bool:
        try:
            result = self._run(host, 'mariadb --no-defaults --protocol=socket --batch '
                               '--skip-column-names --user=' + shlex.quote(DCmdb.AGENT_USER),
                               input='SELECT CURRENT_USER(), VERSION();\nSHOW GRANTS;\nSHOW DATABASES;\n')
        except subprocess.CalledProcessError:
            return False
        lines = result.stdout.splitlines()
        return bool(lines and lines[0].startswith(DCmdb.AGENT_USER + '@localhost\t')
                    and 'MariaDB' in lines[0]
                    and any(('SHOW DATABASES' in line or 'ALL PRIVILEGES' in line)
                            and 'ON *.* TO' in line for line in lines[1:]))

    def ensure_agent(self, host: str) -> bool:
        """Return whether MariaDB inventory access is ready on this host."""
        try:
            client = self._run(host, 'mariadb --no-defaults --version')
            if 'MariaDB' not in client.stdout:
                return False
            if self._ready(host):
                return True
            # Local administrative setup is owned by install/upgrade.
            if self._ssh.is_local(host):
                return False
            command = (
                'set -eu; version=$(mariadb --no-defaults --protocol=socket --user=root '
                '--batch --skip-column-names -e "SELECT VERSION()"); '
                'case "$version" in *MariaDB*) ;; *) exit 1 ;; esac; '
                'mariadb --no-defaults --protocol=socket --user=root --batch'
            )
            self._run(host, command, user='root', input=provisioning_sql())
            return self._ready(host)
        except (OSError, subprocess.SubprocessError):
            # Hosts without MariaDB or administrative access retry next scan.
            return False
