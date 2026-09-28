"""The adopted owner reference of a CWM model element."""

from dataclasses import dataclass, field

from cmdb.entity.TaggedValue import TaggedValue


@dataclass(kw_only=True)
class ModelElement:
    id: int | None = None
    name: str | None = None
    namespace: int | None = None
    taggedValue: list[TaggedValue] = field(default_factory=list)
