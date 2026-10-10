"""Archive declared application directories on their inventoried host."""

from pathlib import Path, PurePosixPath
import re
import shlex

from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.SSH import SSH


class SSHFiles:
    def __init__(self, ssh: SSH) -> None:
        self._ssh = ssh

    def backup_directory(self, host: str, directory: str, pathname: str) -> dict:
        source = PurePosixPath(directory)
        destination = PurePosixPath(pathname)
        if (not source.is_absolute() or source == PurePosixPath('/') or '..' in source.parts
                or any(ord(character) < 32 or ord(character) == 127 for character in directory)):
            raise ValueError('Select an absolute application directory to back up.')
        if (len(destination.parts) != 3 or destination.parts[1] != 'files'
                or '..' in destination.parts or destination.is_absolute()
                or not re.fullmatch(r'[A-Za-z0-9_.%:-]+/files/[A-Za-z0-9_.%:-]+\.tgz', pathname)):
            raise ValueError('Invalid directory backup pathname.')
        script = (Path(__file__).parent / 'scripts/backup-files.sh').read_text()
        command = f'timeout --signal=TERM --kill-after=10 {DCMDB.BACKUP_TIMEOUT_SECONDS} sh -s -- '
        command += shlex.join([DCMDB.BACKUP_DIR, pathname, str(source)])
        result = self._ssh.run(host, command, input=script,
                               timeout=DCMDB.BACKUP_TIMEOUT_SECONDS + 30,
                               connect_timeout=DCMDB.SSH_CONNECT_TIMEOUT_SECONDS)
        fields = result.stdout.strip().split()
        if len(fields) != 2 or not fields[0].isdigit() or not re.fullmatch('[0-9a-f]{64}', fields[1]):
            raise ValueError('The archive command did not return valid file metadata.')
        return {'pathname': pathname, 'sizeBytes': int(fields[0]), 'checksum': fields[1]}
