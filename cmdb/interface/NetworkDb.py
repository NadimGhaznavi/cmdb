"""Report declared listener ports through their application deployments."""

import json

from cmdb.interface.DbMgr import DbMgr


class NetworkDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def ports(self) -> list[dict]:
        """Project listener tags without adding attributes to the CWM entities."""
        rows = self._db.query(
            'SELECT m.hostName, m.ipAddress, ae.name AS application, tv.value '
            'FROM DeployedComponentsUsage u '
            'JOIN DeployedComponent listener ON listener.id=u.usedComponents '
            'JOIN ModelElement ce ON ce.id=listener.component '
            'JOIN DeployedComponent app ON app.id=u.usingComponents AND app.machine=listener.machine '
            'JOIN ModelElement ac ON ac.id=app.component '
            'JOIN SoftwareSystem ss ON ss.id=ac.namespace JOIN ModelElement ae ON ae.id=ss.id '
            'JOIN Machine m ON m.id=listener.machine JOIN TaggedValue tv ON tv.modelElement=listener.id '
            "WHERE ce.name='Network listeners' AND LEFT(tv.tag, 13)='CMDB_NETWORK.' "
            'ORDER BY m.id, ae.name, listener.id, tv.tag')
        ports = []
        for row in rows:
            use, _interface, port = json.loads(row['value'])
            ports.append({'hostName': row['hostName'], 'ipAddress': row['ipAddress'],
                          'application': row['application'], 'serviceName': use, 'portNumber': port})
        return ports
