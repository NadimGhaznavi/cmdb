"""GUI labels for model attributes; keys retain their model spelling."""

from typing import Final


class DLabel:
    ATTRIBUTES: Final[dict[str, str]] = {
        "ipAddress": "IP Address",
        "macAddress": "MAC Address",
        "hostName": "Host Name",
        "site": "Site",
        "deployedComponent": "Deployed Components",
        "createdOn": "Created On",
        "updatedOn": "Updated On",
    }
