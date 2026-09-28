"""Run locally as cmdbagent so private backup directories can be inspected."""

import json
from pathlib import Path
import stat
import sys


request = json.load(sys.stdin)
base = Path(request['directory'])
if not stat.S_ISDIR(base.stat().st_mode):
    raise NotADirectoryError(str(base))
statuses = []
for pathname in request['paths']:
    path = base / pathname
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        statuses.append('Missing')
    else:
        if not stat.S_ISREG(mode):
            raise ValueError(f'Backup path is not a regular file: {path}')
        statuses.append('Found')
json.dump(statuses, sys.stdout)
