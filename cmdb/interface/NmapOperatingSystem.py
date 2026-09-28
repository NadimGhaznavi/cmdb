"""Translate an unambiguous Nmap OS classification to SoftwareSystem fields."""

from cmdb.entity.SoftwareSystem import SoftwareSystem


def operating_system(host: dict) -> SoftwareSystem | None:
    """Accept only matching 100% classifications; never invent release details.

    Nmap may match several fingerprints to the same family/vendor/generation.
    Conflicting or approximate matches leave the existing inventory untouched.
    """
    classifications = set()
    for match in host.get("osmatch", []):
        if str(match.get("accuracy")) != "100":
            continue
        for candidate in match.get("osclass", []):
            if str(candidate.get("accuracy")) != "100":
                continue
            family = candidate.get("osfamily") or None
            supplier = candidate.get("vendor") or None
            version = candidate.get("osgen") or None
            classifications.add((family, supplier, version))
    if len(classifications) != 1:
        return None
    family, supplier, version = classifications.pop()
    if not family:
        return None
    return SoftwareSystem(type="OS", subtype=family, supplier=supplier, version=version)
