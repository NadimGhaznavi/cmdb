"""Run remote commands as cmdb using the service account's SSH identity."""

import subprocess

from cmdb.constants.DCmdb import DCmdb


class SSH:
    def run(self, host: str, command: str, *, port: int = 22,
            timeout: int = 30, connect_timeout: int = 10) -> subprocess.CompletedProcess[str]:
        """Execute a remote shell command and return captured stdout/stderr.

        Nonzero exits raise CalledProcessError; timeouts raise TimeoutExpired.
        The local process needs read access to the cmdb private key.
        """
        if (not host or host.startswith("-") or "@" in host or "\0" in host
                or any(character.isspace() for character in host)):
            raise ValueError("Provide a hostname or IP address without a username.")
        if not command.strip() or "\0" in command:
            raise ValueError("A remote command is required.")
        if not 1 <= port <= 65535 or timeout <= 0 or connect_timeout <= 0:
            raise ValueError("Use a valid port and positive timeouts.")
        return subprocess.run(
            ["/usr/bin/ssh", "-F", "/dev/null", "-T",
             "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
             "-o", "IdentityAgent=none", "-o", "StrictHostKeyChecking=accept-new",
             "-o", f"UserKnownHostsFile={DCmdb.SSH_KNOWN_HOSTS}",
             "-o", f"ConnectTimeout={connect_timeout}",
             "-i", DCmdb.SSH_KEY, "-l", DCmdb.SERVICE_USER, "-p", str(port),
             "--", host, command],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=timeout, check=True,
        )
