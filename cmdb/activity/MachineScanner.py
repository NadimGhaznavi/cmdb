"""Periodically discover machines and refresh their database records."""

from threading import Event, Lock, Thread
from ipaddress import ip_address, ip_network

import nmap
import pymysql

from cmdb.constants.DCMDB import DCMDB
from cmdb.activity.MachineSSH import MachineSSH
from cmdb.activity.ApplicationScanner import ApplicationScanner
from cmdb.entity.StatusMessages import StatusMessages
from cmdb.entity.Machine import Machine
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.Nmap import Nmap
from cmdb.interface.NmapOperatingSystem import operating_system
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb


class MachineScanner(Thread):
    def __init__(self, status_messages: StatusMessages | None = None) -> None:
        super().__init__(name="machine-scanner")
        self.status_messages = status_messages if status_messages is not None else StatusMessages()
        self._stop_requested = Event()
        self._wake = Event()
        self._wake.set()
        self._state_lock = Lock()
        self._scan_id = 0
        self._completed_scan_id = 0
        self._running_scan = False
        self._error = None
        self._up_hosts = None
        self._scan_network = None
        self._host_results = {}
        self._requested_target = None
        self._active_target = None
        self._requested_applications = False
        self._active_applications = False
        self._pending_scan = False

    def host_is_up(self, address: str) -> bool | None:
        """Return the last discovery result, or unknown outside its scope."""
        with self._state_lock:
            if address in self._host_results:
                return self._host_results[address]
            if self._up_hosts is None:
                return None
            if address in self._up_hosts:
                return True
            if self._scan_network is not None and ip_address(address) in self._scan_network:
                return False
            return None

    def request_scan(self, target: str | None = None, *, applications_only: bool = False) -> int:
        """Wake the worker, or share the scan already in progress."""
        with self._state_lock:
            if self._stop_requested.is_set() or not self.is_alive():
                raise RuntimeError("Scanner is unavailable.")
            if self._running_scan:
                if target != self._active_target or applications_only != self._active_applications:
                    raise ValueError("Another scan is in progress. Try again when it finishes.")
                return self._scan_id
            if self._pending_scan and (target != self._requested_target
                                       or applications_only != self._requested_applications):
                raise ValueError("Another scan is pending. Try again when it finishes.")
            self._requested_target = target
            self._requested_applications = applications_only
            self._pending_scan = True
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
        print(f"Machine scanner started: {DCMDB.SCAN_TARGET}, "
              f"interval {DCMDB.SCAN_INTERVAL_SECONDS}s", flush=True)
        while not self._stop_requested.is_set():
            self._wake.wait(DCMDB.SCAN_INTERVAL_SECONDS)
            with self._state_lock:
                if self._stop_requested.is_set():
                    break
                self._wake.clear()
                self._scan_id += 1
                self._running_scan = True
                target = self._requested_target
                applications_only = self._requested_applications
                self._requested_target = None
                self._requested_applications = False
                self._pending_scan = False
                self._active_target = target
                self._active_applications = applications_only
            description = "Applications" if applications_only else f"Inventory ({target or DCMDB.SCAN_TARGET})"
            self.status_messages.append(f"{description}: scan started.")
            error = None
            try:
                if applications_only:
                    self.scan_applications()
                elif target is None:
                    self.scan_once()
                else:
                    self.scan_once(target)
            except (nmap.PortScannerError, nmap.PortScannerTimeout, pymysql.MySQLError, OSError):
                error = "Scan failed. Try again."
            finally:
                outcome = error or ("Scan stopped." if self._stop_requested.is_set() else "Scan complete")
                self.status_messages.append(outcome if outcome == "Scan complete" else f"{description}: {outcome}")
                with self._state_lock:
                    self._completed_scan_id = self._scan_id
                    self._running_scan = False
                    self._error = error

    def scan_once(self, target: str | None = None) -> None:
        result = Nmap().scan(target or DCMDB.SCAN_TARGET, arguments="-sn -n",
                             timeout=DCMDB.SCAN_TIMEOUT_SECONDS)
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
        try:
            network = ip_network(DCMDB.SCAN_TARGET, strict=False)
        except ValueError:
            network = None
        with self._state_lock:
            up_hosts = {machine.ipAddress for machine in machines}
            if target is None:
                self._up_hosts = up_hosts
                self._scan_network = network
                self._host_results.clear()
            else:
                self._host_results[target] = target in up_hosts
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

        scan_error = None
        try:
            self._scan_operating_systems(machine_ids)
        except (nmap.PortScannerError, nmap.PortScannerTimeout, OSError) as error:
            scan_error = error
        if not self._stop_requested.is_set():
            MachineSSH(self._stop_requested).run(machine_ids)
        if not self._stop_requested.is_set():
            ApplicationScanner(self._stop_requested, self.status_messages).run(machine_ids)
        if scan_error is not None:
            raise scan_error

    def scan_applications(self) -> None:
        """Scan applications on inventoried hosts without running Nmap."""
        db = DbMgr()
        try:
            machines = {machine.ipAddress: machine.id for machine in MachineDb(db).list_machines()}
        finally:
            db.close()
        if machines and not self._stop_requested.is_set():
            ApplicationScanner(self._stop_requested, self.status_messages).run(machines)

    def _scan_operating_systems(self, machine_ids: dict[str, int]) -> None:
        # Commit discovery first, without holding a database connection during Nmap.
        result = Nmap().scan(" ".join(machine_ids),
                             arguments="-O -n --osscan-limit --max-os-tries 1",
                             timeout=DCMDB.OS_SCAN_TIMEOUT_SECONDS)
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
