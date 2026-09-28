"""A namespace owns zero or more model elements."""

from dataclasses import dataclass, field

from cmdb.entity.ModelElement import ModelElement


@dataclass(kw_only=True)
class Namespace(ModelElement):
    ownedElement: list[int] = field(default_factory=list)
