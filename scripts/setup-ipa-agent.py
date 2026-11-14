#!/usr/bin/env python3
"""One-time FreeIPA agent migration; preview unless --apply or --check is given."""

import argparse
import base64
import configparser
from datetime import datetime, timezone
import getpass
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile


AGENT = 'cmdbagent'
SERVICE_USER = 'cmdb'
AGENT_HOME = Path('/home/cmdbagent')
KEY = Path('/var/lib/cmdb/.ssh/id_ed25519')
KNOWN_HOSTS = Path('/var/lib/cmdb/.ssh/known_hosts')
BACKUPS = Path('/var/backups/cmdb-ipa-agent')
HOSTGROUP = 'cmdb-agent-hosts'
HBAC_RULE = 'cmdb-agent-access'
SUDO_RULE = 'cmdb-agent-root'
DESCRIPTION = 'Managed by CMDB scripts/setup-ipa-agent.py'
DEFAULT_HOSTS = ('bingo', 'islands', 'kermit', 'neuromancer', 'paris',
                 'phoebe', 'sally', 'wintermute')
SSSD_CONFIG = Path('/etc/sssd/sssd.conf')
NSS_CONFIG = Path('/etc/nsswitch.conf')
SSHD_CONFIG = Path('/etc/ssh/sshd_config')
PASSWD = Path('/etc/passwd')
GROUP = Path('/etc/group')
SSH_DIRECTIVES = ('# CMDB IPA public-key lookup\n'
                  'AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys\n'
                  'AuthorizedKeysCommandUser nobody\n')


def run(*command, input=None, timeout=60, check=True):
    result = subprocess.run(command, input=input, text=True, capture_output=True,
                            timeout=timeout, env=dict(os.environ, LC_ALL='C'))
    if check and result.returncode:
        raise RuntimeError(f'{shlex.join(command)} failed:\n{result.stderr.strip()}\n'
                           f'{result.stdout.strip()}')
    return result


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def key_material(text):
    parts = text.strip().split()
    require(len(parts) >= 2 and parts[0] == 'ssh-ed25519', 'Expected an Ed25519 public key.')
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except ValueError:
        raise RuntimeError('Invalid public key encoding.') from None
    require(len(blob) == 51 and blob[:19] == b'\0\0\0\x0bssh-ed25519\0\0\0\x20',
            'Invalid Ed25519 public key.')
    return ' '.join(parts[:2])


def local_entry(path, name):
    return next((line.split(':') for line in path.read_text().splitlines()
                 if line.partition(':')[0] == name), None)


def set_ini_option(text, section, option, value):
    """Change one setting while retaining comments and unrelated domain options."""
    lines = text.splitlines(keepends=True)
    start = next((i + 1 for i, line in enumerate(lines)
                  if line.strip().lower() == f'[{section}]'.lower()), None)
    require(start is not None, f'Missing [{section}] in {SSSD_CONFIG}.')
    end = next((i for i in range(start, len(lines))
                if lines[i].lstrip().startswith('[')), len(lines))
    for i in range(start, end):
        if re.match(r'\s*' + re.escape(option) + r'\s*=', lines[i], re.I):
            lines[i] = f'{option} = {value}\n'
            return ''.join(lines)
    lines.insert(start, f'{option} = {value}\n')
    return ''.join(lines)


def nss_sudo(text):
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if re.match(r'\s*sudoers\s*:', line):
            sources, marker, comment = line.partition('#')
            # A short-circuit action can prevent SSSD lookup even with "sss" present.
            require('[' not in sources, 'Review sudoers lookup actions in /etc/nsswitch.conf first.')
            names = sources.partition(':')[2].split()
            if 'files' in names and 'sss' in names:
                return text
            names = ['files', *[name for name in names if name != 'files']]
            if 'sss' not in names:
                names.append('sss')
            lines[i] = 'sudoers: ' + ' '.join(names) + (' #' + comment.rstrip() if marker else '') + '\n'
            return ''.join(lines)
    return text.rstrip() + '\nsudoers: files sss\n'


def host_preflight(domain):
    require(os.geteuid() == 0, 'Host setup requires root through sudo -n.')
    for command in ('getent', 'userdel', 'groupdel', 'runuser', 'sudo', 'pgrep',
                    'systemctl', 'sss_cache', 'sss_ssh_authorizedkeys', 'sshd'):
        require(shutil.which(command), f'Install {command} on this host first.')
    config = configparser.ConfigParser(interpolation=None)
    config.read(SSSD_CONFIG)
    section = f'domain/{domain}'
    require(config.get(section, 'id_provider', fallback='') == 'ipa',
            f'Enroll this host in {domain} with the IPA identity provider first.')
    require(config.get(section, 'access_provider', fallback='') == 'ipa',
            'Configure access_provider = ipa before migration so HBAC is enforced.')
    require(not config.getboolean(section, 'use_fully_qualified_names', fallback=False),
            'CMDB needs the short cmdbagent login; use_fully_qualified_names must be false.')
    for path in (SSSD_CONFIG, SSHD_CONFIG):
        require(path.is_file() and not path.is_symlink(), f'Expected a regular configuration file: {path}')
    require(NSS_CONFIG.is_file(), f'Missing {NSS_CONFIG}.')
    if nss_sudo(NSS_CONFIG.read_text()) != NSS_CONFIG.read_text():
        managed = shutil.which('authselect') and run('authselect', 'current', check=False).returncode == 0
        require(not NSS_CONFIG.is_symlink() and not managed,
                'Enable SSSD sudo lookup first: sudo authselect enable-feature with-sudo')
    run('sshd', '-t')
    run('systemctl', 'is-active', 'sssd')
    entry = local_entry(PASSWD, AGENT)
    if entry:
        require(entry[2] != '0', 'Refusing to remove a UID 0 account.')
        require(Path(entry[5]) in (AGENT_HOME, Path('/var/lib/cmdbagent')),
                f'Unexpected local agent home {entry[5]}; review it before migration.')
        home = Path(entry[5])
        require(not home.is_symlink() and not home.is_mount(), f'Refusing to move linked/mounted home {home}.')
        processes = run('pgrep', '-u', entry[2], check=False)
        require(processes.returncode == 1, 'cmdbagent has running processes; wait for CMDB jobs to finish.')
    return config


def verify_client(login, public_key):
    keys = run('sss_ssh_authorizedkeys', login).stdout.splitlines()
    require(any(' '.join(line.split()[:2]) == public_key for line in keys),
            'SSSD did not return the CMDB public key.')
    effective = run('sshd', '-T', '-C', f'user={AGENT},host={socket.getfqdn()},addr=127.0.0.1').stdout
    settings = dict(line.split(None, 1) for line in effective.splitlines() if ' ' in line)
    require(settings.get('authorizedkeyscommand') == '/usr/bin/sss_ssh_authorizedkeys'
            and settings.get('authorizedkeyscommanduser') == 'nobody'
            and settings.get('pubkeyauthentication') == 'yes' and settings.get('usepam') == 'yes',
            'Effective sshd configuration does not permit IPA public-key login with PAM.')
    result = run('runuser', '-u', login, '--', 'sudo', '-k', '-n', 'id', '-u')
    require(result.stdout.strip() == '0', 'IPA passwordless root sudo verification failed.')


def verify_host(uid, gid, public_key):
    require(local_entry(PASSWD, AGENT) is None, 'A local cmdbagent account still masks IPA.')
    require(local_entry(GROUP, AGENT) is None, 'A local cmdbagent group still masks IPA.')
    entry = run('getent', 'passwd', AGENT).stdout.strip().split(':')
    require(len(entry) == 7 and entry[2:4] == [str(uid), str(gid)] and entry[6] == '/bin/sh',
            'The short cmdbagent login does not resolve to the expected IPA identity.')
    verify_client(AGENT, public_key)


def setup_host(args):
    config = host_preflight(args.domain)
    if args.host_mode == 'preflight':
        return
    require(args.ipa_uid > 0 and args.ipa_gid > 0, 'Expected positive IPA UID and GID.')
    key_material(args.public_key)
    if args.host_mode == 'apply':
        entry = local_entry(PASSWD, AGENT)
        require(not AGENT_HOME.is_symlink(), f'Refusing linked home {AGENT_HOME}.')
        if AGENT_HOME.exists() and (not entry or Path(entry[5]) != AGENT_HOME):
            require(AGENT_HOME.is_dir() and AGENT_HOME.stat().st_uid == args.ipa_uid,
                    f'Review ownership of existing {AGENT_HOME} before migration.')
        BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(not BACKUPS.is_symlink() and BACKUPS.stat().st_uid == 0
                and BACKUPS.stat().st_mode & 0o077 == 0, f'{BACKUPS} must be private and root-owned.')
        backup = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),
                                       dir=BACKUPS))
        print(f'Host backups: {backup}', flush=True)
        changes = {}
        original = SSSD_CONFIG.read_text()
        services = [name.strip() for name in config.get('sssd', 'services', fallback='nss, pam').split(',')
                    if name.strip()]
        for service in ('ssh', 'sudo'):
            if service not in services and run('systemctl', 'is-enabled', f'sssd-{service}.socket',
                                               check=False).returncode != 0:
                services.append(service)
        updated = set_ini_option(original, 'sssd', 'services', ', '.join(services))
        updated = set_ini_option(updated, f'domain/{args.domain}', 'sudo_provider', 'ipa')
        changes[SSSD_CONFIG] = updated
        nss_text = NSS_CONFIG.read_text()
        if nss_sudo(nss_text) != nss_text:
            changes[NSS_CONFIG] = nss_sudo(nss_text)
        original_ssh = SSHD_CONFIG.read_text()
        changes[SSHD_CONFIG] = SSH_DIRECTIVES + original_ssh.removeprefix(SSH_DIRECTIVES)
        try:
            for path, content in changes.items():
                shutil.copy2(path, backup / path.name)
                path.write_text(content)
            if shutil.which('sssctl'):
                run('sssctl', 'config-check')
            run('sshd', '-t')
        except Exception:
            for path in changes:
                saved = backup / path.name
                if saved.exists():
                    shutil.copyfile(saved, path)
            raise
        run('sss_cache', '-U', '-R')
        run('systemctl', 'restart', 'sssd')
        ssh_service = 'ssh' if run('systemctl', 'is-active', 'ssh', check=False).returncode == 0 else 'sshd'
        run('systemctl', 'reload', ssh_service)
        qualified = run('getent', 'passwd', f'{AGENT}@{args.domain}').stdout.strip().split(':')
        require(len(qualified) == 7 and qualified[2:4] == [str(args.ipa_uid), str(args.ipa_gid)],
                'IPA identity lookup failed; the local account has not been removed.')
        verify_client(f'{AGENT}@{args.domain}', args.public_key)
        # Recheck processes just before deletion, after all directory/configuration checks.
        host_preflight(args.domain)
        entry = local_entry(PASSWD, AGENT)
        if entry or local_entry(GROUP, AGENT):
            for name in ('passwd', 'shadow', 'group', 'gshadow'):
                path = PASSWD.parent / name
                if path.exists():
                    shutil.copy2(path, backup / name)
        if entry:
            home = Path(entry[5])
            if home.exists():
                shutil.move(str(home), backup / 'local-home')
            try:
                run('userdel', AGENT)
            except Exception:
                if (backup / 'local-home').exists():
                    shutil.move(str(backup / 'local-home'), home)
                raise
            print(f'Previous local agent UID:GID: {entry[2]}:{entry[3]}. '
                  'Files outside its home retain that ownership; check backup storage before resuming jobs.', flush=True)
        if local_entry(GROUP, AGENT):
            run('groupdel', AGENT)
        require(not AGENT_HOME.is_symlink(), f'Refusing linked home {AGENT_HOME}.')
        if AGENT_HOME.exists():
            require(AGENT_HOME.stat().st_uid == args.ipa_uid, f'Review ownership of existing {AGENT_HOME}.')
        else:
            AGENT_HOME.mkdir(mode=0o700)
            os.chown(AGENT_HOME, args.ipa_uid, args.ipa_gid)
    verify_host(args.ipa_uid, args.ipa_gid, args.public_key)


class Directory:
    def __init__(self):
        try:
            from ipalib import api, errors
        except ImportError:
            raise RuntimeError('Use the system python3 with the FreeIPA client installed, outside the app venv.') from None
        try:
            api.bootstrap(context='cli')
            api.finalize()
            api.Backend.rpcclient.connect()
        except errors.PublicError as error:
            raise RuntimeError(f'FreeIPA connection failed (check kinit admin): {error}') from None
        self.api, self.errors = api, errors

    def show(self, kind, name):
        try:
            return self.call(f'{kind}_show', name, all=True)['result']
        except self.errors.NotFound:
            return None

    def call(self, command, name, **options):
        try:
            result = self.api.Command[command](name, **options)
        except self.errors.NotFound:
            raise
        except self.errors.PublicError as error:
            raise RuntimeError(f'IPA {command} {name}: {error}') from None
        def failed(value):
            return any(failed(item) for item in value.values()) if isinstance(value, dict) else bool(value)
        require(not failed(result.get('failed', {})), f'IPA membership update failed: {result.get("failed")}')
        return result


def directory_setup(directory, hosts, key, apply):
    objects = {kind: directory.show(kind, name) for kind, name in
               (('hostgroup', HOSTGROUP), ('hbacrule', HBAC_RULE), ('sudorule', SUDO_RULE))}
    # Never adopt a same-name rule that may grant access to unrelated users/hosts.
    for kind, record in objects.items():
        if record:
            require(record.get('description') == [DESCRIPTION] or record.get('description') == (DESCRIPTION,),
                    f'Existing {kind} is not owned by this setup script; inspect it before continuing.')
            allowed = {'member_host': set(hosts)} if kind == 'hostgroup' else {
                'memberuser_user': {AGENT}, 'memberhost_hostgroup': {HOSTGROUP},
                'memberservice_hbacsvc': {'sshd', 'sudo', 'sudo-i'}}
            for attribute in ('usercategory', 'hostcategory', 'servicecategory', 'memberuser_group',
                              'memberhost_host', 'memberservice_hbacsvcgroup', 'ipasudorunasusercategory',
                              'ipasudorunasgroupcategory', 'member_hostgroup', 'externalhost',
                              'externaluser', 'memberallowcmd_sudocmd', 'memberallowcmd_sudocmdgroup',
                              'memberdenycmd_sudocmd', 'memberdenycmd_sudocmdgroup'):
                require(not record.get(attribute), f'Unexpected {attribute} in {kind}; inspect the existing rule.')
            require(not any(value for name, value in record.items() if name.startswith('ipasudorunas')),
                    f'Unexpected RunAs setting in {kind}; this script grants root sudo only.')
            if kind == 'sudorule':
                require(set(record.get('ipasudoopt', ())) <= {'!authenticate'},
                        'Unexpected sudo options; inspect the existing CMDB rule.')
            for attribute, permitted in allowed.items():
                require(set(record.get(attribute, ())) <= permitted,
                        f'Unexpected {attribute} membership in {kind}; inspect the existing object.')
    for host in hosts:
        require(directory.show('host', host), f'{host} is not an enrolled IPA host.')
    user = directory.show('user', AGENT)
    if apply:
        if user is None:
            directory.call('user_add', AGENT, givenname='CMDB', sn='Agent', loginshell='/bin/sh',
                           homedirectory=str(AGENT_HOME), ipasshpubkey=[key])
        else:
            options = {}
            for attribute, value in (('loginshell', '/bin/sh'), ('homedirectory', str(AGENT_HOME))):
                if list(user.get(attribute, ())) != [value]:
                    options[attribute] = value
            keys = list(user.get('ipasshpubkey', ()))
            if not any(' '.join(item.split()[:2]) == key for item in keys):
                options['ipasshpubkey'] = [*keys, key]
            if options:
                directory.call('user_mod', AGENT, **options)
            if str(user.get('nsaccountlock', False)).lower() == 'true':
                directory.call('user_enable', AGENT)
        for kind, name in (('hostgroup', HOSTGROUP), ('hbacrule', HBAC_RULE), ('sudorule', SUDO_RULE)):
            if objects[kind] is None:
                directory.call(f'{kind}_add', name, description=DESCRIPTION,
                               **({'cmdcategory': 'all'} if kind == 'sudorule' else {}))
                objects[kind] = directory.show(kind, name)
        memberships = [('hostgroup', HOSTGROUP, 'member_host', 'host', hosts, 'add_member'),
                       ('hbacrule', HBAC_RULE, 'memberuser_user', 'user', [AGENT], 'add_user'),
                       ('hbacrule', HBAC_RULE, 'memberhost_hostgroup', 'hostgroup', [HOSTGROUP], 'add_host'),
                       ('hbacrule', HBAC_RULE, 'memberservice_hbacsvc', 'hbacsvc',
                        ['sshd', 'sudo', 'sudo-i'], 'add_service'),
                       ('sudorule', SUDO_RULE, 'memberuser_user', 'user', [AGENT], 'add_user'),
                       ('sudorule', SUDO_RULE, 'memberhost_hostgroup', 'hostgroup', [HOSTGROUP], 'add_host')]
        for kind, name, attribute, option, desired, operation in memberships:
            missing = set(desired) - set(objects[kind].get(attribute, ()))
            if missing:
                directory.call(f'{kind}_{operation}', name, **{option: sorted(missing)})
        rule = objects['sudorule']
        if list(rule.get('cmdcategory', ())) != ['all']:
            directory.call('sudorule_mod', SUDO_RULE, cmdcategory='all')
        require('authenticate' not in rule.get('ipasudoopt', ()), 'Remove conflicting authenticate sudo option first.')
        if '!authenticate' not in rule.get('ipasudoopt', ()):
            directory.call('sudorule_add_option', SUDO_RULE, ipasudoopt='!authenticate')
        for kind, name in (('hbacrule', HBAC_RULE), ('sudorule', SUDO_RULE)):
            if not objects[kind].get('ipaenabledflag', True):
                directory.call(f'{kind}_enable', name)
        return directory_setup(directory, hosts, key, False)
    require(user and list(user.get('loginshell', ())) == ['/bin/sh']
            and list(user.get('homedirectory', ())) == [str(AGENT_HOME)]
            and not user.get('nsaccountlock', False)
            and any(' '.join(item.split()[:2]) == key for item in user.get('ipasshpubkey', ())),
            'IPA cmdbagent is not ready; run --apply first.')
    require(all(objects.values()), 'IPA host group or access rules are missing; run --apply first.')
    for host in hosts:
        require(host in objects['hostgroup'].get('member_host', ()), f'{host} is missing from {HOSTGROUP}.')
    for kind in ('hbacrule', 'sudorule'):
        record = objects[kind]
        require(AGENT in record.get('memberuser_user', ()) and HOSTGROUP in record.get('memberhost_hostgroup', ())
                and record.get('ipaenabledflag', False), f'{kind} is incomplete or disabled.')
    require(set(objects['hbacrule'].get('memberservice_hbacsvc', ())) == {'sshd', 'sudo', 'sudo-i'},
            'HBAC service membership is incomplete.')
    require(list(objects['sudorule'].get('cmdcategory', ())) == ['all']
            and '!authenticate' in objects['sudorule'].get('ipasudoopt', ()), 'Root sudo rule is incomplete.')
    return int(user['uidnumber'][0]), int(user['gidnumber'][0])


def host_command(host, local_host, ssh_user, mode, domain, uid=0, gid=0, key=''):
    command = ['sudo', '-n', 'python3', '-', '--host-mode', mode, '--domain', domain,
               '--ipa-uid', str(uid), '--ipa-gid', str(gid), '--public-key', key]
    if host == local_host:
        return command
    return ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-l', ssh_user, '--', host, shlex.join(command)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='Create IPA policy and migrate the listed hosts.')
    mode.add_argument('--check', action='store_true', help='Verify existing setup without changing configuration or accounts.')
    parser.add_argument('--domain', default='lab.osoyalce.com')
    parser.add_argument('--hosts', nargs='+', help='Explicit enrolled FQDNs; defaults to the eight lab hosts.')
    parser.add_argument('--ssh-user', default=getpass.getuser(), help='Existing administrator login with passwordless sudo.')
    parser.add_argument('--host-mode', choices=('preflight', 'apply', 'check'), help=argparse.SUPPRESS)
    parser.add_argument('--ipa-uid', type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument('--ipa-gid', type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument('--public-key', default='', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    require(re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)+', args.domain), 'Use a lowercase DNS domain.')
    if args.host_mode:
        setup_host(args)
        return
    hosts = args.hosts or [f'{host}.{args.domain}' for host in DEFAULT_HOSTS]
    require(len(hosts) == len(set(hosts)) and all(re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)+', host)
            and host.endswith('.' + args.domain) for host in hosts), 'Use unique enrolled FQDNs in the selected domain.')
    require(re.fullmatch(r'[a-z_][a-z0-9_-]*', args.ssh_user) and args.ssh_user != AGENT,
            'Choose an existing administrator SSH login, separate from cmdbagent.')
    print('Apply' if args.apply else 'Check' if args.check else 'PREVIEW (no commands executed)', flush=True)
    print(f'Agent: {AGENT}; key: {KEY}; administrator: {args.ssh_user}', flush=True)
    print('Hosts: ' + ', '.join(hosts), flush=True)
    print('Policy: SSH and passwordless root commands on this host group only.', flush=True)
    print(f'Local agent accounts/homes are backed up under {BACKUPS} before replacement.', flush=True)
    if not (args.apply or args.check):
        print('Run on the CMDB server: sudo -v; kinit admin; rerun with --apply.', flush=True)
        return
    require(os.geteuid() != 0, 'Run as your administrator login after sudo -v and kinit admin, without sudo on this script.')
    config = configparser.ConfigParser(interpolation=None)
    config.read('/etc/ipa/default.conf')
    local_host = config.get('global', 'host', fallback='')
    require(local_host in hosts, 'Run on the enrolled CMDB server and include it in --hosts.')
    run('klist', '-s')
    run('sudo', '-n', 'true')
    key = key_material(run('sudo', '-n', '-u', SERVICE_USER, 'ssh-keygen', '-y', '-P', '', '-f', str(KEY)).stdout)
    require(key_material(run('sudo', '-n', 'cat', str(KEY) + '.pub').stdout) == key,
            'The existing private and public key files do not match.')
    source = Path(__file__).read_text()
    for host in hosts:
        print(f'Preflight: {host}', flush=True)
        run(*host_command(host, local_host, args.ssh_user, 'preflight', args.domain), input=source)
    uid, gid = directory_setup(Directory(), hosts, key, args.apply)
    for host in hosts:
        print(f'{"Migrate" if args.apply else "Verify"}: {host}', flush=True)
        result = run(*host_command(host, local_host, args.ssh_user, 'apply' if args.apply else 'check',
                                   args.domain, uid, gid, key), input=source, timeout=120)
        print(result.stdout, end='', flush=True)
        if host != local_host:
            result = run('sudo', '-n', '-u', SERVICE_USER, 'ssh', '-F', '/dev/null', '-T',
                         '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none',
                         '-o', 'StrictHostKeyChecking=accept-new', '-o', f'UserKnownHostsFile={KNOWN_HOSTS}',
                         '-o', 'ConnectTimeout=10', '-i', str(KEY), '-l', AGENT, '--', host,
                         'id -un && sudo -k -n id -u')
            require(result.stdout.splitlines() == [AGENT, '0'], f'CMDB key login failed on {host}.')
        elif args.check:
            result = run('sudo', '-n', '-u', SERVICE_USER, 'sudo', '-n', '-H', '-u', AGENT,
                         '--', '/bin/sh', '-c', 'sudo -k -n id -u')
            require(result.stdout.strip() == '0', 'Local cmdb -> cmdbagent -> root access failed; run upgrade.sh.')
        print(f'[ PASSED ] {host}', flush=True)
    print('Setup verified. Run sudo scripts/upgrade.sh from the released checkout, then rerun --check.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(f'[ FAIL ] {error}\nCompleted steps are retained. Correct the issue and rerun; inspect host backups before restoring.',
              file=sys.stderr)
        sys.exit(1)
