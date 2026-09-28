"""Run network scans through python-nmap."""

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
