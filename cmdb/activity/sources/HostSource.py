"""Collect hostname, interface MAC and OS release through the host command interface."""

from pathlib import Path
import ipaddress
import json
import re
import shlex
import socket
import subprocess
from threading import Event

from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.SSH import SSH
from cmdb.interface.HostOperatingSystem import operating_system
from cmdb.entity.SoftwareSystem import SoftwareSystem


class HostSource:
    def __init__(self, stop_requested: Event) -> None:
        self._stop_requested = stop_requested
        self._ssh = SSH()

    def collect(self, address: str) -> dict | None:
        result = self._run(address, "hostname -f 2>/dev/null || hostname")
        hostname = result.stdout.strip()
        if not hostname or len(hostname) > 255 or any(character.isspace() or ord(character) < 32
                                                     or ord(character) == 127 for character in hostname):
            return None
        return {'hostname': hostname, 'mac_address': self._mac_address(address),
                'system': self._operating_system(address)}

    def ensure_access(self, address: str) -> bool:
        if not self._ssh.is_local(address):
            with socket.create_connection((address, 22), timeout=DCMDB.SSH_CONNECT_TIMEOUT_SECONDS):
                pass
        try:
            self._run(address, "true")
        except subprocess.CalledProcessError as error:
            if self._ssh.is_local(address):
                raise
            # A changed host key must not trigger account provisioning.
            if "REMOTE HOST IDENTIFICATION HAS CHANGED" in (error.stderr or ""):
                return False
            public_key = Path(DCMDB.SSH_KEY + ".pub").read_text().strip()
            if (not public_key.startswith("ssh-ed25519 ") or "\n" in public_key
                    or "\r" in public_key):
                raise ValueError("Expected the local cmdb Ed25519 public key.")
            if re.fullmatch(r"[a-z_][a-z0-9_]*", DCMDB.AGENT_USER) is None:
                raise ValueError("Invalid service account name.")
            script = (Path(__file__).parent.parent / "scripts" / "provision-agent.sh").read_text()
            command = "sh -s -- " + shlex.join([DCMDB.AGENT_USER, public_key])
            self._run(address, command, user="root", input=script)
            self._run(address, "true")
        return True

    def _run(self, address: str, command: str, **options) -> subprocess.CompletedProcess[str]:
        if self._stop_requested.is_set():
            raise InterruptedError("SSH activity stopped.")
        return self._ssh.run(address, command, timeout=DCMDB.SSH_COMMAND_TIMEOUT_SECONDS,
                             connect_timeout=DCMDB.SSH_CONNECT_TIMEOUT_SECONDS, **options)

    def _operating_system(self, address: str) -> SoftwareSystem | None:
        """Prefer the administrator's os-release file over the vendor fallback."""
        try:
            result = self._run(address, "if [ -e /etc/os-release ]; then cat /etc/os-release; "
                               "else cat /usr/lib/os-release; fi")
        except (OSError, subprocess.SubprocessError):
            return None
        return operating_system(result.stdout)

    def _mac_address(self, address: str) -> str | None:
        """Read the interface owning the scanned IP through the shared command path."""
        try:
            interfaces = json.loads(self._run(address, "ip -j address show").stdout)
            for interface in interfaces:
                mac = interface.get("address", "")
                if (interface.get("link_type") != "ether"
                        or re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac) is None
                        or mac == "00:00:00:00:00:00"):
                    continue
                if any(ipaddress.ip_address(info["local"]) == ipaddress.ip_address(address)
                       for info in interface.get("addr_info", []) if "local" in info):
                    return mac.upper()
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
            # MAC collection is optional; keep a successful hostname observation.
            return None
        return None
