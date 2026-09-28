"""Queue and persist Debian patch jobs independently of the web service."""

from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb


class PatchDb:
    def __init__(self, db):
        self.db = db

    def hosts(self):
        hosts = SoftwareDeploymentDb(self.db).debian_hosts()
        for host in hosts:
            rows = self.db.query('SELECT id, status, error FROM Patch WHERE machine=%s ORDER BY id DESC LIMIT 1', (host['id'],))
            host['job'] = rows[0] if rows else None
        return hosts

    def request(self, machine):
        with self.db.transaction():
            # Serialize clicks for this machine while checking for an existing active job.
            self.db.query('SELECT id FROM Machine WHERE id=%s FOR UPDATE', (machine,))
            host = next((h for h in self.hosts() if h['id'] == machine), None)
            if host is None:
                raise LookupError('Debian host not found.')
            job = host['job']
            if job and job['status'] in ('queued', 'patching', 'rebooting'):
                return job['id']
            return self.db.insert('INSERT INTO Patch (machine, address) VALUES (%s, %s)', (machine, host['ipAddress']))

    def report(self):
        return self.db.query(
            "SELECT p.id, COALESCE(p.startedOn, p.createdOn) AS patchTime, "
            "TIMESTAMPDIFF(SECOND, p.startedOn, p.completedOn) AS elapsedSeconds, "
            "m.hostName, p.address AS ipAddress, p.status, p.error "
            "FROM Patch p JOIN Machine m ON m.id=p.machine ORDER BY p.id DESC LIMIT 100")

    def next(self):
        rows = self.db.query("SELECT * FROM Patch WHERE status IN ('queued','patching','rebooting') ORDER BY id LIMIT 1")
        return rows[0] if rows else None

    def start(self, identity, boot):
        self.db.execute("UPDATE Patch SET status='patching', startedOn=UTC_TIMESTAMP(), bootId=%s WHERE id=%s", (boot, identity))

    def rebooting(self, identity):
        self.db.execute("UPDATE Patch SET status='rebooting', rebootOn=UTC_TIMESTAMP() WHERE id=%s", (identity,))

    def finish(self, identity, error=None):
        self.db.execute('UPDATE Patch SET status=%s, completedOn=UTC_TIMESTAMP(), error=%s WHERE id=%s',
                        ('failed' if error else 'succeeded', error[-4000:] if error else None, identity))
