#!/usr/bin/env python3
"""Run one scheduled discovery independently of the CMDB web service."""

import argparse
import logging
import os
from pathlib import Path

from cmdb.activity.DiscoveryScheduler import DiscoveryScheduler
from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schedule-id', type=int, required=True)
    args = parser.parse_args()
    if not 0 < args.schedule_id < 2**64:
        parser.error('schedule-id must be a positive database ID')
    try:
        os.environ.update(DatabaseEnvironment.read(Path(DCMDB.DATABASE_ENV)))
        return 0 if DiscoveryScheduler().run(args.schedule_id) else 1
    except Exception:
        logging.exception('Scheduled discovery %s failed', args.schedule_id)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
