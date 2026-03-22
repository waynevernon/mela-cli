# Releasing Mela CLI

## Versioning

1. Update `src/mela_cli/__init__.py`
1. Update `pyproject.toml`
1. Update `CHANGELOG.md`

## Release Flow

1. Run the full test suite locally
1. Commit the release changes
1. Create and push a tag in the form `vX.Y.Z`
1. Create the GitHub release from that tag
1. Let the PyPI publish workflow upload the package via Trusted Publishing

## Install Validation

After publishing:

```bash
pipx install mela-cli
mela --version
mela doctor
```
