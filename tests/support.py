from __future__ import annotations

import io
import os
import plistlib
import sqlite3
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from mela_cli.cli import main

JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"


def build_keyed_archive(image_bytes: bytes) -> bytes:
    archive = {
        "$archiver": "NSKeyedArchiver",
        "$version": 100000,
        "$top": {"root": plistlib.UID(1)},
        "$objects": [
            "$null",
            {"$class": plistlib.UID(5), "ValueStore": plistlib.UID(2)},
            {
                "NS.keys": [plistlib.UID(3)],
                "NS.objects": [plistlib.UID(4)],
                "$class": plistlib.UID(6),
            },
            "CD_data",
            image_bytes,
            {"$classname": "CKRecord", "$classes": ["CKRecord", "NSObject"]},
            {
                "$classname": "NSMutableDictionary",
                "$classes": ["NSMutableDictionary", "NSDictionary", "NSObject"],
            },
        ],
    }
    return plistlib.dumps(archive, fmt=plistlib.FMT_BINARY)


def create_fixture_store(root: Path) -> tuple[Path, Path]:
    db_path = root / "Curcuma.sqlite"
    support_dir = root / "_EXTERNAL_DATA"
    support_dir.mkdir()
    support_dir.joinpath("ABC123").write_bytes(JPEG_BYTES)
    support_dir.joinpath("ARCHIVE").write_bytes(b"bvx2placeholder")

    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE ZRECIPEOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            Z_ENT INTEGER,
            Z_OPT INTEGER,
            ZFAVORITE INTEGER,
            ZWANTTOCOOK INTEGER,
            ZDATE REAL,
            ZCOOKTIME TEXT,
            ZID TEXT,
            ZINGREDIENTS TEXT,
            ZINSTRUCTIONS TEXT,
            ZLINK TEXT,
            ZNOTES TEXT,
            ZNUTRITION TEXT,
            ZPREPTIME TEXT,
            ZTEXT TEXT,
            ZTITLE TEXT,
            ZTOTALTIME TEXT,
            ZYIELD TEXT
        );
        CREATE TABLE ZRECIPETAG (
            Z_PK INTEGER PRIMARY KEY,
            Z_ENT INTEGER,
            Z_OPT INTEGER,
            ZTITLE TEXT
        );
        CREATE TABLE Z_4TAGS (
            Z_4RECIPES INTEGER,
            Z_5TAGS INTEGER,
            PRIMARY KEY (Z_4RECIPES, Z_5TAGS)
        );
        CREATE TABLE ZRECIPEIMAGEOBJECT (
            Z_PK INTEGER PRIMARY KEY,
            Z_ENT INTEGER,
            Z_OPT INTEGER,
            ZINDEX INTEGER,
            ZRECIPE INTEGER,
            ZHEIGHT FLOAT,
            ZWIDTH FLOAT,
            ZDATA BLOB
        );
        """
    )
    recipes = [
        (
            1,
            1,
            0,
            600000000.0,
            "10 min",
            "breakfast-egg-bites",
            "egg\nbacon",
            "cook it",
            "https://example.com/recipe-1",
            "note",
            "protein",
            "5 min",
            "breakfast",
            "Egg Bites",
            "15 min",
            "8",
        ),
        (
            2,
            0,
            1,
            610000000.0,
            "30 min",
            "egg-soup",
            "broth\negg",
            "simmer it",
            "",
            "",
            "",
            "10 min",
            "savory",
            "Egg Soup",
            "40 min",
            "4",
        ),
        (
            3,
            0,
            0,
            620000000.0,
            "12 min",
            "Egg Soup Deluxe",
            "bread\negg",
            "toast it",
            "https://example.com/recipe-3",
            "weekend only",
            "",
            "8 min",
            "snack",
            "Brunch Bites",
            "20 min",
            "2",
        ),
        (
            4,
            0,
            0,
            630000000.0,
            "18 min",
            "breakfast-egg-cups",
            "egg\ncheese",
            "bake it",
            "https://example.com/recipe-4",
            "",
            "",
            "6 min",
            "duplicate title",
            "Egg Bites",
            "24 min",
            "6",
        ),
    ]
    connection.executemany(
        """
        INSERT INTO ZRECIPEOBJECT (
            Z_PK, ZFAVORITE, ZWANTTOCOOK, ZDATE, ZCOOKTIME, ZID,
            ZINGREDIENTS, ZINSTRUCTIONS, ZLINK, ZNOTES, ZNUTRITION,
            ZPREPTIME, ZTEXT, ZTITLE, ZTOTALTIME, ZYIELD
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        recipes,
    )
    connection.executemany(
        "INSERT INTO ZRECIPETAG (Z_PK, ZTITLE) VALUES (?, ?)",
        [
            (1, "Breakfast"),
            (2, "Sous Vide"),
            (3, "Soup"),
        ],
    )
    connection.executemany(
        "INSERT INTO Z_4TAGS (Z_4RECIPES, Z_5TAGS) VALUES (?, ?)",
        [
            (1, 1),
            (1, 2),
            (2, 3),
            (4, 1),
        ],
    )
    connection.executemany(
        """
        INSERT INTO ZRECIPEIMAGEOBJECT
        (Z_PK, ZINDEX, ZRECIPE, ZHEIGHT, ZWIDTH, ZDATA)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 0, 1, 900, 1600, b"\x01" + JPEG_BYTES),
            (2, 0, 2, 800, 1200, b"\x02ABC123\x00"),
            (3, 0, 3, 700, 1000, b"\x02ARCHIVE\x00"),
        ],
    )
    connection.commit()
    connection.close()
    return db_path, support_dir


def create_fake_app(home: Path, application_group: str) -> Path:
    app_path = home / "Applications" / "Mela.app"
    info_path = app_path / "Contents" / "Info.plist"
    info_path.parent.mkdir(parents=True, exist_ok=True)
    with info_path.open("wb") as handle:
        plistlib.dump({"CFBundleIdentifier": "recipes.mela.appkit"}, handle)

    group_root = home / "Library" / "Group Containers" / application_group / "Data"
    group_root.mkdir(parents=True, exist_ok=True)
    return app_path


def run_cli(args: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch.dict(os.environ, env or {}, clear=False):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(args)
    return code, stdout.getvalue(), stderr.getvalue()
