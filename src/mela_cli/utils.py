from __future__ import annotations

import json
import unicodedata
from typing import Any


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    safe = "".join(character.lower() if character.isalnum() else "-" for character in normalized)
    parts = [part for part in safe.split("-") if part]
    return "-".join(parts) or "recipe"


def shorten(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    return value[: width - 3] + "..."


def json_dumps(data: Any, pretty: bool = True) -> str:
    if pretty:
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"
