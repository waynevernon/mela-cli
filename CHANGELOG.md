# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.

## [Unreleased]

## [1.0.0] - 2026-03-21

Initial release.

### Added

- `list`, `show`, `export`, `export-all`, `tags`, `stats`, and `doctor` commands
- `search` as a positional-argument alias for `list --query`
- Short flags: `-f`, `-w`, `-t`, `-n`, `-q`, `-o`
- Dynamic discovery of the Mela install and group container paths
- JSON, CSV, table, text, and Markdown output formats
- `--filename-style` (`slug`, `id`, `id-slug`) for exported filenames
