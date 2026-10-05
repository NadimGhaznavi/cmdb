"""Collect unambiguous Nmap OS classifications for an explicit host scope."""

import nmap

from cmdb.constants.DCMDB import DCMDB
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.Nmap import Nmap
from cmdb.interface.NmapOperatingSystem import operating_system


class NmapOSSource:
    def collect(self, addresses: list[str]) -> list[tuple[str, SoftwareSystem]]:
        if not addresses:
            return []
        result = Nmap().scan(' '.join(addresses),
                             arguments='-O -n --osscan-limit --max-os-tries 1',
                             timeout=DCMDB.OS_SCAN_TIMEOUT_SECONDS)
        if result['nmap']['scaninfo'].get('error'):
            raise nmap.PortScannerError('Nmap reported an OS scan error.')
        observations = []
        for address, host in result['scan'].items():
            if address in addresses and host['status']['state'] == 'up':
                system = operating_system(host)
                if system is not None:
                    observations.append((address, system))
        return observations
