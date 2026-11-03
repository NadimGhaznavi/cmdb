"""Save the discovery policy, maintain cron, and run standalone inventory."""

from crontab import CronSlices

from cmdb.activity.InventoryCoordinator import InventoryCoordinator
from cmdb.interface.Cron import Cron
from cmdb.interface.Database import connect_database
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
            with connect_database() as db:
                with db.transaction():
                    schedule = DiscoveryScheduleDb(db).save(enabled, expression)
                    Cron().update_discovery(schedule['id'], enabled, expression)
                return schedule

    def run(self, identity: int) -> bool:
        with connect_database() as db:
            schedule = DiscoveryScheduleDb(db).get(identity)
        if schedule is None or not schedule['enabled']:
            return True
        coordinator = InventoryCoordinator()
        try:
            coordinator.scan_inventory()
        finally:
            coordinator.prune()
        return True
