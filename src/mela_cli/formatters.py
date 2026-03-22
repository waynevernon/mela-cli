from __future__ import annotations

import csv
import io

from mela_cli.discovery import DiscoveryResult
from mela_cli.store import SUMMARY_FIELD_NAMES, CatalogStats, Recipe, RecipeSummary, TagSummary
from mela_cli.utils import bold, cyan, dim, green, json_dumps, mini_bar, red, section_rule, shorten, yellow


def render_summary_table(recipes: list[RecipeSummary]) -> str:
    if not recipes:
        return "No recipes found.\n"

    title_width = min(max(len(recipe.title) for recipe in recipes), 48)
    header = f"{'PK':>4}  {'F':<2}  {'W':<2}  {'Title':<{title_width}}  Tags"
    rule = dim(f"{'─' * 4}  {'─' * 2}  {'─' * 2}  {'─' * title_width}  {'─' * 20}")
    lines = [bold(header), rule]
    for recipe in recipes:
        fav = (yellow("★") + " ") if recipe.favorite else "  "
        wtc = (cyan("◎") + " ") if recipe.want_to_cook else "  "
        title_plain = f"{shorten(recipe.title, title_width):<{title_width}}"
        title_out = bold(title_plain) if recipe.favorite else title_plain
        tags = dim(cyan(", ".join(recipe.tags))) if recipe.tags else ""
        lines.append(f"{dim(f'{recipe.pk:>4}')}  {fav}  {wtc}  {title_out}  {tags}")
    lines.append("")
    count = len(recipes)
    lines.append(dim(f"{count} {'recipe' if count == 1 else 'recipes'}"))
    return "\n".join(lines) + "\n"


def render_summary_csv(recipes: list[RecipeSummary]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=SUMMARY_FIELD_NAMES, lineterminator="\n")
    writer.writeheader()
    for recipe in recipes:
        writer.writerow(recipe.to_csv_dict())
    return buffer.getvalue()


def render_recipe_text(recipe: Recipe) -> str:
    rule_width = max(len(recipe.title), 48)
    lines: list[str] = [bold(recipe.title), dim("─" * rule_width), ""]

    # Compact metadata block
    meta: list[str] = []

    flags: list[str] = []
    if recipe.favorite:
        flags.append(f"{yellow('★')} Favorite")
    if recipe.want_to_cook:
        flags.append(f"{cyan('◎')} Want to cook")
    if recipe.tags:
        flags.append(cyan(", ".join(recipe.tags)))
    if flags:
        meta.append("  " + dim("  ·  ").join(flags))

    times: list[str] = []
    if recipe.prep_time:
        times.append(f"Prep {recipe.prep_time}")
    if recipe.cook_time:
        times.append(f"Cook {recipe.cook_time}")
    if recipe.total_time:
        times.append(f"Total {recipe.total_time}")
    if recipe.yield_value:
        times.append(f"Serves {recipe.yield_value}")
    if times:
        meta.append(dim("  " + "  ·  ".join(times)))

    link_parts: list[str] = []
    if recipe.link:
        link_parts.append(recipe.link)
    if recipe.created_at:
        link_parts.append(f"Added {recipe.created_at}")
    if link_parts:
        meta.append(dim("  " + "  ·  ".join(link_parts)))

    lines.extend(meta)
    lines.append("")

    if recipe.text:
        lines.extend([section_rule("Summary"), "", *_indent(recipe.text.strip()), ""])
    if recipe.ingredients:
        lines.extend([section_rule("Ingredients"), "", *_indent(recipe.ingredients.strip()), ""])
    if recipe.instructions:
        lines.extend([section_rule("Instructions"), "", *_indent(recipe.instructions.strip()), ""])
    if recipe.notes:
        lines.extend([section_rule("Notes"), "", *_indent(recipe.notes.strip()), ""])
    if recipe.nutrition:
        lines.extend([section_rule("Nutrition"), "", *_indent(recipe.nutrition.strip()), ""])

    return "\n".join(lines).rstrip() + "\n"


def _indent(text: str, prefix: str = "  ") -> list[str]:
    return [prefix + line if line.strip() else "" for line in text.splitlines()]


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
    name_width = min(max(len(tag.name) for tag in tags), 48)
    max_count = max(tag.count for tag in tags)
    header = f"{'Count':>5}  {'Bar':<20}  {'Tag':<{name_width}}"
    rule = dim(f"{'─' * 5}  {'─' * 20}  {'─' * name_width}")
    lines = [bold(header), rule]
    for tag in tags:
        bar = mini_bar(tag.count, max_count, width=20)
        lines.append(f"{tag.count:>5}  {bar}  {cyan(shorten(tag.name, name_width))}")
    lines.append("")
    count = len(tags)
    lines.append(dim(f"{count} {'tag' if count == 1 else 'tags'}"))
    return "\n".join(lines) + "\n"


def render_stats_table(stats: CatalogStats) -> str:
    label_width = 20
    lines: list[str] = []

    def plain_row(label: str, value: int) -> str:
        return f"{dim(f'{label:<{label_width}}')}  {value}"

    def bar_row(label: str, value: int, total: int) -> str:
        pct = round(value / total * 100) if total else 0
        bar = mini_bar(value, total, width=20)
        return f"{dim(f'{label:<{label_width}}')}  {value:>4}  {bar}  {pct:>3}%"

    lines.append(plain_row("Recipes", stats.recipes))
    lines.append(bar_row("Favorites", stats.favorites, stats.recipes))
    lines.append(bar_row("Want to cook", stats.want_to_cook, stats.recipes))
    lines.append(plain_row("Tags", stats.tags))
    lines.append(bar_row("With images", stats.recipes_with_images, stats.recipes))
    lines.append(bar_row("With links", stats.recipes_with_links, stats.recipes))
    return "\n".join(lines) + "\n"


def render_doctor_report(result: DiscoveryResult, output_format: str) -> str:
    if output_format == "json":
        return json_dumps(result.to_json_dict())

    def check(v: bool) -> str:
        return green("✓") if v else red("✗")

    W = 11  # len("Compression")

    def lbl(s: str) -> str:
        return bold(f"{s:<{W}}")

    indent = " " * W

    lines: list[str] = []

    # Platform
    lines.append(f"{lbl('Platform')}  macOS  {check(result.supported_platform)}")
    lines.append("")

    # Path group
    def path_row(label: str, path: object, source: str, exists: bool) -> None:
        lines.append(f"{lbl(label)}  {stringify_path(path)}")
        lines.append(f"{indent}  {dim(source)}  {check(exists)}")

    path_row("App", result.app_path, result.app_path_source, result.app_exists)
    path_row("Database", result.db_path, result.db_path_source, result.db_exists)
    path_row("Support", result.support_dir, result.support_dir_source, result.support_dir_exists)
    lines.append("")

    # Compression
    tool_path = result.compression_tool_resolved_path or dim("(not found)")
    lines.append(
        f"{lbl('Compression')}  {result.compression_tool} → {tool_path}  "
        f"{dim(result.compression_tool_source)}  {check(result.compression_tool_available)}"
    )
    lines.append("")

    # Catalog summary
    count = str(result.recipe_count) if result.recipe_count is not None else dim("unknown")
    catalog_parts = [
        f"{count} recipes",
        f"readable {check(result.can_read_catalog)}",
        f"images {check(result.can_decode_external_images)}",
    ]
    lines.append(f"{lbl('Catalog')}  {'  ·  '.join(catalog_parts)}")

    if result.warnings:
        lines.append("")
        for warning in result.warnings:
            lines.append(f"{yellow('⚠')}  {warning}")

    return "\n".join(lines) + "\n"


def stringify_path(path: object) -> str:
    return str(path) if path else dim("(not found)")


def yes_no(value: bool) -> str:
    return green("yes") if value else dim("no")
