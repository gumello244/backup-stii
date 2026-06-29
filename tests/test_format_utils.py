from __future__ import annotations

"""Unit tests for ui/format_utils.py."""
import unittest

from ui.format_utils import format_bytes, format_time, format_date


class TestFormatBytes(unittest.TestCase):
    """Tests for format_bytes."""

    def test_bytes(self) -> None:
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(512), "512 B")

    def test_kilobytes(self) -> None:
        self.assertEqual(format_bytes(1536), "1,5 KB")

    def test_megabytes(self) -> None:
        self.assertEqual(format_bytes(2 * 1024 * 1024), "2,0 MB")

    def test_gigabytes(self) -> None:
        result = format_bytes(3_400_000_000)
        self.assertIn("GB", result)
        self.assertTrue(result.startswith("3"))


class TestFormatTime(unittest.TestCase):
    """Tests for format_time."""

    def test_seconds(self) -> None:
        self.assertEqual(format_time(0), "~0 segundos")
        self.assertEqual(format_time(45), "~45 segundos")
        self.assertEqual(format_time(59), "~59 segundos")

    def test_one_minute(self) -> None:
        self.assertEqual(format_time(60), "~1 minuto")
        self.assertEqual(format_time(119), "~1 minuto")

    def test_minutes(self) -> None:
        self.assertEqual(format_time(120), "~2 minutos")
        self.assertEqual(format_time(3600), "~60 minutos")


class TestFormatDate(unittest.TestCase):
    """Tests for format_date."""

    def test_date(self) -> None:
        from datetime import datetime
        dt = datetime(2024, 6, 22, 10, 15, 0)
        ts = dt.timestamp()
        self.assertEqual(format_date(ts), "22/06/2024")


if __name__ == "__main__":
    unittest.main()
