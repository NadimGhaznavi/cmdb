"""Resolve CMDB connection settings before opening the generic database layer."""

import os

from cmdb.constants.DDbMgr import DDbMgr
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment
from cmdb.interface.DbMgr import DbMgr


def connect_database() -> DbMgr:
    values = {key: os.environ.get(key, '') for key in
              ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')}
    DatabaseEnvironment.validate(values)
    return DbMgr(host=values['DB_HOST'], port=int(values['DB_PORT']),
                 user=values['DB_USER'], password=values['DB_PASSWORD'], database=values['DB_NAME'],
                 connect_timeout=DDbMgr.CONNECT_TIMEOUT, read_timeout=DDbMgr.READ_TIMEOUT,
                 write_timeout=DDbMgr.WRITE_TIMEOUT)
