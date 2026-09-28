"""A component deployed on a machine."""

from dataclasses import dataclass, field


@dataclass
class DeployedComponent:
    """`machine` holds the containing Machine's stable ID foreign key."""

    pathname: str
    machine: int
    component: int
    id: int | None = None
    deployedSoftwareSystem: list[int] = field(default_factory=list)
