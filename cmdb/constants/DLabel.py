"""GUI labels for model attributes; keys retain their model spelling."""

from typing import Final


class DLabel:
    ATTRIBUTES: Final[dict[str, str]] = {
        "type": "Type",
        "subtype": "Subtype",
        "supplier": "Supplier",
        "version": "Version",
        "codename": "Codename",
        "databases": "Database(s)",
        "ipAddress": "IP Address",
        "macAddress": "MAC Address",
        "hostName": "Host Name",
        "createdOn": "Created On",
        "updatedOn": "Updated On",
    }
