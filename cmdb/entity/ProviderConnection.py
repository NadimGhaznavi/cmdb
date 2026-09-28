"""A provider connection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cmdb.entity.DataProvider import DataProvider


@dataclass
class ProviderConnection:
    dataProvider: DataProvider
