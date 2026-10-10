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
from cmdb.interface.BackupScheduleDb import BackupScheduleDb
from cmdb.activity.Scheduler import Scheduler
from crontab import CronTab
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.DataManagerDb import DataManagerDb
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.NamespaceDb import NamespaceDb
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb
from cmdb.interface.SoftwareSystemDb import SoftwareSystemDb
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

    def test_application_backup_targets_include_only_declarations_and_share_database_policy(self):
        machine = self.machines.upsert(Machine('192.0.2.7', hostName='wintermute'))
        other = self.machines.upsert(Machine('192.0.2.8'))
        DataManagerDb(self.db).record_mariadb(machine, '11.8', '/data/', ['mycount', 'unrelated', 'mysql'])
        DataManagerDb(self.db).record_mariadb(other, '11.8', '/data/', ['mycount'])
        app = SoftwareSystemDb(self.db).create_application('MyCount')
        plain = SoftwareSystemDb(self.db).create_application('Plain')
        self.software.record_application(machine, plain, '/opt/prod/plain', '1.0')
        self.software.record_application(machine, app, '/opt/prod/mycount', '1.0',
                                         components=(('Marketing', 'pages/marketing'),),
                                         databases=(('MyCount', 'mycount'),))
        inventory = BackupDb(self.db)
        rows = inventory.applications()
        self.assertEqual({row['kind'] for row in rows}, {'directory', 'database'})
        self.assertEqual({row['applicationName'] for row in rows}, {'MyCount'})
        self.assertEqual({row['machine'] for row in rows}, {machine})
        component = next(row for row in rows if row['kind'] == 'directory')
        catalog = next(row for row in rows if row['kind'] == 'database')
        self.assertEqual(component['pathname'], '/opt/prod/mycount/pages/marketing')
        self.assertEqual(catalog['databaseName'], 'mycount')
        self.assertEqual(inventory.target(component['modelElement'])['kind'], 'directory')
        self.assertEqual(inventory.target(catalog['modelElement'])['databaseName'], 'mycount')
        self.assertIsNone(inventory.target(plain))
        started = datetime(2026, 10, 7, 15, 53, 1)
        relative = 'wintermute/files/wintermute-mycount-marketing-2026-10-07_15:53:01.tgz'
        identity = inventory.start(component['modelElement'], started)
        inventory.finish(identity, started, result=dict(pathname=relative, sizeBytes=123, checksum='a' * 64))
        policy = BackupScheduleDb(self.db).save(component['modelElement'], True, '0 12 * * *', '1-week')
        BackupScheduleDb(self.db).save(catalog['modelElement'], True, '5 12 * * *', '2-weeks')
        rows = inventory.applications()
        self.assertEqual(next(row for row in rows if row['kind'] == 'directory')['lastBackup'], started)
        declared_db = next(row for row in rows if row['kind'] == 'database')
        standalone_db = next(row for row in inventory.databases() if row['modelElement'] == catalog['modelElement'])
        self.assertEqual(declared_db['scheduleId'], standalone_db['scheduleId'])
        self.assertEqual(declared_db['retention'], '2-weeks')
        self.assertEqual(inventory.files()[0]['pathname'], relative)
        self.software.record_application(machine, app, '/opt/prod/mycount', '2.0',
                                         components=(('Marketing', 'pages/marketing'),),
                                         databases=(('MyCount', 'mycount'),))
        rows = inventory.applications()
        self.assertEqual(next(row for row in rows if row['kind'] == 'directory')['modelElement'], component['modelElement'])
        release = next(row for row in rows if row['kind'] == 'directory')['application']
        with self.db.transaction():
            disabled = SoftwareSystemDb(self.db).delete_application(release)
        self.assertIn(policy['id'], disabled)
        self.assertFalse(BackupScheduleDb(self.db).get(policy['id'])['enabled'])
        self.assertEqual(inventory.applications(), [])
        self.assertEqual(inventory.files()[0]['pathname'], relative)
        self.assertIsNotNone(inventory.get(identity))

    def test_scheduled_directory_backup_dispatches_and_persists_archive(self):
        machine = self.machines.upsert(Machine('192.0.2.7', hostName='wintermute'))
        app = SoftwareSystemDb(self.db).create_application('MyCount')
        self.software.record_application(machine, app, '/opt/prod/mycount', '1.0',
                                         components=(('Marketing', 'pages/marketing'),))
        target = BackupDb(self.db).components()[0]['modelElement']
        def connection():
            db = DbMgr.__new__(DbMgr)
            db._connection = pymysql.connect(
                unix_socket=os.environ['CMDB_TEST_DB_SOCKET'], user='root', database=self.database,
                autocommit=True, cursorclass=pymysql.cursors.DictCursor)
            return db
        tab = CronTab(tab='')
        with patch('cmdb.activity.Scheduler.DbMgr', side_effect=connection), \
                patch('cmdb.activity.BackupManager.DbMgr', side_effect=connection), \
                patch('cmdb.interface.Cron.CronTab', return_value=tab), \
                patch('cmdb.activity.BackupManager.SSHFiles') as remote:
            remote.return_value.backup_directory.return_value = dict(
                pathname='wintermute/files/wintermute-mycount-marketing-2026-10-07_15:53:01.tgz',
                sizeBytes=42, checksum='a' * 64)
            scheduler = Scheduler()
            policy = scheduler.update(target, True, '15 3 * * 0', '2-weeks')
            self.assertEqual(len(tab), 1)
            self.assertTrue(scheduler.run(policy['id']))
            remote.return_value.backup_directory.assert_called_once()
            archive = BackupDb(self.db).files()[0]
            self.assertEqual(archive['sizeBytes'], 42)
            self.assertTrue(archive['pathname'].startswith('wintermute/files/'))
            self.assertIsNotNone(BackupDb(self.db).components()[0]['lastBackup'])
            scheduler.update(target, False, '15 3 * * 0', '2-weeks')
            self.assertEqual(len(tab), 0)
            remote.reset_mock()
            self.assertTrue(scheduler.run(policy['id']))
            remote.assert_not_called()

    def test_application_database_clients_match_same_machine_and_survive_upgrade(self):
        with self.db.transaction():
            machine = self.machines.upsert(Machine('192.0.2.7'))
            other = self.machines.upsert(Machine('192.0.2.8'))
            app = SoftwareSystemDb(self.db).create_application('MyCount')
            remote = DataManagerDb(self.db).record_mariadb(other, '11.8', '/data/', ['mycount'])
            self.software.record_application(machine, app, '/opt/prod/mycount', '1.0',
                                             databases=(('MyCount', 'mycount'),))
            self.assertEqual(self.db.query('SELECT id FROM DataProvider'), [])
            server = DataManagerDb(self.db).record_mariadb(machine, '11.8', '/data/', ['mycount'])
            self.software.record_application(machine, app, '/opt/prod/mycount', '1.0',
                                             databases=(('MyCount', 'MyCount'), ('Missing', 'absent')))
            self.assertEqual(self.db.query('SELECT id FROM DataProvider'), [])
            self.software.record_application(machine, app, '/opt/prod/mycount', '1.0',
                                             databases=(('MyCount', 'mycount'),))
        provider = self.db.query('SELECT id FROM DataProvider')[0]['id']
        connection = self.db.query('SELECT * FROM ProviderConnection')[0]
        self.assertEqual((connection['dataProvider'], connection['dataManager']), (provider, server))
        self.assertEqual(self.db.query('SELECT namespace, name FROM ModelElement WHERE id=%s',
                                      (connection['id'],)), [{'namespace': provider, 'name': 'MyCount'}])
        catalog = self.db.query('SELECT dp.dataPackage FROM DataManagerDataPackage dp WHERE dp.dataManager=%s',
                               (server,))[0]['dataPackage']
        self.assertEqual(self.db.query('SELECT dataPackage FROM DataManagerDataPackage WHERE dataManager=%s',
                                      (provider,)), [{'dataPackage': catalog}])
        backup = BackupDb(self.db).start(catalog, datetime(2026, 10, 10))
        with self.db.transaction():
            self.software.record_application(machine, app, '/opt/prod/mycount', '1.0', databases=(('MyCount', 'mycount'),))
            self.software.record_application(machine, app, '/opt/prod/mycount', '2.0', databases=(('MyCount', 'mycount'),))
            SoftwareSystemDb(self.db).prune_unused(set())
        self.assertEqual(self.db.query('SELECT id FROM DataProvider'), [{'id': provider}])
        self.assertEqual(self.db.query('SELECT * FROM ProviderConnection'), [connection])
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM DeployedComponentsUsage'), [{'n': 1}])
        self.assertEqual(self.db.query('SELECT ss.version FROM DeployedComponent dc '
                                      'JOIN ModelElement me ON me.id=dc.component '
                                      'JOIN SoftwareSystem ss ON ss.id=me.namespace WHERE dc.id=%s',
                                      (provider,)), [{'version': '2.0'}])
        release = self.db.query('SELECT me.namespace FROM ModelElement me JOIN DeployedComponent dc '
                                'ON dc.component=me.id WHERE dc.id=%s', (provider,))[0]['namespace']
        with self.db.transaction():
            SoftwareSystemDb(self.db).delete_application(release)
        self.assertEqual(self.db.query('SELECT id FROM DataProvider'), [])
        self.assertEqual(self.db.query('SELECT id FROM ProviderConnection'), [])
        self.assertEqual(self.db.query('SELECT * FROM DeployedComponentsUsage'), [])
        self.assertEqual({row['id'] for row in self.db.query('SELECT id FROM DataManager')}, {server, remote})
        self.assertEqual(self.db.query('SELECT id FROM Backup'), [{'id': backup}])
        self.assertEqual(len(BackupDb(self.db).databases()), 2)

    def test_application_database_projection_uses_its_provider_and_deduplicates_names(self):
        with self.db.transaction():
            first = self.machines.upsert(Machine('192.0.2.7'))
            second = self.machines.upsert(Machine('192.0.2.8'))
            app = SoftwareSystemDb(self.db).create_application('MyCount')
            DataManagerDb(self.db).record_mariadb(first, '11.8', '/data/', ['mycount', 'audit', 'unrelated'])
            DataManagerDb(self.db).record_mariadb(second, '11.8', '/data/', ['other'])
            self.software.record_application(first, app, '/opt/prod/mycount', '1.0',
                                             components=(('Screenshots', 'pages/marketing'),),
                                             databases=(('MyCount', 'mycount'), ('Audit', 'audit'),
                                                        ('Duplicate label', 'mycount')))
            self.software.record_application(second, app, '/opt/prod/mycount', '1.0')
        deployments = self.software.list_deployments()
        self.assertEqual([row['componentName'] for row in deployments if row['componentName']], ['Screenshots'])
        self.assertEqual(len(self.db.query('SELECT id FROM DataProvider')), 1)
        apps = {row['machine']: row for row in deployments if row['name'] == 'MyCount' and not row['componentName']}
        self.assertEqual(apps[first]['databases'], ['audit', 'mycount'])
        self.assertEqual(apps[second]['databases'], [])
        servers = {row['machine']: row for row in deployments if row['subtype'] == 'MariaDB'}
        self.assertEqual(servers[first]['databases'], ['audit', 'mycount', 'unrelated'])
        self.assertEqual(servers[second]['databases'], ['other'])

    def test_pruning_old_application_release_preserves_shared_active_release(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            first = self.machines.upsert(Machine('192.0.2.7'))
            second = self.machines.upsert(Machine('192.0.2.8'))
            application = definitions.create_application('MyCount')
            self.software.record_application(first, application, '/opt/prod/mycount', '0.4.1')
            self.software.record_application(second, application, '/opt/prod/mycount', '0.4.1')
            self.software.record_application(first, application, '/opt/prod/mycount', '1.0.0')
            self.assertEqual(definitions.prune_unused(set()), [])
        previous = self.db.query('SELECT c.id FROM Component c JOIN ModelElement me ON me.id=c.id '
                                 'WHERE me.namespace=%s', (application,))[0]['id']
        with self.db.transaction():
            self.software.record_application(second, application, '/opt/prod/mycount', '1.0.0')
            removed = definitions.prune_unused(set())
        self.assertEqual([(row['name'], row['version']) for row in removed], [('MyCount', '0.4.1')])
        self.assertEqual(len(self.inventory()), 2)
        self.assertEqual({row['version'] for row in self.inventory()}, {'1.0.0'})
        self.assertEqual(len(definitions.list_applications()), 1)
        for identity in (application, previous):
            self.assertEqual(self.db.query('SELECT id FROM ModelElement WHERE id=%s', (identity,)), [])

    def test_pruning_protects_pending_additions_and_removes_unused_hierarchy_and_tags(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            identity = definitions.create_application('NotInstalled')
            self.db.execute('INSERT INTO TaggedValue (tag, value, modelElement) VALUES (%s,%s,%s)',
                            ('test', 'unused', identity))
            self.assertEqual(definitions.prune_unused({identity}), [])
            self.assertEqual(len(definitions.prune_unused(set())), 1)
            self.assertEqual(definitions.prune_unused(set()), [])
        for table in ('SoftwareSystem', 'Package', 'Namespace', 'ModelElement'):
            self.assertEqual(self.db.query(f'SELECT id FROM {table} WHERE id=%s', (identity,)), [])
        self.assertEqual(self.db.query('SELECT id FROM TaggedValue WHERE modelElement=%s', (identity,)), [])

    def test_pruning_os_and_mariadb_releases_preserves_managers_schemas_and_backups(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            machine = self.machines.upsert(Machine('192.0.2.7'))
            self.software.record_operating_system(machine, SoftwareSystem(type='linux', subtype='debian', version='13.0'))
            self.software.record_operating_system(machine, SoftwareSystem(type='linux', subtype='debian', version='13.1'))
            manager = DataManagerDb(self.db).record_mariadb(machine, '11.8.1-MariaDB', '/var/lib/mysql/', ['app'])
            schema = self.db.query('SELECT id FROM `Catalog`')[0]['id']
            backup = BackupDb(self.db).start(schema, datetime(2026, 10, 4))
            DataManagerDb(self.db).record_mariadb(machine, '11.8.2-MariaDB', '/var/lib/mysql/', ['app'])
            removed = definitions.prune_unused(set())
        self.assertEqual({row['version'] for row in removed}, {'13.0', '11.8.1-MariaDB'})
        self.assertEqual(self.db.query('SELECT id FROM DataManager'), [{'id': manager}])
        self.assertEqual(self.db.query('SELECT id FROM `Catalog`'), [{'id': schema}])
        self.assertEqual(self.db.query('SELECT id FROM Backup'), [{'id': backup}])

    def test_machine_environment_tag_create_update_delete_and_discovery_preservation(self):
        first = self.machines.upsert(Machine('192.0.2.7'))
        second = self.machines.upsert(Machine('192.0.2.8'))
        self.db.execute('INSERT INTO TaggedValue (modelElement, tag, value) VALUES (%s, %s, %s)',
                        (first, 'OtherTag', 'keep'))
        self.assertTrue(self.machines.update_environment(first, 'dev'))
        tag = self.db.query("SELECT * FROM TaggedValue WHERE tag = 'DeploymentEnvironment'")[0]
        self.assertEqual((tag['modelElement'], tag['value']), (first, 'dev'))
        for value in ('qa', 'prod', 'prod'):
            self.assertTrue(self.machines.update_environment(first, value))
            stored = self.db.query("SELECT * FROM TaggedValue WHERE tag = 'DeploymentEnvironment'")
            self.assertEqual(len(stored), 1)
            self.assertEqual((stored[0]['id'], stored[0]['value']), (tag['id'], value))
        self.assertTrue(self.machines.update_environment(second, 'qa'))
        self.machines.upsert(Machine('192.0.2.7', macAddress='00:11:22:33:44:55'))
        machines = {machine.id: machine for machine in self.machines.list_machines()}
        self.assertEqual({tag.tag: tag.value for tag in machines[first].taggedValue},
                         {'OtherTag': 'keep', 'DeploymentEnvironment': 'prod'})
        for _ in range(2):
            self.assertTrue(self.machines.update_environment(first, 'unclassified'))
        machines = {machine.id: machine for machine in self.machines.list_machines()}
        self.assertEqual({tag.tag: tag.value for tag in machines[first].taggedValue}, {'OtherTag': 'keep'})
        self.assertEqual({tag.tag: tag.value for tag in machines[second].taggedValue},
                         {'DeploymentEnvironment': 'qa'})
        self.assertFalse(self.machines.update_environment(999999, 'dev'))

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

    def test_registered_software_systems_include_undeployed_and_distinct_instances(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            first = definitions.create_application('MyCount')
            second = definitions.create_application('MyCount')
            machine = self.machines.upsert(Machine('192.0.2.7'))
            self.software.record_operating_system(machine, SoftwareSystem(
                type='OS', subtype='Linux', supplier='Linux', version='6.X'))
        records = definitions.list_software_systems()
        self.assertEqual(len(records), 3)
        self.assertEqual({row['id'] for row in records if row['name'] == 'MyCount'}, {first, second})
        operating_system = next(row for row in records if row['type'] == 'OS')
        self.assertEqual(operating_system['subtype'], 'Linux')
        self.assertEqual(operating_system['supplier'], 'Linux')
        self.assertEqual(operating_system['version'], '6.X')

    def test_named_application_discovery_reuses_deployment_and_keeps_host_versions_distinct(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            application = definitions.create_application('MyCount')
            first = self.machines.upsert(Machine('192.0.2.7'))
            second = self.machines.upsert(Machine('192.0.2.8'))
            self.software.record_application(first, application, '/opt/prod/mycount', '1.0')
            self.software.record_application(first, application, '/opt/prod/mycount', '1.0')
            self.software.record_application(second, application, '/opt/prod/mycount', '2.0')
        deployments = self.software.list_deployments()
        self.assertEqual(len(deployments), 2)
        self.assertEqual([row['version'] for row in deployments], ['1.0', '2.0'])
        self.assertEqual([row['name'] for row in deployments], ['MyCount', 'MyCount'])
        self.assertEqual(definitions.list_applications(), [{'id': application, 'name': 'MyCount'}])
        self.assertEqual(deployments[0]['softwareSystem'], application)
        self.assertEqual(len(self.machines.list_machines()[0].deployedComponent), 1)

    def test_filesystem_components_share_definitions_and_preserve_host_identity(self):
        definitions = SoftwareSystemDb(self.db)
        components = (("Marketing Screenshots", "pages/marketing"), ("Uploads", "/srv/uploads"))
        with self.db.transaction():
            application = definitions.create_application('MyCount')
            first = self.machines.upsert(Machine('192.0.2.7'))
            second = self.machines.upsert(Machine('192.0.2.8'))
            for machine in (first, first, second):
                self.software.record_application(machine, application, '/opt/prod/mycount', '1.0',
                                                 components=components)
        rows = self.db.query(
            'SELECT dc.id, dc.machine, dc.pathname, dc.component, ce.namespace, ce.name, '
            'de.namespace AS deploymentNamespace FROM DeployedComponent dc '
            'JOIN ModelElement ce ON ce.id=dc.component JOIN ModelElement de ON de.id=dc.id '
            'WHERE ce.name IS NOT NULL ORDER BY dc.machine, ce.name')
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row['namespace'], application)
            self.assertEqual(row['deploymentNamespace'], row['machine'])
            self.assertEqual(row['pathname'], '/opt/prod/mycount/pages/marketing'
                             if row['name'] == 'Marketing Screenshots' else '/srv/uploads')
        self.assertEqual(rows[0]['component'], rows[2]['component'])
        self.assertEqual(rows[1]['component'], rows[3]['component'])
        with self.db.transaction():
            self.software.record_application(first, application, '/opt/prod/mycount', '2.0', components=components)
            self.software.record_application(first, application, '/opt/prod/mycount', '2.0')
        refreshed = {row['id']: row for row in self.software.list_deployments()}
        for row in rows:
            self.assertEqual(refreshed[row['id']]['version'], '2.0' if row['machine'] == first else '1.0')
            self.assertEqual(refreshed[row['id']]['componentName'], row['name'])
            self.assertEqual(refreshed[row['id']]['pathname'], row['pathname'])
        self.assertEqual(sum(row['componentName'] is None for row in refreshed.values()), 2)
        self.assertEqual(len(refreshed), 6)
        self.assertEqual(self.db.query('SELECT COUNT(*) AS count FROM Component')[0]['count'], 6)
        with self.db.transaction():
            definitions.delete_application(application)
        self.assertEqual(len(self.software.list_deployments()), 3)

    def test_filesystem_components_and_application_writes_roll_back_together(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            application = definitions.create_application('MyCount')
            machine = self.machines.upsert(Machine('192.0.2.7'))
        with self.assertRaises(RuntimeError):
            with self.db.transaction():
                self.software.record_application(machine, application, '/opt/prod/mycount', '1.0',
                                                 components=(("Screenshots", "pages/marketing"),))
                raise RuntimeError('abort observation')
        self.assertEqual(self.software.list_deployments(), [])
        self.assertEqual(self.db.query('SELECT * FROM Component'), [])
        self.assertIsNone(definitions.list_software_systems()[0]['version'])

    def test_application_deleted_during_discovery_is_skipped(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            application = definitions.create_application('MyCount')
            machine = self.machines.upsert(Machine('192.0.2.7'))
        with self.db.transaction():
            definitions.delete_application(application)
        with self.db.transaction():
            self.assertFalse(self.software.record_application(
                machine, application, '/opt/prod/mycount', '1.0'))
        self.assertEqual(definitions.list_software_systems(), [])
        self.assertEqual(self.software.list_deployments(), [])

    def test_application_metadata_enrichment_preserves_shared_release_and_discovery(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            application = definitions.create_application('MyCount')
            first = self.machines.upsert(Machine('192.0.2.10'))
            second = self.machines.upsert(Machine('192.0.2.11'))
            self.software.record_application(first, application, '/opt/prod/mycount', '1.0')
            self.software.record_application(second, application, '/opt/prod/mycount', '1.0',
                                             type='application', subtype='inventory',
                                             supplier='Example Supplier', codename='Orion')
            self.software.record_application(first, application, '/opt/prod/mycount', '1.0')
        deployments = self.software.list_deployments()
        self.assertEqual(len(deployments), 2)
        for row in deployments:
            self.assertEqual(row['softwareSystem'], application)
            self.assertEqual((row['type'], row['subtype'], row['supplier'], row['codename']),
                             ('application', 'inventory', 'Example Supplier', 'Orion'))
        self.assertEqual(definitions.list_applications(), [{'id': application, 'name': 'MyCount'}])
        with self.db.transaction():
            self.software.record_application(first, application, '/opt/prod/mycount', '2.0',
                                             type='application', subtype='inventory',
                                             supplier='Example Supplier', codename='Nova')
        deployments = self.software.list_deployments()
        self.assertEqual(len(deployments), 2)
        self.assertEqual([row['version'] for row in deployments], ['2.0', '1.0'])
        self.assertEqual([row['codename'] for row in deployments], ['Nova', 'Orion'])
        self.assertEqual(len(definitions.list_applications()), 1)

    def test_conflicting_application_metadata_keeps_other_hosts_definition(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            application = definitions.create_application('MyCount')
            first = self.machines.upsert(Machine('192.0.2.10'))
            second = self.machines.upsert(Machine('192.0.2.11'))
            self.software.record_application(first, application, '/opt/prod/mycount', '1.0',
                                             type='application', supplier='Supplier A', codename='Orion')
            self.software.record_application(second, application, '/opt/prod/mycount', '1.0',
                                             type='service', supplier='Supplier B', codename='Nova')
            self.software.record_application(second, application, '/opt/prod/mycount', '1.0')
        deployments = self.software.list_deployments()
        self.assertEqual(len(deployments), 2)
        self.assertNotEqual(deployments[0]['softwareSystem'], deployments[1]['softwareSystem'])
        self.assertEqual([(row['type'], row['supplier'], row['codename']) for row in deployments],
                         [('application', 'Supplier A', 'Orion'), ('service', 'Supplier B', 'Nova')])

    def test_delete_application_removes_only_selected_release_and_its_deployments(self):
        definitions = SoftwareSystemDb(self.db)
        with self.db.transaction():
            first = definitions.create_application('MyCount')
            second = definitions.create_application('MyCount')
            machines = [self.machines.upsert(Machine(address)) for address in ('192.0.2.7', '192.0.2.8')]
            for machine in machines:
                self.software.record_application(machine, first, '/opt/prod/mycount', '1.0')
            self.db.execute('INSERT INTO TaggedValue (modelElement, tag, value) VALUES (%s, %s, %s)',
                            (first, 'test', 'value'))
        deployments = self.software.list_deployments()
        deleted_ids = {first} | {row['component'] for row in deployments} | {row['id'] for row in deployments}
        with self.db.transaction():
            self.assertEqual(definitions.delete_application(first), [])
        self.assertEqual(definitions.list_software_systems()[0]['id'], second)
        self.assertEqual(self.software.list_deployments(), [])
        self.assertEqual({machine.id for machine in self.machines.list_machines()}, set(machines))
        self.assertFalse(deleted_ids & {row['id'] for row in self.db.query('SELECT id FROM ModelElement')})
        with self.db.transaction():
            self.assertIsNone(definitions.delete_application(first))
            self.software.record_application(machines[0], second, '/opt/prod/mycount', '1.0')
        self.assertEqual(len(self.software.list_deployments()), 1)

    def test_delete_database_software_preserves_backup_history_and_rediscovery_identity(self):
        definitions = SoftwareSystemDb(self.db)
        machine = self.machines.upsert(Machine('192.0.2.7'))
        managers = DataManagerDb(self.db)
        with self.db.transaction():
            manager = managers.record_mariadb(machine, '11.8.3', '/data/', ['example'])
        application = self.software.list_deployments()[0]['softwareSystem']
        backups = BackupDb(self.db)
        target = backups.databases()[0]['modelElement']
        completed = datetime(2026, 10, 2)
        backup = backups.start(target, completed)
        backups.finish(backup, completed, result=dict(pathname='host/db/example.dump', sizeBytes=1, checksum='a' * 64))
        schedule = self.db.insert('INSERT INTO BackupSchedule (modelElement, enabled) VALUES (%s, 1)', (target,))
        files = backups.files()
        with self.db.transaction():
            self.assertEqual(definitions.delete_application(application), [schedule])
        self.assertEqual(definitions.list_software_systems(), [])
        self.assertEqual(self.software.list_deployments(), [])
        self.assertEqual(backups.databases(), [])
        self.assertEqual(backups.files(), files)
        self.assertEqual(self.db.query('SELECT enabled FROM BackupSchedule')[0]['enabled'], 0)
        with self.db.transaction():
            self.assertEqual(managers.record_mariadb(machine, '11.8.3', '/data/', ['example']), manager)
        self.assertEqual(backups.files(), files)
        self.assertEqual(backups.databases()[0]['modelElement'], target)
        self.assertEqual(len(self.db.query('SELECT id FROM Component')), 1)

    def test_delete_application_dependency_failure_rolls_back(self):
        definitions = SoftwareSystemDb(self.db)
        application = definitions.create_application('MyCount')
        NamespaceDb(self.db).create(namespace=application, name='dependent inventory')
        with self.assertRaises(pymysql.IntegrityError), self.db.transaction():
            definitions.delete_application(application)
        self.assertEqual(definitions.list_software_systems()[0]['id'], application)

    def test_patch_schedule_saves_cron_policy_and_dispatches_queue(self):
        from cmdb.activity.PatchScheduler import PatchScheduler
        from cmdb.interface.PatchDb import PatchDb
        machine = self.machines.upsert(Machine('192.0.2.90', hostName='scheduled.example'))
        self.software.record_operating_system(machine, operating_system('ID=debian\nVERSION_ID=13'))
        tab = CronTab(tab='0 12 * * * /backup # cmdb-backup-schedule-1\n')
        with patch('cmdb.activity.PatchScheduler.DbMgr', return_value=self.db), \
                patch.object(self.db, 'close'), patch('cmdb.interface.Cron.CronTab', return_value=tab):
            schedule = PatchScheduler().update(machine, True, '15 2 * * 0')
            self.assertEqual(PatchDb(self.db).hosts()[0]['schedule']['expression'], '15 2 * * 0')
            PatchScheduler().run(schedule['id'])
            self.assertEqual(PatchDb(self.db).next()['machine'], machine)
            with patch.object(tab, 'write', side_effect=OSError('denied')):
                with self.assertRaises(OSError):
                    PatchScheduler().update(machine, True, '0 1 * * *')
            self.assertEqual(PatchDb(self.db).hosts()[0]['schedule']['expression'], '15 2 * * 0')
            saved = PatchScheduler().update(machine, False, '15 2 * * 0')
            self.assertEqual(saved['id'], schedule['id'])
            self.assertEqual(len(list(tab.find_comment('cmdb-patch-schedule-' + str(schedule['id'])))), 0)
            self.assertEqual(len(list(tab.find_comment('cmdb-backup-schedule-1'))), 1)

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
        records.rebooting(identity)
        self.assertEqual(records.next()['status'], 'rebooting')
        records.finish(identity)
        self.assertIsNone(records.next())
        self.assertEqual(records.hosts()[0]['job']['status'], 'succeeded')
        next_id = records.request(debian)
        self.assertNotEqual(next_id, identity)
        report = records.report()
        self.assertEqual([row['id'] for row in report], [next_id, identity])
        self.assertEqual(report[0]['status'], 'queued')
        self.assertIsNone(report[0]['elapsedSeconds'])
        self.assertEqual(report[1]['status'], 'succeeded')
        self.assertGreaterEqual(report[1]['elapsedSeconds'], 0)
        self.assertNotIn('output', report[1])
        self.assertNotIn('output', {row['Field'] for row in self.db.query('SHOW COLUMNS FROM Patch')})

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
        self.assertEqual(tables, {"DataProvider", "ProviderConnection", "DeployedComponentsUsage", "Schema", "DiscoverySchedule", "PatchSchedule", "Patch", "Backup", "BackupSchedule", "Package", "Catalog", "DataManager", "DataManagerDataPackage", "TaggedValue", "ModelElement", "Namespace", "Machine", "SoftwareSystem", "Component", "DeployedComponent"})
        self.assertIn('name', {row['Field'] for row in self.db.query('SHOW COLUMNS FROM ModelElement')})
        for table in ("Package", "Catalog", "DataManager", "Component", "SoftwareSystem", "Machine", "DeployedComponent"):
            columns = {row["Field"] for row in self.db.query(f"SHOW COLUMNS FROM `{table}`")}
            self.assertNotIn("namespace", columns)
            self.assertNotIn("ownedElement", columns)
            self.assertNotIn("name", columns)

    def test_backup_schedule_references_databases_and_deployments_with_independent_identity(self):
        machine = self.machines.upsert(Machine('192.168.0.7'))
        manager = DataManagerDb(self.db).record_mariadb(machine, '11.8.3', '/data/', ['cmdb'])
        schema = self.db.query('SELECT id FROM `Catalog`')[0]['id']
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
        backups.remove_database(target)
        self.assertEqual(backups.databases(), [])
        self.assertEqual(len(backups.files()), 1)
        DataManagerDb(self.db).record_mariadb(machine, '11.8.3', '/data/', ['mysql'])
        self.assertEqual(backups.databases(), [])
        DataManagerDb(self.db).record_mariadb(machine, '11.8.3', '/data/', ['cmdb'])
        self.assertEqual(backups.databases()[0]['modelElement'], target)
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
            schedule = scheduler.update(target, True, '15 3 * * 0', '2-weeks')
            self.assertEqual(BackupDb(self.db).databases()[0]['retention'], '2-weeks')
            same = scheduler.update(target, True, '15 3 * * 0', 'forever')
            self.assertEqual(schedule['id'], same['id'])
            self.assertEqual(BackupDb(self.db).databases()[0]['expression'], '15 3 * * 0')
            self.assertEqual(str(list(tab.find_comment('cmdb-backup-schedule-' + str(schedule['id'])))[0].slices), '15 3 * * 0')
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
            scheduler.update(target, False, '15 3 * * 0', 'forever')
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
                                       hostName='sally.example', ipAddress='192.0.2.7',
                                       pathname=f'host/db/{identities[2]}.dump', sizeBytes=1))
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
        schemas = self.db.query('SELECT s.id, me.name, me.namespace FROM `Catalog` s '
                                'JOIN ModelElement me ON me.id=s.id ORDER BY s.id')
        self.assertEqual(len(schemas), 8)
        self.assertEqual({row['namespace'] for row in schemas}, {a, b})
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM DataManagerDataPackage')[0]['n'], 8)
        self.assertEqual(record(first, '11.8.4-MariaDB', ['newdb']), a)
        self.assertEqual(len(self.db.query('SELECT id FROM `Catalog`')), 9)
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
        for table in ('SoftwareSystem', 'Component', 'DeployedComponent', 'DataManager', 'Catalog'):
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
            self.db.execute('INSERT INTO `Catalog` (id) VALUES (%s)', (identity,))
            packages.append(identity)
        for manager in managers:
            for package in packages:
                self.db.execute('INSERT INTO DataManagerDataPackage (dataManager, dataPackage) VALUES (%s, %s)',
                                (manager, package))
        self.assertEqual(self.db.query('SELECT COUNT(*) AS n FROM DataManagerDataPackage')[0]['n'], 4)
        names = self.db.query('SELECT me.name FROM `Catalog` s JOIN ModelElement me ON me.id = s.id ORDER BY s.id')
        self.assertEqual([row['name'] for row in names], ['cmdb', 'reporting'])
        for pair in ((managers[0], packages[0]), (packages[0], packages[1]), (managers[0], 999999)):
            with self.assertRaises(pymysql.IntegrityError):
                self.db.execute('INSERT INTO DataManagerDataPackage (dataManager, dataPackage) VALUES (%s, %s)', pair)
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute('INSERT INTO `Catalog` (id) VALUES (%s)',
                            (NamespaceDb(self.db).create(name='not a package'),))
        with self.assertRaises(pymysql.IntegrityError):
            self.db.execute('INSERT INTO DataManager (id) VALUES (%s)', (packages[0],))
