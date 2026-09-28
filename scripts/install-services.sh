#!/usr/bin/env bash
# Deploy CMDB after provisioning its account and database.
set -euo pipefail
umask 022
[[ $# == 0 && $EUID == 0 ]] || { printf 'Usage: sudo scripts/install-services.sh\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

settings_output=$(python3 -B - <<'PY'
from pathlib import Path
import stat
import grp
from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment

installation = Path(DCmdb.BASE_DIR)
if installation.is_symlink() or Path.cwd().resolve() == installation.resolve():
    raise SystemExit('Run deployment from a separate checkout; installation must not be a symlink.')
path = Path(DCmdb.DATABASE_ENV)
info = path.lstat()
if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o640
        or info.st_gid != grp.getgrnam(DCmdb.SERVICE_USER).gr_gid):
    raise SystemExit('Credentials must be a root:cmdb regular file with mode 640; run install.sh first.')
values = DatabaseEnvironment.read(path)
if values['DB_NAME'] != DCmdb.DATABASE_NAME or values['DB_USER'] != DCmdb.DATABASE_USER:
    raise SystemExit('Credentials do not belong to CMDB; run install.sh first.')
print(DCmdb.BASE_DIR)
print(DCmdb.SERVICE_USER)
print(DCmdb.SERVICE_UNIT)
print(DCmdb.SERVICE_HOME)
PY
)
mapfile -t settings <<< "$settings_output"
install_dir=${settings[0]}
account=${settings[1]}
unit=${settings[2]}
account_home=${settings[3]}
getent passwd "$account" >/dev/null
command -v systemd-analyze >/dev/null
command -v sudo >/dev/null
command -v visudo >/dev/null
command -v ssh >/dev/null
command -v ssh-keygen >/dev/null
command -v crontab >/dev/null
[[ -x /usr/bin/nmap ]] || { printf 'Install /usr/bin/nmap before deploying CMDB.\n' >&2; exit 1; }

# Validate the complete rule before atomically installing it.
python3 -B - <<'PY'
from pathlib import Path
import os
import re
import subprocess
from tempfile import NamedTemporaryFile
from cmdb.constants.DCmdb import DCmdb

if re.fullmatch(r'[a-z_][a-z0-9_]*', DCmdb.SERVICE_USER) is None:
    raise SystemExit('Invalid CMDB service account name.')
if re.fullmatch(r'[a-z_][a-z0-9_]*', DCmdb.AGENT_USER) is None or DCmdb.AGENT_USER == DCmdb.SERVICE_USER:
    raise SystemExit('Invalid CMDB inventory account name.')
rule = Path('sudoers/cmdb-nmap').read_text().replace('@USER@', DCmdb.SERVICE_USER)
rule = rule.replace('@AGENT@', DCmdb.AGENT_USER)
target = Path('/etc/sudoers.d/cmdb-nmap')
target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
with NamedTemporaryFile(mode='w', prefix='.cmdb-nmap-', dir=target.parent, delete=False) as stream:
    candidate = Path(stream.name)
    try:
        stream.write(rule)
        stream.flush()
        os.fchown(stream.fileno(), 0, 0)
        os.fchmod(stream.fileno(), 0o440)
        subprocess.run(['visudo', '-cf', str(candidate)], check=True)
        candidate.replace(target)
    finally:
        candidate.unlink(missing_ok=True)
PY

if [[ -e /etc/systemd/system/$unit ]]; then
    systemctl stop "$unit"
fi
usermod --home "$account_home" "$account"
scripts/install-ssh.sh
python3 -B scripts/install-agent.py

printf 'Installing Python dependencies...\n'
if [[ ! -x $install_dir/.venv/bin/python ]]; then
    python3 -m venv "$install_dir/.venv"
fi
"$install_dir/.venv/bin/python" -m pip install -r requirements.txt

printf 'Copying CMDB application and service definition...\n'
python3 -B - <<'PY'
from pathlib import Path
import shutil
from cmdb.constants.DCmdb import DCmdb

destination = Path(DCmdb.BASE_DIR)
shutil.copytree('cmdb', destination / 'cmdb', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copytree('schema', destination / 'schema', dirs_exist_ok=True)
for name in ('cmdb-server.py', 'cmdb-backup.py', 'requirements.txt', 'VERSION'):
    shutil.copy2(name, destination / name)
template = Path('systemd', DCmdb.SERVICE_UNIT).read_text()
unit = template.replace('@APP@', DCmdb.BASE_DIR).replace('@USER@', DCmdb.SERVICE_USER)
unit = unit.replace('@DATABASE_ENV@', DCmdb.DATABASE_ENV)
unit = unit.replace('@SSH_DIR@', DCmdb.SSH_DIR)
unit = unit.replace('@BACKUP_DIR@', DCmdb.BACKUP_DIR)
target = Path('/etc/systemd/system', DCmdb.SERVICE_UNIT)
target.write_text(unit)
target.chmod(0o644)
PY

printf 'Checking MariaDB connection...\n'
(cd -- "$install_dir"
"$install_dir/.venv/bin/python" -B - <<'PY'
import os
from pathlib import Path
from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment
from cmdb.interface.DbMgr import DbMgr

os.environ.update(DatabaseEnvironment.read(Path(DCmdb.DATABASE_ENV)))
db = DbMgr()
try:
    db.query('SELECT 1 AS ready')
finally:
    db.close()
PY
)

systemd-analyze verify "/etc/systemd/system/$unit"
systemctl daemon-reload
systemctl enable --now cron
systemctl enable --now "$unit"

python3 -B - <<'PY'
import json
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
from cmdb.constants.DCmdb import DCmdb

opener = build_opener(ProxyHandler({}))
for endpoint, expected in (('health', 'ok'), ('ready', 'ready')):
    for attempt in range(30):
        try:
            with opener.open(f'http://127.0.0.1:{DCmdb.PORT}/{endpoint}', timeout=1) as response:
                body = json.load(response)
                if response.status == 200 and body == {'status': expected, 'service': 'cmdb-server'}:
                    break
        except (URLError, TimeoutError):
            pass
        time.sleep(1)
    else:
        raise SystemExit('Health check failed; inspect journalctl -u ' + DCmdb.SERVICE_UNIT)
print(f'CMDB server listening on port: {DCmdb.PORT}')
PY
