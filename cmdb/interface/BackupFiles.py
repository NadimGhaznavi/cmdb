"""Check stored dump paths through the local backup agent, without reading dumps."""

import json
from pathlib import Path, PurePosixPath
import shlex

from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.SSH import SSH


class BackupFiles:
    def scan(self, records: list[dict]) -> list[str]:
        paths = []
        for record in records:
            path = PurePosixPath(record['pathname'])
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('Invalid backup pathname.')
            paths.append(str(path))
        script = (Path(__file__).parent / 'scripts/scan-backups.py').read_text()
        result = SSH().run('127.0.0.1', shlex.join(['python3', '-c', script]),
                           input=json.dumps({'directory': DCmdb.BACKUP_DIR, 'paths': paths}))
        statuses = json.loads(result.stdout)
        if (not isinstance(statuses, list) or len(statuses) != len(paths)
                or any(status not in ('Found', 'Missing') for status in statuses)):
            raise ValueError('Invalid filesystem scan result.')
        return statuses
