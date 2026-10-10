"""A provider connection."""

from __future__ import annotations

from dataclasses import dataclass

from cmdb.entity.ModelElement import ModelElement


@dataclass
class ProviderConnection(ModelElement):
    dataProvider: int
    dataManager: int
