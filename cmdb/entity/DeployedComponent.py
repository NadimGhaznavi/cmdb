"""A component deployed on a machine."""

from dataclasses import dataclass


@dataclass
class DeployedComponent:
    """`machine` holds the containing Machine's stable ID foreign key."""

    pathname: str
    machine: int
