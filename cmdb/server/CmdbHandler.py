"""HTTP endpoints for the CMDB server foundation."""

from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler
from ipaddress import ip_address
import json
import logging
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import pymysql

from cmdb.constants.DCmdb import DCmdb
from cmdb.constants.DLabel import DLabel
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.BackupDb import BackupDb
from cmdb.interface.BackupFiles import BackupFiles
from cmdb.interface.PatchDb import PatchDb
from cmdb.activity.Scheduler import Scheduler
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb
from cmdb.entity.Machine import Machine


STATIC_FILES = {
    "/static/machines.css": ("machines.css", "text/css; charset=utf-8"),
    "/static/machines.js": ("machines.js", "text/javascript; charset=utf-8"),
    "/static/vendor/cytoscape-3.34.3.min.js": (
        "vendor/cytoscape-3.34.3.min.js", "text/javascript; charset=utf-8"),
}


def backup_json(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()
    raise TypeError(f'Unsupported backup value: {type(value).__name__}')


def machine_record(machine: Machine) -> dict:
    record = asdict(machine)
    for field in ("createdOn", "updatedOn"):
        value = record[field]
        record[field] = value.replace(tzinfo=timezone.utc).isoformat() if value else None
    return record


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
        elif path == "/api/scan":
            scanner = getattr(self.server, "machine_scanner", None)
            if scanner is None or not scanner.is_alive():
                self.respond(503, b'{"error":"Scanner is unavailable."}', "application/json")
                return
            self.respond(200, json.dumps(scanner.scan_status()).encode("utf-8"), "application/json")
        elif path == '/api/patching/hosts':
            try:
                db = DbMgr()
                try:
                    hosts = PatchDb(db).hosts()
                finally:
                    db.close()
            except pymysql.MySQLError:
                self.respond(503, b'{"error":"Debian hosts are unavailable."}', 'application/json')
                return
            self.respond(200, json.dumps({'hosts': hosts}, default=backup_json).encode(), 'application/json')
        elif path == "/api/machines":
            try:
                db = DbMgr()
                try:
                    machines = MachineDb(db).list_machines()
                    deployments = SoftwareDeploymentDb(db).list_deployments()
                finally:
                    db.close()
            except pymysql.MySQLError:
                self.respond(503, b'{"error":"Machines are unavailable."}', "application/json")
                return
            records = [machine_record(machine) for machine in machines]
            self.respond(200, json.dumps({"machines": records, "softwareDeployments": deployments})
                         .encode("utf-8"), "application/json")
        elif path == '/api/backups' or path.startswith('/api/backups/'):
            try:
                db = DbMgr()
                try:
                    backups = BackupDb(db)
                    if path == '/api/backups':
                        result = {'databases': backups.databases(), 'hosts': backups.hosts()}
                    elif path == '/api/backups/files':
                        result = {'files': backups.files(), 'directory': DCmdb.BACKUP_DIR}
                        for record in result['files']:
                            record['filename'] = PurePosixPath(record['pathname']).name
                    else:
                        identity = path.removeprefix('/api/backups/')
                        result = backups.get(int(identity)) if identity.isdecimal() and len(identity) <= 20 and 0 < int(identity) < 2**64 else None
                finally:
                    db.close()
            except pymysql.MySQLError:
                self.respond(503, b'{"error":"Backup records are unavailable."}', 'application/json')
                return
            if result is None:
                self.respond(404, b'{"error":"Backup not found."}', 'application/json')
            else:
                self.respond(200, json.dumps(result, default=backup_json).encode(), 'application/json')
        elif path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]
            self.respond(200, (Path(__file__).parent / "static" / filename).read_bytes(), content_type)
        elif path == "/":
            template = (Path(__file__).parent / "templates" / "home.html").read_text()
            body = template.replace("{{last_refresh}}", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            for attribute, label in DLabel.ATTRIBUTES.items():
                body = body.replace("{{label." + attribute + "}}", escape(label))
            self.respond(200, body.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self.send_error(404, "Page not found")

    def do_POST(self) -> None:
        if urlsplit(self.path).path == '/api/patching':
            self.request_patch()
            return
        if urlsplit(self.path).path == '/api/backups/files/scan':
            self.scan_backup_files()
            return
        if urlsplit(self.path).path == '/api/backup-schedules':
            self.update_schedule()
            return
        if urlsplit(self.path).path == '/api/backups':
            self.request_backup()
            return
        if urlsplit(self.path).path == "/api/scan":
            scanner = getattr(self.server, "machine_scanner", None)
            try:
                if scanner is None:
                    raise RuntimeError("Scanner is unavailable.")
                scan_id = scanner.request_scan()
            except RuntimeError:
                self.respond(503, b'{"error":"Scanner is unavailable."}', "application/json")
                return
            self.respond(202, json.dumps({"scanId": scan_id}).encode("utf-8"), "application/json")
            return
        if urlsplit(self.path).path != "/api/machines/hostname":
            self.send_error(404, "Page not found")
            return
        if self.headers.get_content_type() != "application/json":
            self.respond(415, b'{"error":"Expected JSON."}', "application/json")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError
            values = json.loads(self.rfile.read(length))
            if not isinstance(values, dict) or values.keys() != {"ipAddress", "hostName"}:
                raise ValueError
            address, hostname = values["ipAddress"], values["hostName"]
            if not isinstance(address, str) or not isinstance(hostname, str):
                raise ValueError
            ip_address(address)
            hostname = hostname.strip()
            if len(hostname) > 255:
                raise ValueError
        except (ValueError, UnicodeError):
            self.respond(400, b'{"error":"Provide an IP address and a hostname of at most 255 characters."}',
                         "application/json")
            return
        except TimeoutError:
            self.respond(408, b'{"error":"Request timed out."}', "application/json")
            return
        try:
            db = DbMgr()
            try:
                machine = MachineDb(db).update_hostname(address, hostname or None)
            finally:
                db.close()
        except pymysql.MySQLError:
            self.respond(503, b'{"error":"Could not save the hostname. Try again."}', "application/json")
            return
        if machine is None:
            self.respond(404, b'{"error":"Machine no longer exists."}', "application/json")
            return
        self.respond(200, json.dumps({"machine": machine_record(machine)}).encode("utf-8"), "application/json")

    def request_patch(self) -> None:
        if self.headers.get_content_type() != 'application/json':
            self.respond(415, b'{"error":"Expected JSON."}', 'application/json')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError
            values = json.loads(self.rfile.read(length))
            if (not isinstance(values, dict) or values.keys() != {'machine'}
                    or type(values['machine']) is not int or not 0 < values['machine'] < 2**64):
                raise ValueError
        except (ValueError, UnicodeError):
            self.respond(400, b'{"error":"Provide a valid machine ID."}', 'application/json')
            return
        except TimeoutError:
            self.respond(408, b'{"error":"Request timed out."}', 'application/json')
            return
        try:
            db = DbMgr()
            try:
                identity = PatchDb(db).request(values['machine'])
            finally:
                db.close()
        except LookupError:
            self.respond(404, b'{"error":"Debian host not found."}', 'application/json')
            return
        except pymysql.MySQLError:
            self.respond(503, b'{"error":"Could not queue patch job."}', 'application/json')
            return
        self.respond(202, json.dumps({'jobId': identity}).encode(), 'application/json')

    def request_backup(self) -> None:
        if self.headers.get_content_type() != 'application/json':
            self.respond(415, b'{"error":"Expected JSON."}', 'application/json')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError
            values = json.loads(self.rfile.read(length))
            if (not isinstance(values, dict) or values.keys() != {'modelElement'}
                    or type(values['modelElement']) is not int or not 0 < values['modelElement'] < 2**64):
                raise ValueError
        except (ValueError, UnicodeError):
            self.respond(400, b'{"error":"Provide a valid modelElement ID."}', 'application/json')
            return
        except TimeoutError:
            self.respond(408, b'{"error":"Request timed out."}', 'application/json')
            return
        manager = getattr(self.server, 'backup_manager', None)
        if manager is None:
            self.respond(503, b'{"error":"Backup manager is unavailable."}', 'application/json')
            return
        try:
            identity = manager.request_backup(values['modelElement'])
        except LookupError:
            self.respond(404, b'{"error":"User database not found."}', 'application/json')
            return
        except (RuntimeError, pymysql.MySQLError):
            self.respond(503, b'{"error":"Could not start the backup."}', 'application/json')
            return
        self.respond(202, json.dumps({'backupId': identity}).encode(), 'application/json')

    def update_schedule(self) -> None:
        if self.headers.get_content_type() != 'application/json':
            self.respond(415, b'{"error":"Expected JSON."}', 'application/json')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError
            values = json.loads(self.rfile.read(length))
            if not isinstance(values, dict) or values.keys() != {'modelElement', 'enabled', 'frequency', 'retention'}:
                raise ValueError
            schedule = Scheduler().update(**values)
        except (ValueError, UnicodeError):
            self.respond(400, b'{"error":"Provide valid daily backup settings."}', 'application/json')
            return
        except LookupError:
            self.respond(404, b'{"error":"User database not found."}', 'application/json')
            return
        except (OSError, RuntimeError, pymysql.MySQLError):
            logging.exception('Could not update backup schedule')
            self.respond(503, b'{"error":"Could not save the schedule and cron entry. Check the service log and retry."}', 'application/json')
            return
        self.respond(200, json.dumps({'schedule': schedule}).encode(), 'application/json')

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        if path.startswith('/api/backups/files/'):
            self.delete_backup_record(path.removeprefix('/api/backups/files/'))
            return
        identity = path.removeprefix('/api/backup-schedules/')
        if (not path.startswith('/api/backup-schedules/') or not identity.isdecimal()
                or len(identity) > 20 or not 0 < int(identity) < 2**64):
            self.respond(404, b'{"error":"Schedule not found."}', 'application/json')
            return
        try:
            Scheduler().delete(int(identity))
        except (OSError, RuntimeError, pymysql.MySQLError):
            logging.exception('Could not delete backup schedule')
            self.respond(503, b'{"error":"Could not delete the schedule and cron entry."}', 'application/json')
            return
        self.respond(200, b'{"status":"deleted"}', 'application/json')

    def scan_backup_files(self) -> None:
        try:
            db = DbMgr()
            try:
                records = BackupDb(db).files()
            finally:
                db.close()
            statuses = BackupFiles().scan(records)
            result = [{'id': row['id'], 'status': status} for row, status in zip(records, statuses)]
        except (OSError, ValueError, subprocess.SubprocessError, pymysql.MySQLError):
            logging.exception('Could not scan backup files')
            self.respond(503, b'{"error":"Could not scan the backup directory. Check access and retry."}', 'application/json')
            return
        self.respond(200, json.dumps({'files': result}).encode(), 'application/json')

    def delete_backup_record(self, identity: str) -> None:
        if not identity.isdecimal() or len(identity) > 20 or not 0 < int(identity) < 2**64:
            self.respond(404, b'{"error":"Backup not found."}', 'application/json')
            return
        try:
            db = DbMgr()
            try:
                backups = BackupDb(db)
                record = backups.get(int(identity))
                if record is None or record['status'] != 'succeeded':
                    self.respond(404, b'{"error":"Backup file record not found."}', 'application/json')
                    return
                if BackupFiles().scan([record]) != ['Missing']:
                    self.respond(409, b'{"error":"The backup file exists. Its record was kept."}', 'application/json')
                    return
                backups.delete(int(identity))
            finally:
                db.close()
        except (OSError, ValueError, subprocess.SubprocessError, pymysql.MySQLError):
            logging.exception('Could not delete missing backup record')
            self.respond(503, b'{"error":"Could not check the file or delete its record. Try again."}', 'application/json')
            return
        self.respond(200, b'{"status":"deleted"}', 'application/json')

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
