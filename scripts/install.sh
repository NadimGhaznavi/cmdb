#!/usr/bin/env bash
# Provision the local accounts and database, then deploy CMDB.
set -euo pipefail
umask 022

if [[ $# == 1 && $1 == --help ]]; then
    printf 'Usage: sudo scripts/install.sh\nInstall CMDB and provision its MariaDB backend.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Run scripts/install.sh as root, without arguments.\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ $(pwd -P) != /opt/prod/cmdb ]] || { printf 'Run installation from a separate checkout.\n' >&2; exit 1; }
command -v mariadb >/dev/null
command -v systemctl >/dev/null
command -v systemd-analyze >/dev/null
command -v sudo >/dev/null
command -v visudo >/dev/null
command -v ssh >/dev/null
command -v ssh-keygen >/dev/null
command -v crontab >/dev/null
[[ -x /usr/bin/nmap ]] || { printf 'Install /usr/bin/nmap before installing CMDB.\n' >&2; exit 1; }
python3 -B - <<'PY'
import sys
import venv
import ensurepip
if sys.version_info < (3, 11):
    raise SystemExit('CMDB requires Python 3.11 or later.')
PY
mariadb --protocol=socket --user=root --batch --skip-column-names -e 'SELECT 1' >/dev/null

settings_output=$(python3 -B - <<'PY'
from pathlib import Path
from cmdb.constants.DCMDB import DCMDB
installation = Path(DCMDB.BASE_DIR)
if installation.is_symlink() or Path.cwd().resolve() == installation.resolve():
    raise SystemExit('Run deployment from a separate checkout; installation must not be a symlink.')
print(DCMDB.BASE_DIR)
print(DCMDB.SERVICE_USER)
print(DCMDB.SERVICE_HOME)
PY
)
mapfile -t settings <<< "$settings_output"
install_dir=${settings[0]}
account=${settings[1]}
account_home=${settings[2]}
getent group "$account" >/dev/null || groupadd --system "$account"
getent passwd "$account" >/dev/null || useradd --system --gid "$account" \
    --no-create-home --home-dir "$account_home" --shell /usr/sbin/nologin "$account"
install -d -m 755 -- "$install_dir"

# Credentials are never sourced as shell code or passed in command arguments.
python3 -B - <<'PY'
import os
from pathlib import Path
import re
import secrets
import stat
import grp
import subprocess
from cmdb.constants.DDbMgr import DDbMgr
from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment

path = Path(DCMDB.DATABASE_ENV)
expected = {'DB_HOST': 'localhost', 'DB_PORT': str(DDbMgr.PORT),
            'DB_NAME': DCMDB.DATABASE_NAME, 'DB_USER': DCMDB.DATABASE_USER}
if path.is_symlink():
    raise SystemExit('Credentials must not be a symbolic link.')
if path.exists():
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or mode not in (0o600, 0o640)
            or (mode == 0o640 and info.st_gid != grp.getgrnam(DCMDB.SERVICE_USER).gr_gid)):
        raise SystemExit('Existing credentials must be root-owned with mode 600 or root:cmdb mode 640.')
    values = DatabaseEnvironment.read(path)
    if any(values[key] != value for key, value in expected.items()):
        raise SystemExit('Existing credentials do not match CMDB.')
    password = values['DB_PASSWORD']
    if re.fullmatch('[a-f0-9]{64}', password) is None:
        raise SystemExit('Existing credentials do not match the generated password format.')
else:
    password = secrets.token_hex(32)
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        for key, value in {**expected, 'DB_PASSWORD': password}.items():
            stream.write(f'{key}={value}\n')

# The independent cron runner needs read access without access to modify credentials.
os.chown(path, 0, grp.getgrnam(DCMDB.SERVICE_USER).gr_gid)
path.chmod(0o640)

database, user = DCMDB.DATABASE_NAME, DCMDB.DATABASE_USER
sql = (f'CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4;\n'
       f"CREATE USER IF NOT EXISTS '{user}'@'localhost' IDENTIFIED BY '{password}';\n"
       f"GRANT ALL ON `{database}`.* TO '{user}'@'localhost';\n")
subprocess.run(['mariadb', '--protocol=socket', '--user=root'], input=sql, text=True, check=True)
subprocess.run(['mariadb', '--no-defaults', '--protocol=socket', '--user=' + user,
                '--database=' + database],
               input=Path('schema/cmdb-schema-v1.sql').read_text(), text=True,
               env={**os.environ, 'MYSQL_PWD': password}, check=True)
PY
exec scripts/install-services.sh
