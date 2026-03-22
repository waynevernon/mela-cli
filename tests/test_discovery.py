from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mela_cli.discovery import ENV_DB_PATH, ENV_SUPPORT_DIR, discover_mela
from tests.support import create_fake_app


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_cli_paths_override_environment(self) -> None:
        explicit_db = self.home / "explicit.sqlite"
        explicit_support = self.home / "explicit-support"
        env = {
            ENV_DB_PATH: str(self.home / "env.sqlite"),
            ENV_SUPPORT_DIR: str(self.home / "env-support"),
        }
        result = discover_mela(
            db_path=explicit_db,
            support_dir=explicit_support,
            env=env,
            home=self.home,
        )
        self.assertEqual(result.db_path, explicit_db)
        self.assertEqual(result.db_path_source, "cli flag")
        self.assertEqual(result.support_dir, explicit_support)
        self.assertEqual(result.support_dir_source, "cli flag")

    def test_discovery_derives_paths_from_app_group_entitlement(self) -> None:
        application_group = "TESTTEAM.recipes.mela"
        app_path = create_fake_app(self.home, application_group)
        group_root = self.home / "Library" / "Group Containers" / application_group / "Data"
        (group_root / "Curcuma.sqlite").write_bytes(b"")
        (group_root / ".Curcuma_SUPPORT" / "_EXTERNAL_DATA").mkdir(parents=True, exist_ok=True)

        with (
            patch("mela_cli.discovery.discover_app_path", return_value=app_path),
            patch("mela_cli.discovery.read_application_groups", return_value=[application_group]),
        ):
            result = discover_mela(home=self.home)

        self.assertEqual(result.app_path, app_path)
        self.assertEqual(result.application_group, application_group)
        self.assertEqual(result.db_path, group_root / "Curcuma.sqlite")
        self.assertEqual(result.db_path_source, "derived from app entitlement")
        self.assertEqual(
            result.support_dir,
            group_root / ".Curcuma_SUPPORT" / "_EXTERNAL_DATA",
        )

    def test_discovery_falls_back_to_group_container_scan(self) -> None:
        group_root = self.home / "Library" / "Group Containers" / "SCAN.recipes.mela" / "Data"
        (group_root / ".Curcuma_SUPPORT" / "_EXTERNAL_DATA").mkdir(parents=True, exist_ok=True)
        (group_root / "Curcuma.sqlite").write_bytes(b"")

        with patch("mela_cli.discovery.discover_app_path", return_value=None):
            result = discover_mela(home=self.home)

        self.assertEqual(result.db_path, group_root / "Curcuma.sqlite")
        self.assertEqual(result.db_path_source, "group container scan")
        self.assertEqual(result.support_dir_source, "group container scan")
        self.assertEqual(result.application_group, "SCAN.recipes.mela")


if __name__ == "__main__":
    unittest.main()
