"""GUI labels for model attributes; keys retain their model spelling."""

from typing import Final


class DLabel:
    ATTRIBUTES: Final[dict[str, str]] = {
        "type": "Type",
        "subtype": "Subtype",
        "supplier": "Supplier",
        "version": "Version",
        "codename": "Codename",
        "ipAddress": "IP Address",
        "macAddress": "MAC Address",
        "hostName": "Host Name",
        "site": "Site",
        "deployedComponent": "Deployed Components",
        "createdOn": "Created On",
        "updatedOn": "Updated On",
    }
