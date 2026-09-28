"""Store OS observations through the CWM software deployment relationships."""

from cmdb.entity.Component import Component
from cmdb.entity.DeployedComponent import DeployedComponent
from cmdb.entity.DeployedSoftwareSystem import DeployedSoftwareSystem
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.DbMgr import DbMgr


class SoftwareDeploymentDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def record_operating_system(self, machine: int, system: SoftwareSystem) -> None:
        """Refresh the scanner's OS deployment at / within the caller's transaction.

        Software definitions can be shared by machines. Each machine has its own
        deployment. The single scanner worker serializes discovery writes.
        """
        if system.type != "OS" or not system.subtype:
            raise ValueError("An operating system classification is required.")
        rows = self._db.query(
            "SELECT id FROM softwareSystems WHERE type <=> %s AND subtype <=> %s "
            "AND supplier <=> %s AND version <=> %s ORDER BY id LIMIT 1",
            (system.type, system.subtype, system.supplier, system.version),
        )
        if rows:
            system.id = rows[0]["id"]
        else:
            system.id = self._db.insert(
                "INSERT INTO softwareSystems (type, subtype, supplier, version) VALUES (%s, %s, %s, %s)",
                (system.type, system.subtype, system.supplier, system.version),
            )

        # Reuse the OS's component definition across deployments of the same release.
        rows = self._db.query(
            "SELECT dc.component FROM deployedComponents dc "
            "JOIN deployedSoftwareSystemComponents link ON link.deployedComponent = dc.id "
            "JOIN deployedSoftwareSystems ds ON ds.id = link.deployedSoftwareSystem "
            "WHERE ds.softwareSystem = %s AND dc.pathname = '/' ORDER BY dc.id LIMIT 1",
            (system.id,),
        )
        component = Component(id=rows[0]["component"] if rows else
                              self._db.insert("INSERT INTO components () VALUES ()"))
        rows = self._db.query(
            "SELECT dc.id, ds.id AS deployedSoftwareSystem FROM deployedComponents dc "
            "JOIN deployedSoftwareSystemComponents link ON link.deployedComponent = dc.id "
            "JOIN deployedSoftwareSystems ds ON ds.id = link.deployedSoftwareSystem "
            "JOIN softwareSystems ss ON ss.id = ds.softwareSystem "
            "WHERE dc.machine = %s AND dc.pathname = '/' AND ss.type = 'OS' "
            "ORDER BY dc.id LIMIT 1",
            (machine,),
        )
        if rows:
            self._db.execute("UPDATE deployedComponents SET component = %s WHERE id = %s",
                             (component.id, rows[0]["id"]))
            self._db.execute("UPDATE deployedSoftwareSystems SET softwareSystem = %s WHERE id = %s",
                             (system.id, rows[0]["deployedSoftwareSystem"]))
        else:
            deployment = DeployedComponent(pathname="/", machine=machine, component=component.id)
            deployment.id = self._db.insert(
                "INSERT INTO deployedComponents (pathname, machine, component) VALUES (%s, %s, %s)",
                (deployment.pathname, deployment.machine, deployment.component),
            )
            deployed_system = DeployedSoftwareSystem(softwareSystem=system.id)
            deployed_system.id = self._db.insert(
                "INSERT INTO deployedSoftwareSystems (softwareSystem) VALUES (%s)",
                (deployed_system.softwareSystem,),
            )
            self._db.execute(
                "INSERT INTO deployedSoftwareSystemComponents (deployedSoftwareSystem, deployedComponent) "
                "VALUES (%s, %s)", (deployed_system.id, deployment.id),
            )
