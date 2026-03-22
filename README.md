# Mela CLI

`mela` is a read-only macOS CLI for browsing and exporting recipes from the local Mela app catalog.

It reads Mela's local Core Data SQLite store directly and never writes to the live database.

## About Mela

[Mela](https://mela.recipes/) is a recipe manager for iOS and macOS with iCloud sync. The
official app supports collecting recipes from the web, feeds, and scans, then using them in
cook mode, meal planning, and groceries workflows. See the official
[Help](https://mela.recipes/help/) and [File Format Documentation](https://mela.recipes/fileformat/index.html)
for product details and the `melarecipe` / `melarecipes` formats.

## Project Relationship

`mela` is an unofficial companion CLI for people who want shell access to their local Mela
catalog. It is not the Mela app itself and it does not use an official Mela API.

## Why Read-only

Mela stores its live catalog in a local Core Data SQLite store inside its macOS app-group
container, and syncing is handled through CloudKit-backed Core Data state rather than simple
document files.

That makes read access practical, but direct writes are risky:

- raw SQLite writes would bypass the Core Data and CloudKit bookkeeping that Mela expects
- the live store includes sync/history metadata in addition to recipe content
- there is no documented public API for in-place catalog edits

`mela` therefore treats the local store as read-only. It is designed to be safe for browsing,
searching, diagnostics, and export. When you need a writable format, use `--format melarecipe`
or `export-all` to generate importable files rather than mutating the live database.

## Status

- Platform: macOS only
- Python: 3.11+
- Scope: read-only
- Primary install path: `pipx install mela-cli`

## What It Does

- Lists and searches recipes in your local Mela catalog as table, JSON, or CSV summaries
- Shows individual recipes in terminal-friendly text, Markdown, or JSON
- Exports recipes as `.melarecipe`, JSON, or Markdown
- Reports tags, catalog stats, and discovery/runtime diagnostics

## What It Does Not Do

- It does not write to Mela's live SQLite database
- It does not provide a supported import/write workflow yet
- It does not target non-macOS platforms

## Installation

Recommended:

```bash
pipx install mela-cli
```

Development install:

```bash
python3 -m pip install -e .
```

## Discovery

By default, `mela` tries to discover the official installed Mela app and derive the live catalog paths from the app's bundle metadata and group container layout.

Discovery precedence:

1. CLI flags
2. Environment variables
3. Auto-discovery

Supported overrides:

- `--app-path`
- `--db-path`
- `--support-dir`
- `--compression-tool`

Environment variables:

- `MELA_APP_PATH`
- `MELA_DB_PATH`
- `MELA_SUPPORT_DIR`
- `MELA_COMPRESSION_TOOL`

Use `mela doctor` to inspect what was discovered.

## Commands

```bash
mela list [-q QUERY] [-f] [-w] [-t TAG] [-n N] [--format table|json|csv]
mela search QUERY [-f] [-w] [-t TAG] [-n N] [--format table|json|csv]  # alias for list --query
mela show SELECTOR [--format text|markdown|json]
mela export SELECTOR [--format melarecipe|json|markdown] [-o DIR] [--filename-style slug|id|id-slug] [--compact]
mela export-all [-q QUERY] [-f] [-w] [-t TAG] [-n N] [--format melarecipe|json|markdown] [-o DIR] [--filename-style slug|id|id-slug] [--compact]
mela tags [--format table|json]
mela stats [--format table|json]
mela doctor [--format table|json]
```

Selector resolution order for single-recipe commands:

1. Numeric primary key
2. Exact Mela record ID
3. Exact title
4. Unique record-ID prefix
5. Unique title fragment

Ambiguous matches fail with a clear error and suggested PKs.

## Option Reference

Global options available before any subcommand:

- `--app-path`: override auto-discovery and point directly at `Mela.app`
- `--db-path`: use a specific `Curcuma.sqlite` file
- `--support-dir`: use a specific Core Data external blob directory
- `--compression-tool`: use a specific `compression_tool` path or command name

`list` options (`search` is an alias that takes the query as a positional argument):

- `-q`/`--query QUERY`: case-insensitive text search across recipe content
- `-f`/`--favorite`: only include favorite recipes
- `-w`/`--want-to-cook`: only include recipes marked want-to-cook
- `-t`/`--tag TAG`: filter by tag; repeat the flag to require multiple tags
- `-n`/`--limit N`: cap the number of returned recipes
- `--format table|json|csv`: choose human-readable table output or machine-readable JSON/CSV

`show` options:

- `SELECTOR`: recipe PK, exact record ID, exact title, unique record-ID prefix, or unique title fragment
- `--format text|markdown|json`: choose terminal text, Markdown, or full recipe JSON

`export` options:

- `SELECTOR`: same selector rules as `show`
- `--format melarecipe|json|markdown`: choose Mela import JSON, full recipe JSON, or Markdown
- `-o`/`--output DIR`: directory to write the exported file (default: current directory)
- `--filename-style slug|id|id-slug`: filename style — title-based slug (default), record UUID, or UUID + slug
- `--compact`: minify JSON output for `melarecipe` and `json` exports; ignored for `markdown`

`export-all` options:

- `-q`/`--query QUERY`: full-text filter across recipe content
- `-f`/`--favorite`, `-w`/`--want-to-cook`, `-t`/`--tag TAG`, `-n`/`--limit N`: same filtering as `list`
- `--format melarecipe|json|markdown`: output format for each exported recipe
- `-o`/`--output DIR`: destination directory for bulk exports (default: current directory)
- `--filename-style slug|id|id-slug`: filename style — title-based slug (default), record UUID, or UUID + slug
- `--compact`: minify JSON output for `melarecipe` and `json` exports; ignored for `markdown`

`tags`, `stats`, and `doctor` options:

- `--format table|json`: choose human-readable table output or machine-readable JSON

## Examples

List favorite recipes:

```bash
mela list --favorite
```

Search for soup recipes as JSON:

```bash
mela list -q soup --format json
```

Export the current summary catalog as CSV:

```bash
mela list --format csv
```

Show one recipe in Markdown:

```bash
mela show 42 --format markdown
```

Export one recipe as a Mela import file to the current directory:

```bash
mela export "Instant Pot Chicken Adobo"
```

Export one recipe to a specific directory, named by record ID:

```bash
mela export "Instant Pot Chicken Adobo" --output ./exports --filename-style id
```

Export minified JSON and inspect it:

```bash
mela export 42 --format json --compact | jq .
```

Export matching recipes to a directory:

```bash
mela export-all --tag Dessert --output ./desserts
```

Inspect runtime discovery:

```bash
mela doctor
```

## Machine-readable Output

JSON is the stable machine-readable interface for v1. CSV is the stable summary export
format for `list` (and its `search` alias).

- `list` returns an array of recipe summaries
- `show` returns a full recipe object
- `tags` returns an array of tag/count objects
- `stats` returns a fixed stats object
- `doctor` returns a structured discovery report

Human-readable table/text/Markdown output may evolve.

Summary fields for `list --format json` and `list --format csv`:

- `pk`
- `id`
- `title`
- `tags`
- `favorite`
- `wantToCook`
- `link`
- `createdAt`
- `prepTime`
- `cookTime`
- `totalTime`
- `yield`
- `imageCount`

CSV conventions:

- fixed header order matching the field list above
- `tags` serialized as a semicolon-delimited string
- booleans serialized as `true` / `false`
- missing values serialized as empty fields
- `imageCount` serialized as an integer

`tags --format json` returns:

```json
[
  {"tag": "Breakfast", "count": 12}
]
```

`stats --format json` returns:

```json
{
  "recipes": 204,
  "favorites": 10,
  "wantToCook": 3,
  "tags": 37,
  "recipesWithImages": 166,
  "recipesWithLinks": 170
}
```

Export format differences:

- `--format json` uses the full Mela CLI recipe schema. It includes fields like `pk`,
  `createdAt`, and structured image objects with metadata plus base64 payloads.
- `--format melarecipe` uses a Mela import-oriented schema. It omits CLI-only fields
  like `pk` and `createdAt`, omits empty optional fields, and serializes `images` as
  an array of base64 strings.
- Both are JSON-encoded. Use `json` for automation against the CLI contract and
  `melarecipe` when you want a file that Mela can import.

`doctor --format json` returns:

```json
{
  "ok": true,
  "supportedPlatform": true,
  "bundleId": "recipes.mela.appkit",
  "applicationGroup": "TEAMID.recipes.mela",
  "appPath": "/Applications/Mela.app",
  "appPathSource": "auto-discovery",
  "appExists": true,
  "dbPath": "/Users/example/Library/Group Containers/TEAMID.recipes.mela/Data/Curcuma.sqlite",
  "dbPathSource": "derived from app entitlement",
  "dbExists": true,
  "supportDir": "/Users/example/Library/Group Containers/TEAMID.recipes.mela/Data/.Curcuma_SUPPORT/_EXTERNAL_DATA",
  "supportDirSource": "derived from app entitlement",
  "supportDirExists": true,
  "compressionTool": "compression_tool",
  "compressionToolSource": "default",
  "compressionToolResolvedPath": "/usr/bin/compression_tool",
  "compressionToolAvailable": true,
  "canReadCatalog": true,
  "canDecodeExternalImages": true,
  "recipeCount": 204,
  "warnings": []
}
```

`doctor` fields are intended for diagnostics and environment inspection. `ok` means the CLI
can read the catalog and decode external image blobs with the currently discovered runtime.

## Troubleshooting

If discovery does not find your Mela install or live catalog:

```bash
mela doctor
```

If needed, override the paths explicitly:

```bash
mela --db-path "/path/to/Curcuma.sqlite" --support-dir "/path/to/_EXTERNAL_DATA" list
```

## Implementation Notes

- The CLI is based on Mela's current local macOS schema and storage layout.
- Image extraction supports:
  - inline blobs
  - raw Core Data external blobs
  - LZFSE-compressed keyed-archive external blobs via macOS `compression_tool`
- `.melarecipe` output is produced from reverse-engineered local data rather than an official Mela API.
