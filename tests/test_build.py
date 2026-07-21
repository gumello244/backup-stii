import unittest
from dist.build import parse_version_tuple, bump_version, generate_version_info_content


class TestBuildScript(unittest.TestCase):
    """Test suite for the build.py CLI utility functions."""

    def test_parse_version_tuple_valid(self) -> None:
        """Verify parsing standard semver strings into 4-integer tuples."""
        self.assertEqual(parse_version_tuple("0.0.2"), (0, 0, 2, 0))
        self.assertEqual(parse_version_tuple("1.2.3"), (1, 2, 3, 0))

    def test_parse_version_tuple_invalid(self) -> None:
        """Verify invalid semver strings raise ValueError with descriptive messages."""
        with self.assertRaises(ValueError) as ctx:
            parse_version_tuple("invalid.version")
        self.assertIn("invalid.version", str(ctx.exception))

    def test_bump_version_major(self) -> None:
        """Verify major version increments and resets minor/patch components."""
        ver, build = bump_version("0.0.2", 2, "major")
        self.assertEqual(ver, "1.0.0")
        self.assertEqual(build, 3)

    def test_bump_version_minor(self) -> None:
        """Verify minor version increments and resets patch component."""
        ver, build = bump_version("0.0.2", 2, "minor")
        self.assertEqual(ver, "0.1.0")
        self.assertEqual(build, 3)

    def test_bump_version_patch(self) -> None:
        """Verify patch version increments and minor/major are preserved."""
        ver, build = bump_version("0.0.2", 2, "patch")
        self.assertEqual(ver, "0.0.3")
        self.assertEqual(build, 3)

    def test_bump_version_build(self) -> None:
        """Verify build level only increments the build count."""
        ver, build = bump_version("0.0.2", 2, "build")
        self.assertEqual(ver, "0.0.2")
        self.assertEqual(build, 3)

    def test_bump_version_invalid(self) -> None:
        """Verify invalid version string format raises ValueError on bump."""
        with self.assertRaises(ValueError):
            bump_version("0.2", 2, "patch")

    def test_generate_version_info_content(self) -> None:
        """Verify the generated Windows version info matches expectations for Remos."""
        content = generate_version_info_content("0.0.2", 5)
        self.assertIn("filevers=(5, 0, 0, 0)", content)
        self.assertIn("prodvers=(0, 0, 2, 0)", content)
        self.assertIn("FileVersion', u'5.0.0'", content)
        self.assertIn("ProductVersion', u'0.0.2'", content)
        self.assertIn("InternalName', u'Remos'", content)


if __name__ == "__main__":
    unittest.main()
