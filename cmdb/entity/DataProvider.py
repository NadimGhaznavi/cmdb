"""A deployed data provider."""

from dataclasses import dataclass, field

from cmdb.entity.DataManager import DataManager
from cmdb.entity.ProviderConnection import ProviderConnection


@dataclass
class DataProvider(DataManager):
    resourceConnection: list[ProviderConnection] = field(default_factory=list)
