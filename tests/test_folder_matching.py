from __future__ import annotations

import unittest

from tg_mcp.telegram_client import TgFolder, _select_folder


class SelectFolderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folders = [
            TgFolder(id=1, name="Module"),
            TgFolder(id=2, name="Module Team"),
            TgFolder(id=3, name="Alerts"),
        ]

    def test_partial_single_match(self) -> None:
        selected = _select_folder(self.folders, "alert")
        self.assertEqual(selected.id, 3)

    def test_partial_ambiguous_then_exact_fallback(self) -> None:
        selected = _select_folder(self.folders, "module")
        self.assertEqual(selected.id, 1)

    def test_partial_ambiguous_without_exact(self) -> None:
        with self.assertRaisesRegex(ValueError, "folder_ambiguous"):
            _select_folder(self.folders, "mod")

    def test_folder_not_found(self) -> None:
        with self.assertRaisesRegex(ValueError, "folder_not_found"):
            _select_folder(self.folders, "unknown")


if __name__ == "__main__":
    unittest.main()
