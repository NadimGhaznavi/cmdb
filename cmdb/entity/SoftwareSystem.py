"""The adopted SoftwareDeployment attributes of a software product release."""

from dataclasses import dataclass


@dataclass
class SoftwareSystem:
    type: str | None = None
    subtype: str | None = None
    supplier: str | None = None
    version: str | None = None
    id: int | None = None
