"""Discovery persistence and background worker lifecycle contracts."""

from unittest import TestCase
from unittest.mock import Mock, patch
from threading import Event

import nmap
import pymysql

from cmdb.entity.Machine import Machine
from cmdb.constants.DCmdb import DCmdb
from cmdb.server.MachineScanner import MachineScanner


class MachineScannerTests(TestCase):
    @patch("cmdb.server.MachineScanner.MachineDb")
    @patch("cmdb.server.MachineScanner.DbMgr")
    @patch("cmdb.server.MachineScanner.Nmap")
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
        worker.scan_once()
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

    @patch("cmdb.server.MachineScanner.MachineDb")
    @patch("cmdb.server.MachineScanner.DbMgr")
    @patch("cmdb.server.MachineScanner.Nmap")
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
        scanner.return_value.scan.assert_called_once_with(
            DCmdb.SCAN_TARGET, arguments="-sn -n", timeout=DCmdb.SCAN_TIMEOUT_SECONDS)
        self.assertEqual([call.args[0] for call in inventory.return_value.upsert.call_args_list],
                         [Machine("192.168.0.1"), Machine("192.168.0.2"),
                          Machine("192.168.0.3")])

    @patch("cmdb.server.MachineScanner.DbMgr")
    @patch("cmdb.server.MachineScanner.Nmap")
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

    @patch("cmdb.server.MachineScanner.DbMgr")
    @patch("cmdb.server.MachineScanner.Nmap")
    def test_stop_during_scan_prevents_writes(self, scanner, db):
        worker = MachineScanner()

        def finish(*args, **kwargs):
            worker._stop_requested.set()
            return {"nmap": {"scaninfo": {}}, "scan": {}}

        scanner.return_value.scan.side_effect = finish
        worker.scan_once()
        db.assert_not_called()
