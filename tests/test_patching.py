"""Patch workflow checks; no real package changes or reboots."""

from datetime import timedelta
import subprocess
import unittest
from unittest.mock import Mock, patch

from cmdb.activity.PatchRunner import PatchRunner, now
from cmdb.interface.SSHPatch import SSHPatch

OLD = '11111111-1111-1111-1111-111111111111'
NEW = '22222222-2222-2222-2222-222222222222'


class PatchRunnerTests(unittest.TestCase):
    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_success_always_reboots_even_with_no_updates(self, remote):
        remote.return_value.run.side_effect = [OLD, '0 upgraded', '', NEW, 'healthy']
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='queued'))
        self.assertEqual([c.args[1] for c in remote.return_value.run.call_args_list],
                         ['probe', 'patch', 'reboot', 'probe', 'verify'])
        self.assertEqual([c.args[0] for c in runner.record.call_args_list], ['start', 'rebooting', 'finish'])
        runner.record.assert_called_with('finish', 1)

    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_patch_failure_stops_before_reboot(self, remote):
        remote.return_value.run.side_effect = [OLD, subprocess.CalledProcessError(100, 'apt', stderr='apt failed')]
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='queued'))
        self.assertEqual(remote.return_value.run.call_count, 2)
        runner.record.assert_called_with('finish', 1, 'apt failed')

    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_resume_after_cmdb_reboot_only_verifies(self, remote):
        remote.return_value.run.side_effect = [NEW, 'healthy']
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='rebooting', bootId=OLD, rebootOn=now()))
        self.assertEqual([c.args[1] for c in remote.return_value.run.call_args_list], ['probe', 'verify'])
        runner.record.assert_called_once_with('finish', 1)

    @patch('cmdb.activity.PatchRunner.time.sleep')
    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_waits_for_new_boot_not_just_reachable_ssh(self, remote, sleep):
        remote.return_value.run.side_effect = [OLD, OSError('offline'), NEW, 'healthy']
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='rebooting', bootId=OLD, rebootOn=now()))
        self.assertEqual(sleep.call_count, 2)
        runner.record.assert_called_once_with('finish', 1)

    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_timeout_and_failed_health_check_are_failures(self, remote):
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='rebooting', bootId=OLD,
                            rebootOn=now()-timedelta(minutes=16)))
        self.assertIn('15 minutes', runner.record.call_args.args[2])
        remote.return_value.run.side_effect = [NEW, subprocess.CalledProcessError(1, 'check', stderr='degraded')]
        runner.execute(dict(id=2, address='192.0.2.1', status='rebooting', bootId=OLD, rebootOn=now()))
        runner.record.assert_called_with('finish', 2, 'degraded')

    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_interrupted_apt_is_not_automatically_repeated(self, remote):
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='patching'))
        remote.return_value.run.assert_not_called()
        self.assertIn('interrupted', runner.record.call_args.args[2])

    @patch('cmdb.interface.SSHPatch.subprocess.run')
    @patch('cmdb.interface.SSHPatch.SSH')
    def test_local_actions_use_only_installed_helper_and_remote_uses_root(self, ssh, run):
        ssh.return_value.is_local.return_value = True
        run.return_value.stdout = OLD
        self.assertEqual(SSHPatch().run('127.0.0.1', 'probe'), OLD)
        self.assertEqual(run.call_args.args[0], ['/usr/bin/sudo', '-n', '/bin/sh',
                         '/opt/prod/cmdb/cmdb/interface/scripts/patch-host.sh', 'probe'])
        ssh.return_value.is_local.return_value = False
        SSHPatch().run('192.0.2.1', 'patch')
        self.assertEqual(ssh.return_value.run.call_args.kwargs['user'], 'root')
        with self.assertRaises(ValueError):
            SSHPatch().run('127.0.0.1', 'patch; reboot')

class PatchScriptTests(unittest.TestCase):
    def test_package_commands_fail_before_upgrade_and_never_reboot_implicitly(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import os
        source = Path('cmdb/interface/scripts/patch-host.sh').read_text()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / 'os-release'
            release.write_text('ID=debian\n')
            script = root / 'patch-host.sh'
            script.write_text(source.replace('PATH=/usr/sbin:/usr/bin:/sbin:/bin', f'PATH={root}:/usr/bin:/bin')
                             .replace('. /etc/os-release', f'. {release}'))
            for name, body in {
                'apt-get': 'echo "$*" >> "$LOG"\ncase "$*" in *update*) exit "${UPDATE_EXIT:-0}";; esac\n',
                'dpkg': 'exit 0\n',
                'shutdown': 'echo reboot >> "$LOG"\n',
                'systemctl': 'echo running\n',
            }.items():
                path = root / name
                path.write_text('#!/bin/sh\n' + body)
                path.chmod(0o755)
            log = root / 'log'
            env = dict(os.environ, LOG=str(log))
            subprocess.run(['sh', str(script), 'patch'], env=env, check=True)
            commands = log.read_text()
            self.assertIn('APT::Update::Error-Mode=any update', commands)
            self.assertIn('--with-new-pkgs', commands)
            self.assertNotIn('reboot', commands)
            log.write_text('')
            self.assertNotEqual(subprocess.run(['sh', str(script), 'patch'], env=dict(env, UPDATE_EXIT='100')).returncode, 0)
            self.assertNotIn('upgrade', log.read_text())
            release.write_text('ID=ubuntu\n')
            log.write_text('')
            self.assertNotEqual(subprocess.run(['sh', str(script), 'patch'], env=env).returncode, 0)
            self.assertEqual(log.read_text(), '')
