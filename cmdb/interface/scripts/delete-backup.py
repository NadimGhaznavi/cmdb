"""Remove one recorded dump as cmdbagent, confined to the backup directory."""

import json
from pathlib import Path
import stat
import sys


request = json.load(sys.stdin)
base = Path(request['directory']).resolve(strict=True)
if not base.is_dir():
    raise NotADirectoryError(str(base))
relative = Path(request['pathname'])
if relative.is_absolute() or '..' in relative.parts or not relative.parts:
    raise ValueError('Invalid backup pathname.')
path = base / relative
resolved = path.resolve()
if not resolved.is_relative_to(base):
    raise ValueError('Backup path is outside the backup directory.')
try:
    mode = path.lstat().st_mode
except FileNotFoundError:
    pass
else:
    if not stat.S_ISREG(mode):
        raise ValueError('Backup path is not a regular file.')
    path.unlink(missing_ok=True)
