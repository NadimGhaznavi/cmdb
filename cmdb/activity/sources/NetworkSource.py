"""Discover responding hosts without DNS lookups."""

import nmap

from cmdb.constants.DCMDB import DCMDB
from cmdb.entity.Machine import Machine
from cmdb.interface.Nmap import Nmap


class NetworkSource:
    def collect(self, target: str) -> list[Machine]:
        result = Nmap().scan(target, arguments='-sn -n', timeout=DCMDB.SCAN_TIMEOUT_SECONDS)
        if result['nmap']['scaninfo'].get('error'):
            raise nmap.PortScannerError('Nmap reported a scan error.')
        return [Machine(ipAddress=address, macAddress=host.get('addresses', {}).get('mac') or None)
                for address, host in result['scan'].items() if host['status']['state'] == 'up']
