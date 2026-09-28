"""MariaDB provisioning flow without remote connections or account mutations."""

import subprocess
from threading import Event
from unittest import TestCase
from unittest.mock import Mock

from cmdb.interface.SSHDb import SSHDb, provisioning_sql


def result(stdout=''):
    return subprocess.CompletedProcess([], 0, stdout, '')


READY = 'cmdbagent@localhost\t11.8.3-MariaDB\nGRANT SHOW DATABASES ON *.* TO `cmdbagent`@`localhost`\n'
DENIED = subprocess.CalledProcessError(1, ['mariadb'], stderr='Access denied')


class SSHDbTests(TestCase):
    def setUp(self):
        self.ssh = Mock()
        self.ssh.is_local.return_value = False
        self.stop = Event()
        self.db = SSHDb(self.ssh, self.stop)

    def test_existing_database_identity_needs_no_root(self):
        self.ssh.run.side_effect = [result('MariaDB'), result(READY)]
        self.assertTrue(self.db.ensure_agent('host'))
        self.assertTrue(all('user' not in call.kwargs for call in self.ssh.run.call_args_list))

    def test_provisions_then_retests_as_agent(self):
        self.ssh.run.side_effect = [result('MariaDB'), DENIED, result(), result(READY)]
        self.assertTrue(self.db.ensure_agent('host'))
        calls = self.ssh.run.call_args_list
        self.assertEqual(calls[2].kwargs['user'], 'root')
        self.assertEqual(calls[2].kwargs['input'], provisioning_sql())
        self.assertIn('IDENTIFIED VIA unix_socket', calls[2].kwargs['input'])
        self.assertNotIn('user', calls[3].kwargs)

    def test_missing_grant_triggers_repair(self):
        self.ssh.run.side_effect = [result('MariaDB'), result('cmdbagent@localhost\tMariaDB\nGRANT USAGE'),
                                    result(), result(READY)]
        self.assertTrue(self.db.ensure_agent('host'))
        self.assertEqual(self.ssh.run.call_count, 4)

    def test_local_provisioning_is_left_to_installer(self):
        self.ssh.is_local.return_value = True
        self.ssh.run.side_effect = [result('MariaDB'), DENIED]
        self.assertFalse(self.db.ensure_agent('host'))
        self.assertEqual(self.ssh.run.call_count, 2)

    def test_missing_server_denied_root_and_retest_failures_are_optional(self):
        for responses in ([DENIED], [result('MySQL')], [result('MariaDB'), DENIED, DENIED],
                          [result('MariaDB'), DENIED, result(), DENIED]):
            self.ssh.run.side_effect = responses
            self.assertFalse(self.db.ensure_agent('host'))

    def test_shutdown_prevents_remote_commands(self):
        self.stop.set()
        self.assertFalse(self.db.ensure_agent('host'))
        self.ssh.run.assert_not_called()
