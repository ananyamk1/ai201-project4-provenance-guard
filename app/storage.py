from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    attribution TEXT NOT NULL,
    confidence REAL NOT NULL,
    llm_score REAL NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def init_storage(app) -> None:
    instance_path = Path(app.instance_path)
    instance_path.mkdir(parents=True, exist_ok=True)
    database_path = Path(app.config["DATABASE"])
    if not database_path.is_absolute():
        database_path = Path(app.instance_path) / database_path
    app.config["DATABASE"] = str(database_path)
    with sqlite3.connect(app.config["DATABASE"]) as connection:
        connection.executescript(SCHEMA)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@contextmanager
def db_cursor():
    connection = get_db()
    cursor = connection.cursor()
    try:
        yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def close_db(_error=None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()



def make_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")



def insert_audit_entry(entry: dict) -> None:
    payload = json.dumps(entry, ensure_ascii=True)
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO audit_log (
                content_id, creator_id, timestamp, attribution,
                confidence, llm_score, status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["content_id"],
                entry["creator_id"],
                entry["timestamp"],
                entry["attribution"],
                entry["confidence"],
                entry["llm_score"],
                entry["status"],
                payload,
            ),
        )


def get_latest_entry(content_id: str) -> dict | None:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT payload_json
            FROM audit_log
            WHERE content_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (content_id,),
        )
        row = cursor.fetchone()
    return json.loads(row["payload_json"]) if row else None


def append_appeal_entry(appeal_entry: dict) -> None:
    payload = json.dumps(appeal_entry, ensure_ascii=True)
    with db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO audit_log (
                content_id, creator_id, timestamp, attribution,
                confidence, llm_score, status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                appeal_entry["content_id"],
                appeal_entry.get("creator_id", ""),
                appeal_entry["timestamp"],
                appeal_entry["attribution"],
                appeal_entry["confidence"],
                appeal_entry["llm_score"],
                appeal_entry["status"],
                payload,
            ),
        )


def list_audit_entries(limit: int = 20) -> list[dict]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT payload_json
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def list_all_audit_entries() -> list[dict]:
    with db_cursor() as cursor:
        cursor.execute(
            """
            SELECT payload_json
            FROM audit_log
            ORDER BY id DESC
            """
        )
        rows = cursor.fetchall()
    return [json.loads(row["payload_json"]) for row in rows]



def get_recent_entries(limit: int = 20) -> list[dict]:
    return list_audit_entries(limit)
