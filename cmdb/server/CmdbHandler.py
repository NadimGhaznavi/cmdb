"""HTTP endpoints for the CMDB server foundation."""

from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

import pymysql

from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb


STATIC_FILES = {
    "/static/machines.css": ("machines.css", "text/css; charset=utf-8"),
    "/static/machines.js": ("machines.js", "text/javascript; charset=utf-8"),
    "/static/vendor/cytoscape-3.34.3.min.js": (
        "vendor/cytoscape-3.34.3.min.js", "text/javascript; charset=utf-8"),
}


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
        elif path == "/api/machines":
            try:
                db = DbMgr()
                try:
                    machines = MachineDb(db).list_machines()
                finally:
                    db.close()
            except pymysql.MySQLError:
                self.respond(503, b'{"error":"Machines are unavailable."}', "application/json")
                return
            records = []
            for machine in machines:
                record = asdict(machine)
                for field in ("createdOn", "updatedOn"):
                    value = record[field]
                    record[field] = value.replace(tzinfo=timezone.utc).isoformat() if value else None
                records.append(record)
            self.respond(200, json.dumps({"machines": records}).encode("utf-8"), "application/json")
        elif path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]
            self.respond(200, (Path(__file__).parent / "static" / filename).read_bytes(), content_type)
        elif path == "/":
            template = (Path(__file__).parent / "templates" / "home.html").read_text()
            body = template.replace("{{last_refresh}}", datetime.now().strftime("%b %d - %H:%M:%S"))
            self.respond(200, body.encode("utf-8"), "text/html; charset=utf-8")
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
