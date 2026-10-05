"""Collect one host's MariaDB instance and schema names."""

from threading import Event

from cmdb.interface.SSH import SSH
from cmdb.interface.SSHDb import SSHDb


class MariaDBSource:
    def __init__(self, stop_requested: Event) -> None:
        self._database = SSHDb(SSH(), stop_requested)

    def collect(self, address: str) -> dict | None:
        return self._database.inventory(address)
