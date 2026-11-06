"""Nmap result and failure contracts without running network scans."""

import subprocess
import unittest
from unittest.mock import patch

import nmap

from cmdb.interface.Nmap import Nmap


class NmapTests(unittest.TestCase):
    @patch('cmdb.interface.Nmap.subprocess.run')
    @patch('cmdb.interface.Nmap.nmap.PortScanner')
    def test_raw_scan_is_ip_only_comprehensive_and_preserves_output(self, factory, run):
        output = b'Nmap scan report for 192.0.2.7\n443/tcp open https\n\xff'
        run.return_value.stdout = output
        scanner = Nmap()
        self.assertEqual(scanner.scan_raw('192.0.2.7', timeout=300), output.decode('utf-8', errors='replace'))
        command = run.call_args.args[0]
        self.assertEqual(command, ['sudo', '-n', '/usr/bin/nmap', '-n', '-Pn', '-A', '-p-',
                                   '--version-all', '--reason', '-v', '--host-timeout', '300s',
                                   '--script-timeout', '30s', '-oN', '-', '192.0.2.7'])
        self.assertEqual(run.call_args.kwargs,
                         {'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT, 'timeout': 330, 'check': True})
        run.reset_mock()
        for target in ('example.com', '192.0.2.0/24', '192.0.2.7 --script all', ''):
            with self.subTest(target=target), self.assertRaises(ValueError):
                scanner.scan_raw(target, timeout=300)
        run.assert_not_called()
        scanner.scan_raw('2001:db8::7', timeout=300)
        self.assertEqual(run.call_args.args[0][-2:], ['-6', '2001:db8::7'])

    @patch('cmdb.interface.Nmap.subprocess.run')
    @patch('cmdb.interface.Nmap.nmap.PortScanner')
    def test_nmap_host_timeout_is_incomplete_even_with_zero_exit_status(self, factory, run):
        output = b'Skipping host 192.0.2.7 due to host timeout\n'
        run.return_value.stdout = output
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            Nmap().scan_raw('192.0.2.7', timeout=300)
        self.assertEqual(caught.exception.output, output)

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
