"""Patch workflow checks; no real package changes or reboots."""

from datetime import timedelta
import os
import subprocess
import unittest
from unittest.mock import Mock, patch

from cmdb.activity.PatchRunner import PatchRunner, now
from cmdb.interface.SSHPatch import SSHPatch

OLD = '11111111-1111-1111-1111-111111111111'
NEW = '22222222-2222-2222-2222-222222222222'


class PatchRunnerTests(unittest.TestCase):
    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_kernel_success_always_reboots_even_with_no_updates(self, remote):
        remote.return_value.run.side_effect = [OLD, '0 upgraded', '', NEW, 'healthy']
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='queued', patchType='kernel'))
        self.assertEqual([c.args[1] for c in remote.return_value.run.call_args_list],
                         ['probe', 'patch-kernel', 'reboot', 'probe', 'verify'])
        self.assertEqual([c.args[0] for c in runner.record.call_args_list], ['start', 'rebooting', 'finish'])
        runner.record.assert_called_with('finish', 1)

    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_other_patching_verifies_packages_without_reboot(self, remote):
        remote.return_value.run.side_effect = [OLD, 'updated', 'healthy']
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='queued', patchType='other'))
        self.assertEqual([c.args[1] for c in remote.return_value.run.call_args_list],
                         ['probe', 'patch-other', 'verify-packages'])
        self.assertEqual([c.args[0] for c in runner.record.call_args_list], ['start', 'finish'])
        runner.record.assert_called_with('finish', 1)

    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_other_package_verification_failure_is_recorded_without_reboot(self, remote):
        remote.return_value.run.side_effect = [OLD, '', subprocess.CalledProcessError(1, 'dnf', stderr='broken dependency')]
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='queued', patchType='other'))
        runner.record.assert_called_with('finish', 1, 'broken dependency')
        self.assertNotIn('reboot', [c.args[1] for c in remote.return_value.run.call_args_list])

    @patch('cmdb.activity.PatchRunner.SSHPatch')
    def test_patch_failure_stops_before_reboot(self, remote):
        remote.return_value.run.side_effect = [OLD, subprocess.CalledProcessError(100, 'apt', stderr='apt failed')]
        runner = PatchRunner()
        runner.record = Mock()
        runner.execute(dict(id=1, address='192.0.2.1', status='queued', patchType='kernel'))
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

    @patch('cmdb.interface.SSHPatch.SSH')
    def test_actions_use_agent_sudo_and_preserve_the_host_timeout(self, ssh):
        ssh.return_value.run.return_value.stdout = OLD
        for action, timeout in (('probe', 60), ('patch-kernel', 7200), ('patch-other', 7200),
                                ('reboot', 60), ('verify', 60), ('verify-packages', 60)):
            self.assertEqual(SSHPatch().run('192.0.2.1', action), OLD)
            call = ssh.return_value.run.call_args
            self.assertEqual(call.args[1], f'sudo -n timeout --kill-after=10 {timeout} /bin/sh -s -- {action}')
            self.assertNotIn('user', call.kwargs)
            self.assertIn('apt-get', call.kwargs['input'])
            self.assertEqual(call.kwargs['timeout'], timeout + 30)
        with self.assertRaises(ValueError):
            SSHPatch().run('127.0.0.1', 'patch; reboot')

    @patch('cmdb.interface.SSH.subprocess.run')
    @patch('cmdb.interface.SSH.pwd.getpwnam')
    @patch('cmdb.interface.SSH.SSH.is_local', return_value=True)
    def test_local_patch_switches_to_agent_before_using_its_sudo(self, local, account, run):
        account.return_value.pw_uid = os.geteuid() + 1
        run.return_value.stdout = OLD
        self.assertEqual(SSHPatch().run('127.0.0.1', 'probe'), OLD)
        argv = run.call_args.args[0]
        self.assertEqual(argv, ['/usr/bin/sudo', '-n', '-H', '-u', 'cmdbagent', '--', '/bin/sh', '-c',
                               'sudo -n timeout --kill-after=10 60 /bin/sh -s -- probe'])
        self.assertIn('apt-get', run.call_args.kwargs['input'])


class PatchScriptTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.release = self.root / 'os-release'
        self.release.write_text('ID=debian\n')
        self.preferences = self.root / 'preferences'
        self.preferences.write_text('Package: example\nPin: version 1*\nPin-Priority: 900\n')
        self.script = self.root / 'patch-host.sh'
        self.script.write_text(Path('cmdb/interface/scripts/patch-host.sh').read_text()
                               .replace('PATH=/usr/sbin:/usr/bin:/sbin:/bin', f'PATH={self.root}:/usr/bin:/bin')
                               .replace('. /etc/os-release', f'. {self.release}'))
        commands = {
            'apt-get': '''echo "apt-get $*" >> "$LOG"
for argument in "$@"; do
    case "$argument" in Dir::Etc::preferences=*) cat "${argument#*=}" > "$PIN_SNAPSHOT";; esac
done
case "$*" in
    *" update") exit "${UPDATE_EXIT:-0}";;
    *" upgrade"|*" install "*) exit "${UPGRADE_EXIT:-0}";;
    check) exit "${CHECK_EXIT:-0}";;
esac
''',
            'apt-config': '''printf "original_preferences='%s'\\n" "$ORIGINAL_PREFERENCES"''',
            'dpkg-query': '''printf '%s\\n' 'installed linux-image-amd64' 'installed linux-image-6.1-amd64' \\
'installed linux-headers-amd64' 'installed linux-kbuild-6.1' 'installed linux-compiler-gcc-12-x86' \\
'installed bash' 'installed linux-libc-dev' 'config-files linux-image-5.1-amd64'
''',
            'dpkg': 'printf "%s" "${AUDIT:-}"\n',
            'dnf': '''echo "dnf $*" >> "$LOG"
case "$*" in *upgrade*) exit "${UPGRADE_EXIT:-0}";; check) exit "${CHECK_EXIT:-0}";; esac
''',
            'shutdown': 'echo reboot >> "$LOG"\n',
            'systemctl': 'echo "${SYSTEM_STATE:-running}"\n',
        }
        for name, body in commands.items():
            path = self.root / name
            path.write_text('#!/bin/sh\n' + body)
            path.chmod(0o755)
        self.log = self.root / 'log'
        self.log.touch()
        self.env = dict(os.environ, LOG=str(self.log), TMPDIR=str(self.root),
                        ORIGINAL_PREFERENCES=str(self.preferences), PIN_SNAPSHOT=str(self.root / 'pin-snapshot'))

    def run_action(self, action, **environment):
        return subprocess.run(['sh', str(self.script), action], env=dict(self.env, **environment),
                              capture_output=True, text=True)

    def test_debian_kernel_targets_installed_kernel_packages_and_keeps_userspace_out(self):
        result = self.run_action('patch-kernel')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.log.read_text()
        self.assertIn('APT::Update::Error-Mode=any update', commands)
        self.assertIn('--only-upgrade --no-remove', commands)
        self.assertIn('install linux-image-amd64 linux-image-6.1-amd64 linux-headers-amd64', commands)
        for excluded in ('bash', 'linux-libc-dev', 'linux-image-5.1-amd64', 'autoremove', 'reboot'):
            self.assertNotIn(excluded, commands)
        self.assertIn('apt-get check', commands)

    def test_debian_other_pins_kernels_and_preserves_existing_preferences(self):
        result = self.run_action('patch-other')
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.log.read_text()
        self.assertIn('--with-new-pkgs --no-remove', commands)
        pin = (self.root / 'pin-snapshot').read_text()
        self.assertIn('linux-image-* linux-headers-* linux-modules-* linux-kbuild-* linux-compiler-*', pin)
        self.assertIn('Pin-Priority: -1', pin)
        self.assertTrue(pin.endswith(self.preferences.read_text()))
        self.assertIn('apt-get check', commands)
        self.assertNotIn('autoremove', commands)
        self.assertNotIn('reboot', commands)
        self.assertEqual(list(self.root.glob('tmp*')), [])

    def test_fedora_uses_separate_dnf_filters_and_package_checks(self):
        self.release.write_text('ID=fedora\n')
        for action, expected in [('patch-kernel', 'dnf -y --refresh upgrade kernel*'),
                                 ('patch-other', 'dnf -y --refresh --exclude=kernel* upgrade')]:
            with self.subTest(action=action):
                self.log.write_text('')
                result = self.run_action(action)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.log.read_text().splitlines(), [expected, 'dnf check'])

    def test_update_failure_stops_before_any_package_transaction(self):
        for action in ('patch-kernel', 'patch-other'):
            with self.subTest(action=action):
                self.log.write_text('')
                self.assertNotEqual(self.run_action(action, UPDATE_EXIT='100').returncode, 0)
                self.assertEqual(len(self.log.read_text().splitlines()), 1)

    def test_transaction_and_health_failures_never_reboot(self):
        for system in ('debian', 'fedora'):
            self.release.write_text(f'ID={system}\n')
            for action in ('patch-kernel', 'patch-other'):
                for environment in ({'UPGRADE_EXIT': '1'}, {'CHECK_EXIT': '1'}):
                    with self.subTest(system=system, action=action, environment=environment):
                        self.log.write_text('')
                        self.assertNotEqual(self.run_action(action, **environment).returncode, 0)
                        self.assertNotIn('reboot', self.log.read_text())
                        self.assertEqual(list(self.root.glob('tmp*')), [])

    def test_verification_uses_distribution_package_manager_and_kernel_checks_system_state(self):
        for system, expected in [('debian', 'apt-get check'), ('fedora', 'dnf check')]:
            self.release.write_text(f'ID={system}\n')
            self.log.write_text('')
            self.assertEqual(self.run_action('verify').returncode, 0)
            self.assertEqual(self.log.read_text().strip(), expected)
            self.log.write_text('')
            self.assertNotEqual(self.run_action('verify', SYSTEM_STATE='degraded').returncode, 0)
            self.assertEqual(self.log.read_text(), '')
            self.assertEqual(self.run_action('verify-packages', SYSTEM_STATE='degraded').returncode, 0)

    def test_unsupported_host_and_invalid_action_stop_before_package_commands(self):
        self.assertNotEqual(self.run_action('patch').returncode, 0)
        self.release.write_text('ID=ubuntu\n')
        self.assertNotEqual(self.run_action('patch-other').returncode, 0)
        self.assertEqual(self.log.read_text(), '')
