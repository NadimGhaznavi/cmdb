"""Provision MariaDB inventory access through the host's SSH command interface."""

from pathlib import Path
import re
import json
import shlex
import subprocess
from threading import Event

from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.SSH import SSH


def provisioning_sql() -> str:
    if re.fullmatch(r'[a-z_][a-z0-9_]*', DCMDB.AGENT_USER) is None:
        raise ValueError('Invalid database agent name.')
    return (Path(__file__).resolve().parents[2] / 'schema/cmdbagent.sql').read_text().replace(
        '@AGENT@', DCMDB.AGENT_USER)


class SSHDb:
    def __init__(self, ssh: SSH, stop_requested: Event) -> None:
        self._ssh = ssh
        self._stop_requested = stop_requested

    def backup_db(self, host: str, database: str, pathname: str) -> dict:
        """Dump on the database host and return completed-file metadata."""
        from pathlib import PurePosixPath
        path = PurePosixPath(pathname)
        if (path.is_absolute() or len(path.parts) != 4 or path.parts[1] != 'db'
                or any(part in ('.', '..') for part in path.parts)
                or not re.fullmatch(r'[A-Za-z0-9_.%:-]+/db/[A-Za-z0-9_.%:-]+/[A-Za-z0-9_.%:-]+\.dump', pathname)):
            raise ValueError('Invalid backup pathname.')
        if not database or '\0' in database or database.lower() in ('mysql', 'information_schema', 'performance_schema', 'sys'):
            raise ValueError('Select a user database to back up.')
        if not self.ensure_agent(host):
            raise RuntimeError('Database backup access is unavailable. Upgrade the local agent or check remote root provisioning.')
        script = (Path(__file__).parent / 'scripts/backup-db.sh').read_text()
        command = 'timeout --signal=TERM --kill-after=10 ' + str(DCMDB.BACKUP_TIMEOUT_SECONDS)
        command += ' sh -s -- ' + shlex.join([DCMDB.BACKUP_DIR, pathname, database, DCMDB.AGENT_USER])
        result = self._ssh.run(host, command, input=script,
                               timeout=DCMDB.BACKUP_TIMEOUT_SECONDS + 30,
                               connect_timeout=DCMDB.SSH_CONNECT_TIMEOUT_SECONDS)
        fields = result.stdout.strip().split()
        if len(fields) != 2 or not fields[0].isdigit() or not re.fullmatch('[0-9a-f]{64}', fields[1]):
            raise ValueError('The backup command did not return valid file metadata.')
        return {'pathname': pathname, 'sizeBytes': int(fields[0]), 'checksum': fields[1]}

    def drop_db(self, host: str, database: str) -> None:
        if (not database or len(database) > 64 or '\0' in database
                or database.lower() in ('cmdb', 'mysql', 'information_schema', 'performance_schema', 'sys')):
            raise ValueError('This database cannot be deleted.')
        script = Path(__file__).parent / 'scripts/drop-database.py'
        if self._ssh.is_local(host):
            installed = str(Path(DCMDB.BASE_DIR) / 'cmdb/interface/scripts/drop-database.py')
            subprocess.run(['/usr/bin/sudo', '-n', '/usr/bin/python3', installed, database],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True, timeout=40)
        else:
            self._ssh.run(host, shlex.join(['python3', '-c', script.read_text(), database]),
                          user='root', timeout=40, connect_timeout=DCMDB.SSH_CONNECT_TIMEOUT_SECONDS)

    def _run(self, host: str, command: str, **options):
        if self._stop_requested.is_set():
            raise InterruptedError('Database provisioning stopped.')
        return self._ssh.run(host, command, timeout=DCMDB.SSH_COMMAND_TIMEOUT_SECONDS,
                             connect_timeout=DCMDB.SSH_CONNECT_TIMEOUT_SECONDS, **options)

    def _ready(self, host: str) -> bool:
        try:
            result = self._run(host, 'mariadb --no-defaults --protocol=socket --skip-ssl --batch '
                               '--skip-column-names --user=' + shlex.quote(DCMDB.AGENT_USER),
                               input='SELECT CURRENT_USER(), VERSION();\nSHOW GRANTS;\nSHOW DATABASES;\n')
        except subprocess.CalledProcessError:
            return False
        lines = result.stdout.splitlines()
        return bool(lines and lines[0].startswith(DCMDB.AGENT_USER + '@localhost\t')
                    and 'MariaDB' in lines[0]
                    and any(('ALL PRIVILEGES' in line or all(privilege in line.split(' ON ')[0]
                             for privilege in ('SHOW DATABASES', 'SELECT', 'SHOW VIEW', 'TRIGGER', 'EVENT')))
                            and 'ON *.* TO' in line for line in lines[1:]))

    def inventory(self, host: str) -> dict | None:
        """Collect a complete server/database observation before any inventory writes."""
        if not self.ensure_agent(host):
            return None
        try:
            sql = (Path(__file__).resolve().parents[2] / 'schema/mariadb-inventory.sql').read_text()
            result = self._run(host, 'mariadb --no-defaults --protocol=socket --skip-ssl --batch --raw '
                               '--skip-column-names --user=' + shlex.quote(DCMDB.AGENT_USER), input=sql)
            lines = result.stdout.splitlines()
            if not lines:
                return None
            server = json.loads(lines[0])
            version, pathname = server['version'], server['pathname']
            names = [json.loads(line) for line in lines[1:]]
            if (not isinstance(version, str) or 'MariaDB' not in version or len(version) > 255
                    or not isinstance(pathname, str) or not pathname.startswith('/')
                    or any(not isinstance(name, str) or not name or len(name) > 255 for name in names)):
                return None
            return {'version': version, 'pathname': pathname, 'databases': names}
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            return None

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
                'set -eu; version=$(mariadb --no-defaults --protocol=socket --skip-ssl --user=root '
                '--batch --skip-column-names -e "SELECT VERSION()"); '
                'case "$version" in *MariaDB*) ;; *) exit 1 ;; esac; '
                'mariadb --no-defaults --protocol=socket --skip-ssl --user=root --batch'
            )
            self._run(host, command, user='root', input=provisioning_sql())
            return self._ready(host)
        except (OSError, subprocess.SubprocessError):
            # Hosts without MariaDB or administrative access retry next scan.
            return False
