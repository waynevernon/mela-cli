from __future__ import annotations

import csv
import io

from mela_cli.discovery import DiscoveryResult
from mela_cli.store import SUMMARY_FIELD_NAMES, CatalogStats, Recipe, RecipeSummary, TagSummary
from mela_cli.utils import json_dumps, shorten


def render_summary_table(recipes: list[RecipeSummary]) -> str:
    if not recipes:
        return "No recipes found.\n"

    title_width = min(max(len(recipe.title) for recipe in recipes), 48)
    lines = [
        f"{'PK':>4}  {'F':1}  {'W':1}  {'Title':<{title_width}}  Tags",
        f"{'-' * 4}  {'-'}  {'-'}  {'-' * title_width}  {'-' * 20}",
    ]
    for recipe in recipes:
        lines.append(
            f"{recipe.pk:>4}  "
            f"{'Y' if recipe.favorite else '.':1}  "
            f"{'Y' if recipe.want_to_cook else '.':1}  "
            f"{shorten(recipe.title, title_width):<{title_width}}  "
            f"{', '.join(recipe.tags)}"
        )
    lines.append("")
    lines.append(f"{len(recipes)} recipe(s)")
    return "\n".join(lines) + "\n"


def render_summary_csv(recipes: list[RecipeSummary]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SUMMARY_FIELD_NAMES, lineterminator="\n")
    writer.writeheader()
    for recipe in recipes:
        writer.writerow(recipe.to_csv_dict())
    return buffer.getvalue()


def render_recipe_text(recipe: Recipe) -> str:
    lines: list[str] = [recipe.title, "=" * len(recipe.title), ""]
    lines.extend(
        [
            f"ID: {recipe.identifier}",
            f"Favorite: {'yes' if recipe.favorite else 'no'}",
            f"Want to cook: {'yes' if recipe.want_to_cook else 'no'}",
        ]
    )
    if recipe.tags:
        lines.append(f"Tags: {', '.join(recipe.tags)}")
    if recipe.link:
        lines.append(f"Link: {recipe.link}")
    if recipe.created_at:
        lines.append(f"Added: {recipe.created_at}")
    if recipe.prep_time:
        lines.append(f"Prep time: {recipe.prep_time}")
    if recipe.cook_time:
        lines.append(f"Cook time: {recipe.cook_time}")
    if recipe.total_time:
        lines.append(f"Total time: {recipe.total_time}")
    if recipe.yield_value:
        lines.append(f"Yield: {recipe.yield_value}")
    lines.append(f"Images: {len(recipe.images)}")
    lines.append("")

    if recipe.text:
        lines.extend(["Summary", "-------", recipe.text.strip(), ""])
    if recipe.ingredients:
        lines.extend(["Ingredients", "-----------", recipe.ingredients.strip(), ""])
    if recipe.instructions:
        lines.extend(["Instructions", "------------", recipe.instructions.strip(), ""])
    if recipe.notes:
        lines.extend(["Notes", "-----", recipe.notes.strip(), ""])
    if recipe.nutrition:
        lines.extend(["Nutrition", "---------", recipe.nutrition.strip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def render_recipe_markdown(recipe: Recipe) -> str:
    lines: list[str] = [f"# {recipe.title}", ""]
    if recipe.text:
        lines.extend([recipe.text.strip(), ""])
    lines.extend(
        [
            f"- ID: `{recipe.identifier}`",
            f"- Favorite: {'yes' if recipe.favorite else 'no'}",
            f"- Want to cook: {'yes' if recipe.want_to_cook else 'no'}",
        ]
    )
    if recipe.tags:
        lines.append(f"- Tags: {', '.join(recipe.tags)}")
    if recipe.link:
        lines.append(f"- Link: {recipe.link}")
    if recipe.created_at:
        lines.append(f"- Added: {recipe.created_at}")
    if recipe.prep_time:
        lines.append(f"- Prep time: {recipe.prep_time}")
    if recipe.cook_time:
        lines.append(f"- Cook time: {recipe.cook_time}")
    if recipe.total_time:
        lines.append(f"- Total time: {recipe.total_time}")
    if recipe.yield_value:
        lines.append(f"- Yield: {recipe.yield_value}")
    lines.append(f"- Images: {len(recipe.images)}")
    lines.append("")
    if recipe.ingredients:
        lines.extend(["## Ingredients", "", recipe.ingredients.strip(), ""])
    if recipe.instructions:
        lines.extend(["## Instructions", "", recipe.instructions.strip(), ""])
    if recipe.notes:
        lines.extend(["## Notes", "", recipe.notes.strip(), ""])
    if recipe.nutrition:
        lines.extend(["## Nutrition", "", recipe.nutrition.strip(), ""])
    return "\n".join(lines).rstrip() + "\n"


def render_tag_table(tags: list[TagSummary]) -> str:
    if not tags:
        return "No tags found.\n"
    width = min(max(len(tag.name) for tag in tags), 48)
    lines = [
        f"{'Count':>5}  {'Tag':<{width}}",
        f"{'-' * 5}  {'-' * width}",
    ]
    for tag in tags:
        lines.append(f"{tag.count:>5}  {shorten(tag.name, width):<{width}}")
    lines.append("")
    lines.append(f"{len(tags)} tag(s)")
    return "\n".join(lines) + "\n"


def render_stats_table(stats: CatalogStats) -> str:
    rows = [
        ("Recipes", str(stats.recipes)),
        ("Favorites", str(stats.favorites)),
        ("Want to cook", str(stats.want_to_cook)),
        ("Tags", str(stats.tags)),
        ("Recipes with images", str(stats.recipes_with_images)),
        ("Recipes with links", str(stats.recipes_with_links)),
    ]
    return render_key_value_rows(rows)


def render_doctor_report(result: DiscoveryResult, output_format: str) -> str:
    if output_format == "json":
        return json_dumps(result.to_json_dict())
    rows = [
        ("OK", yes_no(result.ok)),
        ("Supported platform", yes_no(result.supported_platform)),
        ("Bundle ID", result.bundle_id or "(not found)"),
        ("Application group", result.application_group or "(not found)"),
        ("App path", stringify_path(result.app_path)),
        ("App path source", result.app_path_source),
        ("App exists", yes_no(result.app_exists)),
        ("DB path", stringify_path(result.db_path)),
        ("DB path source", result.db_path_source),
        ("DB exists", yes_no(result.db_exists)),
        ("Support dir", stringify_path(result.support_dir)),
        ("Support dir source", result.support_dir_source),
        ("Support dir exists", yes_no(result.support_dir_exists)),
        ("Compression tool", result.compression_tool),
        ("Compression tool source", result.compression_tool_source),
        ("Compression tool path", result.compression_tool_resolved_path or "(not found)"),
        ("Compression tool available", yes_no(result.compression_tool_available)),
        ("Can read catalog", yes_no(result.can_read_catalog)),
        ("Can decode external images", yes_no(result.can_decode_external_images)),
        ("Recipe count", str(result.recipe_count) if result.recipe_count is not None else "(unknown)"),
    ]
    if result.warnings:
        rows.append(("Warnings", "\n".join(result.warnings)))
    return render_key_value_rows(rows)


def render_key_value_rows(rows: list[tuple[str, str]]) -> str:
    width = max(len(label) for label, _ in rows)
    lines: list[str] = []
    for label, value in rows:
        if "\n" in value:
            first, *rest = value.splitlines()
            lines.append(f"{label:<{width}} : {first}")
            for item in rest:
                lines.append(f"{'':<{width}}   {item}")
        else:
            lines.append(f"{label:<{width}} : {value}")
    return "\n".join(lines) + "\n"


def stringify_path(path: object) -> str:
    return str(path) if path else "(not found)"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"
