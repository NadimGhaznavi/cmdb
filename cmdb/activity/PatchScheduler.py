"""Save cron policy and enqueue scheduled patches independently of HTTP."""

from crontab import CronSlices

from cmdb.interface.Cron import Cron
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.PatchDb import PatchDb
from cmdb.interface.PatchScheduleDb import PatchScheduleDb
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb


class PatchScheduler:
    def update(self, machine, enabled, expression):
        if (type(machine) is not int or not 0 < machine < 2**64
                or type(enabled) is not bool or not isinstance(expression, str)
                or len(expression) > 255 or '\n' in expression or '\r' in expression):
            raise ValueError('Invalid patch schedule.')
        expression = ' '.join(expression.split())
        if expression or enabled:
            if len(expression.split()) != 5 or not CronSlices.is_valid(expression):
                raise ValueError('Use five cron fields: minute hour day-of-month month day-of-week.')
        with Cron.EDIT_LOCK:
            db = DbMgr()
            try:
                with db.transaction():
                    if not any(host['id'] == machine for host in SoftwareDeploymentDb(db).debian_hosts()):
                        raise LookupError('Debian host not found.')
                    schedule = PatchScheduleDb(db).save(machine, enabled, expression)
                    Cron().update_patch(schedule['id'], enabled, expression)
                return schedule
            finally:
                db.close()

    def run(self, identity):
        db = DbMgr()
        try:
            schedule = PatchScheduleDb(db).get(identity)
            if schedule and schedule['enabled']:
                PatchDb(db).request(schedule['machine'])
        finally:
            db.close()
