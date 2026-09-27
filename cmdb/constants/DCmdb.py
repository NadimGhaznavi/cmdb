"""CMDB runtime and installation defaults."""

from typing import Final


class DCmdb:
    BASE_DIR: Final[str] = "/opt/prod/cmdb"
    SERVICE_USER: Final[str] = "cmdb"
    SERVICE_UNIT: Final[str] = "cmdb-server.service"
    DATABASE_ENV: Final[str] = "/etc/cmdb/database.env"
    DATABASE_NAME: Final[str] = "cmdb"
    DATABASE_USER: Final[str] = "cmdb"
    HOST: Final[str] = "0.0.0.0"
    PORT: Final[int] = 14444
    REQUEST_TIMEOUT: Final[int] = 10
