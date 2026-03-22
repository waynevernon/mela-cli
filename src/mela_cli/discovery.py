from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

EXPECTED_BUNDLE_ID = "recipes.mela.appkit"
ENV_APP_PATH = "MELA_APP_PATH"
ENV_DB_PATH = "MELA_DB_PATH"
ENV_SUPPORT_DIR = "MELA_SUPPORT_DIR"
ENV_COMPRESSION_TOOL = "MELA_COMPRESSION_TOOL"


@dataclass(slots=True)
class DiscoveryResult:
    supported_platform: bool
    app_path: Path | None
    app_path_source: str
    bundle_id: str | None
    application_group: str | None
    db_path: Path | None
    db_path_source: str
    support_dir: Path | None
    support_dir_source: str
    compression_tool: str
    compression_tool_source: str
    compression_tool_resolved_path: str | None
    warnings: list[str] = field(default_factory=list)
    recipe_count: int | None = None

    @property
    def app_exists(self) -> bool:
        return self.app_path is not None and self.app_path.exists()

    @property
    def db_exists(self) -> bool:
        return self.db_path is not None and self.db_path.exists()

    @property
    def support_dir_exists(self) -> bool:
        return self.support_dir is not None and self.support_dir.exists()

    @property
    def compression_tool_available(self) -> bool:
        return self.compression_tool_resolved_path is not None

    @property
    def can_read_catalog(self) -> bool:
        return self.supported_platform and self.db_exists

    @property
    def can_decode_external_images(self) -> bool:
        return self.can_read_catalog and self.support_dir_exists and self.compression_tool_available

    @property
    def ok(self) -> bool:
        return self.can_read_catalog and self.can_decode_external_images

    def to_json_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "supportedPlatform": self.supported_platform,
            "bundleId": self.bundle_id,
            "applicationGroup": self.application_group,
            "appPath": str(self.app_path) if self.app_path else None,
            "appPathSource": self.app_path_source,
            "appExists": self.app_exists,
            "dbPath": str(self.db_path) if self.db_path else None,
            "dbPathSource": self.db_path_source,
            "dbExists": self.db_exists,
            "supportDir": str(self.support_dir) if self.support_dir else None,
            "supportDirSource": self.support_dir_source,
            "supportDirExists": self.support_dir_exists,
            "compressionTool": self.compression_tool,
            "compressionToolSource": self.compression_tool_source,
            "compressionToolResolvedPath": self.compression_tool_resolved_path,
            "compressionToolAvailable": self.compression_tool_available,
            "canReadCatalog": self.can_read_catalog,
            "canDecodeExternalImages": self.can_decode_external_images,
            "recipeCount": self.recipe_count,
            "warnings": self.warnings,
        }


def discover_mela(
    app_path: Path | None = None,
    db_path: Path | None = None,
    support_dir: Path | None = None,
    compression_tool: str | None = None,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> DiscoveryResult:
    env = env or os.environ
    home = home or Path.home()
    warnings: list[str] = []
    supported_platform = sys.platform == "darwin"
    if not supported_platform:
        warnings.append("Mela CLI currently supports macOS only.")

    resolved_app_path, app_path_source = resolve_path_value(
        explicit=app_path,
        env_value=env.get(ENV_APP_PATH),
        explicit_source="cli flag",
        env_source=ENV_APP_PATH,
    )
    if resolved_app_path is None:
        resolved_app_path = discover_app_path(home)
        app_path_source = "auto-discovery" if resolved_app_path else "not found"

    bundle_id = read_bundle_id(resolved_app_path) if resolved_app_path else None
    if bundle_id and bundle_id != EXPECTED_BUNDLE_ID:
        warnings.append(
            f"Discovered app bundle id {bundle_id!r}; expected {EXPECTED_BUNDLE_ID!r}."
        )

    application_group = None
    if resolved_app_path and resolved_app_path.exists():
        app_groups = read_application_groups(resolved_app_path)
        application_group = select_application_group(app_groups)
        if not application_group and app_groups:
            application_group = app_groups[0]
        if not application_group and not app_groups:
            warnings.append("Could not read Mela application-group entitlement from the app bundle.")
    elif resolved_app_path and not resolved_app_path.exists():
        warnings.append(f"Configured app path does not exist: {resolved_app_path}")

    resolved_db_path, db_path_source = resolve_path_value(
        explicit=db_path,
        env_value=env.get(ENV_DB_PATH),
        explicit_source="cli flag",
        env_source=ENV_DB_PATH,
    )
    resolved_support_dir, support_dir_source = resolve_path_value(
        explicit=support_dir,
        env_value=env.get(ENV_SUPPORT_DIR),
        explicit_source="cli flag",
        env_source=ENV_SUPPORT_DIR,
    )

    derived_db_path: Path | None = None
    derived_support_dir: Path | None = None
    if application_group:
        derived_db_path, derived_support_dir = derive_store_paths(home, application_group)

    scanned_db_path, scanned_support_dir, scanned_group = scan_group_containers(home)
    if application_group is None and scanned_group:
        application_group = scanned_group

    if resolved_db_path is None:
        if derived_db_path and derived_db_path.exists():
            resolved_db_path = derived_db_path
            db_path_source = "derived from app entitlement"
        elif scanned_db_path:
            resolved_db_path = scanned_db_path
            db_path_source = "group container scan"
        elif derived_db_path:
            resolved_db_path = derived_db_path
            db_path_source = "derived from app entitlement"
    if resolved_support_dir is None:
        if derived_support_dir and derived_support_dir.exists():
            resolved_support_dir = derived_support_dir
            support_dir_source = "derived from app entitlement"
        elif scanned_support_dir:
            resolved_support_dir = scanned_support_dir
            support_dir_source = "group container scan"
        elif derived_support_dir:
            resolved_support_dir = derived_support_dir
            support_dir_source = "derived from app entitlement"

    if resolved_db_path is None:
        warnings.append("Could not locate Curcuma.sqlite automatically.")
    elif not resolved_db_path.exists():
        warnings.append(f"Database path does not exist: {resolved_db_path}")

    if resolved_support_dir is None:
        warnings.append("Could not locate the Core Data external blob directory automatically.")
    elif not resolved_support_dir.exists():
        warnings.append(f"Support directory does not exist: {resolved_support_dir}")

    resolved_compression_tool = compression_tool or env.get(ENV_COMPRESSION_TOOL) or "compression_tool"
    compression_tool_source = (
        "cli flag"
        if compression_tool
        else ENV_COMPRESSION_TOOL
        if env.get(ENV_COMPRESSION_TOOL)
        else "default"
    )
    compression_tool_resolved_path = shutil.which(resolved_compression_tool)
    if compression_tool_resolved_path is None:
        warnings.append(
            f"Compression tool {resolved_compression_tool!r} is not available on PATH."
        )

    recipe_count = None
    if resolved_db_path and resolved_db_path.exists():
        recipe_count = count_recipes(resolved_db_path)

    return DiscoveryResult(
        supported_platform=supported_platform,
        app_path=resolved_app_path,
        app_path_source=app_path_source,
        bundle_id=bundle_id,
        application_group=application_group,
        db_path=resolved_db_path,
        db_path_source=db_path_source,
        support_dir=resolved_support_dir,
        support_dir_source=support_dir_source,
        compression_tool=resolved_compression_tool,
        compression_tool_source=compression_tool_source,
        compression_tool_resolved_path=compression_tool_resolved_path,
        warnings=warnings,
        recipe_count=recipe_count,
    )


def resolve_path_value(
    explicit: Path | None,
    env_value: str | None,
    explicit_source: str,
    env_source: str,
) -> tuple[Path | None, str]:
    if explicit is not None:
        return explicit.expanduser(), explicit_source
    if env_value:
        return Path(env_value).expanduser(), env_source
    return None, "not set"


def discover_app_path(home: Path) -> Path | None:
    candidate_paths = [
        Path("/Applications/Mela.app"),
        home / "Applications/Mela.app",
    ]
    spotlight_paths = discover_spotlight_app_paths()
    for path in candidate_paths + spotlight_paths:
        if path.exists() and read_bundle_id(path) == EXPECTED_BUNDLE_ID:
            return path
    return None


def discover_spotlight_app_paths() -> list[Path]:
    if shutil.which("mdfind") is None:
        return []
    result = subprocess.run(
        ["mdfind", f'kMDItemCFBundleIdentifier == "{EXPECTED_BUNDLE_ID}"'],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        path = Path(line.strip())
        if path.name == "Mela.app":
            paths.append(path)
    return paths


def read_bundle_id(app_path: Path | None) -> str | None:
    if app_path is None:
        return None
    info_path = app_path / "Contents/Info.plist"
    if not info_path.exists():
        return None
    try:
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
    except Exception:
        return None
    value = info.get("CFBundleIdentifier")
    return str(value) if value else None


def read_application_groups(app_path: Path) -> list[str]:
    if shutil.which("codesign") is None:
        return []
    result = subprocess.run(
        ["codesign", "-d", "--entitlements", ":-", str(app_path)],
        capture_output=True,
        text=False,
    )
    payload = result.stdout or result.stderr
    plist_bytes = extract_plist_bytes(payload)
    if not plist_bytes:
        return []
    try:
        plist = plistlib.loads(plist_bytes)
    except Exception:
        return []
    groups = plist.get("com.apple.security.application-groups", [])
    if not isinstance(groups, list):
        return []
    return [str(group) for group in groups]


def extract_plist_bytes(payload: bytes) -> bytes | None:
    for marker in (b"<?xml", b"<plist"):
        index = payload.find(marker)
        if index != -1:
            return payload[index:]
    return None


def select_application_group(groups: list[str]) -> str | None:
    for group in groups:
        if "recipes.mela" in group:
            return group
    return None


def derive_store_paths(home: Path, application_group: str) -> tuple[Path, Path]:
    group_root = home / "Library/Group Containers" / application_group / "Data"
    return (
        group_root / "Curcuma.sqlite",
        group_root / ".Curcuma_SUPPORT/_EXTERNAL_DATA",
    )


def scan_group_containers(home: Path) -> tuple[Path | None, Path | None, str | None]:
    root = home / "Library/Group Containers"
    if not root.exists():
        return None, None, None
    candidates = sorted(root.glob("*recipes.mela*/Data/Curcuma.sqlite"))
    for candidate in candidates:
        support_dir = candidate.parent / ".Curcuma_SUPPORT/_EXTERNAL_DATA"
        application_group = candidate.parent.parent.name
        if support_dir.exists():
            return candidate, support_dir, application_group
    if candidates:
        candidate = candidates[0]
        return candidate, candidate.parent / ".Curcuma_SUPPORT/_EXTERNAL_DATA", candidate.parent.parent.name
    return None, None, None


def count_recipes(db_path: Path) -> int | None:
    import sqlite3
    from urllib.parse import quote

    try:
        uri = f"file:{quote(str(db_path))}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            row = connection.execute("SELECT count(*) FROM ZRECIPEOBJECT").fetchone()
        finally:
            connection.close()
    except Exception:
        return None
    return int(row[0]) if row else None
