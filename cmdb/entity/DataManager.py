"""A data manager deployed on a machine."""

from cmdb.entity.DeployedComponent import DeployedComponent
from dataclasses import dataclass, field


@dataclass
class DataManager(DeployedComponent):
    clientConnection: list[int] = field(default_factory=list, kw_only=True)
    dataPackage: list[int] = field(default_factory=list)
