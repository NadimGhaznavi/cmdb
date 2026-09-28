"""Run host commands through SSH, or directly for local targets."""

import subprocess
import ipaddress
import os
import pwd
import socket

from cmdb.constants.DCmdb import DCmdb


class SSH:
    def is_local(self, host: str) -> bool:
        """Recognize addresses assigned here without launching a command."""
        try:
            addresses = socket.getaddrinfo(host, 0, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        for family, kind, protocol, _, address in addresses:
            if ipaddress.ip_address(address[0]).is_unspecified:
                continue
            try:
                with socket.socket(family, kind, protocol) as probe:
                    probe.bind(address)
                return True
            except OSError:
                continue
        return False

    def run(self, host: str, command: str, *, user: str = DCmdb.AGENT_USER, port: int = 22,
            timeout: int = 30, connect_timeout: int = 10,
            input: str | None = None) -> subprocess.CompletedProcess[str]:
        """Execute a host shell command and return captured stdout/stderr.

        Nonzero exits raise CalledProcessError; timeouts raise TimeoutExpired.
        The local process needs read access to the cmdb private key.
        """
        if (not host or host.startswith("-") or "@" in host or "\0" in host
                or any(character.isspace() for character in host)):
            raise ValueError("Provide a hostname or IP address without a username.")
        if not command.strip() or "\0" in command:
            raise ValueError("A remote command is required.")
        if (not user or user.startswith("-") or "@" in user or "\0" in user
                or any(character.isspace() for character in user)):
            raise ValueError("Provide a remote username without a hostname.")
        if not 1 <= port <= 65535 or timeout <= 0 or connect_timeout <= 0:
            raise ValueError("Use a valid port and positive timeouts.")
        if self.is_local(host):
            argv = ["/bin/sh", "-c", command]
            try:
                target_uid = pwd.getpwnam(user).pw_uid
            except KeyError as error:
                raise PermissionError("Local inventory account is not installed.") from error
            if target_uid != os.geteuid():
                if user != DCmdb.AGENT_USER:
                    raise PermissionError("Local identity switching is limited to the inventory agent.")
                argv = ["/usr/bin/sudo", "-n", "-H", "-u", user, "--", *argv]
        else:
            argv = ["/usr/bin/ssh", "-F", "/dev/null", "-T",
             "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
             "-o", "IdentityAgent=none", "-o", "StrictHostKeyChecking=accept-new",
             "-o", f"UserKnownHostsFile={DCmdb.SSH_KNOWN_HOSTS}",
             "-o", f"ConnectTimeout={connect_timeout}",
             "-i", DCmdb.SSH_KEY, "-l", user, "-p", str(port),
             "--", host, command]
        return subprocess.run(
            argv,
            **({"stdin": subprocess.DEVNULL} if input is None else {"input": input}),
            capture_output=True, text=True,
            timeout=timeout, check=True,
        )
