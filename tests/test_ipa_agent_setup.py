"""Exercise the IPA migration using a fake directory and disposable host files."""

from argparse import Namespace
import base64
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/setup-ipa-agent.py'
SPEC = importlib.util.spec_from_file_location('ipa_agent_setup', SCRIPT)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
KEY = 'ssh-ed25519 ' + base64.b64encode(b'\0\0\0\x0bssh-ed25519\0\0\0\x20' + b'k' * 32).decode()
OTHER_KEY = 'ssh-ed25519 ' + base64.b64encode(b'\0\0\0\x0bssh-ed25519\0\0\0\x20' + b'o' * 32).decode()
HOSTS = ['neuromancer.lab.osoyalce.com', 'bingo.lab.osoyalce.com']


class FakeDirectory:
    def __init__(self):
        self.records = {('host', host): {'fqdn': [host]} for host in HOSTS}
        self.writes = []

    def show(self, kind, name):
        return deepcopy(self.records.get((kind, name)))

    def call(self, command, name, **options):
        self.writes.append((command, name, options))
        kind, operation = command.split('_', 1)
        if operation == 'add':
            record = {key: [value] if isinstance(value, str) else value for key, value in options.items()}
            if kind == 'user':
                record.update(uidnumber=['12345'], gidnumber=['12346'], nsaccountlock=False)
            if kind in ('hbacrule', 'sudorule'):
                record['ipaenabledflag'] = True
            self.records[kind, name] = record
        else:
            record = self.records[kind, name]
            if operation == 'mod':
                record.update({key: [value] if isinstance(value, str) else value for key, value in options.items()})
            elif operation == 'enable':
                record['ipaenabledflag' if kind != 'user' else 'nsaccountlock'] = kind != 'user'
            elif operation == 'add_option':
                record.setdefault('ipasudoopt', []).append(options['ipasudoopt'])
            else:
                attributes = {'host': 'member_host' if kind == 'hostgroup' else 'memberhost_host',
                              'user': 'memberuser_user', 'hostgroup': 'memberhost_hostgroup',
                              'hbacsvc': 'memberservice_hbacsvc'}
                for option, values in options.items():
                    record.setdefault(attributes[option], []).extend(values)
        return {'result': deepcopy(record), 'failed': {}}


class IpaAgentSetupTests(TestCase):
    def test_preview_never_opens_directory_or_executes_commands(self):
        with patch.object(setup, 'run') as run, patch.object(setup, 'Directory') as directory, \
                redirect_stdout(io.StringIO()) as output:
            setup.main([])
        run.assert_not_called()
        directory.assert_not_called()
        self.assertIn('PREVIEW', output.getvalue())
        for host in setup.DEFAULT_HOSTS:
            self.assertIn(host + '.lab.osoyalce.com', output.getvalue())

    def test_invalid_hosts_and_agent_admin_login_are_rejected(self):
        for args in (['--hosts', 'host;touch.lab.osoyalce.com'],
                     ['--hosts', 'host.example.org'], ['--hosts', HOSTS[0], HOSTS[0]],
                     ['--ssh-user', 'cmdbagent'], ['--ssh-user', 'admin;id']):
            with self.subTest(args=args), patch.object(setup, 'run') as run:
                with self.assertRaises(RuntimeError):
                    setup.main(args)
                run.assert_not_called()

    def test_key_validation_and_transport_preserve_arguments(self):
        self.assertEqual(setup.key_material(KEY + ' comment'), KEY)
        for key in ('ssh-ed25519 invalid', 'ssh-ed25519 aGk=', 'ssh-rsa AAAA'):
            with self.assertRaises(RuntimeError):
                setup.key_material(key)
        command = setup.host_command(HOSTS[1], HOSTS[0], 'nadim', 'apply', 'lab.osoyalce.com', 10, 11, KEY)
        self.assertEqual(command[-2], HOSTS[1])
        arguments = shlex.split(command[-1])
        self.assertEqual(arguments[-1], KEY)
        self.assertEqual(arguments[:4], ['sudo', '-n', 'python3', '-'])

    def test_config_changes_preserve_other_settings_and_comments(self):
        text = '# keep me\n[sssd]\nservices = nss, pam, autofs\n\n[domain/lab.osoyalce.com]\n'
        text += 'id_provider = ipa\nipa_server = _srv_, kermit.lab.osoyalce.com\n'
        updated = setup.set_ini_option(text, 'sssd', 'services', 'nss, pam, autofs, ssh, sudo')
        updated = setup.set_ini_option(updated, 'domain/lab.osoyalce.com', 'sudo_provider', 'ipa')
        self.assertIn('# keep me', updated)
        self.assertIn('ipa_server = _srv_, kermit.lab.osoyalce.com', updated)
        self.assertEqual(updated.count('services ='), 1)
        self.assertIn('sudo_provider = ipa', updated)
        self.assertEqual(setup.nss_sudo('sudoers: files\n'), 'sudoers: files sss\n')
        managed = '# generated by authselect\nsudoers:    files sss\n'
        self.assertEqual(setup.nss_sudo(managed), managed)
        self.assertIn('sudoers: files ldap sss # keep\n', setup.nss_sudo('sudoers: ldap # keep\n'))
        with self.assertRaisesRegex(RuntimeError, 'lookup actions'):
            setup.nss_sudo('sudoers: files [SUCCESS=return] sss\n')

    def test_directory_creation_and_rerun_preserve_identity_and_scope(self):
        directory = FakeDirectory()
        self.assertEqual(setup.directory_setup(directory, HOSTS, KEY, True), (12345, 12346))
        sudo = directory.records['sudorule', setup.SUDO_RULE]
        self.assertNotIn('hostcategory', sudo)
        self.assertNotIn('usercategory', sudo)
        self.assertNotIn('ipasudorunasusercategory', sudo)
        self.assertEqual(sudo['memberhost_hostgroup'], [setup.HOSTGROUP])
        self.assertEqual(sudo['memberuser_user'], ['cmdbagent'])
        self.assertEqual(sudo['ipasudoopt'], ['!authenticate'])
        directory.writes.clear()
        setup.directory_setup(directory, HOSTS, KEY, True)
        self.assertEqual(directory.writes, [])
        setup.directory_setup(directory, HOSTS, KEY, False)
        self.assertEqual(directory.writes, [])

    def test_existing_user_retains_uid_and_other_public_keys(self):
        directory = FakeDirectory()
        directory.records['user', setup.AGENT] = {'uidnumber': ['9001'], 'gidnumber': ['9002'],
            'loginshell': ['/bin/false'], 'homedirectory': ['/ipahome/cmdbagent'],
            'ipasshpubkey': [OTHER_KEY], 'nsaccountlock': False}
        self.assertEqual(setup.directory_setup(directory, HOSTS, KEY, True), (9001, 9002))
        self.assertEqual(directory.records['user', setup.AGENT]['ipasshpubkey'], [OTHER_KEY, KEY])

    def test_directory_preflight_rejects_unenrolled_hosts_before_writes(self):
        directory = FakeDirectory()
        del directory.records['host', HOSTS[1]]
        with self.assertRaisesRegex(RuntimeError, 'not an enrolled'):
            setup.directory_setup(directory, HOSTS, KEY, True)
        self.assertEqual(directory.writes, [])

    def test_existing_unrelated_or_broad_rules_are_never_adopted(self):
        for record in ({'description': ['Someone else']},
                       {'description': [setup.DESCRIPTION], 'usercategory': ['all']},
                       {'description': [setup.DESCRIPTION], 'memberuser_user': ['nadim']},
                       {'description': [setup.DESCRIPTION], 'ipasudorunas_user': ['nadim']},
                       {'description': [setup.DESCRIPTION], 'ipasudoopt': ['authenticate']}):
            with self.subTest(record=record):
                directory = FakeDirectory()
                directory.records['sudorule', setup.SUDO_RULE] = record
                with self.assertRaises(RuntimeError):
                    setup.directory_setup(directory, HOSTS, KEY, True)
                self.assertEqual(directory.writes, [])

    def test_check_does_not_repair_missing_directory_objects(self):
        directory = FakeDirectory()
        with self.assertRaisesRegex(RuntimeError, 'run --apply'):
            setup.directory_setup(directory, HOSTS, KEY, False)
        self.assertEqual(directory.writes, [])

    def test_failed_ipa_membership_is_not_reported_as_success(self):
        directory = setup.Directory.__new__(setup.Directory)
        directory.errors = Namespace(NotFound=KeyError, PublicError=ValueError)
        directory.api = Namespace(Command={'hbacrule_add_service': Mock(return_value={
            'failed': {'memberservice': {'hbacsvc': [('sudo', 'not found')]}}})})
        with self.assertRaisesRegex(RuntimeError, 'membership update failed'):
            directory.call('hbacrule_add_service', setup.HBAC_RULE, hbacsvc=['sudo'])

    def test_client_wait_accepts_delayed_sssd_policy(self):
        with patch.object(setup, 'verify_client', side_effect=[RuntimeError('policy not ready'), None]) as verify, \
                patch.object(setup.time, 'monotonic', side_effect=[0, 1]), \
                patch.object(setup.time, 'sleep') as sleep:
            setup.wait_for_client('cmdbagent@lab.osoyalce.com', KEY)
        self.assertEqual(verify.call_count, 2)
        sleep.assert_called_once_with(setup.CLIENT_READY_INTERVAL)

    def test_client_wait_preserves_failure_after_deadline(self):
        with patch.object(setup, 'verify_client', side_effect=RuntimeError('policy not ready')), \
                patch.object(setup.time, 'monotonic', side_effect=[0, setup.CLIENT_READY_TIMEOUT]), \
                patch.object(setup.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'policy not ready'):
                setup.wait_for_client('cmdbagent@lab.osoyalce.com', KEY)
        sleep.assert_not_called()

    def test_client_accepts_sshd_keyword_case_from_debian_and_fedora(self):
        settings = ('AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys\n'
                    'AuthorizedKeysCommandUser nobody\nPubkeyAuthentication yes\nUsePAM yes\n')
        for effective in (settings, settings.lower()):
            with self.subTest(effective=effective), patch.object(setup, 'run', side_effect=[
                    subprocess.CompletedProcess([], 0, stdout=KEY + '\n'),
                    subprocess.CompletedProcess([], 0, stdout=effective),
                    subprocess.CompletedProcess([], 0, stdout='0\n')]):
                setup.verify_client('cmdbagent@lab.osoyalce.com', KEY)

    def test_client_rejects_disabled_pam_before_testing_sudo(self):
        with patch.object(setup, 'run', side_effect=[
                subprocess.CompletedProcess([], 0, stdout=KEY + '\n'),
                subprocess.CompletedProcess([], 0, stdout=(
                    'AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys\n'
                    'AuthorizedKeysCommandUser nobody\nPubkeyAuthentication yes\nUsePAM no\n'))]) as run:
            with self.assertRaisesRegex(RuntimeError, 'Effective sshd configuration'):
                setup.verify_client('cmdbagent@lab.osoyalce.com', KEY)
        self.assertEqual(run.call_count, 2)

    def test_administrator_preflight_failure_prevents_all_directory_writes(self):
        config = Namespace(read=Mock(), get=Mock(return_value=HOSTS[0]))
        def command(*args, **options):
            if HOSTS[1] in args:
                raise RuntimeError('administrator SSH failed')
            return subprocess.CompletedProcess(args, 0, stdout=KEY + '\n', stderr='')
        with patch.object(setup.os, 'geteuid', return_value=1000), \
                patch.object(setup.configparser, 'ConfigParser', return_value=config), \
                patch.object(setup, 'run', side_effect=command), \
                patch.object(setup, 'Directory') as directory, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'administrator SSH failed'):
                setup.main(['--apply', '--hosts', *HOSTS])
            directory.assert_not_called()

    def test_apply_bootstraps_service_key_after_all_host_preflights(self):
        config = Namespace(read=Mock(), get=Mock(return_value=HOSTS[0]))
        def command(*args, **options):
            output = (setup.AGENT + '\n0\n' if args[-1] == 'id -un && sudo -k -n id -u'
                      else KEY + '\n')
            return subprocess.CompletedProcess(args, 0, stdout=output, stderr='')
        with patch.object(setup.os, 'geteuid', return_value=1000), \
                patch.object(setup.configparser, 'ConfigParser', return_value=config), \
                patch.object(setup, 'run', side_effect=command) as run, \
                patch.object(setup, 'Directory', return_value=FakeDirectory()), \
                redirect_stdout(io.StringIO()):
            setup.main(['--apply', '--ssh-user', 'nadim', '--hosts', *HOSTS])
        commands = [call.args for call in run.call_args_list]
        bootstrap = commands.index(('sudo', '-n', str(SCRIPT.with_name('install-ssh.sh'))))
        for host in HOSTS:
            preflight = tuple(setup.host_command(host, HOSTS[0], 'nadim', 'preflight', 'lab.osoyalce.com'))
            self.assertLess(commands.index(preflight), bootstrap)
        key = ('sudo', '-n', '-u', setup.SERVICE_USER, 'ssh-keygen', '-y', '-P', '', '-f', str(setup.KEY))
        self.assertLess(bootstrap, commands.index(key))


class HostMigrationTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cmdb-ipa-host-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        (self.home / 'original').write_text('old home contents')
        files = {'SSSD_CONFIG': self.root / 'sssd.conf', 'NSS_CONFIG': self.root / 'nsswitch.conf',
                 'SSHD_CONFIG': self.root / 'sshd_config', 'PASSWD': self.root / 'passwd',
                 'GROUP': self.root / 'group', 'AGENT_HOME': self.home, 'BACKUPS': self.root / 'backups'}
        self.addCleanup(patch.stopall)
        for name, value in files.items():
            patch.object(setup, name, value).start()
        setup.SSSD_CONFIG.write_text('[sssd]\nservices = nss, pam, autofs\n[domain/lab.osoyalce.com]\n'
                                     'id_provider = ipa\naccess_provider = ipa\nipa_server = _srv_\n')
        setup.NSS_CONFIG.write_text('passwd: files sss\nsudoers: files sss\n')
        setup.SSHD_CONFIG.write_text('# original ssh config\nUsePAM yes\n')
        setup.PASSWD.write_text(f'root:x:0:0::/root:/bin/sh\ncmdbagent:x:123:124::{self.home}:/bin/sh\n')
        setup.GROUP.write_text('cmdbagent:x:124:\n')
        (self.root / 'shadow').write_text('fixture only\n')
        self.events = []
        self.args = Namespace(domain='lab.osoyalce.com', host_mode='apply', ipa_uid=12345,
                              ipa_gid=12346, public_key=KEY)
        patch.object(setup.os, 'geteuid', return_value=0).start()
        owners = {setup.BACKUPS: 0}
        stat = Path.stat
        def host_stat(path, **options):
            result = stat(path, **options)
            if path in owners:
                values = list(result)
                values[4] = owners[path]
                return os.stat_result(values)
            return result
        patch.object(Path, 'stat', host_stat).start()
        self.chown = patch.object(setup.os, 'chown', side_effect=lambda path, uid, gid: owners.update({path: uid})).start()
        patch.object(setup.shutil, 'which', side_effect=lambda command: '/fake/' + command).start()
        patch.object(setup, 'run', side_effect=self.command).start()

    def command(self, *command, **options):
        self.events.append(command)
        output, code = '', 0
        if command[0] == 'pgrep':
            code = 1
        elif command[:2] == ('getent', 'passwd'):
            output = f'cmdbagent:x:12345:12346::{self.home}:/bin/sh\n'
        elif command[0] == 'sss_ssh_authorizedkeys':
            output = KEY + '\n'
        elif command[:2] == ('sshd', '-T'):
            output = ('authorizedkeyscommand /usr/bin/sss_ssh_authorizedkeys\n'
                      'authorizedkeyscommanduser nobody\npubkeyauthentication yes\nusepam yes\n')
        elif command[0] == 'runuser':
            output = '0\n'
        elif command[0] == 'userdel':
            self.assertTrue(any((setup.BACKUPS).glob('*/local-home/original')))
            self.assertTrue(any((setup.BACKUPS).glob('*/shadow')))
            setup.PASSWD.write_text('root:x:0:0::/root:/bin/sh\n')
        elif command[0] == 'groupdel':
            setup.GROUP.write_text('')
        return subprocess.CompletedProcess(command, code, stdout=output, stderr='')

    def test_apply_archives_home_before_removal_and_checks_the_directory_identity(self):
        with redirect_stdout(io.StringIO()):
            setup.setup_host(self.args)
        self.assertFalse((self.home / 'original').exists())
        self.assertTrue(self.home.is_dir())
        self.assertIsNone(setup.local_entry(setup.PASSWD, 'cmdbagent'))
        self.assertTrue(any(setup.BACKUPS.glob('*/local-home/original')))
        self.chown.assert_called_once_with(self.home, 12345, 12346)
        lookup = ('getent', 'passwd', 'cmdbagent@lab.osoyalce.com')
        self.assertLess(self.events.index(lookup), self.events.index(('userdel', 'cmdbagent')))
        sudo_check = ('runuser', '-u', 'cmdbagent@lab.osoyalce.com', '--', 'sudo', '-k', '-n', 'id', '-u')
        self.assertLess(self.events.index(sudo_check), self.events.index(('userdel', 'cmdbagent')))
        with redirect_stdout(io.StringIO()):
            setup.setup_host(self.args)
        self.assertEqual(self.events.count(('userdel', 'cmdbagent')), 1)

    def test_running_jobs_stop_preflight_without_changing_files(self):
        original = setup.SSSD_CONFIG.read_text()
        runner = self.command
        def busy(*command, **options):
            if command[0] == 'pgrep':
                return subprocess.CompletedProcess(command, 0, stdout='99\n', stderr='')
            return runner(*command, **options)
        with patch.object(setup, 'run', side_effect=busy), self.assertRaisesRegex(RuntimeError, 'running processes'):
            setup.setup_host(self.args)
        self.assertFalse(setup.BACKUPS.exists())
        self.assertEqual(setup.SSSD_CONFIG.read_text(), original)
        self.assertTrue((self.home / 'original').exists())

    def test_missing_ipa_key_keeps_local_account_and_home(self):
        runner = self.command
        def missing_key(*command, **options):
            if command[0] == 'sss_ssh_authorizedkeys':
                return subprocess.CompletedProcess(command, 0, stdout='', stderr='')
            return runner(*command, **options)
        with patch.object(setup, 'run', side_effect=missing_key), \
                patch.object(setup.time, 'monotonic', side_effect=[0, setup.CLIENT_READY_TIMEOUT]), \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'public key'):
                setup.setup_host(self.args)
        self.assertIsNotNone(setup.local_entry(setup.PASSWD, 'cmdbagent'))
        self.assertTrue((self.home / 'original').exists())
        self.assertNotIn(('userdel', 'cmdbagent'), self.events)

    def test_invalid_sshd_update_restores_configs_before_account_removal(self):
        original_sssd, original_ssh = setup.SSSD_CONFIG.read_text(), setup.SSHD_CONFIG.read_text()
        runner = self.command
        def bad_config(*command, **options):
            if command[:2] == ('sshd', '-t') and setup.SSHD_CONFIG.read_text() != original_ssh:
                raise RuntimeError('sshd rejected configuration')
            return runner(*command, **options)
        with patch.object(setup, 'run', side_effect=bad_config), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'sshd rejected'):
                setup.setup_host(self.args)
        self.assertEqual(setup.SSSD_CONFIG.read_text(), original_sssd)
        self.assertEqual(setup.SSHD_CONFIG.read_text(), original_ssh)
        self.assertNotIn(('userdel', 'cmdbagent'), self.events)

    def test_check_leaves_accounts_configs_and_homes_untouched(self):
        self.args.host_mode = 'check'
        setup.PASSWD.write_text('root:x:0:0::/root:/bin/sh\n')
        setup.GROUP.write_text('')
        original = setup.SSSD_CONFIG.read_text()
        with redirect_stdout(io.StringIO()):
            setup.setup_host(self.args)
        self.assertFalse(setup.BACKUPS.exists())
        self.assertEqual(setup.SSSD_CONFIG.read_text(), original)
        self.assertTrue((self.home / 'original').exists())
        self.assertFalse(any(command[0] in ('userdel', 'groupdel', 'sss_cache') for command in self.events))
