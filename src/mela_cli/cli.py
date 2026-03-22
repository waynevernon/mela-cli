from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

from mela_cli import __version__
from mela_cli.discovery import DiscoveryResult, discover_mela
from mela_cli.formatters import (
    render_doctor_report,
    render_recipe_markdown,
    render_recipe_text,
    render_stats_table,
    render_summary_csv,
    render_summary_table,
    render_tag_table,
)
from mela_cli.store import (
    AmbiguousRecipeError,
    MelaError,
    MelaStore,
    Recipe,
    RecipeNotFoundError,
    RecipeSummary,
)
from mela_cli.utils import json_dumps, slugify

ENV_EPILOG = """
Environment variables:
  MELA_APP_PATH
  MELA_DB_PATH
  MELA_SUPPORT_DIR
  MELA_COMPRESSION_TOOL
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only CLI for browsing and exporting recipes from the Mela macOS app.",
        epilog=ENV_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--app-path", type=Path, help="Path to the installed Mela.app bundle.")
    parser.add_argument("--db-path", type=Path, help="Path to Curcuma.sqlite.")
    parser.add_argument(
        "--support-dir",
        type=Path,
        help="Path to Core Data external blob storage (_EXTERNAL_DATA).",
    )
    parser.add_argument(
        "--compression-tool",
        help="Path or command name for macOS compression_tool.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List recipes in the catalog.")
    list_parser.add_argument("-q", "--query", help="Case-insensitive text search.")
    add_recipe_filters(list_parser)
    add_summary_output_option(list_parser)
    list_parser.set_defaults(handler=handle_list)

    search_parser = subparsers.add_parser("search", help="Alias for 'list --query'.")
    search_parser.add_argument("query", help="Case-insensitive query string.")
    add_recipe_filters(search_parser)
    add_summary_output_option(search_parser)
    search_parser.set_defaults(handler=handle_list)

    show_parser = subparsers.add_parser("show", help="Show one recipe.")
    show_parser.add_argument(
        "selector",
        help="Recipe PK, exact record ID, exact title, unique record-ID prefix, or unique title fragment.",
    )
    show_parser.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        default="text",
        help="Output format.",
    )
    show_parser.set_defaults(handler=handle_show)

    export_parser = subparsers.add_parser("export", help="Export one recipe.")
    export_parser.add_argument(
        "selector",
        help="Recipe PK, exact record ID, exact title, unique record-ID prefix, or unique title fragment.",
    )
    export_parser.add_argument(
        "--format",
        choices=("melarecipe", "json", "markdown"),
        default="melarecipe",
        help="Export format.",
    )
    export_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("."),
        help="Directory to write exported files (default: current directory).",
    )
    export_parser.add_argument(
        "--filename-style",
        choices=("slug", "id", "id-slug"),
        default="slug",
        dest="filename_style",
        help="Filename style: slug (title-based, default), id (record UUID), or id-slug.",
    )
    export_parser.add_argument(
        "--compact",
        action="store_true",
        help="Minify JSON output for melarecipe/json exports; ignored for markdown.",
    )
    export_parser.set_defaults(handler=handle_export)

    export_all_parser = subparsers.add_parser("export-all", help="Export multiple recipes.")
    export_all_parser.add_argument("-q", "--query", help="Text search to filter exported recipes.")
    add_recipe_filters(export_all_parser)
    export_all_parser.add_argument(
        "--format",
        choices=("melarecipe", "json", "markdown"),
        default="melarecipe",
        help="Export format.",
    )
    export_all_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("."),
        help="Directory to write exported files (default: current directory).",
    )
    export_all_parser.add_argument(
        "--compact",
        action="store_true",
        help="Minify JSON output for melarecipe/json exports; ignored for markdown.",
    )
    export_all_parser.add_argument(
        "--filename-style",
        choices=("slug", "id", "id-slug"),
        default="slug",
        dest="filename_style",
        help="Filename style: slug (title-based, default), id (record UUID), or id-slug (UUID + title).",
    )
    export_all_parser.set_defaults(handler=handle_export_all)

    tags_parser = subparsers.add_parser("tags", help="List tags and usage counts.")
    add_table_json_output_option(tags_parser)
    tags_parser.set_defaults(handler=handle_tags)

    stats_parser = subparsers.add_parser("stats", help="Show catalog statistics.")
    add_table_json_output_option(stats_parser)
    stats_parser.set_defaults(handler=handle_stats)

    doctor_parser = subparsers.add_parser("doctor", help="Inspect discovery and runtime prerequisites.")
    add_table_json_output_option(doctor_parser)
    doctor_parser.set_defaults(handler=handle_doctor)

    return parser


def add_recipe_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-f", "--favorite", action="store_true", help="Only include favorite recipes.")
    parser.add_argument(
        "-w",
        "--want-to-cook",
        action="store_true",
        help="Only include recipes marked want-to-cook.",
    )
    parser.add_argument(
        "-t",
        "--tag",
        action="append",
        default=[],
        dest="tags",
        help="Filter by tag. Can be passed multiple times.",
    )
    parser.add_argument("-n", "--limit", type=int, help="Maximum number of recipes to return.")


def add_summary_output_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        help="Output format.",
    )


def add_table_json_output_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if not argv and len(sys.argv) == 1:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    discovery = discover_mela(
        app_path=args.app_path,
        db_path=args.db_path,
        support_dir=args.support_dir,
        compression_tool=args.compression_tool,
        env=os.environ,
    )

    try:
        return int(args.handler(args, discovery) or 0)
    except (RecipeNotFoundError, AmbiguousRecipeError, MelaError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def handle_list(args: argparse.Namespace, discovery: DiscoveryResult) -> int:
    store = open_store(discovery)
    try:
        recipes = store.list_recipes(
            query=getattr(args, "query", None),
            favorite=args.favorite,
            want_to_cook=args.want_to_cook,
            tags=args.tags,
            limit=args.limit,
        )
    finally:
        store.close()

    write_summary_output(recipes, args.format)
    return 0


def handle_show(args: argparse.Namespace, discovery: DiscoveryResult) -> int:
    store = open_store(discovery)
    try:
        recipe = store.get_recipe(args.selector)
    finally:
        store.close()

    if args.format == "json":
        sys.stdout.write(json_dumps(recipe.to_json_dict()))
    elif args.format == "markdown":
        sys.stdout.write(render_recipe_markdown(recipe))
    else:
        sys.stdout.write(render_recipe_text(recipe))
    return 0


def handle_export(args: argparse.Namespace, discovery: DiscoveryResult) -> int:
    store = open_store(discovery)
    try:
        recipe = store.get_recipe(args.selector)
    finally:
        store.close()

    args.output.mkdir(parents=True, exist_ok=True)
    destination = default_export_path(recipe, args.format, args.output, args.filename_style)
    destination.write_text(render_export(recipe, args.format, compact=args.compact), encoding="utf-8")
    print(destination)
    return 0


def handle_export_all(args: argparse.Namespace, discovery: DiscoveryResult) -> int:
    store = open_store(discovery)
    try:
        summaries = store.list_recipes(
            query=args.query,
            favorite=args.favorite,
            want_to_cook=args.want_to_cook,
            tags=args.tags,
            limit=args.limit,
        )
        args.output.mkdir(parents=True, exist_ok=True)
        used_paths: set[Path] = set()
        for summary in summaries:
            recipe = store.get_recipe(str(summary.pk))
            path = default_export_path(recipe, args.format, args.output, args.filename_style)
            destination = path if args.filename_style != "slug" else unique_export_path(path, used_paths)
            destination.write_text(
                render_export(recipe, args.format, compact=args.compact),
                encoding="utf-8",
            )
            used_paths.add(destination)
    finally:
        store.close()
    return 0


def handle_tags(args: argparse.Namespace, discovery: DiscoveryResult) -> int:
    store = open_store(discovery)
    try:
        tags = store.list_tags()
    finally:
        store.close()

    if args.format == "json":
        sys.stdout.write(json_dumps([tag.to_json_dict() for tag in tags]))
    else:
        sys.stdout.write(render_tag_table(tags))
    return 0


def handle_stats(args: argparse.Namespace, discovery: DiscoveryResult) -> int:
    store = open_store(discovery)
    try:
        stats = store.get_stats()
    finally:
        store.close()

    if args.format == "json":
        sys.stdout.write(json_dumps(stats.to_json_dict()))
    else:
        sys.stdout.write(render_stats_table(stats))
    return 0


def handle_doctor(args: argparse.Namespace, discovery: DiscoveryResult) -> int:
    sys.stdout.write(render_doctor_report(discovery, output_format=args.format))
    return 0


def write_summary_output(recipes: list[RecipeSummary], output_format: str) -> None:
    if output_format == "json":
        sys.stdout.write(json_dumps([recipe.to_json_dict() for recipe in recipes]))
    elif output_format == "csv":
        sys.stdout.write(render_summary_csv(recipes))
    else:
        sys.stdout.write(render_summary_table(recipes))


def open_store(discovery: DiscoveryResult) -> MelaStore:
    if not discovery.supported_platform:
        raise MelaError("Mela CLI currently supports macOS only.")
    if discovery.db_path is None:
        raise MelaError(
            "Could not locate Curcuma.sqlite. Run `mela doctor` for discovery details."
        )
    if not discovery.db_path.exists():
        raise MelaError(
            f"Database path does not exist: {discovery.db_path}. Run `mela doctor` for details."
        )
    return MelaStore(
        db_path=discovery.db_path,
        support_dir=discovery.support_dir,
        compression_tool=discovery.compression_tool,
    )


def render_export(recipe: Recipe, export_format: str, compact: bool) -> str:
    if export_format == "melarecipe":
        return json_dumps(recipe.to_melarecipe_dict(), pretty=not compact)
    if export_format == "json":
        return json_dumps(recipe.to_json_dict(), pretty=not compact)
    if export_format == "markdown":
        return render_recipe_markdown(recipe)
    raise ValueError(f"Unsupported export format {export_format!r}.")


def default_export_path(
    recipe: Recipe, export_format: str, base_dir: Path, filename_style: str = "slug"
) -> Path:
    suffix = {
        "melarecipe": ".melarecipe",
        "json": ".json",
        "markdown": ".md",
    }[export_format]
    if filename_style == "id":
        stem = recipe.identifier
    elif filename_style == "id-slug":
        stem = f"{recipe.identifier}-{slugify(recipe.title)}"
    else:
        stem = slugify(recipe.title)
    return base_dir / f"{stem}{suffix}"


def unique_export_path(path: Path, used_paths: set[Path]) -> Path:
    if path not in used_paths and not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}-{counter}{suffix}")
        if candidate not in used_paths and not candidate.exists():
            return candidate
        counter += 1


def capture_help_output(argv: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout, stderr
    try:
        try:
            code = main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return code, stdout.getvalue() + stderr.getvalue()
