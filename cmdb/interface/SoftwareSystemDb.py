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

    def list_applications(self) -> list[dict]:
        """Named definitions created by Add Application are discovery targets."""
        return self._db.query(
            'SELECT MIN(ss.id) AS id, me.name FROM SoftwareSystem ss '
            'JOIN ModelElement me ON me.id = ss.id '
            'WHERE me.name IS NOT NULL AND ss.type IS NULL GROUP BY me.name ORDER BY id')

    def list_software_systems(self) -> list[dict]:
        """Return every registered SoftwareSystem, including undeployed definitions."""
        return self._db.query(
            'SELECT ss.id, me.name, ss.type, ss.subtype, ss.supplier, ss.version '
            'FROM SoftwareSystem ss JOIN ModelElement me ON me.id = ss.id '
            'ORDER BY me.name, ss.subtype, ss.id')
