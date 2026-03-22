# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

## [Unreleased]

## [1.0.0] - 2026-03-21

### Added

- Initial read-only Mela CLI command surface: `list`, `show`, `export`, `export-all`, `tags`, `stats`, and `doctor`
- `search` command as a positional-argument alias for `list --query`
- `-q`/`--query` on `list` and `export-all` for text search
- Short flags across all commands: `-f` (`--favorite`), `-w` (`--want-to-cook`), `-t` (`--tag`), `-n` (`--limit`), `-q` (`--query`), `-o` (`--output`)
- `-o`/`--output` replaces `--output-dir`; optional with default `.` on both `export` and `export-all`
- Dynamic discovery for the official Mela install and group container paths
- JSON, CSV, table, text, and Markdown output formats
- `--filename-style` option (`slug`, `id`, `id-slug`) to control exported filenames
- CI and PyPI publishing workflows with ruff linting and mypy type checking
- Stable summary schemas for `list`, plus documented JSON contracts for `tags`, `stats`, and `doctor`
