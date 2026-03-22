from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mela_cli.cli import default_export_path
from mela_cli.store import AmbiguousRecipeError, MelaStore
from mela_cli.utils import slugify
from tests.support import JPEG_BYTES, build_keyed_archive, create_fixture_store


class MelaStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path, self.support_dir = create_fixture_store(self.root)
        self.store = MelaStore(db_path=self.db_path, support_dir=self.support_dir)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_list_recipes_returns_filtered_summaries(self) -> None:
        recipes = self.store.list_recipes(favorite=True)
        self.assertEqual([recipe.title for recipe in recipes], ["Egg Bites"])

    def test_search_recipes_matches_notes_and_text(self) -> None:
        recipes = self.store.list_recipes(query="weekend")
        self.assertEqual([recipe.title for recipe in recipes], ["Brunch Bites"])

    def test_selector_title_fragment_resolves_unique_match(self) -> None:
        recipe = self.store.get_recipe("Soup")
        self.assertEqual(recipe.identifier, "egg-soup")

    def test_selector_record_id_prefix_resolves_unique_match(self) -> None:
        recipe = self.store.get_recipe("egg-s")
        self.assertEqual(recipe.identifier, "egg-soup")

    def test_exact_title_wins_before_record_id_prefix(self) -> None:
        recipe = self.store.get_recipe("Egg Soup")
        self.assertEqual(recipe.identifier, "egg-soup")

    def test_duplicate_exact_title_is_ambiguous(self) -> None:
        with self.assertRaises(AmbiguousRecipeError):
            self.store.get_recipe("Egg Bites")

    def test_ambiguous_record_id_prefix_is_reported(self) -> None:
        with self.assertRaises(AmbiguousRecipeError):
            self.store.get_recipe("breakfast-egg")

    def test_inline_and_raw_external_images_decode(self) -> None:
        recipe_one = self.store.get_recipe("1")
        recipe_two = self.store.get_recipe("2")
        self.assertEqual(recipe_one.images[0].data, JPEG_BYTES)
        self.assertEqual(recipe_two.images[0].data, JPEG_BYTES)

    def test_lzfse_archive_reference_uses_archive_parser(self) -> None:
        archive = build_keyed_archive(JPEG_BYTES)
        with patch.object(self.store, "_decode_lzfse_file", return_value=archive):
            recipe = self.store.get_recipe("3")
        self.assertEqual(recipe.images[0].data, JPEG_BYTES)

    def test_list_tags_returns_counts(self) -> None:
        tags = self.store.list_tags()
        self.assertEqual(tags[0].to_json_dict(), {"tag": "Breakfast", "count": 2})
        self.assertEqual(tags[1].to_json_dict(), {"tag": "Soup", "count": 1})

    def test_summary_json_contains_rich_summary_fields(self) -> None:
        summary = next(recipe for recipe in self.store.list_recipes() if recipe.pk == 1)
        self.assertEqual(
            summary.to_json_dict(),
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

    def test_stats_are_aggregated(self) -> None:
        stats = self.store.get_stats()
        self.assertEqual(
            stats.to_json_dict(),
            {
                "recipes": 4,
                "favorites": 1,
                "wantToCook": 1,
                "tags": 3,
                "recipesWithImages": 3,
                "recipesWithLinks": 3,
            },
        )


class CliHelperTests(unittest.TestCase):
    def test_slugify_normalizes_unicode(self) -> None:
        self.assertEqual(slugify("Creme Brulee"), "creme-brulee")

    def test_default_export_path_uses_sanitized_title(self) -> None:
        recipe = type("RecipeStub", (), {"title": "Creme Brulee"})()
        path = default_export_path(recipe, "melarecipe", Path("/tmp"))
        self.assertEqual(path, Path("/tmp/creme-brulee.melarecipe"))


if __name__ == "__main__":
    unittest.main()
