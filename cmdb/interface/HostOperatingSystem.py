"""Translate host-reported os-release data to SoftwareSystem fields."""

import shlex

from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.entity.TaggedValue import TaggedValue


def operating_system(contents: str) -> SoftwareSystem | None:
    """Read release assignments as data, never as executable shell code."""
    fields = {}
    try:
        for line in contents.splitlines():
            key, separator, value = line.partition("=")
            if not separator or key not in ("ID", "VERSION_ID", "VENDOR_NAME",
                                            "DEBIAN_VERSION_FULL", "VERSION_CODENAME"):
                continue
            words = shlex.split(value, comments=True)
            if len(words) > 1:
                return None
            value = words[0] if words else ""
            if len(value) > 255 or any(ord(char) < 32 or ord(char) == 127 for char in value):
                return None
            fields[key] = value or None
    except ValueError:
        return None
    if not fields.get("ID"):
        return None
    version = fields.get("VERSION_ID")
    supplier = fields.get("VENDOR_NAME")
    if fields["ID"] == "debian":
        version = fields.get("DEBIAN_VERSION_FULL") or version
        supplier = "Debian"
    tags = []
    if fields.get("VERSION_CODENAME"):
        tags.append(TaggedValue(tag="VERSION_CODENAME", value=fields["VERSION_CODENAME"]))
    return SoftwareSystem(type="linux", subtype=fields["ID"],
                          supplier=supplier, version=version, taggedValue=tags)
