"""Sequential workloads, request lifecycle and inventory pruning contracts."""

import subprocess
from threading import Event
from unittest import TestCase
from unittest.mock import Mock, patch

import nmap
import pymysql

from cmdb.activity.InventoryCoordinator import InventoryCoordinator
from cmdb.entity.Machine import Machine
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.entity.TaggedValue import TaggedValue
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb


class InventoryCoordinatorTests(TestCase):
    def setUp(self):
        for name in ('DbMgr', 'MachineDb', 'SoftwareDeploymentDb', 'SoftwareSystemDb', 'DataManagerDb'):
            patcher = patch('cmdb.activity.InventoryCoordinator.' + name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.SoftwareSystemDb.return_value.list_applications.return_value = [{'id': 17, 'name': 'MyCount'}]
        self.SoftwareSystemDb.return_value.prune_unused.return_value = []
        self.MachineDb.return_value.list_machines.return_value = [Machine('192.0.2.7', id=7)]
        self.MachineDb.return_value.upsert.return_value = 7
        self.worker = InventoryCoordinator()
        for name in ('_network', '_nmap_os', '_host', '_mariadb', '_application'):
            setattr(self.worker, name, Mock())
        self.worker._network.collect.return_value = [Machine('192.0.2.7')]
        self.worker._nmap_os.collect.return_value = []
        self.worker._host.ensure_access.return_value = True
        self.worker._host.collect.return_value = {
            'hostname': 'SALLY.Example.COM', 'mac_address': None, 'system': None}
        self.worker._mariadb.collect.return_value = None
        self.worker._application.collect.return_value = ('observed', '/opt/prod/mycount', SoftwareSystem(version='1.2.3'), ())

    def test_inventory_collects_and_saves_in_sequence_without_open_remote_transaction(self):
        order = []
        transaction_open = False
        def begin():
            nonlocal transaction_open
            self.assertFalse(transaction_open)
            transaction_open = True
        def end(*args):
            nonlocal transaction_open
            transaction_open = False
        transaction = self.DbMgr.return_value.transaction.return_value
        transaction.__enter__.side_effect = begin
        transaction.__exit__.side_effect = end
        def collect(label, value):
            def read(*args):
                self.assertFalse(transaction_open)
                order.append(label)
                return value
            return read
        system = SoftwareSystem(type='OS', subtype='Linux', version='6.X')
        self.worker._network.collect.side_effect = collect('network', [Machine('192.0.2.7')])
        self.worker._nmap_os.collect.side_effect = collect('nmap-os', [('192.0.2.7', system)])
        self.worker._host.ensure_access.side_effect = collect('access', True)
        self.worker._host.collect.side_effect = collect('host', {
            'hostname': 'sally', 'mac_address': 'AA:BB:CC:DD:EE:FF', 'system': system})
        observation = {'version': '11.8-MariaDB', 'pathname': '/var/lib/mysql/', 'databases': ['cmdb']}
        self.worker._mariadb.collect.side_effect = collect('mariadb', observation)
        self.worker._application.collect.side_effect = collect('application', ('observed', '/opt/prod/mycount', SoftwareSystem(version='1.2.3'), ()))
        self.worker.scan_inventory()
        self.assertEqual(order, ['network', 'nmap-os', 'access', 'host', 'mariadb', 'application'])
        self.DataManagerDb.return_value.record_mariadb.assert_called_once_with(7, **observation)
        self.MachineDb.return_value.update_discovered_mac.assert_called_once_with(7, 'AA:BB:CC:DD:EE:FF')
        self.assertEqual(self.SoftwareDeploymentDb.return_value.record_operating_system.call_count, 2)
        self.SoftwareDeploymentDb.return_value.record_application.assert_called_once_with(
            7, 17, '/opt/prod/mycount', '1.2.3',
            type=None, subtype=None, supplier=None, codename=None, components=())
        self.assertEqual(self.worker.status_messages.snapshot()[-1]['message'], 'sally: MyCount 1.2.3')

    def test_os_timeout_still_collects_host_database_and_applications(self):
        self.worker._nmap_os.collect.side_effect = nmap.PortScannerTimeout('timeout')
        with self.assertRaises(nmap.PortScannerTimeout):
            self.worker.scan_inventory()
        self.worker._host.collect.assert_called_once()
        self.worker._mariadb.collect.assert_called_once()
        self.worker._application.collect.assert_called_once()

    def test_application_metadata_reaches_persistence(self):
        system = SoftwareSystem(version='1.2.3', type='application', subtype='inventory',
                                supplier='Example Supplier', taggedValue=[
                                    TaggedValue(tag='VERSION_CODENAME', value='Orion')])
        self.worker._application.collect.return_value = ('observed', '/opt/prod/mycount', system, (('Screenshots', 'pages/marketing'),))
        self.worker.scan_applications()
        self.SoftwareDeploymentDb.return_value.record_application.assert_called_once_with(
            7, 17, '/opt/prod/mycount', '1.2.3', type='application', subtype='inventory',
            supplier='Example Supplier', codename='Orion', components=(('Screenshots', 'pages/marketing'),))

    def test_host_failure_does_not_block_application_or_next_host(self):
        self.worker._network.collect.return_value.append(Machine('192.0.2.8'))
        self.MachineDb.return_value.upsert.side_effect = [7, 8]
        self.worker._host.ensure_access.side_effect = [subprocess.TimeoutExpired('ssh', 30), True]
        self.worker.scan_inventory()
        self.assertEqual(self.worker._application.collect.call_count, 2)
        self.worker._mariadb.collect.assert_called_once_with('192.0.2.8')

    def test_absent_failed_and_deleted_applications_preserve_inventory(self):
        for outcome in ('not detected', 'read failed', 'unsupported name'):
            self.worker._application.collect.return_value = (outcome, None, None, ())
            self.worker.scan_applications()
            self.assertIn(outcome, self.worker.status_messages.snapshot()[-1]['message'])
        self.SoftwareDeploymentDb.assert_not_called()
        self.worker._application.collect.return_value = ('observed', '/opt/prod/mycount', SoftwareSystem(version='1.2.3'), ())
        self.SoftwareDeploymentDb.return_value.record_application.return_value = False
        self.worker.scan_applications()
        self.assertIn('definition removed', self.worker.status_messages.snapshot()[-1]['message'])
        self.worker._network.collect.assert_not_called()

    def test_stop_after_read_prevents_write(self):
        def read(*args):
            self.worker._stop_requested.set()
            return ('observed', '/opt/prod/mycount', SoftwareSystem(version='1.2.3'), ())
        self.worker._application.collect.side_effect = read
        self.worker.scan_applications()
        self.SoftwareDeploymentDb.assert_not_called()

    def test_reachability_retains_last_successful_discovery_and_target_scope(self):
        with patch('cmdb.activity.InventoryCoordinator.DCMDB.SCAN_TARGET', '192.0.2.0/24'):
            self.worker._network.collect.return_value = []
            self.worker.scan_inventory()
            self.assertFalse(self.worker.host_is_up('192.0.2.7'))
            self.assertIsNone(self.worker.host_is_up('192.0.3.7'))
            self.worker._network.collect.side_effect = nmap.PortScannerTimeout('timeout')
            with self.assertRaises(nmap.PortScannerTimeout):
                self.worker.scan_inventory()
            self.assertFalse(self.worker.host_is_up('192.0.2.7'))
            self.worker._network.collect.side_effect = None
            self.worker._network.collect.return_value = [Machine('192.0.2.7')]
            self.worker.scan_inventory('192.0.2.7')
            self.assertTrue(self.worker.host_is_up('192.0.2.7'))
            self.assertFalse(self.worker.host_is_up('192.0.2.8'))

    def test_fifo_requests_each_prune_even_when_collection_fails(self):
        worker = self.worker
        worker.is_alive = Mock(return_value=True)
        ids = [worker.request_scan('192.0.2.7'), worker.request_scan(applications_only=True),
               worker.request_scan('192.0.2.8')]
        self.assertEqual(ids, [1, 2, 3])
        order = []
        def inventory(target):
            order.append(target)
            if target == '192.0.2.7':
                raise OSError('private details')
            worker._stop_requested.set()
        worker.scan_inventory = inventory
        worker.scan_applications = lambda application: order.append('applications')
        worker.run()
        self.assertEqual(order, ['192.0.2.7', 'applications', '192.0.2.8'])
        self.assertEqual(self.SoftwareSystemDb.return_value.prune_unused.call_count, 3)
        self.assertEqual(worker.scan_status()['completedScanId'], 3)
        self.assertEqual(worker.scan_status(1)['error'], 'Scan failed. Try again.')
        self.assertIsNone(worker.scan_status(2)['error'])
        messages = [entry['message'] for entry in worker.status_messages.snapshot()]
        self.assertIn('Inventory (192.0.2.7): Scan failed. Try again.', messages)

    def test_add_during_active_request_survives_pruning_until_own_scan(self):
        worker = self.worker
        entered, release = Event(), Event()
        self.SoftwareSystemDb.return_value.create_application.return_value = 42
        protected = []
        def prune(ids):
            protected.append(set(ids))
            return [] if ids else [{'name': 'NewApp', 'type': None, 'subtype': None, 'version': None}]
        self.SoftwareSystemDb.return_value.prune_unused.side_effect = prune
        def inventory(target):
            entered.set()
            if not release.wait(3):
                raise AssertionError('Timed out waiting for registration')
        worker.scan_inventory = inventory
        worker.scan_applications = Mock(side_effect=lambda identity: worker._stop_requested.set())
        worker.start()
        try:
            worker.request_scan()
            self.assertTrue(entered.wait(3))
            self.assertEqual(worker.add_application('NewApp'), (42, 2))
            release.set()
            worker.join(3)
            self.assertFalse(worker.is_alive())
        finally:
            release.set()
            worker.stop()
        self.assertEqual(protected, [{42}, set()])
        worker.scan_applications.assert_called_once_with(42)
        self.assertIn('NewApp: pruned — no deployed components.',
                      [entry['message'] for entry in worker.status_messages.snapshot()])

    def test_empty_inventory_still_prunes_and_logs_release_name(self):
        worker = self.worker
        worker._network.collect.return_value = []
        self.SoftwareSystemDb.return_value.prune_unused.return_value = [
            {'name': 'BMGeoIP', 'type': None, 'subtype': None, 'version': '0.4.1'}]
        original = worker.scan_inventory
        def scan(target):
            original(target)
            worker._stop_requested.set()
        worker.scan_inventory = scan
        worker.is_alive = Mock(return_value=True)
        worker.request_scan()
        worker.run()
        self.SoftwareSystemDb.return_value.prune_unused.assert_called_once_with(set())
        worker._host.collect.assert_not_called()
        self.assertIn('BMGeoIP 0.4.1: pruned — no deployed components.',
                      [entry['message'] for entry in worker.status_messages.snapshot()])

    def test_worker_waits_without_a_timer_until_explicit_request(self):
        waiting, scanned = Event(), Event()
        original_wait = self.worker._wake.wait
        def wait(*args):
            self.assertEqual(args, ())
            waiting.set()
            return original_wait(*args)
        self.worker._wake.wait = wait
        self.worker.scan_inventory = Mock(side_effect=lambda target: scanned.set())
        self.worker.start()
        try:
            self.assertTrue(waiting.wait(3))
            self.worker.scan_inventory.assert_not_called()
            self.DbMgr.assert_not_called()
            self.worker.request_scan()
            self.assertTrue(scanned.wait(3))
        finally:
            self.worker.stop()
        self.worker.scan_inventory.assert_called_once_with(None)

    def test_registration_failure_rolls_back_without_queued_or_protected_work(self):
        self.worker.is_alive = Mock(return_value=True)
        self.SoftwareSystemDb.return_value.create_application.side_effect = pymysql.OperationalError('failed')
        with self.assertRaises(pymysql.OperationalError):
            self.worker.add_application('NewApp')
        self.assertFalse(self.worker._requests)
        self.assertFalse(self.worker._protected_applications)
        self.DbMgr.return_value.close.assert_called_once()
        self.assertIs(self.DbMgr.return_value.transaction.return_value.__exit__.call_args.args[0],
                      pymysql.OperationalError)

    def test_unavailable_worker_rejects_registration_and_scan_without_writes(self):
        with self.assertRaises(RuntimeError):
            self.worker.request_scan()
        with self.assertRaises(RuntimeError):
            self.worker.add_application('NewApp')
        self.DbMgr.assert_not_called()

    def test_pruning_failure_is_reported_and_next_request_runs(self):
        worker = self.worker
        worker.is_alive = Mock(return_value=True)
        worker.request_scan(applications_only=True)
        worker.request_scan(applications_only=True)
        calls = 0
        def scan(identity):
            nonlocal calls
            calls += 1
            if calls == 2:
                worker._stop_requested.set()
        worker.scan_applications = scan
        self.SoftwareSystemDb.return_value.prune_unused.side_effect = [pymysql.OperationalError('failed'), []]
        worker.run()
        self.assertEqual(calls, 2)
        self.assertIn('Applications: Inventory pruning failed. Try again.',
                      [entry['message'] for entry in worker.status_messages.snapshot()])


class ApplicationDeploymentTests(TestCase):
    def test_deleted_definition_is_not_recreated_by_stale_observation(self):
        db = Mock()
        db.query.return_value = []
        self.assertFalse(SoftwareDeploymentDb(db).record_application(7, 17, '/opt/prod/mycount', '1.2.3'))
        db.execute.assert_not_called()
        db.insert.assert_not_called()
