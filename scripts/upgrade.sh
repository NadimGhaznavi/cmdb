#!/usr/bin/env bash
# Reuse provisioning and deployment while retaining database credentials.
set -euo pipefail
if [[ $# == 1 && $1 == --help ]]; then
    printf 'Usage: sudo scripts/upgrade.sh\nDeploy CMDB from this checkout, retaining database data and credentials.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Usage: sudo scripts/upgrade.sh\n' >&2; exit 1; }
exec "$(dirname -- "${BASH_SOURCE[0]}")/install.sh"
