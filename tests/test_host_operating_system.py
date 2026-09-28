"""Host-reported release parsing without running the file as a script."""

from unittest import TestCase

from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.entity.TaggedValue import TaggedValue
from cmdb.interface.HostOperatingSystem import operating_system


class HostOperatingSystemTests(TestCase):
    def test_release_fields_map_to_existing_attributes(self):
        self.assertEqual(operating_system(
            'ID="Example Linux"\nVERSION_ID="13.2"\nVENDOR_NAME="Example Vendor"\n'),
            SoftwareSystem(type="linux", subtype="Example Linux", supplier="Example Vendor", version="13.2"))

    def test_debian_full_version_and_codename(self):
        self.assertEqual(operating_system(
            'ID=debian\nVERSION_ID=13\nDEBIAN_VERSION_FULL=13.6\nVERSION_CODENAME=trixie\n'),
            SoftwareSystem(type="linux", subtype="debian", version="13.6",
                           taggedValue=[TaggedValue(tag="VERSION_CODENAME", value="trixie")]))

    def test_other_distributions_use_version_id(self):
        self.assertEqual(operating_system('ID=ubuntu\nVERSION_ID=24.04\nDEBIAN_VERSION_FULL=13.6').version,
                         '24.04')

    def test_optional_fields_are_not_inferred_from_other_values(self):
        self.assertEqual(operating_system('ID=Debian\nVERSION="trixie"\n'),
                         SoftwareSystem(type="linux", subtype="Debian"))

    def test_invalid_or_missing_release_leaves_inventory_untouched(self):
        for contents in ('', 'VERSION_ID=13', 'ID="unterminated', 'ID=two words',
                         'ID=""', 'ID=' + 'x' * 256, 'ID="bad\x00value"'):
            with self.subTest(contents=contents):
                self.assertIsNone(operating_system(contents))

    def test_shell_expressions_are_only_text(self):
        self.assertEqual(operating_system('ID="$(touch /tmp/never-run)"').subtype,
                         '$(touch /tmp/never-run)')
