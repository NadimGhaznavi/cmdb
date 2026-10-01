"""Status history preserves its records when callers modify snapshots."""

from unittest import TestCase
from datetime import datetime, timezone
from unittest.mock import patch

from cmdb.entity.StatusMessages import StatusMessages


class StatusMessagesTests(TestCase):
    @patch('cmdb.entity.StatusMessages.datetime')
    def test_timestamp_is_recorded_when_appended(self, clock):
        clock.now.return_value = datetime(2026, 10, 1, 12, 34, 56, tzinfo=timezone.utc)
        history = StatusMessages()
        history.append('Scan started')
        clock.now.assert_called_once_with(timezone.utc)
        self.assertEqual(history.snapshot(), [{'timestamp': '2026-10-01T12:34:56+00:00',
                                              'source': __name__, 'message': 'Scan started'}])

    def test_snapshot_does_not_expose_stored_records(self):
        history = StatusMessages()
        history.append('First line\nSecond line')
        snapshot = history.snapshot()
        timestamp = snapshot[0]['timestamp']
        snapshot[0]['timestamp'] = 'changed'
        snapshot[0]['source'] = 'changed'
        snapshot[0]['message'] = 'changed'
        snapshot.clear()
        self.assertEqual(history.snapshot(), [
            {'timestamp': timestamp, 'source': __name__, 'message': 'First line Second line'}])
