"""Save the discovery policy, maintain cron, and run standalone inventory."""

from crontab import CronSlices

from cmdb.activity.InventoryCoordinator import InventoryCoordinator
from cmdb.interface.Cron import Cron
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.DiscoveryScheduleDb import DiscoveryScheduleDb


class DiscoveryScheduler:
    def update(self, enabled: bool, expression: str) -> dict:
        if (type(enabled) is not bool or not isinstance(expression, str)
                or len(expression) > 255 or '\n' in expression or '\r' in expression):
            raise ValueError('Invalid discovery schedule settings.')
        expression = ' '.join(expression.split())
        if len(expression.split()) != 5 or not CronSlices.is_valid(expression):
            raise ValueError('Use five cron fields: minute hour day-of-month month day-of-week.')
        with Cron.EDIT_LOCK:
            db = DbMgr()
            try:
                with db.transaction():
                    schedule = DiscoveryScheduleDb(db).save(enabled, expression)
                    Cron().update_discovery(schedule['id'], enabled, expression)
                return schedule
            finally:
                db.close()

    def run(self, identity: int) -> bool:
        db = DbMgr()
        try:
            schedule = DiscoveryScheduleDb(db).get(identity)
        finally:
            db.close()
        if schedule is None or not schedule['enabled']:
            return True
        coordinator = InventoryCoordinator()
        try:
            coordinator.scan_inventory()
        finally:
            coordinator.prune()
        return True
