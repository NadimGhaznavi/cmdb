"""Discovery persistence and background worker lifecycle contracts."""

from unittest import TestCase
from unittest.mock import Mock, patch

import nmap
import pymysql

from cmdb.entity.Machine import Machine
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
                                "hostnames": [{"name": "router"}]},
                "192.168.0.2": {"status": {"state": "up"},
                                "hostnames": [{"name": ""}]},
                "192.168.0.3": {"status": {"state": "down"}},
            },
        }
        worker = MachineScanner()
        worker.scan_once()
        self.assertEqual([call.args[0] for call in inventory.return_value.upsert.call_args_list],
                         [Machine("192.168.0.1", "router"), Machine("192.168.0.2")])
        db.return_value.transaction.assert_called_once()
        db.return_value.close.assert_called_once()

        inventory.return_value.upsert.side_effect = pymysql.OperationalError("failed")
        with self.assertRaises(pymysql.OperationalError):
            worker.scan_once()
        self.assertEqual(db.return_value.close.call_count, 2)
        transaction = db.return_value.transaction.return_value
        self.assertIs(transaction.__exit__.call_args.args[0], pymysql.OperationalError)

    @patch("cmdb.server.MachineScanner.DbMgr")
    @patch("cmdb.server.MachineScanner.Nmap")
    def test_empty_or_failed_scans_do_not_open_database(self, scanner, db):
        for info in ({}, {"error": ["socket unavailable"]}):
            scanner.return_value.scan.return_value = {"nmap": {"scaninfo": info}, "scan": {}}
            MachineScanner().scan_once()
        db.assert_not_called()

    @patch("builtins.print")
    def test_expected_errors_retry_after_interval_and_print_only_start(self, output):
        worker = MachineScanner()
        worker._stop_requested = Mock()
        worker._stop_requested.is_set.return_value = False
        worker._stop_requested.wait.side_effect = [False, False, True]
        worker.scan_once = Mock(side_effect=[nmap.PortScannerTimeout("timeout"),
                                            pymysql.OperationalError("unavailable"), None])
        worker.run()
        self.assertEqual(worker.scan_once.call_count, 3)
        self.assertEqual(worker._stop_requested.wait.call_count, 3)
        output.assert_called_once()

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
