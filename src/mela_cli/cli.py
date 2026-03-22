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
Environment variables (each overrides the corresponding flag):
  MELA_APP_PATH          path to Mela.app
  MELA_DB_PATH           path to Curcuma.sqlite
  MELA_SUPPORT_DIR       path to the Core Data external blob directory
  MELA_COMPRESSION_TOOL  path or name of the compression_tool binary

Run 'mela <command> --help' for command-specific options and examples.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only CLI for browsing and exporting recipes from the Mela macOS app.",
        epilog=ENV_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--app-path", type=Path, metavar="PATH", help="Override path to Mela.app.")
    parser.add_argument("--db-path", type=Path, metavar="PATH", help="Override path to Curcuma.sqlite.")
    parser.add_argument(
        "--support-dir",
        type=Path,
        metavar="PATH",
        help="Override path to the Core Data external blob directory (_EXTERNAL_DATA).",
    )
    parser.add_argument(
        "--compression-tool",
        metavar="CMD",
        help="Override path or name of the macOS compression_tool binary.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser(
        "list",
        help="List recipes in the catalog.",
        description=(
            "List recipes as a table, JSON array, or CSV. Columns: PK, F (★ favorite), "
            "W (◎ want-to-cook), Title, Tags. Combine filters freely."
        ),
        epilog=(
            "Examples:\n"
            "  mela list                          # all recipes\n"
            "  mela list -q soup                  # text search\n"
            "  mela list -f -t Breakfast          # favorites tagged Breakfast\n"
            "  mela list --format json            # JSON array of summaries\n"
            "  mela list --format csv             # CSV export of full summary\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    list_parser.add_argument("-q", "--query", help="Case-insensitive text search.")
    add_recipe_filters(list_parser)
    add_summary_output_option(list_parser)
    list_parser.set_defaults(handler=handle_list)

    search_parser = subparsers.add_parser(
        "search",
        help="Search recipes by text (alias for 'list --query').",
        description="Search recipes by text query. Equivalent to 'mela list --query QUERY'.",
        epilog=(
            "Examples:\n"
            "  mela search soup\n"
            "  mela search soup -f --format json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    search_parser.add_argument("query", help="Case-insensitive query string.")
    add_recipe_filters(search_parser)
    add_summary_output_option(search_parser)
    search_parser.set_defaults(handler=handle_list)

    show_parser = subparsers.add_parser(
        "show",
        help="Show one recipe.",
        description=(
            "Show a single recipe. Accepts a numeric PK, exact title, Mela record ID, "
            "or a unique prefix/fragment of either. Ambiguous selectors fail with suggested PKs."
        ),
        epilog=(
            "Examples:\n"
            "  mela show 42\n"
            "  mela show 'Egg Bites'\n"
            "  mela show egg            # unique title fragment\n"
            "  mela show 42 --format markdown\n"
            "  mela show 42 --format json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show_parser.add_argument(
        "selector",
        help="Recipe PK, exact record ID, exact title, unique record-ID prefix, or unique title fragment.",
    )
    show_parser.add_argument(
        "--format",
        choices=("text", "markdown", "json"),
        default="text",
        help="Output format: text (terminal-friendly, default), markdown, or json (full recipe object).",
    )
    show_parser.set_defaults(handler=handle_show)

    export_parser = subparsers.add_parser(
        "export",
        help="Export one recipe to a file.",
        description=(
            "Export a single recipe to a file. The default format is melarecipe — a JSON file "
            "that Mela can import directly via File > Import. Use json for automation or markdown "
            "for plain-text archiving."
        ),
        epilog=(
            "Examples:\n"
            "  mela export 'Egg Bites'                      # .melarecipe in current dir\n"
            "  mela export 42 -o ./exports                  # write to ./exports/\n"
            "  mela export 42 --format json --compact       # minified JSON\n"
            "  mela export 42 --format markdown             # Markdown file\n"
            "  mela export 42 --filename-style id           # filename is the record UUID\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_parser.add_argument(
        "selector",
        help="Recipe PK, exact record ID, exact title, unique record-ID prefix, or unique title fragment.",
    )
    export_parser.add_argument(
        "--format",
        choices=("melarecipe", "json", "markdown"),
        default="melarecipe",
        help=(
            "Export format: melarecipe (Mela-importable JSON, default), "
            "json (full recipe object), or markdown."
        ),
    )
    export_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("."),
        help="Directory to write the exported file (default: current directory).",
    )
    export_parser.add_argument(
        "--filename-style",
        choices=("slug", "id", "id-slug"),
        default="slug",
        dest="filename_style",
        help=(
            "Filename style: slug (title-based slug, default), id (record UUID), "
            "or id-slug (UUID + title slug)."
        ),
    )
    export_parser.add_argument(
        "--compact",
        action="store_true",
        help="Minify JSON output for melarecipe/json exports; ignored for markdown.",
    )
    export_parser.set_defaults(handler=handle_export)

    export_all_parser = subparsers.add_parser(
        "export-all",
        help="Bulk export recipes to a directory.",
        description=(
            "Export multiple recipes to a directory, one file per recipe. "
            "Accepts the same filters as 'list'. The default format is melarecipe — "
            "a JSON file that Mela can import directly via File > Import."
        ),
        epilog=(
            "Examples:\n"
            "  mela export-all -o ./exports                     # all recipes\n"
            "  mela export-all -t Dessert -o ./desserts         # one tag\n"
            "  mela export-all -f --format markdown -o ./md    # favorites as Markdown\n"
            "  mela export-all -q soup --filename-style id-slug # UUID+title filenames\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export_all_parser.add_argument("-q", "--query", help="Case-insensitive text search to filter exported recipes.")
    add_recipe_filters(export_all_parser)
    export_all_parser.add_argument(
        "--format",
        choices=("melarecipe", "json", "markdown"),
        default="melarecipe",
        help=(
            "Export format: melarecipe (Mela-importable JSON, default), "
            "json (full recipe object), or markdown."
        ),
    )
    export_all_parser.add_argument(
        "--filename-style",
        choices=("slug", "id", "id-slug"),
        default="slug",
        dest="filename_style",
        help=(
            "Filename style: slug (title-based slug, default), id (record UUID), "
            "or id-slug (UUID + title slug)."
        ),
    )
    export_all_parser.add_argument(
        "--compact",
        action="store_true",
        help="Minify JSON output for melarecipe/json exports; ignored for markdown.",
    )
    export_all_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("."),
        help="Directory to write exported files (default: current directory).",
    )
    export_all_parser.set_defaults(handler=handle_export_all)

    tags_parser = subparsers.add_parser(
        "tags",
        help="List tags and usage counts.",
        description="List all tags with recipe counts, sorted by count descending.",
    )
    add_table_json_output_option(tags_parser)
    tags_parser.set_defaults(handler=handle_tags)

    stats_parser = subparsers.add_parser(
        "stats",
        help="Show catalog statistics.",
        description="Show aggregate statistics for the catalog: recipe count, favorites, images, links, and tags.",
    )
    add_table_json_output_option(stats_parser)
    stats_parser.set_defaults(handler=handle_stats)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnose setup and path discovery.",
        description=(
            "Show what mela discovered about your Mela install: app path, database path, "
            "support directory, compression tool, and whether the catalog is readable. "
            "Run this first if any command fails to find the database."
        ),
    )
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
        metavar="TAG",
        help="Filter by tag. Can be passed multiple times.",
    )
    parser.add_argument("-n", "--limit", type=int, help="Maximum number of recipes to return.")


def add_summary_output_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        help="Output format (default: table).",
    )


def add_table_json_output_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format (default: table).",
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
