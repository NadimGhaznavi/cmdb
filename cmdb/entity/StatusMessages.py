"""Hold the CMDB server's status history for its current lifetime."""

from threading import Lock


class StatusMessages:
    def __init__(self) -> None:
        self._messages: list[str] = []
        self._lock = Lock()

    def append(self, message: str) -> None:
        """Add one display line without storing anything on disk."""
        with self._lock:
            self._messages.append(' '.join(message.splitlines()))

    def snapshot(self) -> list[str]:
        with self._lock:
            return self._messages.copy()
