#!/usr/bin/env python3
"""Run the independent Debian patch queue, resuming verification after reboot."""

import os
import argparse
import logging
from pathlib import Path

from cmdb.activity.PatchRunner import PatchRunner
from cmdb.activity.PatchScheduler import PatchScheduler
from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schedule-id', type=int, help='Queue one cron schedule and exit')
    args = parser.parse_args()
    if args.schedule_id is not None and not 0 < args.schedule_id < 2**64:
        parser.error('schedule-id must be a positive database ID')
    try:
        os.environ.update(DatabaseEnvironment.read(Path(DCmdb.DATABASE_ENV)))
        if args.schedule_id is not None:
            PatchScheduler().run(args.schedule_id)
        else:
            PatchRunner().serve()
        return 0
    except Exception:
        logging.exception('Patch runner failed')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
