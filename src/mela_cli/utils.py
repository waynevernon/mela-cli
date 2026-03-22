from __future__ import annotations

import json
import os
import sys
import unicodedata
from typing import Any


def use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if use_color() else s


def dim(s: str) -> str:
    return f"\033[2m{s}\033[0m" if use_color() else s


def green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if use_color() else s


def red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if use_color() else s


def cyan(s: str) -> str:
    return f"\033[36m{s}\033[0m" if use_color() else s


def yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if use_color() else s


def section_rule(title: str, width: int = 50) -> str:
    fill = max(width - len(title) - 4, 4)
    return dim("── ") + bold(title) + dim(f" {'─' * fill}")


def mini_bar(value: int, total: int, width: int = 20) -> str:
    if total == 0:
        return dim("░" * width)
    filled = round(value / total * width)
    return green("█" * filled) + dim("░" * (width - filled))


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
