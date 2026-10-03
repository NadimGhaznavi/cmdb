"""Discover named applications using their installation and constants convention."""

import ast
from pathlib import PurePosixPath
import re
import shlex
import subprocess
from threading import Event

from cmdb.constants.DCMDB import DCMDB
from cmdb.entity.StatusMessages import StatusMessages
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.SSH import SSH
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb
from cmdb.interface.SoftwareSystemDb import SoftwareSystemDb


def application_version(source: str) -> str | None:
    """Read a literal VERSION at module or class scope without executing code."""
    try:
        module = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    statements = list(module.body)
    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            statements.extend(statement.body)
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets, value = [statement.target], statement.value
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in targets):
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                version = value.value.strip()
                if version and len(version) <= 255 and not any(
                        ord(character) < 32 or ord(character) == 127 for character in version):
                    return version
    return None


class ApplicationScanner:
    def __init__(self, stop_requested: Event, status_messages: StatusMessages | None = None) -> None:
        self._stop_requested = stop_requested
        self.status_messages = status_messages if status_messages is not None else StatusMessages()
        self._ssh = SSH()

    def run(self, machines: dict[str, int]) -> None:
        db = DbMgr()
        try:
            applications = SoftwareSystemDb(db).list_applications()
            hostnames = {machine.id: machine.hostName for machine in MachineDb(db).list_machines()}
        finally:
            db.close()
        for address, machine in machines.items():
            hostname = (hostnames.get(machine) or '').split('.')[0].lower()
            host = hostname or address
            for application in applications:
                if self._stop_requested.is_set():
                    return
                name = application['name']
                # The convention requires a Python module name and one path segment.
                if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) is None:
                    continue
                pathname = str(PurePosixPath(DCMDB.BASE_INSTALL_DIR) / name.lower())
                constants_dir = PurePosixPath(pathname) / name.lower() / 'constants'
                constants = str(constants_dir / ('D' + name + '.py'))
                command = (f'if [ -d {shlex.quote(pathname)} ] && [ -f {shlex.quote(constants)} ]; '
                           f'then cat -- {shlex.quote(constants)}; fi')
                try:
                    result = self._ssh.run(address, command,
                                           timeout=DCMDB.SSH_COMMAND_TIMEOUT_SECONDS,
                                           connect_timeout=DCMDB.SSH_CONNECT_TIMEOUT_SECONDS)
                except (OSError, subprocess.SubprocessError):
                    self.status_messages.append(f'{host}: {name} — read failed.')
                    continue
                version = application_version(result.stdout)
                if self._stop_requested.is_set():
                    return
                if version is None:
                    self.status_messages.append(f'{host}: {name} — not detected.')
                    continue
                db = DbMgr()
                try:
                    with db.transaction():
                        recorded = SoftwareDeploymentDb(db).record_application(
                            machine, application['id'], pathname, version)
                finally:
                    db.close()
                self.status_messages.append(f'{host}: {name} {version}' if recorded
                                            else f'{host}: {name} — definition removed; skipped.')
