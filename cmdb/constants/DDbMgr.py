"""Shared database connection defaults."""

from typing import Final


class DDbMgr:
    PORT: Final[int] = 3306
    CONNECT_TIMEOUT: Final[int] = 10
    READ_TIMEOUT: Final[int] = 30
    WRITE_TIMEOUT: Final[int] = 30
