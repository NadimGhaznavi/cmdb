"""Fresh-schema integration checks against an explicitly supplied test MariaDB socket."""

import os
import hashlib
import shlex
import subprocess
from tempfile import TemporaryDirectory
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import pymysql

from cmdb.entity.Machine import Machine
from cmdb.entity.Backup import Backup
from cmdb.interface.BackupDb import BackupDb
from cmdb.activity.Scheduler import Scheduler
from crontab import CronTab
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.DataManagerDb import DataManagerDb
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.NamespaceDb import NamespaceDb
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb
from cmdb.interface.HostOperatingSystem import operating_system


@unittest.skipUnless(os.environ.get("CMDB_TEST_DB_SOCKET"), "Set CMDB_TEST_DB_SOCKET for database checks")
class SoftwareDeploymentDbTests(unittest.TestCase):
    def setUp(self):
        self.db = DbMgr.__new__(DbMgr)
        self.db._connection = pymysql.connect(
            unix_socket=os.environ["CMDB_TEST_DB_SOCKET"], user="root", autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
        self.addCleanup(self.db.close)
        self.database = "cmdb_test_" + uuid4().hex
        self.db.execute(f"CREATE DATABASE `{self.database}`")
        self.addCleanup(self.db.execute, f"DROP DATABASE `{self.database}`")
        self.db.execute(f"USE `{self.database}`")
        schema = Path(__file__).resolve().parents[1] / "schema/cmdb-schema-v1.sql"
        for statement in schema.read_text().split(';'):
            if statement.strip():
                self.db.execute(statement)
        self.machines = MachineDb(self.db)
        self.software = SoftwareDeploymentDb(self.db)

    def record(self, machine, version="6.X"):
        with self.db.transaction():
            self.software.record_operating_system(machine, SoftwareSystem(
                type="OS", subtype="Linux", supplier="Linux", version=version))

    def inventory(self):
        return self.db.query(
            "SELECT dc.id, dc.machine, dc.pathname, dc.component, "
            "ss.id AS softwareSystem, ss.type, ss.subtype, ss.supplier, ss.version "
            "FROM DeployedComponent dc "
            "JOIN Component c ON c.id = dc.component "
            "JOIN ModelElement me ON me.id = c.id "
            "JOIN SoftwareSystem ss ON ss.id = me.namespace ORDER BY dc.machine")

    def test_debian_patch_queue_and_reboot_records(self):
        from cmdb.interface.PatchDb import PatchDb
        debian = self.machines.upsert(Machine('192.0.2.80', hostName='debian.example'))
        other = self.machines.upsert(Machine('192.0.2.81', hostName='ubuntu.example'))
        self.software.record_operating_system(debian, operating_system('ID=debian\nVERSION_ID=13'))
        self.software.record_operating_system(other, operating_system('ID=ubuntu\nVERSION_ID=24'))
        records = PatchDb(self.db)
        self.assertEqual([host['id'] for host in records.hosts()], [debian])
        with self.assertRaises(LookupError):
            records.request(other)
        identity = records.request(debian)
        self.assertEqual(records.request(debian), identity)
        records.start(identity, '11111111-1111-1111-1111-111111111111')
        records.rebooting(identity, '0 upgraded')
        self.assertEqual(records.next()['status'], 'rebooting')
        records.finish(identity)
        self.assertIsNone(records.next())
        self.assertEqual(records.hosts()[0]['job']['status'], 'succeeded')
        self.assertNotEqual(records.request(debian), identity)

    def test_discovery_populates_relationships_and_repeat_scans_reuse_records(self):
        machine = self.machines.upsert(Machine("192.168.0.7", hostName="worker"))
        self.record(machine)
        first = self.inventory()
        self.record(machine)
        self.assertEqual(self.inventory(), first)
        self.assertEqual(first[0]["pathname"], "/")
        self.assertEqual(first[0]["type"], "OS")
        self.assertEqual(first[0]["version"], "6.X")
        self.assertEqual(self.machines.list_machines()[0].deployedComponent, [first[0]["id"]])
        for table in ("SoftwareSystem", "Component", "DeployedComponent"):
            self.assertEqual(self.db.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"], 1)

    def test_shared_definition_has_separate_deployments_and_updates_only_one_machine(self):
        a = self.machines.upsert(Machine("192.168.0.7"))
        b = self.machines.upsert(Machine("192.168.0.8"))
        self.record(a)
        self.record(b)
        old = self.inventory()
        self.assertEqual(old[0]["softwareSystem"], old[1]["softwareSystem"])
        self.assertEqual(old[0]["component"], old[1]["component"])
        self.assertNotEqual(old[0]["id"], old[1]["id"])
        self.record(a, version="7.X")
        new = self.inventory()
        self.assertEqual(new[0]["version"], "7.X")
        self.assertEqual(new[0]["id"], old[0]["id"])
        self.assertEqual(new[1], old[1])

    def test_machine_id_and_manual_values_survive_scans_and_ip_changes(self):
        machine = self.machines.upsert(Machine("192.168.0.7", macAddress="00:11:22:33:44:55"))
        self.machines.update_hostname("192.168.0.7", "edited")
        self.record(machine)
        self.assertEqual(self.machines.upsert(Machine("192.168.0.7")), machine)
        self.db.execute("UPDATE Machine SET ipAddress = %s WHERE id = %s", ("192.168.0.8", machine))
        self.assertEqual(self.machines.upsert(Machine("192.168.0.8")), machine)
        stored = self.machines.list_machines()[0]
        self.assertEqual(stored.hostName, "edited")
        self.assertEqual(stored.macAddress, "00:11:22:33:44:55")
        self.assertEqual(self.inventory()[0]["machine"], machine)

    def test_host_release_replaces_fingerprint_and_reuses_deployment(self):
        machine = self.machines.upsert(Machine("192.168.0.7"))
        self.record(machine)
        deployment = self.inventory()[0]["id"]
        for _ in range(2):
            with self.db.transaction():
                self.software.record_operating_system(machine, operating_system(
                    'ID=debian\nVERSION_ID=13\n'))
            rows = self.inventory()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], deployment)
            self.assertEqual(rows[0]["subtype"], "debian")
            self.assertEqual(rows[0]["version"], "13")
            self.assertEqual(rows[0]["supplier"], "Debian")
        self.assertEqual(self.db.query("SELECT COUNT(*) AS n FROM SoftwareSystem")[0]["n"], 2)

    def test_ssh_hostname_updates_only_the_identified_machine(self):
        first = self.machines.upsert(Machine("192.168.0.7", hostName="old"))
        second = self.machines.upsert(Machine("192.168.0.8", hostName="other"))
        original = self.machines.list_machines()[0]
        with self.db.transaction():
            self.machines.update_discovered_hostname(first, "reported.example.lan")
            self.machines.update_discovered_mac(first, "AA:BB:CC:DD:EE:FF")
        stored = {machine.id: machine for machine in self.machines.list_machines()}
        self.assertEqual(stored[first].hostName, "reported.example.lan")
        self.assertEqual(stored[first].createdOn, original.createdOn)
        self.assertEqual(stored[second].hostName, "other")
        self.assertEqual(stored[first].macAddress, "AA:BB:CC:DD:EE:FF")
        self.assertIsNone(stored[second].macAddress)

    def test_codename_belongs_to_shared_system_and_conflicts_do_not_mutate_it(self):
        first = self.machines.upsert(Machine("192.168.0.7"))
        second = self.machines.upsert(Machine("192.168.0.8"))
        release = 'ID=debian\nDEBIAN_VERSION_FULL=13.6\nVERSION_CODENAME=trixie\n'
        for machine in (first, second, first):
            with self.db.transaction():
                self.software.record_operating_system(machine, operating_system(release))
        old = self.inventory()
        self.assertEqual(old[0]["softwareSystem"], old[1]["softwareSystem"])
        tags = self.db.query("SELECT tag, value, modelElement FROM TaggedValue")
        self.assertEqual(tags, [{"tag": "VERSION_CODENAME", "value": "trixie",
                                 "modelElement": old[0]["softwareSystem"]}])
        projected = self.software.list_deployments()
        self.assertEqual([row["machine"] for row in projected], [first, second])
        self.assertTrue(all(row["codename"] == "trixie" and row["subtype"] == "debian"
                            and row["version"] == "13.6" for row in projected))
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute("INSERT INTO TaggedValue (tag, value, modelElement) VALUES (%s, %s, %s)",
                            ("VERSION_CODENAME", "duplicate", old[0]["softwareSystem"]))
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute("INSERT INTO TaggedValue (tag, value, modelElement) VALUES (%s, %s, %s)",
                            ("VERSION_CODENAME", "trixie", 999999))
        with self.db.transaction():
            self.software.record_operating_system(first, operating_system(release.replace('trixie', 'other')))
        new = self.inventory()
        self.assertEqual(new[0]["id"], old[0]["id"])
        self.assertNotEqual(new[0]["softwareSystem"], old[0]["softwareSystem"])
        self.assertEqual(new[1], old[1])

    def test_foreign_keys_and_rollback_prevent_partial_os_records(self):
        with self.assertRaises(pymysql.IntegrityError):
            self.record(999999)
        for table in ("ModelElement", "Namespace", "SoftwareSystem", "Component", "DeployedComponent"):
            self.assertEqual(self.db.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"], 0)
        machine = self.machines.upsert(Machine("192.168.0.7"))
        with self.assertRaises(pymysql.IntegrityError):
            with self.db.transaction():
                identity = NamespaceDb(self.db).create_package(namespace=machine)
                self.db.execute("INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)",
                                (identity, "/", machine, 999999))

    def test_ownership_is_on_parent_and_supports_multiple_components(self):
        machine = self.machines.upsert(Machine("192.168.0.7"))
        self.record(machine)
        first = self.inventory()[0]
        namespaces = NamespaceDb(self.db)
        with self.db.transaction():
            component = namespaces.create(namespace=first["softwareSystem"])
            self.db.execute("INSERT INTO Component (id) VALUES (%s)", (component,))
            deployment = namespaces.create_package(namespace=machine)
            self.db.execute(
                "INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)",
                (deployment, "/boot", machine, component))
        self.assertEqual(len(self.inventory()), 2)
        stored = self.machines.list_machines()[0]
        self.assertEqual(stored.ownedElement, stored.deployedComponent)
        self.assertEqual(len(stored.deployedComponent), 2)
        with self.db.transaction():
            standalone = namespaces.create()
            self.db.execute("INSERT INTO Component (id) VALUES (%s)", (standalone,))
        self.assertIsNone(self.db.query("SELECT namespace FROM ModelElement WHERE id=%s", (standalone,))[0]["namespace"])
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute("UPDATE ModelElement SET namespace=%s WHERE id=%s", (999999, standalone))

    def test_deployment_owner_must_match_on_insert_and_updates_to_either_table(self):
        machine = self.machines.upsert(Machine("192.168.0.7"))
        other_machine = self.machines.upsert(Machine("192.168.0.8"))
        self.record(machine)
        deployment = self.inventory()[0]
        for owner in (None, other_machine):
            with self.subTest(owner=owner), self.assertRaises(pymysql.IntegrityError):
                with self.db.transaction():
                    identity = NamespaceDb(self.db).create_package(namespace=owner)
                    self.db.execute(
                        "INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)",
                        (identity, "/invalid", machine, deployment["component"]),
                    )
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute("UPDATE DeployedComponent SET machine=%s WHERE id=%s",
                            (other_machine, deployment["id"]))
        for owner in (None, other_machine):
            with self.subTest(owner=owner), self.assertRaises(pymysql.IntegrityError):
                self.db.execute("UPDATE ModelElement SET namespace=%s WHERE id=%s",
                                (owner, deployment["id"]))
        self.assertEqual(self.inventory(), [deployment])
        self.assertEqual(self.db.query("SELECT namespace FROM ModelElement WHERE id=%s",
                                       (deployment["id"],))[0]["namespace"], machine)

    def test_matching_owner_must_still_be_a_machine(self):
        machine = self.machines.upsert(Machine("192.168.0.7"))
        self.record(machine)
        deployment = self.inventory()[0]
        with self.assertRaises(pymysql.IntegrityError):
            with self.db.transaction():
                identity = NamespaceDb(self.db).create_package(namespace=deployment["softwareSystem"])
                self.db.execute(
                    "INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)",
                    (identity, "/invalid", deployment["softwareSystem"], deployment["component"]),
                )

    def test_schema_uses_exact_class_names_and_keeps_inherited_fields_on_parents(self):
        tables = {next(iter(row.values())) for row in self.db.query("SHOW TABLES")}
        self.assertEqual(tables, {"Patch", "Backup", "BackupSchedule", "Package", "Schema", "DataManager", "DataManagerDataPackage", "TaggedValue", "ModelElement", "Namespace", "Machine", "SoftwareSystem", "Component", "DeployedComponent"})
        self.assertIn('name', {row['Field'] for row in self.db.query('SHOW COLUMNS FROM ModelElement')})
        for table in ("Package", "Schema", "DataManager", "Component", "SoftwareSystem", "Machine", "DeployedComponent"):
            columns = {row["Field"] for row in self.db.query(f"SHOW COLUMNS FROM `{table}`")}
            self.assertNotIn("namespace", columns)
            self.assertNotIn("ownedElement", columns)
            self.assertNotIn("name", columns)

    def test_backup_schedule_references_databases_and_deployments_with_independent_identity(self):
        machine = self.machines.upsert(Machine('192.168.0.7'))
        manager = DataManagerDb(self.db).record_mariadb(machine, '11.8.3', '/data/', ['cmdb'])
        schema = self.db.query('SELECT id FROM `Schema`')[0]['id']
        for target in (schema, manager):
            self.db.execute('INSERT INTO BackupSchedule (modelElement) VALUES (%s)', (target,))
        rows = self.db.query('SELECT * FROM BackupSchedule ORDER BY id')
        self.assertEqual([row['modelElement'] for row in rows], [schema, manager])
        for row in rows:
            self.assertEqual((row['enabled'], row['frequency'], row['retention']), (0, 'daily', '1-week'))
        for retention in ('1-week', '2-weeks', '1-month', 'forever'):
            self.db.execute('UPDATE BackupSchedule SET enabled=1, retention=%s WHERE modelElement=%s',
                            (retention, schema))
            stored = self.db.query('SELECT enabled, retention FROM BackupSchedule WHERE modelElement=%s', (schema,))[0]
            self.assertEqual(stored, {'enabled': 1, 'retention': retention})
        for target in (schema, 999999):
            with self.assertRaises(pymysql.IntegrityError):
                self.db.execute('INSERT INTO BackupSchedule (modelElement) VALUES (%s)', (target,))
        target = NamespaceDb(self.db).create(name='backup target')
        self.db.execute('INSERT INTO BackupSchedule (modelElement) VALUES (%s)', (target,))
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute('DELETE FROM ModelElement WHERE id=%s', (target,))

    def test_backup_attempts_preserve_history_independently_of_schedule(self):
        target = NamespaceDb(self.db).create(name='cmdb')
        started = datetime(2026, 9, 28, 13, 29)
        completed = datetime(2026, 9, 28, 13, 30)
        identity = self.db.insert('INSERT INTO Backup (modelElement, startedOn) VALUES (%s, %s)',
                                  (target, started))
        running = Backup(**self.db.query('SELECT * FROM Backup WHERE id=%s', (identity,))[0])
        self.assertEqual(running, Backup(modelElement=target, startedOn=started, id=identity))
        self.db.execute('UPDATE Backup SET status=%s, completedOn=%s, pathname=%s, sizeBytes=%s, '
                        'checksum=%s WHERE id=%s',
                        ('succeeded', completed, 'sally/cmdb/example.dump', 123, 'a' * 64, identity))
        success = Backup(**self.db.query('SELECT * FROM Backup WHERE id=%s', (identity,))[0])
        self.assertEqual((success.status, success.sizeBytes, success.checksum), ('succeeded', 123, 'a' * 64))
        self.db.execute('INSERT INTO Backup (modelElement, startedOn, completedOn, status, error) '
                        'VALUES (%s, %s, %s, %s, %s)', (target, completed, completed, 'failed', 'Dump failed'))
        self.db.execute('INSERT INTO BackupSchedule (modelElement) VALUES (%s)', (target,))
        self.db.execute('DELETE FROM BackupSchedule WHERE modelElement=%s', (target,))
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM Backup')[0]['n'], 2)
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute('DELETE FROM ModelElement WHERE id=%s', (target,))
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute('INSERT INTO Backup (modelElement, startedOn) VALUES (%s, %s)', (999999, started))

    def test_backup_rejects_inconsistent_results_and_invalid_checksums(self):
        target = NamespaceDb(self.db).create(name='cmdb')
        started = datetime(2026, 9, 28, 13, 29)
        valid = dict(modelElement=target, startedOn=started, completedOn=started,
                     status='succeeded', pathname='sally/cmdb/example.dump', sizeBytes=123,
                     checksum='0123456789abcdef' * 4, error=None)
        for field, value in (('status', 'unknown'), ('status', 'running'), ('completedOn', None),
                             ('completedOn', datetime(2026, 9, 27)), ('pathname', None),
                             ('pathname', ''), ('sizeBytes', None), ('sizeBytes', -1),
                             ('checksum', None), ('checksum', 'a' * 63), ('checksum', 'g' * 64),
                             ('checksum', 'a' * 63 + '\n'), ('error', 'Unexpected error')):
            values = valid | {field: value}
            with self.subTest(field=field, value=value), self.assertRaises(pymysql.MySQLError):
                self.db.execute('INSERT INTO Backup (modelElement, startedOn, completedOn, status, '
                                'pathname, sizeBytes, checksum, error) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                                tuple(values.values()))

    def test_host_dump_restores_real_mariadb_data_and_checksum(self):
        self.db.execute('CREATE TABLE backup_payload (id INT PRIMARY KEY, value TEXT)')
        self.db.execute('INSERT INTO backup_payload VALUES (%s, %s)', (1, 'A quoted \' value'))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / 'bin'
            binaries.mkdir()
            # Only socket routing is a fixture; dump and restore are real.
            fixtures = {
                'mariadb-dump': '#!/bin/sh\nshift\nexec /usr/bin/mariadb-dump --no-defaults --socket='
                    + shlex.quote(os.environ['CMDB_TEST_DB_SOCKET']) + ' "$@"\n',
            }
            for name, contents in fixtures.items():
                path = binaries / name
                path.write_text(contents)
                path.chmod(0o755)
            script = Path(__file__).resolve().parents[1] / 'cmdb/interface/scripts/backup-db.sh'
            result = subprocess.run(['sh', str(script), directory, f'host/db/{self.database}/real.dump', self.database, 'root'],
                                    env=dict(os.environ, PATH=str(binaries) + ':' + os.environ['PATH']),
                                    text=True, capture_output=True, check=True)
            dump = (root / f'host/db/{self.database}/real.dump').read_bytes()
            self.assertEqual(result.stdout.split(), [str(len(dump)), hashlib.sha256(dump).hexdigest()])
            self.db.execute('DELETE FROM backup_payload')
            subprocess.run(['/usr/bin/mariadb', '--no-defaults', '--socket=' + os.environ['CMDB_TEST_DB_SOCKET'],
                            '--user=root'], input=dump, capture_output=True, check=True)
            self.assertEqual(self.db.query('SELECT * FROM backup_payload'), [{'id': 1, 'value': 'A quoted \' value'}])

    def test_backup_inventory_and_last_success_survive_later_failure(self):
        machine = self.machines.upsert(Machine('192.0.2.7', hostName='host'))
        DataManagerDb(self.db).record_mariadb(machine, '11.8.3', '/data/', ['cmdb', 'mysql', 'sys'])
        backups = BackupDb(self.db)
        items = backups.databases()
        self.assertEqual([row['databaseName'] for row in items], ['cmdb'])
        target = items[0]['modelElement']
        started = datetime(2026, 9, 28, 12)
        identity = backups.start(target, started)
        backups.finish(identity, started, result=dict(pathname='host/db/test.dump', sizeBytes=1, checksum='a' * 64))
        failed = backups.start(target, started)
        backups.finish(failed, started, error='Dump failed')
        row = backups.databases()[0]
        self.assertEqual(row['lastBackup'], started)
        self.assertEqual(row['latestBackup'], failed)
        running = backups.start(target, started)
        self.assertEqual(backups.get(running)['status'], 'running')
        self.assertEqual(backups.get(identity)['status'], 'succeeded')
        backups.delete(identity)
        self.assertIsNone(backups.get(identity))
        self.assertEqual(backups.files(), [])
        self.assertIsNone(backups.databases()[0]['lastBackup'])
        backups.delete(running)
        self.assertEqual(backups.get(running)['status'], 'running')

    def test_cron_policy_and_independent_runner_persist_outcomes_without_web_service(self):
        machine = self.machines.upsert(Machine('192.0.2.7', hostName='sally.example'))
        DataManagerDb(self.db).record_mariadb(machine, '11.8.3', '/data/', ['cmdb'])
        target = BackupDb(self.db).databases()[0]['modelElement']
        def connection():
            db = DbMgr.__new__(DbMgr)
            db._connection = pymysql.connect(unix_socket=os.environ['CMDB_TEST_DB_SOCKET'],
                user='root', database=self.database, autocommit=True, cursorclass=pymysql.cursors.DictCursor)
            return db
        tab = CronTab(tab='15 4 * * * /bin/true # unrelated\n')
        with patch('cmdb.activity.Scheduler.DbMgr', side_effect=connection), \
                patch('cmdb.activity.BackupManager.DbMgr', side_effect=connection), \
                patch('cmdb.interface.Cron.CronTab', return_value=tab), \
                patch('cmdb.activity.BackupManager.SSHDb') as remote:
            scheduler = Scheduler()
            schedule = scheduler.update(target, True, 'daily', '2-weeks')
            self.assertEqual(BackupDb(self.db).databases()[0]['retention'], '2-weeks')
            same = scheduler.update(target, True, 'daily', 'forever')
            self.assertEqual(schedule['id'], same['id'])
            self.assertEqual(len(list(tab.find_comment('cmdb-backup-schedule-' + str(schedule['id'])))), 1)
            existing = BackupDb(self.db).start(target, datetime(2026, 9, 28))
            remote.return_value.backup_db.return_value = dict(pathname='sally/db/test.dump', sizeBytes=42, checksum='a' * 64)
            self.assertTrue(scheduler.run(schedule['id']))
            self.assertEqual(BackupDb(self.db).get(existing)['status'], 'running')
            stored = self.db.query("SELECT * FROM Backup WHERE status='succeeded'")[0]
            self.assertEqual((stored['modelElement'], stored['sizeBytes']), (target, 42))
            remote.return_value.backup_db.side_effect = subprocess.CalledProcessError(1, 'dump', stderr='Permission denied')
            self.assertFalse(scheduler.run(schedule['id']))
            self.assertEqual(self.db.query("SELECT error FROM Backup WHERE status='failed'")[0]['error'], 'Permission denied')
            scheduler.update(target, False, 'daily', 'forever')
            self.assertEqual(len(tab), 1)
            remote.reset_mock()
            self.assertTrue(scheduler.run(schedule['id']))
            remote.assert_not_called()
            scheduler.delete(schedule['id'])
            self.assertTrue(scheduler.run(schedule['id']))
            self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM Backup')[0]['n'], 3)

    def test_backup_files_include_only_successes_in_completion_order(self):
        machine = self.machines.upsert(Machine('192.0.2.7', hostName='sally.example'))
        DataManagerDb(self.db).record_mariadb(machine, '11.8.3', '/data/', ['cmdb'])
        backups = BackupDb(self.db)
        target = backups.databases()[0]['modelElement']
        self.assertEqual(backups.files(), [])
        earlier, later = datetime(2026, 9, 28, 12), datetime(2026, 9, 28, 13)
        identities = []
        for completed in (later, earlier, later):
            identity = backups.start(target, earlier)
            backups.finish(identity, completed, result=dict(pathname=f'host/db/{identity}.dump',
                                                            sizeBytes=1, checksum='a' * 64))
            identities.append(identity)
        failed = backups.start(target, later)
        backups.finish(failed, later, error='Dump failed')
        backups.start(target, later)
        files = backups.files()
        self.assertEqual([row['id'] for row in files], [identities[2], identities[0], identities[1]])
        self.assertEqual(files[0], dict(id=identities[2], backupTime=later, elapsedSeconds=3600, databaseName='cmdb',
                                       hostName='sally.example', ipAddress='192.0.2.7', pathname=f'host/db/{identities[2]}.dump'))
        self.assertEqual(files[-1]['elapsedSeconds'], 0)

    def test_backup_schedule_rejects_invalid_policy_values(self):
        target = NamespaceDb(self.db).create(name='backup target')
        self.db.execute('INSERT INTO BackupSchedule (modelElement) VALUES (%s)', (target,))
        for column, value in (('enabled', 2), ('enabled', None), ('frequency', 'weekly'),
                              ('frequency', None), ('retention', '3-weeks'), ('retention', None)):
            with self.subTest(column=column, value=value), self.assertRaises(pymysql.MySQLError):
                self.db.execute(f'UPDATE BackupSchedule SET {column}=%s WHERE modelElement=%s', (value, target))

    def test_mariadb_inventory_reuses_instances_and_keeps_schema_names_scoped(self):
        first = self.machines.upsert(Machine('192.168.0.7'))
        second = self.machines.upsert(Machine('192.168.0.8'))
        self.record(first)
        inventory = DataManagerDb(self.db)
        def record(machine, version='11.8.3-MariaDB', names=None):
            with self.db.transaction():
                return inventory.record_mariadb(machine, version, '/var/lib/mysql/',
                                                names if names is not None else ['cmdb', 'mysql', 'Mixed', 'mixed'])
        a = record(first)
        b = record(second)
        self.assertEqual(record(first), a)
        self.assertNotEqual(a, b)
        schemas = self.db.query('SELECT s.id, me.name, me.namespace FROM `Schema` s '
                                'JOIN ModelElement me ON me.id=s.id ORDER BY s.id')
        self.assertEqual(len(schemas), 8)
        self.assertEqual({row['namespace'] for row in schemas}, {a, b})
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM DataManagerDataPackage')[0]['n'], 8)
        self.assertEqual(record(first, '11.8.4-MariaDB', ['newdb']), a)
        self.assertEqual(len(self.db.query('SELECT id FROM `Schema`')), 9)
        versions = self.db.query('SELECT dc.id, ss.version FROM DataManager dm '
            'JOIN DeployedComponent dc ON dc.id=dm.id JOIN Component c ON c.id=dc.component '
            'JOIN ModelElement me ON me.id=c.id JOIN SoftwareSystem ss ON ss.id=me.namespace ORDER BY dc.id')
        self.assertEqual(versions, [{'id': a, 'version': '11.8.4-MariaDB'}, {'id': b, 'version': '11.8.3-MariaDB'}])
        self.assertEqual(len(self.inventory()), 3)  # OS plus two MariaDB deployments.
        deployments = {row['id']: row for row in self.software.list_deployments()}
        self.assertEqual(deployments[a]['databases'], ['Mixed', 'cmdb', 'mixed', 'mysql', 'newdb'])
        self.assertEqual(deployments[b]['databases'], ['Mixed', 'cmdb', 'mixed', 'mysql'])
        os_deployment = next(row for row in deployments.values() if row['type'] == 'OS')
        self.assertEqual(os_deployment['databases'], [])

    def test_mariadb_failure_rolls_back_its_whole_observation(self):
        with self.assertRaises(pymysql.IntegrityError), self.db.transaction():
            DataManagerDb(self.db).record_mariadb(999999, '11.8.3-MariaDB', '/data/', ['cmdb'])
        for table in ('SoftwareSystem', 'Component', 'DeployedComponent', 'DataManager', 'Schema'):
            self.assertEqual(self.db.query(f'SELECT COUNT(*) AS n FROM `{table}`')[0]['n'], 0)

    def test_data_packages_preserve_many_to_many_and_parent_identity(self):
        managers = []
        for address in ('192.168.0.7', '192.168.0.8'):
            machine = self.machines.upsert(Machine(address))
            self.record(machine)
        for deployment in self.inventory():
            self.db.execute('INSERT INTO DataManager (id) VALUES (%s)', (deployment['id'],))
            managers.append(deployment['id'])
        packages = []
        for name in ('cmdb', 'reporting'):
            identity = NamespaceDb(self.db).create_package(name=name)
            self.db.execute('INSERT INTO `Schema` (id) VALUES (%s)', (identity,))
            packages.append(identity)
        for manager in managers:
            for package in packages:
                self.db.execute('INSERT INTO DataManagerDataPackage (dataManager, dataPackage) VALUES (%s, %s)',
                                (manager, package))
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM DataManagerDataPackage')[0]['n'], 4)
        names = self.db.query('SELECT me.name FROM `Schema` s JOIN ModelElement me ON me.id = s.id ORDER BY s.id')
        self.assertEqual([row['name'] for row in names], ['cmdb', 'reporting'])
        for pair in ((managers[0], packages[0]), (packages[0], packages[1]), (managers[0], 999999)):
            with self.assertRaises(pymysql.IntegrityError):
                self.db.execute('INSERT INTO DataManagerDataPackage (dataManager, dataPackage) VALUES (%s, %s)', pair)
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute('INSERT INTO `Schema` (id) VALUES (%s)',
                            (NamespaceDb(self.db).create(name='not a package'),))
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute('INSERT INTO DataManager (id) VALUES (%s)', (packages[0],))
