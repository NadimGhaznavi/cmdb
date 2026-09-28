"""A software component, identified through its deployments for now."""

from dataclasses import dataclass, field


@dataclass
class Component:
    id: int | None = None
    deployment: list[int] = field(default_factory=list)
