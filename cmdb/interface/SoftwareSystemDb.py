"""Persist manually maintained software definitions."""

from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.NamespaceDb import NamespaceDb


class SoftwareSystemDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def create_application(self, name: str) -> int:
        """Create a named SoftwareSystem in the caller's transaction."""
        identity = NamespaceDb(self._db).create_package(name=name)
        self._db.execute('INSERT INTO SoftwareSystem (id) VALUES (%s)', (identity,))
        return identity
