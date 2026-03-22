# mela-cli

Read-only macOS CLI for browsing and exporting recipes from the Mela app's local SQLite store. Never writes to the live database. macOS only, Python 3.11+, zero runtime dependencies.

## Source layout

```
src/mela_cli/
  cli.py          # argparse definitions + command handlers
  store.py        # MelaStore: SQLite queries, image decoding, data models
  discovery.py    # auto-discover Mela.app and group container paths
  formatters.py   # render functions for all output formats
  utils.py        # slugify, json_dumps
tests/
  support.py      # fixture helpers: create_fixture_store, run_cli, etc.
  test_cli.py
  test_store.py
  test_discovery.py
```

## Dev commands

```bash
.venv/bin/python -m unittest discover tests -v  # run tests
.venv/bin/python -m ruff check src/ tests/      # lint
.venv/bin/python -m mypy src/mela_cli/          # type check
.venv/bin/python -m mela_cli [command]          # run locally
./mela [command]                                # dev convenience script
```

## Conventions

- Line length 120 (ruff), mypy strict — all code must lint and type-check cleanly
- Tests use stdlib `unittest` only — no pytest
- All SQL queries use parameterized `?` placeholders — never string interpolation
- `MelaStore` opens SQLite read-only via URI (`?mode=ro`)
- Image decoding handles three storage formats: inline blob (0x01 prefix), external file reference (0x02), LZFSE-compressed NSKeyedArchiver — all decoded to raw bytes and serialized as base64 at export time
- When adding a new listing command, reuse `add_recipe_filters()`, `add_summary_output_option()`, and `add_table_json_output_option()` from `cli.py`
- `search` is an alias for `list --query` — both route to `handle_list`, which uses `getattr(args, "query", None)` to handle both call shapes
- Only add `dest=` to argparse args when the inferred name would be wrong (e.g. `--tag` → `dest="tags"` is necessary; `--output` → `dest="output"` is redundant)

## Hard rules

- Never write to any Mela store path (`discovery.db_path` or anything under the group container)
- No runtime dependencies — keep `dependencies = []` in `pyproject.toml`

## Keeping docs current

**README.md** must be updated in the same commit as any change to commands, flags, defaults, or output formats. The Commands, Option Reference, and Examples sections document live behavior — they are not a release artifact.

**CHANGELOG.md** is updated only at release time.

## Releasing

See `RELEASING.md`. Short version:

1. Bump version in `src/mela_cli/__init__.py` and `pyproject.toml`
2. Update `CHANGELOG.md`
3. Commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`
4. `gh release create vX.Y.Z --title "X.Y.Z" --notes "..."`

Pushing the tag triggers the PyPI publish workflow via Trusted Publishing.
