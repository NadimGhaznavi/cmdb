"""Persist the adopted CWM ownership hierarchy."""

from cmdb.interface.DbMgr import DbMgr


class NamespaceDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def create(self, namespace: int | None = None, *, name: str | None = None) -> int:
        """Allocate a shared identity in the caller's transaction."""
        identity = self._db.insert("INSERT INTO ModelElement (namespace, name) VALUES (%s, %s)",
                                   (namespace, name))
        self._db.execute("INSERT INTO Namespace (id) VALUES (%s)", (identity,))
        return identity

    def create_package(self, namespace: int | None = None, *, name: str | None = None) -> int:
        """Allocate a Package and its ancestors within the caller's transaction."""
        identity = self.create(namespace, name=name)
        self._db.execute("INSERT INTO Package (id) VALUES (%s)", (identity,))
        return identity
