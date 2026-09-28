"""The adopted SoftwareDeployment attributes of a software product release."""

from dataclasses import dataclass

from cmdb.entity.Namespace import Namespace


@dataclass
class SoftwareSystem(Namespace):
    type: str | None = None
    subtype: str | None = None
    supplier: str | None = None
    version: str | None = None
