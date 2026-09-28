"""Periodically discover machines and refresh their database records."""

from threading import Event, Lock, Thread

import nmap
import pymysql

from cmdb.constants.DCmdb import DCmdb
from cmdb.entity.Machine import Machine
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.Nmap import Nmap
from cmdb.interface.NmapOperatingSystem import operating_system
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb


class MachineScanner(Thread):
    def __init__(self) -> None:
        super().__init__(name="machine-scanner")
        self._stop_requested = Event()
        self._wake = Event()
        self._wake.set()
        self._state_lock = Lock()
        self._scan_id = 0
        self._completed_scan_id = 0
        self._running_scan = False
        self._error = None

    def request_scan(self) -> int:
        """Wake the worker, or share the scan already in progress."""
        with self._state_lock:
            if self._stop_requested.is_set() or not self.is_alive():
                raise RuntimeError("Scanner is unavailable.")
            if self._running_scan:
                return self._scan_id
            self._wake.set()
            return self._scan_id + 1

    def scan_status(self) -> dict:
        with self._state_lock:
            return {"scanId": self._scan_id, "completedScanId": self._completed_scan_id,
                    "running": self._running_scan, "error": self._error}

    def stop(self) -> None:
        self._stop_requested.set()
        self._wake.set()
        self.join()

    def run(self) -> None:
        print(f"Machine scanner started: {DCmdb.SCAN_TARGET}, "
              f"interval {DCmdb.SCAN_INTERVAL_SECONDS}s", flush=True)
        while not self._stop_requested.is_set():
            self._wake.wait(DCmdb.SCAN_INTERVAL_SECONDS)
            with self._state_lock:
                if self._stop_requested.is_set():
                    break
                self._wake.clear()
                self._scan_id += 1
                self._running_scan = True
            error = None
            try:
                self.scan_once()
            except (nmap.PortScannerError, nmap.PortScannerTimeout, pymysql.MySQLError, OSError):
                error = "Scan failed. Try again."
            finally:
                with self._state_lock:
                    self._completed_scan_id = self._scan_id
                    self._running_scan = False
                    self._error = error

    def scan_once(self) -> None:
        result = Nmap().scan(DCmdb.SCAN_TARGET, arguments="-sn -n",
                             timeout=DCmdb.SCAN_TIMEOUT_SECONDS)
        if result["nmap"]["scaninfo"].get("error"):
            raise nmap.PortScannerError("Nmap reported a scan error.")
        if self._stop_requested.is_set():
            return
        machines = []
        for address, host in result["scan"].items():
            if self._stop_requested.is_set():
                return
            if host["status"]["state"] != "up":
                continue
            mac_address = host.get("addresses", {}).get("mac") or None
            machines.append(Machine(ipAddress=address, macAddress=mac_address))
        if not machines:
            return
        db = DbMgr()
        machine_ids = {}
        try:
            inventory = MachineDb(db)
            with db.transaction():
                for machine in machines:
                    if self._stop_requested.is_set():
                        break
                    machine_ids[machine.ipAddress] = inventory.upsert(machine)
        finally:
            db.close()
        if self._stop_requested.is_set():
            return

        # Commit discovery first, without holding a database connection during Nmap.
        result = Nmap().scan(" ".join(machine_ids),
                             arguments="-O -n --osscan-limit --max-os-tries 1",
                             timeout=DCmdb.OS_SCAN_TIMEOUT_SECONDS)
        if result["nmap"]["scaninfo"].get("error"):
            raise nmap.PortScannerError("Nmap reported an OS scan error.")
        observations = []
        for address, host in result["scan"].items():
            if address not in machine_ids or host["status"]["state"] != "up":
                continue
            system = operating_system(host)
            if system is not None:
                observations.append((machine_ids[address], system))
        if self._stop_requested.is_set() or not observations:
            return
        db = DbMgr()
        try:
            deployment = SoftwareDeploymentDb(db)
            with db.transaction():
                for machine_id, system in observations:
                    if self._stop_requested.is_set():
                        break
                    deployment.record_operating_system(machine_id, system)
        finally:
            db.close()
