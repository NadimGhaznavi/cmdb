"""A software system deployment constituted by deployed components."""

from dataclasses import dataclass, field


@dataclass
class DeployedSoftwareSystem:
    softwareSystem: int
    id: int | None = None
    deployedComponent: list[int] = field(default_factory=list)
