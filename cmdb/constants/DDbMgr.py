"""Shared database connection defaults."""

from typing import Final


class DDbMgr:
    CHARSET: Final[str] = "utf8mb4"
    COLLATION: Final[str] = "utf8mb4_unicode_ci"
    PORT: Final[int] = 3306
    CONNECT_TIMEOUT: Final[int] = 10
    READ_TIMEOUT: Final[int] = 30
    WRITE_TIMEOUT: Final[int] = 30
