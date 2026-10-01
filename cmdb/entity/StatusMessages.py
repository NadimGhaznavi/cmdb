"""Hold the CMDB server's status history for its current lifetime."""

from threading import Lock
import sys


class StatusMessages:
    def __init__(self) -> None:
        self._messages: list[dict[str, str]] = []
        self._lock = Lock()

    def append(self, message: str) -> None:
        """Add one display line with the calling module's name."""
        source = sys._getframe(1).f_globals['__name__']
        with self._lock:
            self._messages.append({'source': source, 'message': ' '.join(message.splitlines())})

    def snapshot(self) -> list[dict[str, str]]:
        with self._lock:
            return [message.copy() for message in self._messages]
