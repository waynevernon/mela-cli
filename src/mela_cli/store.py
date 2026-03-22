from __future__ import annotations

import base64
import plistlib
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)
SUMMARY_FIELD_NAMES = (
    "pk",
    "id",
    "title",
    "tags",
    "favorite",
    "wantToCook",
    "link",
    "createdAt",
    "prepTime",
    "cookTime",
    "totalTime",
    "yield",
    "imageCount",
)


class MelaError(RuntimeError):
    """Base exception for Mela CLI failures."""


class RecipeNotFoundError(MelaError):
    """Raised when a recipe selector does not match any recipe."""


class AmbiguousRecipeError(MelaError):
    """Raised when a recipe selector matches more than one recipe."""


class ImageDecodeError(MelaError):
    """Raised when an image blob cannot be decoded."""


@dataclass(slots=True)
class RecipeImage:
    index: int
    width: int | None
    height: int | None
    data: bytes

    @property
    def extension(self) -> str:
        return detect_image_extension(self.data)

    @property
    def media_type(self) -> str:
        return detect_image_media_type(self.data)

    @property
    def base64_data(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "width": self.width,
            "height": self.height,
            "extension": self.extension,
            "mediaType": self.media_type,
            "base64": self.base64_data,
        }


@dataclass(slots=True)
class RecipeSummary:
    pk: int
    identifier: str
    title: str
    link: str | None
    favorite: bool
    want_to_cook: bool
    created_at: str | None
    prep_time: str | None
    cook_time: str | None
    total_time: str | None
    yield_value: str | None
    image_count: int
    tags: list[str]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "id": self.identifier,
            "title": self.title,
            "tags": self.tags,
            "favorite": self.favorite,
            "wantToCook": self.want_to_cook,
            "link": self.link,
            "createdAt": self.created_at,
            "prepTime": self.prep_time,
            "cookTime": self.cook_time,
            "totalTime": self.total_time,
            "yield": self.yield_value,
            "imageCount": self.image_count,
        }

    def to_csv_dict(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "id": self.identifier,
            "title": self.title,
            "tags": ";".join(self.tags),
            "favorite": str(self.favorite).lower(),
            "wantToCook": str(self.want_to_cook).lower(),
            "link": self.link or "",
            "createdAt": self.created_at or "",
            "prepTime": self.prep_time or "",
            "cookTime": self.cook_time or "",
            "totalTime": self.total_time or "",
            "yield": self.yield_value or "",
            "imageCount": self.image_count,
        }


@dataclass(slots=True)
class Recipe:
    pk: int
    identifier: str
    title: str
    text: str | None
    ingredients: str | None
    instructions: str | None
    link: str | None
    notes: str | None
    nutrition: str | None
    prep_time: str | None
    cook_time: str | None
    total_time: str | None
    yield_value: str | None
    favorite: bool
    want_to_cook: bool
    created_at: str | None
    tags: list[str]
    images: list[RecipeImage]

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "id": self.identifier,
            "title": self.title,
            "text": self.text,
            "ingredients": self.ingredients,
            "instructions": self.instructions,
            "link": self.link,
            "notes": self.notes,
            "nutrition": self.nutrition,
            "prepTime": self.prep_time,
            "cookTime": self.cook_time,
            "totalTime": self.total_time,
            "yield": self.yield_value,
            "favorite": self.favorite,
            "wantToCook": self.want_to_cook,
            "createdAt": self.created_at,
            "tags": self.tags,
            "images": [image.to_json_dict() for image in self.images],
        }

    def to_melarecipe_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.identifier,
            "title": self.title,
            "favorite": self.favorite,
            "wantToCook": self.want_to_cook,
        }
        optional_fields = {
            "text": self.text,
            "link": self.link,
            "yield": self.yield_value,
            "cookTime": self.cook_time,
            "prepTime": self.prep_time,
            "totalTime": self.total_time,
            "notes": self.notes,
            "ingredients": self.ingredients,
            "instructions": self.instructions,
            "nutrition": self.nutrition,
        }
        for key, value in optional_fields.items():
            if value:
                payload[key] = value
        if self.tags:
            payload["tags"] = self.tags
        if self.images:
            payload["images"] = [image.base64_data for image in self.images]
        return payload


@dataclass(slots=True)
class TagSummary:
    name: str
    count: int

    def to_json_dict(self) -> dict[str, Any]:
        return {"tag": self.name, "count": self.count}


@dataclass(slots=True)
class CatalogStats:
    recipes: int
    favorites: int
    want_to_cook: int
    tags: int
    recipes_with_images: int
    recipes_with_links: int

    def to_json_dict(self) -> dict[str, int]:
        return {
            "recipes": self.recipes,
            "favorites": self.favorites,
            "wantToCook": self.want_to_cook,
            "tags": self.tags,
            "recipesWithImages": self.recipes_with_images,
            "recipesWithLinks": self.recipes_with_links,
        }


def apple_timestamp_to_iso8601(value: float | int | None) -> str | None:
    if value is None:
        return None
    timestamp = APPLE_EPOCH + timedelta(seconds=float(value))
    return timestamp.isoformat().replace("+00:00", "Z")


def detect_image_extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if len(data) > 12 and data[4:12] in {
        b"ftypheic",
        b"ftypheix",
        b"ftyphevc",
        b"ftyphevx",
        b"ftypmif1",
    }:
        return ".heic"
    return ".bin"


def detect_image_media_type(data: bytes) -> str:
    extension = detect_image_extension(data)
    return {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".heic": "image/heic",
    }.get(extension, "application/octet-stream")


class MelaStore:
    def __init__(
        self,
        db_path: Path,
        support_dir: Path | None,
        compression_tool: str = "compression_tool",
    ) -> None:
        self.db_path = db_path
        self.support_dir = support_dir
        self.compression_tool = compression_tool
        self._connection: sqlite3.Connection | None = None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            uri = f"file:{quote(str(self.db_path))}?mode=ro"
            self._connection = sqlite3.connect(uri, uri=True)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def list_recipes(
        self,
        query: str | None = None,
        favorite: bool = False,
        want_to_cook: bool = False,
        tags: list[str] | None = None,
        limit: int | None = None,
    ) -> list[RecipeSummary]:
        sql, params = self._build_summary_query(
            query=query,
            favorite=favorite,
            want_to_cook=want_to_cook,
            tags=tags or [],
        )
        rows = self.connection.execute(sql, params).fetchall()
        summaries = self._group_summary_rows(rows)
        if limit is not None:
            return summaries[:limit]
        return summaries

    def get_recipe(self, selector: str) -> Recipe:
        pk = self._resolve_recipe_pk(selector)
        row = self.connection.execute(
            """
            SELECT
                Z_PK AS pk,
                ZID AS identifier,
                ZTITLE AS title,
                ZTEXT AS text,
                ZINGREDIENTS AS ingredients,
                ZINSTRUCTIONS AS instructions,
                ZLINK AS link,
                ZNOTES AS notes,
                ZNUTRITION AS nutrition,
                ZPREPTIME AS prep_time,
                ZCOOKTIME AS cook_time,
                ZTOTALTIME AS total_time,
                ZYIELD AS yield_value,
                ZFAVORITE AS favorite,
                ZWANTTOCOOK AS want_to_cook,
                ZDATE AS created_at
            FROM ZRECIPEOBJECT
            WHERE Z_PK = ?
            """,
            (pk,),
        ).fetchone()
        if row is None:
            raise RecipeNotFoundError(f"Recipe selector {selector!r} did not resolve to a recipe.")
        return Recipe(
            pk=row["pk"],
            identifier=row["identifier"],
            title=row["title"],
            text=row["text"],
            ingredients=row["ingredients"],
            instructions=row["instructions"],
            link=row["link"],
            notes=row["notes"],
            nutrition=row["nutrition"],
            prep_time=row["prep_time"],
            cook_time=row["cook_time"],
            total_time=row["total_time"],
            yield_value=row["yield_value"],
            favorite=bool(row["favorite"]),
            want_to_cook=bool(row["want_to_cook"]),
            created_at=apple_timestamp_to_iso8601(row["created_at"]),
            tags=self._fetch_tags(pk),
            images=self._fetch_images(pk),
        )

    def list_tags(self) -> list[TagSummary]:
        rows = self.connection.execute(
            """
            SELECT t.ZTITLE AS tag_name, count(rt.Z_4RECIPES) AS recipe_count
            FROM ZRECIPETAG t
            LEFT JOIN Z_4TAGS rt ON rt.Z_5TAGS = t.Z_PK
            GROUP BY t.Z_PK, t.ZTITLE
            ORDER BY recipe_count DESC, lower(t.ZTITLE)
            """
        ).fetchall()
        return [TagSummary(name=row["tag_name"], count=int(row["recipe_count"])) for row in rows]

    def get_stats(self) -> CatalogStats:
        row = self.connection.execute(
            """
            SELECT
                count(*) AS recipe_count,
                sum(CASE WHEN ZFAVORITE = 1 THEN 1 ELSE 0 END) AS favorite_count,
                sum(CASE WHEN ZWANTTOCOOK = 1 THEN 1 ELSE 0 END) AS want_to_cook_count,
                sum(CASE WHEN coalesce(ZLINK, '') != '' THEN 1 ELSE 0 END) AS recipes_with_links
            FROM ZRECIPEOBJECT
            """
        ).fetchone()
        image_row = self.connection.execute(
            "SELECT count(DISTINCT ZRECIPE) AS recipes_with_images FROM ZRECIPEIMAGEOBJECT"
        ).fetchone()
        tag_row = self.connection.execute("SELECT count(*) AS tag_count FROM ZRECIPETAG").fetchone()
        return CatalogStats(
            recipes=int(row["recipe_count"] or 0),
            favorites=int(row["favorite_count"] or 0),
            want_to_cook=int(row["want_to_cook_count"] or 0),
            tags=int(tag_row["tag_count"] or 0),
            recipes_with_images=int(image_row["recipes_with_images"] or 0),
            recipes_with_links=int(row["recipes_with_links"] or 0),
        )

    def _build_summary_query(
        self,
        query: str | None,
        favorite: bool,
        want_to_cook: bool,
        tags: list[str],
    ) -> tuple[str, list[Any]]:
        sql = """
            SELECT
                r.Z_PK AS pk,
                r.ZID AS identifier,
                r.ZTITLE AS title,
                r.ZLINK AS link,
                r.ZFAVORITE AS favorite,
                r.ZWANTTOCOOK AS want_to_cook,
                r.ZDATE AS created_at,
                r.ZPREPTIME AS prep_time,
                r.ZCOOKTIME AS cook_time,
                r.ZTOTALTIME AS total_time,
                r.ZYIELD AS yield_value,
                (
                    SELECT count(*)
                    FROM ZRECIPEIMAGEOBJECT image
                    WHERE image.ZRECIPE = r.Z_PK
                ) AS image_count,
                t.ZTITLE AS tag
            FROM ZRECIPEOBJECT r
            LEFT JOIN Z_4TAGS rt ON rt.Z_4RECIPES = r.Z_PK
            LEFT JOIN ZRECIPETAG t ON t.Z_PK = rt.Z_5TAGS
        """
        clauses: list[str] = []
        params: list[Any] = []

        if favorite:
            clauses.append("r.ZFAVORITE = 1")
        if want_to_cook:
            clauses.append("r.ZWANTTOCOOK = 1")
        if query:
            clauses.append(
                """
                lower(
                    coalesce(r.ZTITLE, '') || char(10) ||
                    coalesce(r.ZTEXT, '') || char(10) ||
                    coalesce(r.ZINGREDIENTS, '') || char(10) ||
                    coalesce(r.ZINSTRUCTIONS, '') || char(10) ||
                    coalesce(r.ZNOTES, '') || char(10) ||
                    coalesce(r.ZNUTRITION, '') || char(10) ||
                    coalesce(r.ZLINK, '')
                ) LIKE ?
                """
            )
            params.append(f"%{query.lower()}%")
        for tag in tags:
            clauses.append(
                """
                EXISTS (
                    SELECT 1
                    FROM Z_4TAGS filter_rt
                    JOIN ZRECIPETAG filter_t ON filter_t.Z_PK = filter_rt.Z_5TAGS
                    WHERE filter_rt.Z_4RECIPES = r.Z_PK
                      AND lower(filter_t.ZTITLE) = ?
                )
                """
            )
            params.append(tag.lower())

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY lower(r.ZTITLE), lower(coalesce(t.ZTITLE, ''))"
        return sql, params

    def _group_summary_rows(self, rows: list[sqlite3.Row]) -> list[RecipeSummary]:
        summaries: dict[int, RecipeSummary] = {}
        for row in rows:
            pk = row["pk"]
            summary = summaries.get(pk)
            if summary is None:
                summary = RecipeSummary(
                    pk=pk,
                    identifier=row["identifier"],
                    title=row["title"],
                    link=row["link"],
                    favorite=bool(row["favorite"]),
                    want_to_cook=bool(row["want_to_cook"]),
                    created_at=apple_timestamp_to_iso8601(row["created_at"]),
                    prep_time=row["prep_time"],
                    cook_time=row["cook_time"],
                    total_time=row["total_time"],
                    yield_value=row["yield_value"],
                    image_count=int(row["image_count"] or 0),
                    tags=[],
                )
                summaries[pk] = summary
            if row["tag"] and row["tag"] not in summary.tags:
                summary.tags.append(row["tag"])
        return list(summaries.values())

    def _resolve_recipe_pk(self, selector: str) -> int:
        selector = selector.strip()
        if selector.isdigit():
            row = self.connection.execute(
                "SELECT Z_PK AS pk FROM ZRECIPEOBJECT WHERE Z_PK = ?",
                (int(selector),),
            ).fetchone()
            if row is not None:
                return int(row["pk"])

        exact_id_rows = self.connection.execute(
            """
            SELECT Z_PK AS pk, ZTITLE AS title, ZID AS identifier
            FROM ZRECIPEOBJECT
            WHERE ZID = ?
            ORDER BY lower(ZTITLE), Z_PK
            """,
            (selector,),
        ).fetchall()
        if len(exact_id_rows) == 1:
            return int(exact_id_rows[0]["pk"])
        if len(exact_id_rows) > 1:
            raise AmbiguousRecipeError(self._format_ambiguous_matches(selector, exact_id_rows))

        exact_title_rows = self.connection.execute(
            """
            SELECT Z_PK AS pk, ZTITLE AS title, ZID AS identifier
            FROM ZRECIPEOBJECT
            WHERE lower(ZTITLE) = lower(?)
            ORDER BY lower(ZTITLE), Z_PK
            """,
            (selector,),
        ).fetchall()
        if len(exact_title_rows) == 1:
            return int(exact_title_rows[0]["pk"])
        if len(exact_title_rows) > 1:
            raise AmbiguousRecipeError(self._format_ambiguous_matches(selector, exact_title_rows))

        prefix_rows = self.connection.execute(
            """
            SELECT Z_PK AS pk, ZTITLE AS title, ZID AS identifier
            FROM ZRECIPEOBJECT
            WHERE lower(ZID) LIKE ?
            ORDER BY lower(ZTITLE), Z_PK
            """,
            (f"{selector.lower()}%",),
        ).fetchall()
        if len(prefix_rows) == 1:
            return int(prefix_rows[0]["pk"])
        if len(prefix_rows) > 1:
            raise AmbiguousRecipeError(self._format_ambiguous_matches(selector, prefix_rows))

        fuzzy_rows = self.connection.execute(
            """
            SELECT Z_PK AS pk, ZTITLE AS title, ZID AS identifier
            FROM ZRECIPEOBJECT
            WHERE lower(ZTITLE) LIKE ?
            ORDER BY lower(ZTITLE), Z_PK
            """,
            (f"%{selector.lower()}%",),
        ).fetchall()
        if len(fuzzy_rows) == 1:
            return int(fuzzy_rows[0]["pk"])
        if len(fuzzy_rows) > 1:
            raise AmbiguousRecipeError(self._format_ambiguous_matches(selector, fuzzy_rows))
        raise RecipeNotFoundError(f"No recipe matched selector {selector!r}.")

    def _format_ambiguous_matches(self, selector: str, rows: list[sqlite3.Row]) -> str:
        matches = ", ".join(f"{row['pk']}: {row['title']}" for row in rows[:5])
        if len(rows) > 5:
            matches += ", ..."
        return f"Selector {selector!r} matched multiple recipes. Use a PK. Matches: {matches}"

    def _fetch_tags(self, recipe_pk: int) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT t.ZTITLE AS tag
            FROM Z_4TAGS rt
            JOIN ZRECIPETAG t ON t.Z_PK = rt.Z_5TAGS
            WHERE rt.Z_4RECIPES = ?
            ORDER BY lower(t.ZTITLE)
            """,
            (recipe_pk,),
        ).fetchall()
        return [row["tag"] for row in rows if row["tag"]]

    def _fetch_images(self, recipe_pk: int) -> list[RecipeImage]:
        rows = self.connection.execute(
            """
            SELECT ZINDEX AS image_index, ZWIDTH AS width, ZHEIGHT AS height, ZDATA AS data
            FROM ZRECIPEIMAGEOBJECT
            WHERE ZRECIPE = ?
            ORDER BY ZINDEX, Z_PK
            """,
            (recipe_pk,),
        ).fetchall()
        images: list[RecipeImage] = []
        for row in rows:
            images.append(
                RecipeImage(
                    index=int(row["image_index"] or 0),
                    width=int(row["width"]) if row["width"] is not None else None,
                    height=int(row["height"]) if row["height"] is not None else None,
                    data=self._decode_image_blob(row["data"]),
                )
            )
        return images

    def _decode_image_blob(self, blob: bytes | memoryview | None) -> bytes:
        if blob is None:
            raise ImageDecodeError("Encountered an empty image blob.")
        data = bytes(blob)
        if not data:
            raise ImageDecodeError("Encountered a zero-length image blob.")

        prefix = data[0]
        if prefix == 0x01:
            payload = data[1:]
            if detect_image_extension(payload) == ".bin":
                raise ImageDecodeError("Inline image blob did not contain a recognized image payload.")
            return payload
        if prefix == 0x02:
            reference = data[1:].split(b"\x00", 1)[0].decode("ascii")
            return self._decode_external_image(reference)
        if detect_image_extension(data) != ".bin":
            return data
        raise ImageDecodeError(f"Unsupported image blob prefix 0x{prefix:02x}.")

    def _decode_external_image(self, reference: str) -> bytes:
        if self.support_dir is None:
            raise ImageDecodeError(
                "An external image blob was referenced, but no support directory was configured."
            )
        path = self.support_dir / reference
        if not path.exists():
            raise ImageDecodeError(f"External image payload {reference} was not found.")

        data = path.read_bytes()
        if detect_image_extension(data) != ".bin":
            return data
        if data.startswith(b"bvx2"):
            archive = self._decode_lzfse_file(path)
            image = self._extract_image_from_keyed_archive(archive)
            if image is None:
                raise ImageDecodeError(f"Decoded archive {reference} did not contain CD_data.")
            return image
        raise ImageDecodeError(f"External image payload {reference} is not a supported format.")

    def _decode_lzfse_file(self, path: Path) -> bytes:
        with tempfile.NamedTemporaryFile() as output_handle:
            try:
                result = subprocess.run(
                    [
                        self.compression_tool,
                        "-decode",
                        "-a",
                        "lzfse",
                        "-i",
                        str(path),
                        "-o",
                        output_handle.name,
                    ],
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError:
                raise ImageDecodeError(
                    f"compression tool {self.compression_tool!r} is not on PATH — "
                    "run 'mela doctor' to diagnose, or set --compression-tool / MELA_COMPRESSION_TOOL."
                )
            if result.returncode != 0:
                raise ImageDecodeError(
                    f"compression_tool failed for {path.name}: {result.stderr.strip()}"
                )
            return Path(output_handle.name).read_bytes()

    @staticmethod
    def _extract_image_from_keyed_archive(payload: bytes) -> bytes | None:
        archive = plistlib.loads(payload)
        objects = archive.get("$objects", [])
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            keys = obj.get("NS.keys")
            values = obj.get("NS.objects")
            if not isinstance(keys, list) or not isinstance(values, list):
                continue
            decoded: dict[Any, Any] = {}
            for key_uid, value_uid in zip(keys, values):
                key = MelaStore._resolve_archive_value(key_uid, objects)
                value = MelaStore._resolve_archive_value(value_uid, objects)
                decoded[key] = value
            image_bytes = decoded.get("CD_data")
            if isinstance(image_bytes, bytes):
                return image_bytes
        return None

    @staticmethod
    def _resolve_archive_value(value: Any, objects: list[Any]) -> Any:
        if isinstance(value, plistlib.UID):
            return objects[value.data]
        return value
