#!/usr/bin/env python3
"""Run the independent Debian patch queue, resuming verification after reboot."""

import os
from pathlib import Path

from cmdb.activity.PatchRunner import PatchRunner
from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment


if __name__ == '__main__':
    os.environ.update(DatabaseEnvironment.read(Path(DCmdb.DATABASE_ENV)))
    PatchRunner().serve()
