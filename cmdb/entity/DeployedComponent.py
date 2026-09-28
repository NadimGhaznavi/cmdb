"""A component deployed on a machine."""

from dataclasses import dataclass

from cmdb.entity.Namespace import Namespace


@dataclass
class DeployedComponent(Namespace):
    """`machine` holds the containing Machine's stable ID foreign key."""

    pathname: str
    machine: int
    component: int
