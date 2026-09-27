"""Database mechanics without a running MariaDB server."""

import os
import unittest
from unittest.mock import patch

import pymysql

from cmdb.interface.DbMgr import DbMgr


class DbMgrTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {
            "DB_HOST": "localhost", "DB_USER": "cmdb", "DB_PASSWORD": "test",
            "DB_NAME": "cmdb",
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        connector = patch("cmdb.interface.DbMgr.pymysql.connect")
        self.connect = connector.start()
        self.addCleanup(connector.stop)
        self.connection = self.connect.return_value
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.db = DbMgr()
        self.addCleanup(self.db.close)

    def test_connection_has_no_schema_side_effects(self):
        options = self.connect.call_args.kwargs
        self.assertEqual(options["port"], 3306)
        self.assertEqual(options["init_command"], "SET time_zone = '+00:00'")
        self.assertTrue(options["autocommit"])
        self.assertEqual(options["charset"], "utf8mb4")
        self.connection.cursor.assert_not_called()

    def test_parameters_remain_bound_and_results_are_materialized(self):
        value = "quote'; DROP TABLE pages; --"
        self.cursor.execute.return_value = 1
        self.cursor.lastrowid = 42
        self.assertEqual(self.db.insert("INSERT INTO example(value) VALUES (%s)", (value,)), 42)
        self.cursor.execute.assert_called_once_with("INSERT INTO example(value) VALUES (%s)", (value,))
        self.cursor.fetchall.return_value = ({"value": value},)
        self.assertEqual(self.db.query("SELECT value FROM example"), [{"value": value}])
        self.assertEqual(self.connection.cursor.return_value.__exit__.call_count, 2)

    def test_success_commits_and_failure_rolls_back(self):
        with self.db.transaction():
            self.db.execute("SELECT 1")
        self.connection.commit.assert_called_once()
        self.connection.rollback.assert_not_called()
        error = pymysql.IntegrityError(1062, "duplicate")
        with self.assertRaises(pymysql.IntegrityError) as raised:
            with self.db.transaction():
                raise error
        self.assertIs(raised.exception, error)
        self.connection.rollback.assert_called_once()
        self.assertEqual(self.connection.commit.call_count, 1)

    def test_failed_commit_rolls_back(self):
        error = pymysql.OperationalError(2013, "connection lost")
        self.connection.commit.side_effect = error
        with self.assertRaises(pymysql.OperationalError) as raised:
            with self.db.transaction():
                pass
        self.assertIs(raised.exception, error)
        self.connection.rollback.assert_called_once()

    def test_cancellation_rolls_back_and_cursor_errors_propagate(self):
        with self.assertRaises(KeyboardInterrupt):
            with self.db.transaction():
                raise KeyboardInterrupt()
        self.connection.rollback.assert_called_once()
        error = pymysql.ProgrammingError(1064, "invalid query")
        self.cursor.execute.side_effect = error
        with self.assertRaises(pymysql.ProgrammingError) as raised:
            self.db.query("invalid query")
        self.assertIs(raised.exception, error)
        self.connection.cursor.return_value.__exit__.assert_called_once()

    def test_read_only_transaction(self):
        with self.db.transaction(read_only=True):
            pass
        self.cursor.execute.assert_called_once_with("START TRANSACTION READ ONLY", ())
        self.connection.begin.assert_not_called()
        self.connection.commit.assert_called_once()

    def test_failed_rollback_preserves_original_error(self):
        error = pymysql.OperationalError(2013, "connection lost")
        self.connection.rollback.side_effect = pymysql.InterfaceError(0, "closed connection")
        with self.assertRaises(pymysql.OperationalError) as raised:
            with self.db.transaction():
                raise error
        self.assertIs(raised.exception, error)
        self.assertIn("rollback also failed", error.__notes__[0])

    def test_close_releases_connection(self):
        self.db.close()
        self.connection.close.assert_called_once()

    def test_invalid_port_does_not_connect(self):
        self.connect.reset_mock()
        for value in ("0", "65536", "invalid"):
            with self.subTest(port=value), patch.dict(os.environ, {"DB_PORT": value}):
                with self.assertRaises(ValueError):
                    DbMgr()
        self.connect.assert_not_called()

