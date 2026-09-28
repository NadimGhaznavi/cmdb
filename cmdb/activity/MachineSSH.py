"""Establish cmdb SSH access and obtain machine-reported hostnames."""

from pathlib import Path
import re
import shlex
import socket
import subprocess
from threading import Event

from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.SSH import SSH


class MachineSSH:
    def __init__(self, stop_requested: Event) -> None:
        self._stop_requested = stop_requested
        self._ssh = SSH()

    def run(self, machines: dict[str, int]) -> None:
        for address, machine_id in machines.items():
            if self._stop_requested.is_set():
                return
            try:
                with socket.create_connection((address, 22), timeout=DCmdb.SSH_CONNECT_TIMEOUT_SECONDS):
                    pass
                hostname = self._hostname(address)
            except (OSError, subprocess.SubprocessError, ValueError):
                # Closed ports, unsupported hosts and denied logins retry next scan.
                continue
            if hostname is None or self._stop_requested.is_set():
                continue
            db = DbMgr()
            try:
                with db.transaction():
                    MachineDb(db).update_discovered_hostname(machine_id, hostname)
            finally:
                db.close()

    def _run(self, address: str, command: str, **options) -> subprocess.CompletedProcess[str]:
        if self._stop_requested.is_set():
            raise InterruptedError("SSH activity stopped.")
        return self._ssh.run(address, command, timeout=DCmdb.SSH_COMMAND_TIMEOUT_SECONDS,
                             connect_timeout=DCmdb.SSH_CONNECT_TIMEOUT_SECONDS, **options)

    def _hostname(self, address: str) -> str | None:
        try:
            self._run(address, "true")
        except subprocess.CalledProcessError as error:
            # A changed host key must not trigger account provisioning.
            if "REMOTE HOST IDENTIFICATION HAS CHANGED" in (error.stderr or ""):
                return None
            public_key = Path(DCmdb.SSH_KEY + ".pub").read_text().strip()
            if (not public_key.startswith("ssh-ed25519 ") or "\n" in public_key
                    or "\r" in public_key):
                raise ValueError("Expected the local cmdb Ed25519 public key.")
            if re.fullmatch(r"[a-z_][a-z0-9_]*", DCmdb.SERVICE_USER) is None:
                raise ValueError("Invalid service account name.")
            script = (Path(__file__).parent / "scripts" / "provision-cmdb.sh").read_text()
            command = "sh -s -- " + shlex.join([DCmdb.SERVICE_USER, public_key])
            self._run(address, command, user="root", input=script)
            self._run(address, "true")
        result = self._run(address, "hostname -f 2>/dev/null || hostname")
        hostname = result.stdout.strip()
        if not hostname or len(hostname) > 255 or any(character.isspace() or ord(character) < 32
                                                     or ord(character) == 127 for character in hostname):
            return None
        return hostname
