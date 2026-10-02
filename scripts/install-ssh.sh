#!/usr/bin/env bash
# Provision the local service account's reusable SSH identity.
set -euo pipefail
umask 077
[[ $# == 0 && $EUID == 0 ]] || { printf 'Usage: sudo scripts/install-ssh.sh\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 -B - <<'PY'
import os
from pathlib import Path
import pwd
import subprocess

from cmdb.constants.DCMDB import DCMDB

account = pwd.getpwnam(DCMDB.SERVICE_USER)
home = Path(DCMDB.SERVICE_HOME)
directory = Path(DCMDB.SSH_DIR)
key = Path(DCMDB.SSH_KEY)
public = key.with_suffix('.pub')
known_hosts = Path(DCMDB.SSH_KNOWN_HOSTS)

for path in (home, directory, key, public, known_hosts):
    if path.is_symlink():
        raise SystemExit('CMDB SSH paths must not be symbolic links.')
for path, mode in ((home, 0o750), (directory, 0o700)):
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
    os.chown(path, account.pw_uid, account.pw_gid)
for path in (key, public, known_hosts):
    if path.exists() and not path.is_file():
        raise SystemExit('CMDB SSH files must be regular files.')

if not key.exists():
    subprocess.run(['/usr/bin/ssh-keygen', '-q', '-t', 'ed25519', '-N', '',
                    '-C', DCMDB.SERVICE_USER, '-f', str(key)], check=True)
key.chmod(0o600)
os.chown(key, account.pw_uid, account.pw_gid)
# Reconstruct the public half if missing, retaining the existing private key.
result = subprocess.run(['/usr/bin/ssh-keygen', '-y', '-P', '', '-f', str(key)],
                        capture_output=True, text=True, check=True)
public.write_text(result.stdout)
public.chmod(0o644)
os.chown(public, account.pw_uid, account.pw_gid)
known_hosts.touch(exist_ok=True)
known_hosts.chmod(0o600)
os.chown(known_hosts, account.pw_uid, account.pw_gid)
print(f'CMDB SSH public key: {public}')
PY
