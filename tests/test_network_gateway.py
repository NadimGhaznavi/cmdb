"""Default gateway selection without relying on the test host's routes."""

from unittest import TestCase
from unittest.mock import patch

from cmdb.interface.Network import Network


HEADER = 'Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n'


class DefaultGatewayTests(TestCase):
    @patch('cmdb.interface.Network.Path.read_text')
    def test_lowest_metric_active_default_gateway(self, read):
        read.return_value = HEADER + (
            'eth0 00000000 010200C0 0003 0 0 100 00000000 0 0 0\n'
            'eth1 00000000 0100000A 0003 0 0 50 00000000 0 0 0\n'
            'eth2 00000000 0101000A 0002 0 0 1 00000000 0 0 0\n'
            'eth3 000200C0 00000000 0001 0 0 0 00FFFFFF 0 0 0\n')
        self.assertEqual(Network.default_gateway(), '10.0.0.1')

    @patch('cmdb.interface.Network.Path.read_text')
    def test_absent_gateway_or_routing_table(self, read):
        for routes in (HEADER, HEADER + 'eth0 00000000 00000000 0001 0 0 0 00000000 0 0 0\n'):
            read.return_value = routes
            self.assertIsNone(Network.default_gateway())
        for error in (FileNotFoundError(), PermissionError()):
            read.side_effect = error
            self.assertIsNone(Network.default_gateway())
