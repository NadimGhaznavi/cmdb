"""The adopted owner reference of a CWM model element."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class ModelElement:
    id: int | None = None
    namespace: int | None = None
