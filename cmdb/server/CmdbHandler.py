"""HTTP endpoints for the CMDB server foundation."""

from http.server import BaseHTTPRequestHandler
import logging
from pathlib import Path
from urllib.parse import urlsplit

import pymysql

from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DbMgr import DbMgr


class CmdbHandler(BaseHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(DCmdb.REQUEST_TIMEOUT)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self.respond(200, b'{"status":"ok","service":"cmdb-server"}', "application/json")
        elif path == "/ready":
            try:
                db = DbMgr()
                try:
                    db.query("SELECT 1 AS ready")
                finally:
                    db.close()
            except pymysql.MySQLError:
                logging.exception("CMDB database readiness check failed")
                self.respond(503, b'{"status":"unavailable","service":"cmdb-server"}', "application/json")
                return
            self.respond(200, b'{"status":"ready","service":"cmdb-server"}', "application/json")
        elif path == "/":
            self.respond(200, (Path(__file__).parent / "templates" / "home.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self.send_error(404, "Page not found")

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
