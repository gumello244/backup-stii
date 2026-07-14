from __future__ import annotations

"""Unit tests for assets.py helper functions."""
import os
import sys
import unittest
from unittest.mock import patch

from ui.assets import asset_path


class TestAssets(unittest.TestCase):
    """Test suite for asset path resolution under different environments."""

    def test_asset_path_dev(self) -> None:
        """Verify asset_path resolutions in development mode (not frozen)."""
        with patch.object(sys, "frozen", False, create=True):
            path = asset_path("icon.ico")
            expected_suffix = os.path.join("ui", "assets", "icon.ico")
            self.assertTrue(
                path.endswith(expected_suffix),
                f"Expected path '{path}' to end with '{expected_suffix}'",
            )

    def test_asset_path_frozen(self) -> None:
        """Verify asset_path resolutions in PyInstaller frozen environment."""
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", "C:\\mock_meipass_dir", create=True):
            path = asset_path("icon.ico")
            expected = os.path.join("C:\\mock_meipass_dir", "ui", "assets", "icon.ico")
            self.assertEqual(path, expected)
