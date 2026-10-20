#!/usr/bin/env bash
# Validate production network settings and restart the CMDB web server.
set -euo pipefail
if [[ ${1:-} == --help && $# == 1 ]]; then
    printf 'Usage: sudo scripts/restart.sh\nApply conf/cmdb.json and restart the CMDB web server.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Run scripts/restart.sh as root, without arguments.\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
install_dir=$(python3 -B - <<'PY'
from cmdb.constants.DCMDB import DCMDB
print(DCMDB.BASE_DIR)
PY
)
cd -- "$install_dir"
.venv/bin/python -B - <<'PY'
from pathlib import Path
import subprocess

from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.Configuration import Configuration

Configuration.read(Path(DCMDB.BASE_DIR) / DCMDB.CONFIG_FILE, DCMDB.CMDB_NETWORK)
subprocess.run(['systemctl', 'restart', DCMDB.SERVICE_UNIT], check=True)
print('Applied production network configuration and restarted CMDB.')
PY
