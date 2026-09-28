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
                identity = NamespaceDb(self.db).create(namespace=machine)
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
            deployment = namespaces.create(namespace=machine)
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
                    identity = NamespaceDb(self.db).create(namespace=owner)
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
                identity = NamespaceDb(self.db).create(namespace=deployment["softwareSystem"])
                self.db.execute(
                    "INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)",
                    (identity, "/invalid", deployment["softwareSystem"], deployment["component"]),
                )

    def test_schema_uses_exact_class_names_and_keeps_inherited_fields_on_parents(self):
        tables = {next(iter(row.values())) for row in self.db.query("SHOW TABLES")}
        self.assertEqual(tables, {"TaggedValue", "ModelElement", "Namespace", "Machine", "SoftwareSystem", "Component", "DeployedComponent"})
        for table in ("Component", "SoftwareSystem", "Machine", "DeployedComponent"):
            columns = {row["Field"] for row in self.db.query(f"SHOW COLUMNS FROM {table}")}
            self.assertNotIn("namespace", columns)
            self.assertNotIn("ownedElement", columns)
            self.assertNotIn("name", columns)
