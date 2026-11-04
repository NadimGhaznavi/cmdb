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
from cmdb.interface.Database import connect_database
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.Network import Network
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb
from cmdb.interface.SoftwareSystemDb import SoftwareSystemDb


@contextmanager
def inventory_database():
    """Close each connection after its short inventory transaction."""
    with connect_database() as db:
        with db.transaction():
            yield db


class InventoryCoordinator(Thread):
    def __init__(self, status_messages: StatusMessages | None = None) -> None:
        super().__init__(name='inventory-coordinator')
        self.status_messages = status_messages if status_messages is not None else StatusMessages()
        self._stop_requested = Event()
        self._wake = Event()
        self._state_lock = Lock()
        self._requests = deque()
        self._next_scan_id = 0
        self._scan_id = 0
        self._completed_scan_id = 0
        self._running_scan = False
        self._error = None
        self._outcomes = deque(maxlen=100)
        self._protected_applications = set()
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

    def stop(self) -> None:
        self._stop_requested.set()
        self._wake.set()
        self.join()

    def run(self) -> None:
        print(f'Inventory coordinator ready: {DCMDB.SCAN_TARGET}', flush=True)
        while not self._stop_requested.is_set():
            self._wake.wait()
            with self._state_lock:
                if self._stop_requested.is_set():
                    break
                if not self._requests:
                    continue
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
        up_hosts = {machine.ipAddress for machine in machines}
        scope = ip_network(target or DCMDB.SCAN_TARGET, strict=False)
        gateway = Network.default_gateway()
        with inventory_database() as db:
            inventory = MachineDb(db)
            for machine in machines:
                machine.id = inventory.upsert(machine)
                if machine.ipAddress == gateway:
                    inventory.update_discovered_hostname(machine.id, 'GATEWAY')
                    inventory.update_environment(machine.id, 'prod')
            stored = inventory.list_machines()
            for machine in stored:
                if ip_address(machine.ipAddress) in scope:
                    inventory.update_discovered_online(machine.id, machine.ipAddress in up_hosts)
            hostnames = {machine.id: machine.hostName for machine in stored}
            for machine in machines:
                machine.hostName = 'GATEWAY' if machine.ipAddress == gateway else hostnames.get(machine.id)
        if not machines or self._stop_requested.is_set():
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
            online = self._collect_applications(machine, applications)
            if self._stop_requested.is_set():
                return
            if not online:
                online = any(host.ipAddress == machine.ipAddress
                             for host in self._network.collect(machine.ipAddress))
            if self._stop_requested.is_set():
                return
            with inventory_database() as db:
                MachineDb(db).update_discovered_online(machine.id, online)

    def _collect_applications(self, machine: Machine, applications: list[dict]) -> bool:
        host = (machine.hostName or '').split('.')[0].lower() or machine.ipAddress
        mariadb_observation = None
        mariadb_collected = False
        detected = False
        for application in applications:
            if self._stop_requested.is_set():
                return detected
            name = application['name']
            outcome, pathname, system, components, databases, network = self._application.collect(machine.ipAddress, name)
            if self._stop_requested.is_set():
                return detected
            if outcome == 'observed':
                detected = True
                if databases and not mariadb_collected:
                    mariadb_observation = self._mariadb.collect(machine.ipAddress)
                    mariadb_collected = True
                if self._stop_requested.is_set():
                    return detected
                with inventory_database() as db:
                    if databases and mariadb_observation is not None:
                        DataManagerDb(db).record_mariadb(machine.id, **mariadb_observation)
                    recorded = SoftwareDeploymentDb(db).record_application(
                        machine.id, application['id'], pathname, system.version,
                        type=system.type, subtype=system.subtype, supplier=system.supplier,
                        codename=system.taggedValue[0].value if system.taggedValue else None,
                        components=components, network=network, databases=tuple(
                            declaration for declaration in databases
                            if mariadb_observation is not None and declaration[1] in mariadb_observation['databases']))
                message = f'{host}: {name} {system.version}' if recorded else f'{host}: {name} — definition removed; skipped.'
            else:
                message = f'{host}: {name} — {outcome}.'
            self.status_messages.append(message)
        return detected

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
