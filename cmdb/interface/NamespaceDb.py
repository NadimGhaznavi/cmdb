"""Persist the adopted CWM ownership hierarchy."""

from cmdb.interface.DbMgr import DbMgr


class NamespaceDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def create(self, namespace: int | None = None) -> int:
        """Allocate a shared identity in the caller's transaction."""
        identity = self._db.insert("INSERT INTO ModelElement (namespace) VALUES (%s)", (namespace,))
        self._db.execute("INSERT INTO Namespace (id) VALUES (%s)", (identity,))
        return identity
