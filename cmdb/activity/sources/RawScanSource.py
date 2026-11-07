"""Collect a short IP-only port and service scan for an unclassified host."""

from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.Nmap import Nmap


class RawScanSource:
    def collect(self, address: str) -> str:
        return Nmap().scan_raw(address, timeout=DCMDB.RAW_SCAN_TIMEOUT_SECONDS)
