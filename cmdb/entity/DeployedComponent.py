"""A component deployed on a machine."""

from dataclasses import dataclass

from cmdb.entity.Package import Package


@dataclass
class DeployedComponent(Package):
    """`machine` holds the containing Machine's stable ID foreign key."""

    pathname: str
    machine: int
    component: int
