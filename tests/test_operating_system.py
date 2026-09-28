"""OS classification rules without performing network scans."""

from unittest import TestCase

from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.NmapOperatingSystem import operating_system


def os_host(*classifications, accuracy="100"):
    return {"status": {"state": "up"}, "osmatch": [
        {"accuracy": accuracy, "osclass": list(classifications)}]}


LINUX = {"accuracy": "100", "osfamily": "Linux", "vendor": "Linux", "osgen": "6.X"}


class OperatingSystemTests(TestCase):
    def test_classification_uses_only_software_system_attributes(self):
        host = os_host(LINUX)
        host["osmatch"][0]["name"] = "Freeform fingerprint name is not an inherited name field"
        self.assertEqual(operating_system(host),
                         SoftwareSystem(type="OS", subtype="Linux", supplier="Linux", version="6.X"))

    def test_missing_optional_fields_are_not_invented(self):
        self.assertEqual(operating_system(os_host({"accuracy": "100", "osfamily": "Linux"})),
                         SoftwareSystem(type="OS", subtype="Linux"))

    def test_duplicate_classifications_are_one_result(self):
        self.assertIsNotNone(operating_system(os_host(LINUX, LINUX)))

    def test_absent_incomplete_approximate_and_conflicting_results_are_ignored(self):
        for host in ({}, os_host(), os_host({"accuracy": "100"}),
                     os_host(LINUX, accuracy="98"),
                     os_host({**LINUX, "accuracy": "98"}),
                     os_host(LINUX, {**LINUX, "osgen": "5.X"})):
            with self.subTest(host=host):
                self.assertIsNone(operating_system(host))
