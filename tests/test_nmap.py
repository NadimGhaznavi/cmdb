"""Nmap result and failure contracts without running network scans."""

import unittest
from unittest.mock import patch

import nmap

from cmdb.interface.Nmap import Nmap


class NmapTests(unittest.TestCase):
    @patch("cmdb.interface.Nmap.nmap.PortScanner")
    def test_returns_library_results_and_accepts_scan_options(self, factory):
        result = {"nmap": {"scanstats": {"uphosts": "1"}},
                  "scan": {"192.168.1.10": {"status": {"state": "up"}}}}
        factory.return_value.scan.return_value = result
        scanner = Nmap()
        factory.assert_called_once_with(nmap_search_path=("/usr/bin/nmap",))
        self.assertEqual(scanner.scan("192.168.1.10", "22,80", arguments="-sT -n",
                                      timeout=30), result)
        factory.return_value.scan.assert_called_once_with(
            hosts="192.168.1.10", ports="22,80", arguments="-sT -n", timeout=30, sudo=True)

    @patch("cmdb.interface.Nmap.nmap.PortScanner")
    def test_empty_hosts_do_not_start_a_scan(self, factory):
        scanner = Nmap()
        for hosts in ("", " \n\t"):
            with self.subTest(hosts=hosts), self.assertRaises(ValueError):
                scanner.scan(hosts)
        factory.return_value.scan.assert_not_called()

    @patch("cmdb.interface.Nmap.nmap.PortScanner")
    def test_scan_errors_and_timeouts_reach_the_caller(self, factory):
        scanner = Nmap()
        for error in (nmap.PortScannerError("scan failed"),
                      nmap.PortScannerTimeout("scan timed out")):
            factory.return_value.scan.side_effect = error
            with self.subTest(error=error), self.assertRaises(type(error)) as caught:
                scanner.scan("192.168.1.10")
            self.assertIs(caught.exception, error)

    @patch("cmdb.interface.Nmap.nmap.PortScanner",
           side_effect=nmap.PortScannerError("nmap executable not found"))
    def test_missing_executable_reaches_the_caller(self, factory):
        with self.assertRaises(nmap.PortScannerError):
            Nmap()
