"""A CWM tag/value pair attached to a model element."""

from dataclasses import dataclass


@dataclass
class TaggedValue:
    tag: str
    value: str
    modelElement: int | None = None
    id: int | None = None
