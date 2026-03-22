from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from mela_cli.cli import capture_help_output
from tests.support import create_fixture_store, run_cli


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path, self.support_dir = create_fixture_store(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def args(self, *command: str) -> list[str]:
        return [
            "--db-path",
            str(self.db_path),
            "--support-dir",
            str(self.support_dir),
            *command,
        ]

    def test_help_lists_release_commands(self) -> None:
        code, output = capture_help_output(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("doctor", output)
        self.assertIn("export-all", output)

    def test_show_outputs_text(self) -> None:
        code, stdout, stderr = run_cli(self.args("show", "2"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Egg Soup", stdout)
        self.assertIn("Ingredients", stdout)

    def test_export_json_writes_to_output_dir(self) -> None:
        code, stdout, stderr = run_cli(
            self.args("export", "2", "--format", "json", "--output", str(self.root))
        )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        exported = self.root / "egg-soup.json"
        self.assertTrue(exported.exists())
        payload = json.loads(exported.read_text())
        self.assertEqual(payload["title"], "Egg Soup")

    def test_show_json_returns_full_recipe_object(self) -> None:
        code, stdout, stderr = run_cli(self.args("show", "2", "--format", "json"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["id"], "egg-soup")
        self.assertEqual(payload["ingredients"], "broth\negg")
        self.assertEqual(payload["images"][0]["extension"], ".jpg")

    def test_export_prints_destination_path(self) -> None:
        code, stdout, stderr = run_cli(
            self.args("export", "2", "--output", str(self.root))
        )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        exported = self.root / "egg-soup.melarecipe"
        self.assertTrue(exported.exists())
        self.assertIn("egg-soup.melarecipe", stdout)

    def test_tags_json_is_machine_readable(self) -> None:
        code, stdout, stderr = run_cli(self.args("tags", "--format", "json"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(all(set(item) == {"tag", "count"} for item in payload))
        self.assertEqual(payload[0], {"tag": "Breakfast", "count": 2})

    def test_stats_json_is_machine_readable(self) -> None:
        code, stdout, stderr = run_cli(self.args("stats", "--format", "json"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(
            payload,
            {
                "recipes": 4,
                "favorites": 1,
                "wantToCook": 1,
                "tags": 3,
                "recipesWithImages": 3,
                "recipesWithLinks": 3,
            },
        )

    def test_list_json_uses_rich_summary_schema(self) -> None:
        code, stdout, stderr = run_cli(self.args("list", "--format", "json"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        recipe = next(item for item in payload if item["pk"] == 1)
        self.assertEqual(
            recipe,
            {
                "pk": 1,
                "id": "breakfast-egg-bites",
                "title": "Egg Bites",
                "link": "https://example.com/recipe-1",
                "favorite": True,
                "wantToCook": False,
                "createdAt": "2020-01-06T10:40:00Z",
                "prepTime": "5 min",
                "cookTime": "10 min",
                "totalTime": "15 min",
                "yield": "8",
                "imageCount": 1,
                "tags": ["Breakfast", "Sous Vide"],
            },
        )

    def test_list_csv_uses_fixed_header_order(self) -> None:
        code, stdout, stderr = run_cli(self.args("list", "--format", "csv"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            stdout.splitlines()[0],
            "pk,id,title,tags,favorite,wantToCook,link,createdAt,prepTime,cookTime,totalTime,yield,imageCount",
        )
        rows = list(csv.DictReader(io.StringIO(stdout)))
        recipe = next(item for item in rows if item["pk"] == "1")
        self.assertEqual(recipe["tags"], "Breakfast;Sous Vide")
        self.assertEqual(recipe["favorite"], "true")
        self.assertEqual(recipe["imageCount"], "1")

    def test_search_csv_returns_summary_rows(self) -> None:
        code, stdout, stderr = run_cli(self.args("search", "weekend", "--format", "csv"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        rows = list(csv.DictReader(io.StringIO(stdout)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Brunch Bites")
        self.assertEqual(rows[0]["id"], "Egg Soup Deluxe")

    def test_doctor_json_reports_overrides(self) -> None:
        code, stdout, stderr = run_cli(self.args("doctor", "--format", "json"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(
            set(payload),
            {
                "ok",
                "supportedPlatform",
                "bundleId",
                "applicationGroup",
                "appPath",
                "appPathSource",
                "appExists",
                "dbPath",
                "dbPathSource",
                "dbExists",
                "supportDir",
                "supportDirSource",
                "supportDirExists",
                "compressionTool",
                "compressionToolSource",
                "compressionToolResolvedPath",
                "compressionToolAvailable",
                "canReadCatalog",
                "canDecodeExternalImages",
                "recipeCount",
                "warnings",
            },
        )
        self.assertEqual(payload["dbPathSource"], "cli flag")
        self.assertTrue(payload["dbExists"])
        self.assertIsInstance(payload["warnings"], list)

    def test_ambiguous_selector_is_reported_on_stderr(self) -> None:
        code, stdout, stderr = run_cli(self.args("show", "Egg Bites"))
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("matched multiple recipes", stderr)

    def test_record_id_prefix_selector_resolves_in_cli(self) -> None:
        code, stdout, stderr = run_cli(self.args("show", "egg-s"))
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Egg Soup", stdout)


if __name__ == "__main__":
    unittest.main()
