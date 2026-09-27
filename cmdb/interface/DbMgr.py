"""MariaDB connection, query, and transaction mechanics."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
import os
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from cmdb.constants.DDbMgr import DDbMgr


class DbMgr:
    """Own one connection; do not share an instance between worker threads."""

    def __init__(self) -> None:
        try:
            port = int(os.environ.get("DB_PORT", DDbMgr.PORT))
        except ValueError as error:
            raise ValueError("DB_PORT must be an integer between 1 and 65535.") from error
        if not 1 <= port <= 65535:
            raise ValueError("DB_PORT must be between 1 and 65535.")
        self._connection = pymysql.connect(
            host=os.environ["DB_HOST"],
            port=port,
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.environ["DB_NAME"],
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,
            connect_timeout=DDbMgr.CONNECT_TIMEOUT,
            read_timeout=DDbMgr.READ_TIMEOUT,
            write_timeout=DDbMgr.WRITE_TIMEOUT,
            init_command="SET time_zone = '+00:00'",
        )

    def execute(self, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> int:
        """Execute bound SQL and return the affected row count."""
        with self._connection.cursor() as cursor:
            return cursor.execute(sql, params)

    def insert(self, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> int:
        """Insert a record and return its generated ID."""
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid

    def execute_many(self, sql: str, rows: Sequence[Sequence[Any]]) -> int:
        """Execute a batch with bound parameters and return the affected count."""
        with self._connection.cursor() as cursor:
            return cursor.executemany(sql, rows)

    def query(self, sql: str, params: Sequence[Any] | Mapping[str, Any] = ()) -> list[dict[str, Any]]:
        """Return materialized rows; cursors never escape this interface."""
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())

    @contextmanager
    def transaction(self, *, read_only: bool = False) -> Iterator[None]:
        """Commit on success, roll back on failure. Do not nest or execute DDL."""
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
                error.add_note("Database rollback also failed; discard this connection.")
            raise

    def close(self) -> None:
        self._connection.close()
