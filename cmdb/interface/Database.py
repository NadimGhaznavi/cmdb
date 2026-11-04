"""Resolve CMDB connection settings before opening the generic database layer."""

import os

from cmdb.constants.DDbMgr import DDbMgr
from cmdb.interface.DbMgr import DbMgr


def connect_database() -> DbMgr:
    return DbMgr(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
                 user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'], database=os.environ['DB_NAME'],
                 connect_timeout=DDbMgr.CONNECT_TIMEOUT, read_timeout=DDbMgr.READ_TIMEOUT,
                 write_timeout=DDbMgr.WRITE_TIMEOUT)
