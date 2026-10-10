"""A component deployed on a machine."""

from dataclasses import dataclass, field

from cmdb.entity.Package import Package


@dataclass
class DeployedComponent(Package):
    """`machine` holds the containing Machine's stable ID foreign key."""

    pathname: str
    machine: int
    component: int
    usedComponents: list[int] = field(default_factory=list, kw_only=True)
