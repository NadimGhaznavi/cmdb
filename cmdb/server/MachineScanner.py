"""Periodically discover machines and refresh their database records."""

from threading import Event, Thread
import socket

import nmap
import pymysql

from cmdb.constants.DCmdb import DCmdb
from cmdb.entity.Machine import Machine
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.Nmap import Nmap


class MachineScanner(Thread):
    def __init__(self) -> None:
        super().__init__(name="machine-scanner")
        self._stop_requested = Event()

    def stop(self) -> None:
        self._stop_requested.set()
        self.join()

    def run(self) -> None:
        print(f"Machine scanner started: {DCmdb.SCAN_TARGET}, "
              f"interval {DCmdb.SCAN_INTERVAL_SECONDS}s", flush=True)
        while not self._stop_requested.is_set():
            try:
                self.scan_once()
            except (nmap.PortScannerError, nmap.PortScannerTimeout, pymysql.MySQLError, OSError):
                pass
            if self._stop_requested.wait(DCmdb.SCAN_INTERVAL_SECONDS):
                break

    def scan_once(self) -> None:
        result = Nmap().scan(DCmdb.SCAN_TARGET, arguments="-sn",
                             timeout=DCmdb.SCAN_TIMEOUT_SECONDS)
        if result["nmap"]["scaninfo"].get("error") or self._stop_requested.is_set():
            return
        machines = []
        for address, host in result["scan"].items():
            if self._stop_requested.is_set():
                return
            if host["status"]["state"] != "up":
                continue
            host_name = next((entry["name"] for entry in host.get("hostnames", [])
                              if entry["name"]), None)
            if not host_name:
                try:
                    host_name = socket.gethostbyaddr(address)[0] or None
                except OSError:
                    pass
            machines.append(Machine(ipAddress=address, hostName=host_name))
        if not machines:
            return
        db = DbMgr()
        try:
            inventory = MachineDb(db)
            with db.transaction():
                for machine in machines:
                    if self._stop_requested.is_set():
                        break
                    inventory.upsert(machine)
        finally:
            db.close()
