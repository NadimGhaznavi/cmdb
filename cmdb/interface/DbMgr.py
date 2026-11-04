"""Application-independent MariaDB connection, SQL, and transaction mechanics."""

from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor


BMFORGE_COMPONENT = {"id": "bmforge.db-server", "spec_version": "0.5.0"}


class DbMgr:
    """Own one connection in the worker that opens it; never share across threads."""

    def __init__(self, *, host, port, user, password, database, unix_socket=None,
                 connect_timeout=10, read_timeout=30, write_timeout=30):
        # The application resolves configuration before constructing this interface.
        self._connection = pymysql.connect(
            host=host, port=port, user=user, password=password, database=database,
            unix_socket=unix_socket, charset="utf8mb4",
            collation="utf8mb4_unicode_ci", cursorclass=DictCursor,
            autocommit=True, connect_timeout=connect_timeout,
            read_timeout=read_timeout, write_timeout=write_timeout,
            sql_mode="STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION",
            init_command="SET time_zone = '+00:00'",
        )

    def execute(self, sql, params=()):
        with self._connection.cursor() as cursor:
            return cursor.execute(sql, params)

    def insert(self, sql, params=()):
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid

    def execute_many(self, sql, rows):
        with self._connection.cursor() as cursor:
            return cursor.executemany(sql, rows)

    def query(self, sql, params=()):
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    @contextmanager
    def transaction(self, *, read_only=False):
        """Commit related statements on success, roll back on error; no nesting/DDL."""
        if read_only:
            self.execute("START TRANSACTION READ ONLY")
        else:
            self._connection.begin()
        try:
            yield
            self._connection.commit()
        except BaseException as error:
            try:
                self._connection.rollback()
            except BaseException:
                error.add_note("Rollback also failed; discard this connection.")
            raise

    def health(self):
        """Probe through this application's connection, not a CMDB connection."""
        return self.query("SELECT 1 AS ok")[0]["ok"] == 1

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
