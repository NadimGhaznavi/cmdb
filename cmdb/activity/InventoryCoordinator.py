"""Run queued inventory workloads sequentially and apply their observations."""

from collections import deque
from contextlib import contextmanager
from ipaddress import ip_address, ip_network
import subprocess
from threading import Event, Lock, Thread

import nmap
import pymysql

from cmdb.constants.DCMDB import DCMDB
from cmdb.entity.StatusMessages import StatusMessages
from cmdb.entity.Machine import Machine
from cmdb.activity.sources.ApplicationSource import ApplicationSource
from cmdb.activity.sources.HostSource import HostSource
from cmdb.activity.sources.MariaDBSource import MariaDBSource
from cmdb.activity.sources.NetworkSource import NetworkSource
from cmdb.activity.sources.NmapOSSource import NmapOSSource
from cmdb.interface.DataManagerDb import DataManagerDb
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb
from cmdb.interface.SoftwareSystemDb import SoftwareSystemDb


@contextmanager
def inventory_database():
    """Close each connection after its short inventory transaction."""
    db = DbMgr()
    try:
        with db.transaction():
            yield db
    finally:
        db.close()


class InventoryCoordinator(Thread):
    def __init__(self, status_messages: StatusMessages | None = None) -> None:
        super().__init__(name='inventory-coordinator')
        self.status_messages = status_messages if status_messages is not None else StatusMessages()
        self._stop_requested = Event()
        self._wake = Event()
        self._wake.set()
        self._state_lock = Lock()
        self._requests = deque()
        self._next_scan_id = 0
        self._scan_id = 0
        self._completed_scan_id = 0
        self._running_scan = False
        self._error = None
        self._outcomes = deque(maxlen=100)
        self._protected_applications = set()
        self._up_hosts = None
        self._scan_network = None
        self._host_results = {}
        self._network = NetworkSource()
        self._nmap_os = NmapOSSource()
        self._host = HostSource(self._stop_requested)
        self._mariadb = MariaDBSource(self._stop_requested)
        self._application = ApplicationSource()

    def _enqueue(self, target: str | None, applications_only: bool,
                 application: int | None = None) -> int:
        self._next_scan_id += 1
        self._requests.append((self._next_scan_id, target, applications_only, application))
        self._wake.set()
        return self._next_scan_id

    def _check_available(self) -> None:
        if self._stop_requested.is_set() or not self.is_alive():
            raise RuntimeError('Scanner is unavailable.')

    def request_scan(self, target: str | None = None, *, applications_only: bool = False) -> int:
        """Queue one request; the single worker completes requests in FIFO order."""
        with self._state_lock:
            self._check_available()
            return self._enqueue(target, applications_only)

    def add_application(self, name: str) -> tuple[int, int]:
        """Register and queue discovery atomically with respect to pruning."""
        with self._state_lock:
            self._check_available()
            with inventory_database() as db:
                identity = SoftwareSystemDb(db).create_application(name)
            self._protected_applications.add(identity)
            scan_id = self._enqueue(None, True, identity)
            return identity, scan_id

    def scan_status(self, scan_id: int | None = None) -> dict:
        with self._state_lock:
            return {'scanId': self._scan_id, 'completedScanId': self._completed_scan_id,
                    'running': self._running_scan,
                    'error': self._error if scan_id is None else dict(self._outcomes).get(scan_id)}

    def host_is_up(self, address: str) -> bool | None:
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

    def stop(self) -> None:
        self._stop_requested.set()
        self._wake.set()
        self.join()

    def run(self) -> None:
        print(f'Inventory coordinator started: {DCMDB.SCAN_TARGET}, '
              f'interval {DCMDB.SCAN_INTERVAL_SECONDS}s', flush=True)
        while not self._stop_requested.is_set():
            self._wake.wait(DCMDB.SCAN_INTERVAL_SECONDS)
            with self._state_lock:
                if self._stop_requested.is_set():
                    break
                if not self._requests:
                    self._enqueue(None, False)
                scan_id, target, applications_only, application = self._requests.popleft()
                if not self._requests:
                    self._wake.clear()
                self._scan_id = scan_id
                self._running_scan = True
                self._error = None
            description = 'Applications' if applications_only else f'Inventory ({target or DCMDB.SCAN_TARGET})'
            self.status_messages.append(f'{description}: scan started.')
            error = None
            try:
                if applications_only:
                    self.scan_applications(application)
                else:
                    self.scan_inventory(target)
            except (nmap.PortScannerError, nmap.PortScannerTimeout, pymysql.MySQLError, OSError):
                error = 'Scan failed. Try again.'
            finally:
                try:
                    self.prune(application)
                except pymysql.MySQLError:
                    error = 'Inventory pruning failed. Try again.'
                outcome = error or ('Scan stopped.' if self._stop_requested.is_set() else 'Scan complete')
                self.status_messages.append(outcome if outcome == 'Scan complete' else f'{description}: {outcome}')
                with self._state_lock:
                    self._completed_scan_id = scan_id
                    self._running_scan = False
                    self._error = error
                    self._outcomes.append((scan_id, error))

    def scan_inventory(self, target: str | None = None) -> None:
        machines = self._network.collect(target or DCMDB.SCAN_TARGET)
        if self._stop_requested.is_set():
            return
        with self._state_lock:
            up_hosts = {machine.ipAddress for machine in machines}
            if target is None:
                self._up_hosts = up_hosts
                try:
                    self._scan_network = ip_network(DCMDB.SCAN_TARGET, strict=False)
                except ValueError:
                    self._scan_network = None
                self._host_results.clear()
            else:
                self._host_results[target] = target in up_hosts
        if not machines:
            return
        with inventory_database() as db:
            inventory = MachineDb(db)
            for machine in machines:
                machine.id = inventory.upsert(machine)
            hostnames = {machine.id: machine.hostName for machine in inventory.list_machines()}
            for machine in machines:
                machine.hostName = hostnames.get(machine.id)
        if self._stop_requested.is_set():
            return
        scan_error = None
        try:
            observations = self._nmap_os.collect([machine.ipAddress for machine in machines])
            if observations and not self._stop_requested.is_set():
                identities = {machine.ipAddress: machine.id for machine in machines}
                with inventory_database() as db:
                    deployment = SoftwareDeploymentDb(db)
                    for address, system in observations:
                        deployment.record_operating_system(identities[address], system)
        except (nmap.PortScannerError, nmap.PortScannerTimeout, OSError) as error:
            scan_error = error
        applications = self._applications()
        for machine in machines:
            if self._stop_requested.is_set():
                return
            self._collect_host(machine)
            self._collect_applications(machine, applications)
        if scan_error is not None:
            raise scan_error

    def _collect_host(self, machine: Machine) -> None:
        try:
            if not self._host.ensure_access(machine.ipAddress):
                return
            observation = self._host.collect(machine.ipAddress)
        except (OSError, subprocess.SubprocessError, ValueError):
            return
        if observation is None or self._stop_requested.is_set():
            return
        with inventory_database() as db:
            inventory = MachineDb(db)
            inventory.update_discovered_hostname(machine.id, observation['hostname'])
            if observation['mac_address'] is not None:
                inventory.update_discovered_mac(machine.id, observation['mac_address'])
            if observation['system'] is not None:
                SoftwareDeploymentDb(db).record_operating_system(machine.id, observation['system'])
        machine.hostName = observation['hostname']
        if self._stop_requested.is_set():
            return
        observation = self._mariadb.collect(machine.ipAddress)
        if observation is not None and not self._stop_requested.is_set():
            with inventory_database() as db:
                DataManagerDb(db).record_mariadb(machine.id, **observation)

    def _applications(self, application: int | None = None) -> list[dict]:
        with inventory_database() as db:
            software = SoftwareSystemDb(db)
            if application is None:
                return software.list_applications()
            return [record for record in software.list_software_systems()
                    if record['id'] == application]

    def scan_applications(self, application: int | None = None) -> None:
        with inventory_database() as db:
            machines = MachineDb(db).list_machines()
        applications = self._applications(application)
        for machine in machines:
            if self._stop_requested.is_set():
                return
            self._collect_applications(machine, applications)

    def _collect_applications(self, machine: Machine, applications: list[dict]) -> None:
        host = (machine.hostName or '').split('.')[0].lower() or machine.ipAddress
        for application in applications:
            if self._stop_requested.is_set():
                return
            name = application['name']
            outcome, pathname, system = self._application.collect(machine.ipAddress, name)
            if self._stop_requested.is_set():
                return
            if outcome == 'observed':
                with inventory_database() as db:
                    recorded = SoftwareDeploymentDb(db).record_application(
                        machine.id, application['id'], pathname, system.version,
                        type=system.type, subtype=system.subtype, supplier=system.supplier,
                        codename=system.taggedValue[0].value if system.taggedValue else None)
                message = f'{host}: {name} {system.version}' if recorded else f'{host}: {name} — definition removed; skipped.'
            else:
                message = f'{host}: {name} — {outcome}.'
            self.status_messages.append(message)

    def prune(self, application: int | None = None) -> None:
        """Remove unused definitions, preserving additions awaiting their own request."""
        with self._state_lock:
            self._protected_applications.discard(application)
            with inventory_database() as db:
                removed = SoftwareSystemDb(db).prune_unused(self._protected_applications)
        for system in removed:
            name = system['name'] or system['subtype'] or system['type'] or 'SoftwareSystem'
            version = f" {system['version']}" if system['version'] else ''
            self.status_messages.append(f'{name}{version}: pruned — no deployed components.')
