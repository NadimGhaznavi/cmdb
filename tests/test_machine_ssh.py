"""SSH follow-up decisions without touching LAN hosts or real accounts."""

from pathlib import Path
import subprocess
import json
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import Mock, patch

from cmdb.activity.MachineSSH import MachineSSH
from cmdb.constants.DCmdb import DCmdb


def result(stdout=''):
    return subprocess.CompletedProcess(['ssh'], 0, stdout, '')


def denied():
    return subprocess.CalledProcessError(255, ['ssh'], stderr='Permission denied (publickey).')


class MachineSSHTests(TestCase):
    def setUp(self):
        for name in ('SSH', 'DbMgr', 'MachineDb', 'socket.create_connection'):
            mock = patch('cmdb.activity.MachineSSH.' + name)
            setattr(self, name.split('.')[-1], mock.start())
            self.addCleanup(mock.stop)
        self.stop = Event()
        self.activity = MachineSSH(self.stop)
        self.SSH.return_value.is_local.return_value = False
        self.remote = self.SSH.return_value.run
        directory = TemporaryDirectory(prefix='cmdb-public-test-')
        self.addCleanup(directory.cleanup)
        key = Path(directory.name) / 'id_ed25519'
        Path(str(key) + '.pub').write_text('ssh-ed25519 AAAATEST cmdb\n')
        settings = patch.object(DCmdb, 'SSH_KEY', str(key))
        settings.start()
        self.addCleanup(settings.stop)

    def test_existing_cmdb_login_updates_hostname_by_id_without_root(self):
        self.remote.side_effect = [result(), result('worker.example.lan\n'), result('[]')]
        self.activity.run({'192.168.0.7': 42})
        self.create_connection.assert_called_once_with(('192.168.0.7', 22),
                                                       timeout=DCmdb.SSH_CONNECT_TIMEOUT_SECONDS)
        self.assertTrue(all('user' not in call.kwargs for call in self.remote.call_args_list))
        self.MachineDb.return_value.update_discovered_hostname.assert_called_once_with(42, 'worker.example.lan')
        self.DbMgr.return_value.close.assert_called_once()

    def test_local_and_remote_hosts_share_interface_lookup(self):
        interfaces = [
            {'link_type': 'ether', 'address': 'aa:bb:cc:dd:ee:01',
             'addr_info': [{'local': '10.0.0.1'}]},
            {'link_type': 'ether', 'address': 'aa:bb:cc:dd:ee:02',
             'addr_info': [{'local': '192.168.0.7'}]},
        ]
        for local in (True, False):
            with self.subTest(local=local):
                self.create_connection.reset_mock()
                self.MachineDb.return_value.reset_mock()
                self.SSH.return_value.is_local.return_value = local
                self.remote.side_effect = [result(), result('sally'), result(json.dumps(interfaces))]
                self.activity.run({'192.168.0.7': 42})
                self.assertEqual(self.create_connection.call_count, 0 if local else 1)
                self.MachineDb.return_value.update_discovered_mac.assert_called_once_with(
                    42, 'AA:BB:CC:DD:EE:02')

    def test_failed_mac_lookup_preserves_hostname_and_previous_mac(self):
        self.remote.side_effect = [result(), result('sally'),
                                   subprocess.CalledProcessError(127, ['ip'])]
        self.activity.run({'192.168.0.7': 42})
        self.MachineDb.return_value.update_discovered_hostname.assert_called_once_with(42, 'sally')
        self.MachineDb.return_value.update_discovered_mac.assert_not_called()

    def test_local_command_failure_never_provisions(self):
        self.SSH.return_value.is_local.return_value = True
        self.remote.side_effect = denied()
        self.activity.run({'192.168.0.7': 42})
        self.remote.assert_called_once()
        self.create_connection.assert_not_called()
        self.DbMgr.assert_not_called()

    def test_root_provisions_then_cmdb_is_tested_before_hostname_read(self):
        self.remote.side_effect = [denied(), result(), result(), result('worker\n'), result('[]')]
        self.activity.run({'192.168.0.7': 42})
        calls = self.remote.call_args_list
        self.assertEqual(calls[0].args[1], 'true')
        self.assertEqual(calls[1].kwargs['user'], 'root')
        self.assertIn('ssh-ed25519 AAAATEST cmdb', calls[1].args[1])
        self.assertIn('authorized_keys', calls[1].kwargs['input'])
        self.assertEqual(calls[2].args[1], 'true')
        self.assertNotIn('user', calls[2].kwargs)
        self.assertEqual(calls[3].args[1], 'hostname -f 2>/dev/null || hostname')
        self.MachineDb.return_value.update_discovered_hostname.assert_called_once_with(42, 'worker')

    def test_failed_root_or_cmdb_retest_preserves_hostname(self):
        for responses in ([denied(), denied()], [denied(), result(), denied()]):
            with self.subTest(responses=responses):
                self.remote.side_effect = responses
                self.activity.run({'192.168.0.7': 42})
        self.DbMgr.assert_not_called()

    def test_closed_port_does_not_attempt_login(self):
        self.create_connection.side_effect = ConnectionRefusedError()
        self.activity.run({'192.168.0.7': 42})
        self.remote.assert_not_called()
        self.DbMgr.assert_not_called()

    def test_unresponsive_host_does_not_block_the_next_machine(self):
        self.remote.side_effect = [subprocess.TimeoutExpired(['ssh'], 30), result(), result('second\n'), result('[]')]
        self.activity.run({'192.168.0.7': 42, '192.168.0.8': 43})
        self.MachineDb.return_value.update_discovered_hostname.assert_called_once_with(43, 'second')

    def test_invalid_hostname_and_command_failure_do_not_trigger_root_or_db_updates(self):
        for response in (result(''), result('banner\nhost\n'), result('x' * 256),
                         subprocess.CalledProcessError(1, ['hostname'])):
            self.remote.reset_mock()
            self.remote.side_effect = [result(), response]
            self.activity.run({'192.168.0.7': 42})
            self.assertEqual(self.remote.call_count, 2)
        self.DbMgr.assert_not_called()

    def test_changed_host_key_is_not_a_provisioning_trigger(self):
        self.remote.side_effect = subprocess.CalledProcessError(
            255, ['ssh'], stderr='WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!')
        self.activity.run({'192.168.0.7': 42})
        self.remote.assert_called_once()
        self.DbMgr.assert_not_called()

    def test_stop_between_connections_prevents_provisioning(self):
        def fail(*args, **kwargs):
            self.stop.set()
            raise denied()
        self.remote.side_effect = fail
        self.activity.run({'192.168.0.7': 42})
        self.remote.assert_called_once()
        self.DbMgr.assert_not_called()
