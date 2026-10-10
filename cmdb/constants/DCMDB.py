"""CMDB runtime and installation defaults."""

from typing import Final


class DCMDB:
    CMDB_TYPE: Final[str] = "application"
    CMDB_SUBTYPE: Final[str] = "Metadata Repo"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Maryam"
    VERSION: Final[str] = "1.4.1"
    BASE_INSTALL_DIR: Final[str] = "/opt/prod"
    BASE_DIR: Final[str] = "/opt/prod/cmdb"
    SERVICE_USER: Final[str] = "cmdb"
    AGENT_USER: Final[str] = "cmdbagent"
    AGENT_HOME: Final[str] = "/var/lib/cmdbagent"
    SERVICE_HOME: Final[str] = "/var/lib/cmdb"
    SSH_DIR: Final[str] = SERVICE_HOME + "/.ssh"
    SSH_KEY: Final[str] = SSH_DIR + "/id_ed25519"
    SSH_KNOWN_HOSTS: Final[str] = SSH_DIR + "/known_hosts"
    SSH_CONNECT_TIMEOUT_SECONDS: Final[int] = 5
    SSH_COMMAND_TIMEOUT_SECONDS: Final[int] = 30
    BACKUP_DIR: Final[str] = "/imports/disk1/backups"
    BACKUP_TIMEOUT_SECONDS: Final[int] = 3600
    BACKUP_CRON: Final[str] = "0 12 * * *"
    SERVICE_UNIT: Final[str] = "cmdb-server.service"
    DATABASE_ENV: Final[str] = "/etc/cmdb/database.env"
    DATABASE_NAME: Final[str] = "cmdb"
    DATABASE_USER: Final[str] = "cmdb"
    HOST: Final[str] = "0.0.0.0"
    PORT: Final[int] = 14444
    REQUEST_TIMEOUT: Final[int] = 10
    SCAN_TARGET: Final[str] = "192.168.0.0/24"
    DISCOVERY_CRON: Final[str] = "*/5 * * * *"
    SCAN_TIMEOUT_SECONDS: Final[int] = 30
    OS_SCAN_TIMEOUT_SECONDS: Final[int] = 180
