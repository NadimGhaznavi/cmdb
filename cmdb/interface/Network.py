"""Resolve network bindings and the local default gateway."""

from functools import cache
from ipaddress import IPv4Address
from pathlib import Path

from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.Configuration import Configuration


class Network:
    @staticmethod
    def default_gateway() -> str | None:
        """Read the lowest-metric active IPv4 default gateway on Linux."""
        try:
            routes = Path('/proc/net/route').read_text().splitlines()
        except OSError:
            return None
        gateways = []
        for route in routes[1:]:
            fields = route.split()
            if (len(fields) >= 8 and fields[1] == '00000000'
                    and fields[7] == '00000000' and int(fields[3], 16) & 3 == 3
                    and fields[2] != '00000000'):
                gateway = str(IPv4Address(int(fields[2], 16).to_bytes(4, 'little')))
                gateways.append((int(fields[6]), gateway))
        return min(gateways, key=lambda route: route[0])[1] if gateways else None

    @staticmethod
    def binding(use: str) -> tuple[str, int]:
        path = Path(DCMDB.BASE_DIR) / DCMDB.CONFIG_FILE
        return Network._bindings(path, DCMDB.CMDB_NETWORK)[use]

    @staticmethod
    def destination(use: str) -> tuple[str, int]:
        interface, port = Network.binding(use)
        return ('127.0.0.1' if interface == '0.0.0.0' else interface, port)

    @staticmethod
    @cache
    def _bindings(path: Path, defaults: tuple[tuple[str, str, int], ...]) -> dict[str, tuple[str, int]]:
        return Configuration.read(path, defaults)
