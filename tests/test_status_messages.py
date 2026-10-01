"""Status history preserves its records when callers modify snapshots."""

from unittest import TestCase

from cmdb.entity.StatusMessages import StatusMessages


class StatusMessagesTests(TestCase):
    def test_snapshot_does_not_expose_stored_records(self):
        history = StatusMessages()
        history.append('First line\nSecond line')
        snapshot = history.snapshot()
        snapshot[0]['source'] = 'changed'
        snapshot[0]['message'] = 'changed'
        snapshot.clear()
        self.assertEqual(history.snapshot(), [
            {'source': __name__, 'message': 'First line Second line'}])
