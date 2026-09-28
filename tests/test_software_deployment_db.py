"""Fresh-schema integration checks against an explicitly supplied test MariaDB socket."""

import os
from pathlib import Path
import unittest
from uuid import uuid4

import pymysql

from cmdb.entity.Machine import Machine
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.MachineDb import MachineDb
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb


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
            "SELECT dc.id, dc.machine, dc.pathname, dc.component, ds.id AS deployment, "
            "ss.id AS softwareSystem, ss.type, ss.subtype, ss.supplier, ss.version "
            "FROM deployedComponents dc "
            "JOIN deployedSoftwareSystemComponents link ON link.deployedComponent = dc.id "
            "JOIN deployedSoftwareSystems ds ON ds.id = link.deployedSoftwareSystem "
            "JOIN softwareSystems ss ON ss.id = ds.softwareSystem ORDER BY dc.machine")

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
        for table in ("softwareSystems", "components", "deployedSoftwareSystems", "deployedComponents"):
            self.assertEqual(self.db.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"], 1)

    def test_shared_definition_has_separate_deployments_and_updates_only_one_machine(self):
        a = self.machines.upsert(Machine("192.168.0.7"))
        b = self.machines.upsert(Machine("192.168.0.8"))
        self.record(a)
        self.record(b)
        old = self.inventory()
        self.assertEqual(old[0]["softwareSystem"], old[1]["softwareSystem"])
        self.assertEqual(old[0]["component"], old[1]["component"])
        self.assertNotEqual(old[0]["deployment"], old[1]["deployment"])
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
        self.db.execute("UPDATE machines SET ipAddress = %s WHERE id = %s", ("192.168.0.8", machine))
        self.assertEqual(self.machines.upsert(Machine("192.168.0.8")), machine)
        stored = self.machines.list_machines()[0]
        self.assertEqual(stored.hostName, "edited")
        self.assertEqual(stored.macAddress, "00:11:22:33:44:55")
        self.assertEqual(self.inventory()[0]["machine"], machine)

    def test_foreign_keys_and_rollback_prevent_partial_os_records(self):
        with self.assertRaises(pymysql.IntegrityError):
            self.record(999999)
        for table in ("softwareSystems", "components", "deployedComponents", "deployedSoftwareSystems"):
            self.assertEqual(self.db.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"], 0)
        machine = self.machines.upsert(Machine("192.168.0.7"))
        with self.assertRaises(pymysql.IntegrityError):
            self.db.insert("INSERT INTO deployedComponents (pathname, machine, component) VALUES (%s, %s, %s)",
                           ("/", machine, 999999))

    def test_deployed_system_component_association_supports_many_to_many(self):
        machine = self.machines.upsert(Machine("192.168.0.7"))
        self.record(machine)
        first = self.inventory()[0]
        second_system = self.db.insert("INSERT INTO deployedSoftwareSystems (softwareSystem) VALUES (%s)",
                                       (first["softwareSystem"],))
        second_component = self.db.insert(
            "INSERT INTO deployedComponents (pathname, machine, component) VALUES (%s, %s, %s)",
            ("/boot", machine, first["component"]))
        self.db.execute(
            "INSERT INTO deployedSoftwareSystemComponents (deployedSoftwareSystem, deployedComponent) "
            "VALUES (%s, %s), (%s, %s)",
            (second_system, first["id"], first["deployment"], second_component))
        self.assertEqual(len(self.inventory()), 3)
