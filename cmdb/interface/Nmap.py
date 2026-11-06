"""Run structured and raw-output Nmap scans."""

from ipaddress import ip_address
import subprocess
from typing import Any

import nmap


class Nmap:
    """Own one scanner; do not share an instance between worker threads."""

    def __init__(self) -> None:
        self._scanner = nmap.PortScanner(nmap_search_path=("/usr/bin/nmap",))

    def scan(
        self,
        hosts: str,
        ports: str | None = None,
        *,
        arguments: str = "-sV",
        timeout: int = 0,
    ) -> dict[str, Any]:
        """Return python-nmap results, propagating scan errors and timeouts.

        Hosts and ports use Nmap's target and port syntax. A timeout of zero
        leaves the scan unlimited, following python-nmap's convention.
        """
        if not hosts.strip():
            raise ValueError("Scan hosts must not be empty.")
        return self._scanner.scan(
            hosts=hosts, ports=ports, arguments=arguments, timeout=timeout, sudo=True,
        )

    def scan_raw(self, address: str, *, timeout: int) -> str:
        """Capture common TCP ports and basic service details within one short budget."""
        target = ip_address(address)
        command = ['sudo', '-n', '/usr/bin/nmap', '-n', '-Pn', '-sV', '--version-light',
                   '--top-ports', '1000', '-T4', '--max-retries', '1', '--reason', '-v',
                   '--stats-every', '5s', '--host-timeout', f'{timeout}s']
        if target.version == 6:
            command.append('-6')
        command.append(str(target))
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=timeout, check=True)
        if b'due to host timeout' in result.stdout:
            raise subprocess.TimeoutExpired(command, timeout, output=result.stdout)
        return result.stdout.decode('utf-8', errors='replace')
