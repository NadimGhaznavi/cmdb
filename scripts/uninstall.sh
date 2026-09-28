#!/usr/bin/env bash
# Remove CMDB and its database, retaining credentials and accounts.
set -euo pipefail
umask 022
if [[ $# == 1 && $1 == --help ]]; then
    printf 'Usage: sudo scripts/uninstall.sh\nRemove the CMDB service, application, and database; keep credentials and accounts.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Run scripts/uninstall.sh as root, without arguments.\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 -B - <<'PYTHON'
from pathlib import Path
import re
import shutil
import subprocess

from cmdb.constants.DCmdb import DCmdb

application = Path(DCmdb.BASE_DIR)
if application.is_symlink() or application != Path('/opt/prod/cmdb'):
    raise SystemExit('Refusing to remove an unexpected application directory.')
if Path.cwd().resolve().is_relative_to(application.resolve()):
    raise SystemExit('Run uninstall from a separate checkout.')
if re.fullmatch(r'[a-z_][a-z0-9_]*', DCmdb.DATABASE_NAME) is None:
    raise SystemExit('Invalid CMDB database name.')
if Path(DCmdb.SERVICE_UNIT).name != DCmdb.SERVICE_UNIT:
    raise SystemExit('Invalid CMDB service unit name.')

# Check database access before removing anything.
mariadb = ['mariadb', '--protocol=socket', '--user=root']
subprocess.run(mariadb, input='SELECT 1;\n', text=True,
               stdout=subprocess.DEVNULL, check=True)
unit = Path('/etc/systemd/system') / DCmdb.SERVICE_UNIT
state = subprocess.run(
    ['systemctl', 'show', DCmdb.SERVICE_UNIT, '--property=LoadState', '--value'],
    capture_output=True, text=True, check=True).stdout.strip()
if unit.exists() or unit.is_symlink() or state != 'not-found':
    subprocess.run(['systemctl', 'disable', '--now', DCmdb.SERVICE_UNIT], check=True)

# Retain the database user and its password so installation can reuse the credentials.
subprocess.run(mariadb, input=f'DROP DATABASE IF EXISTS `{DCmdb.DATABASE_NAME}`;\n',
               text=True, check=True)
unit.unlink(missing_ok=True)
Path('/etc/sudoers.d/cmdb-nmap').unlink(missing_ok=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
if application.exists():
    shutil.rmtree(application)
print('Removed CMDB service, application, database, and Nmap sudoers rule.')
print('Preserved credentials, database account, Linux account, and system packages.')
PYTHON
