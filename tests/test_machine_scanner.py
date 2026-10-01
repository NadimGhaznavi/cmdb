"""Discovery persistence and background worker lifecycle contracts."""

from unittest import TestCase
from unittest.mock import Mock, call, patch
from threading import Event

import nmap
import pymysql

from cmdb.entity.Machine import Machine
from cmdb.entity.StatusMessages import StatusMessages
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.constants.DCmdb import DCmdb
from cmdb.activity.MachineScanner import MachineScanner


class MachineScannerTests(TestCase):
    def test_worker_reports_scan_outcome_to_shared_history(self):
        for applications_only in (False, True):
            for failure in (None, OSError('private failure')):
                with self.subTest(applications_only=applications_only, failure=failure):
                    history = StatusMessages()
                    worker = MachineScanner(history)
                    worker._requested_applications = applications_only
                    waits = 0

                    def wait(interval):
                        nonlocal waits
                        waits += 1
                        if waits == 2:
                            worker._stop_requested.set()

                    worker._wake.wait = Mock(side_effect=wait)
                    worker.scan_once = Mock(side_effect=failure)
                    worker.scan_applications = Mock(side_effect=failure)
                    worker.run()
                    description = ('Applications' if applications_only
                                   else f'Inventory ({DCmdb.SCAN_TARGET})')
                    outcome = 'Scan failed. Try again.' if failure else 'Scan completed.'
                    self.assertEqual(history.snapshot(), [
                        {'source': 'cmdb.activity.MachineScanner',
                         'message': f'{description}: scan started.'},
                        {'source': 'cmdb.activity.MachineScanner',
                         'message': f'{description}: {outcome}'}])
                    selected = worker.scan_applications if applications_only else worker.scan_once
                    selected.assert_called_once_with()

    def setUp(self):
        applications = patch("cmdb.activity.MachineScanner.ApplicationScanner")
        self.applications = applications.start()
        self.addCleanup(applications.stop)
        activity = patch("cmdb.activity.MachineScanner.MachineSSH")
        self.ssh_activity = activity.start()
        self.addCleanup(activity.stop)

    @patch("cmdb.activity.MachineScanner.SoftwareDeploymentDb")
    @patch("cmdb.activity.MachineScanner.MachineDb")
    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_os_scan_follows_committed_discovery_and_uses_stable_machine_id(
            self, scanner, db, inventory, deployment):
        discovery = {"nmap": {"scaninfo": {}}, "scan": {
            "192.168.0.7": {"status": {"state": "up"}}}}
        detected = {"status": {"state": "up"}, "osmatch": [{"accuracy": "100", "osclass": [
            {"accuracy": "100", "osfamily": "Linux", "vendor": "Linux", "osgen": "6.X"}]}]}
        inventory.return_value.upsert.return_value = 42

        def scan(*args, **kwargs):
            if kwargs['arguments'] == '-sn -n':
                return discovery
            db.return_value.transaction.return_value.__exit__.assert_called_once_with(None, None, None)
            db.return_value.close.assert_called_once()
            return {"nmap": {"scaninfo": {}}, "scan": {
                "192.168.0.7": detected, "192.168.0.99": detected}}

        scanner.return_value.scan.side_effect = scan
        MachineScanner().scan_once()
        deployment.return_value.record_operating_system.assert_called_once_with(
            42, SoftwareSystem(type="OS", subtype="Linux", supplier="Linux", version="6.X"))
        self.assertEqual(db.return_value.close.call_count, 2)
        self.ssh_activity.return_value.run.assert_called_once_with({"192.168.0.7": 42})
        self.applications.return_value.run.assert_called_once_with({"192.168.0.7": 42})

    @patch("cmdb.activity.MachineScanner.SoftwareDeploymentDb")
    @patch("cmdb.activity.MachineScanner.MachineDb")
    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_os_timeout_retains_committed_machine_discovery(self, scanner, db, inventory, deployment):
        scanner.return_value.scan.side_effect = [
            {"nmap": {"scaninfo": {}}, "scan": {"192.168.0.7": {"status": {"state": "up"}}}},
            nmap.PortScannerTimeout("OS scan timed out"),
        ]
        with self.assertRaises(nmap.PortScannerTimeout):
            MachineScanner().scan_once()
        inventory.return_value.upsert.assert_called_once()
        db.return_value.transaction.return_value.__exit__.assert_called_once_with(None, None, None)
        db.return_value.close.assert_called_once()
        deployment.assert_not_called()
        self.ssh_activity.return_value.run.assert_called_once()

    @patch("cmdb.activity.MachineScanner.SoftwareDeploymentDb")
    @patch("cmdb.activity.MachineScanner.MachineDb")
    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_stop_during_os_scan_prevents_os_writes(self, scanner, db, inventory, deployment):
        worker = MachineScanner()
        result = {"nmap": {"scaninfo": {}}, "scan": {
            "192.168.0.7": {"status": {"state": "up"}}}}

        def scan(*args, **kwargs):
            if kwargs['arguments'] != '-sn -n':
                worker._stop_requested.set()
            return result

        scanner.return_value.scan.side_effect = scan
        worker.scan_once()
        inventory.return_value.upsert.assert_called_once()
        deployment.assert_not_called()
        self.ssh_activity.assert_not_called()

    @patch("cmdb.activity.MachineScanner.MachineDb")
    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_only_up_hosts_are_persisted_and_connection_is_closed(self, scanner, db, inventory):
        scanner.return_value.scan.return_value = {
            "nmap": {"scaninfo": {}},
            "scan": {
                "192.168.0.1": {"status": {"state": "up"},
                                "addresses": {"ipv4": "192.168.0.1", "mac": "00:11:22:33:44:55"},
                                "hostnames": [{"name": "router"}]},
                "192.168.0.2": {"status": {"state": "up"},
                                "hostnames": [{"name": ""}]},
                "192.168.0.3": {"status": {"state": "down"}},
            },
        }
        worker = MachineScanner()
        self.assertIsNone(worker.host_is_up("192.168.0.1"))
        worker.scan_once()
        self.assertTrue(worker.host_is_up("192.168.0.1"))
        self.assertFalse(worker.host_is_up("192.168.0.3"))
        self.assertFalse(worker.host_is_up("192.168.0.99"))
        self.assertIsNone(worker.host_is_up("192.168.1.1"))
        self.assertEqual([call.args[0] for call in inventory.return_value.upsert.call_args_list],
                         [Machine("192.168.0.1", macAddress="00:11:22:33:44:55"),
                          Machine("192.168.0.2")])
        db.return_value.transaction.assert_called_once()
        db.return_value.close.assert_called_once()

        inventory.return_value.upsert.side_effect = pymysql.OperationalError("failed")
        with self.assertRaises(pymysql.OperationalError):
            worker.scan_once()
        self.assertEqual(db.return_value.close.call_count, 2)
        transaction = db.return_value.transaction.return_value
        self.assertIs(transaction.__exit__.call_args.args[0], pymysql.OperationalError)

    @patch("cmdb.activity.MachineScanner.MachineDb")
    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_discovery_disables_dns_and_ignores_reported_hostnames(self, scanner, db, inventory):
        scanner.return_value.scan.return_value = {
            "nmap": {"scaninfo": {}}, "scan": {
                "192.168.0.1": {"status": {"state": "up"}, "hostnames": [{"name": "router"}]},
                "192.168.0.2": {"status": {"state": "up"}, "hostnames": []},
                "192.168.0.3": {"status": {"state": "up"}, "hostnames": [{"name": ""}]},
            },
        }
        with patch("socket.gethostbyaddr") as lookup:
            MachineScanner().scan_once()
            lookup.assert_not_called()
        self.assertEqual(scanner.return_value.scan.call_args_list, [
            call(DCmdb.SCAN_TARGET, arguments="-sn -n", timeout=DCmdb.SCAN_TIMEOUT_SECONDS),
            call("192.168.0.1 192.168.0.2 192.168.0.3",
                 arguments="-O -n --osscan-limit --max-os-tries 1", timeout=DCmdb.OS_SCAN_TIMEOUT_SECONDS),
        ])
        self.assertEqual([call.args[0] for call in inventory.return_value.upsert.call_args_list],
                         [Machine("192.168.0.1"), Machine("192.168.0.2"),
                          Machine("192.168.0.3")])
        self.ssh_activity.return_value.run.assert_called_once()

    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_reachability_retains_last_successful_discovery(self, scanner, db):
        worker = MachineScanner()
        scanner.return_value.scan.return_value = {"nmap": {"scaninfo": {}}, "scan": {}}
        worker.scan_once()
        self.assertFalse(worker.host_is_up("192.168.0.7"))
        scanner.return_value.scan.side_effect = nmap.PortScannerTimeout("timeout")
        with self.assertRaises(nmap.PortScannerTimeout):
            worker.scan_once()
        self.assertFalse(worker.host_is_up("192.168.0.7"))
        fresh_worker = MachineScanner()
        with self.assertRaises(nmap.PortScannerTimeout):
            fresh_worker.scan_once()
        self.assertIsNone(fresh_worker.host_is_up("192.168.0.7"))
        db.assert_not_called()

    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_targeted_scan_preserves_other_host_results(self, scanner, db):
        worker = MachineScanner()
        scanner.return_value.scan.return_value = {"nmap": {"scaninfo": {}}, "scan": {}}
        worker.scan_once()
        scanner.return_value.scan.return_value = {"nmap": {"scaninfo": {}}, "scan": {
            "192.168.0.7": {"status": {"state": "up"}}}}
        with patch("cmdb.activity.MachineScanner.MachineDb") as inventory:
            inventory.return_value.upsert.return_value = 7
            worker.scan_once("192.168.0.7")
        self.assertTrue(worker.host_is_up("192.168.0.7"))
        self.assertFalse(worker.host_is_up("192.168.0.8"))
        self.ssh_activity.return_value.run.assert_called_once_with({"192.168.0.7": 7})
        self.assertEqual(scanner.return_value.scan.call_args_list[1].args, ("192.168.0.7",))
        scanner.return_value.scan.return_value = {"nmap": {"scaninfo": {}}, "scan": {}}
        worker.scan_once("192.168.0.8")
        self.assertTrue(worker.host_is_up("192.168.0.7"))
        self.assertFalse(worker.host_is_up("192.168.0.8"))

    def test_targeted_requests_share_same_target_and_reject_other_scans(self):
        worker = MachineScanner()
        worker.is_alive = Mock(return_value=True)
        self.assertEqual(worker.request_scan("192.168.0.7"), 1)
        self.assertEqual(worker.request_scan("192.168.0.7"), 1)
        with self.assertRaises(ValueError):
            worker.request_scan("192.168.0.8")
        worker._running_scan = True
        worker._active_target = "192.168.0.7"
        worker._scan_id = 1
        self.assertEqual(worker.request_scan("192.168.0.7"), 1)
        with self.assertRaises(ValueError):
            worker.request_scan()

    @patch("cmdb.activity.MachineScanner.MachineDb")
    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_application_scan_uses_inventoried_hosts_without_nmap(self, nmap, db, inventory):
        inventory.return_value.list_machines.return_value = [Machine('192.0.2.7', id=7)]
        MachineScanner().scan_applications()
        self.applications.return_value.run.assert_called_once_with({'192.0.2.7': 7})
        db.return_value.close.assert_called_once()
        nmap.assert_not_called()

    def test_application_requests_share_and_reject_inventory_scan(self):
        worker = MachineScanner()
        worker.is_alive = Mock(return_value=True)
        self.assertEqual(worker.request_scan(applications_only=True), 1)
        self.assertEqual(worker.request_scan(applications_only=True), 1)
        with self.assertRaises(ValueError):
            worker.request_scan()
        worker._running_scan = True
        worker._active_applications = True
        worker._scan_id = 1
        self.assertEqual(worker.request_scan(applications_only=True), 1)
        with self.assertRaises(ValueError):
            worker.request_scan('192.0.2.7')

    @patch('builtins.print')
    def test_worker_dispatches_application_scan(self, output):
        worker = MachineScanner()
        worker.is_alive = Mock(return_value=True)
        worker.request_scan(applications_only=True)
        worker.scan_once = Mock()
        worker.scan_applications = Mock(side_effect=worker._stop_requested.set)
        worker.run()
        worker.scan_applications.assert_called_once()
        worker.scan_once.assert_not_called()
        self.assertEqual(worker.scan_status()['completedScanId'], 1)

    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_empty_or_failed_scans_do_not_open_database(self, scanner, db):
        for info in ({}, {"error": ["socket unavailable"]}):
            scanner.return_value.scan.return_value = {"nmap": {"scaninfo": info}, "scan": {}}
            if info:
                with self.assertRaises(nmap.PortScannerError):
                    MachineScanner().scan_once()
            else:
                MachineScanner().scan_once()
        db.assert_not_called()

    @patch("builtins.print")
    def test_expected_errors_retry_after_interval_and_print_only_start(self, output):
        worker = MachineScanner()
        worker._wake.wait = Mock()
        failures = [nmap.PortScannerTimeout("timeout"), pymysql.OperationalError("unavailable")]
        def scan():
            if failures:
                raise failures.pop(0)
            worker._stop_requested.set()
        worker.scan_once = Mock(side_effect=scan)
        worker.run()
        self.assertEqual(worker.scan_once.call_count, 3)
        self.assertEqual(worker._wake.wait.call_count, 3)
        self.assertEqual(worker.scan_status()["completedScanId"], 3)
        output.assert_called_once()

    @patch("builtins.print")
    def test_requests_wake_worker_and_share_an_active_scan(self, output):
        worker = MachineScanner()
        entered = Event()
        release = Event()
        def scan():
            entered.set()
            self.assertTrue(release.wait(3))
        worker.scan_once = Mock(side_effect=scan)
        worker.start()
        try:
            self.assertTrue(entered.wait(3))
            self.assertEqual(worker.request_scan(), 1)
            self.assertEqual(worker.request_scan(), 1)
            self.assertEqual(worker.scan_once.call_count, 1)
            release.set()
            # Waiting on the worker's event means the first scan has finished.
            waiting = Event()
            original_wait = worker._wake.wait
            def wait(timeout):
                waiting.set()
                return original_wait(timeout)
            worker._wake.wait = wait
            # If already waiting, an explicit request still wakes the same worker.
            entered.clear()
            requested = worker.request_scan()
            if requested == 1:
                self.assertTrue(waiting.wait(3))
                requested = worker.request_scan()
            self.assertEqual(requested, 2)
            self.assertTrue(entered.wait(3))
        finally:
            release.set()
            worker.stop()
        self.assertEqual(worker.scan_once.call_count, 2)

    @patch("builtins.print")
    def test_scan_failure_is_reported_and_stopped_worker_rejects_requests(self, output):
        worker = MachineScanner()
        def fail():
            worker._stop_requested.set()
            raise nmap.PortScannerTimeout("private details")
        worker.scan_once = fail
        worker.run()
        self.assertEqual(worker.scan_status()["error"], "Scan failed. Try again.")
        with self.assertRaises(RuntimeError):
            worker.request_scan()

    @patch("builtins.print")
    def test_stop_wakes_waiting_worker(self, output):
        worker = MachineScanner()
        worker.scan_once = Mock()
        worker.start()
        worker.stop()
        self.assertFalse(worker.is_alive())

    @patch("cmdb.activity.MachineScanner.DbMgr")
    @patch("cmdb.activity.MachineScanner.Nmap")
    def test_stop_during_scan_prevents_writes(self, scanner, db):
        worker = MachineScanner()

        def finish(*args, **kwargs):
            worker._stop_requested.set()
            return {"nmap": {"scaninfo": {}}, "scan": {}}

        scanner.return_value.scan.side_effect = finish
        worker.scan_once()
        db.assert_not_called()
