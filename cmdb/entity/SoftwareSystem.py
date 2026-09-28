"""The adopted SoftwareDeployment attributes of a software product release."""

from dataclasses import dataclass

from cmdb.entity.Package import Package


@dataclass
class SoftwareSystem(Package):
    type: str | None = None
    subtype: str | None = None
    supplier: str | None = None
    version: str | None = None
