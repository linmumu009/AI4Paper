"""
User presets service layer.

Stores per-user LLM presets and Prompt presets in dedicated SQLite tables.

Tables
------
    user_llm_presets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        name        TEXT NOT NULL,
        base_url    TEXT NOT NULL DEFAULT '',
        api_key     TEXT NOT NULL DEFAULT '',
        model       TEXT NOT NULL DEFAULT '',
        max_tokens  INTEGER,
        temperature REAL,
        input_hard_limit   INTEGER,
        input_safety_margin INTEGER,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )

    user_prompt_presets (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL,
        name            TEXT NOT NULL,
        prompt_content  TEXT NOT NULL DEFAULT '',
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    )
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create preset tables if they don't exist."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_llm_presets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT NOT NULL,
                base_url    TEXT NOT NULL DEFAULT '',
                api_key     TEXT NOT NULL DEFAULT '',
                model       TEXT NOT NULL DEFAULT '',
                max_tokens  INTEGER,
                temperature REAL,
                input_hard_limit   INTEGER,
                input_safety_margin INTEGER,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_prompt_presets (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                name            TEXT NOT NULL,
                prompt_content  TEXT NOT NULL DEFAULT '',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# LLM Presets CRUD
# ---------------------------------------------------------------------------

def list_llm_presets(user_id: int) -> list[dict]:
    """Return all LLM presets for a user, ordered by created_at desc."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM user_llm_presets WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_llm_preset(user_id: int, preset_id: int) -> Optional[dict]:
    """Return a single LLM preset, or None if not found or not owned."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM user_llm_presets WHERE id = ? AND user_id = ?",
            (preset_id, user_id),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def create_llm_preset(user_id: int, data: dict) -> dict:
    """Create a new LLM preset and return it."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO user_llm_presets
               (user_id, name, base_url, api_key, model, max_tokens,
                temperature, input_hard_limit, input_safety_margin,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                data.get("name", "未命名配置"),
                data.get("base_url", ""),
                data.get("api_key", ""),
                data.get("model", ""),
                data.get("max_tokens"),
                data.get("temperature"),
                data.get("input_hard_limit"),
                data.get("input_safety_margin"),
                now, now,
            ),
        )
        conn.commit()
        return get_llm_preset(user_id, cur.lastrowid) or {}
    finally:
        conn.close()


def update_llm_preset(user_id: int, preset_id: int, data: dict) -> Optional[dict]:
    """Update an existing LLM preset. Returns updated preset or None."""
    existing = get_llm_preset(user_id, preset_id)
    if not existing:
        return None
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """UPDATE user_llm_presets SET
               name = ?, base_url = ?, api_key = ?, model = ?,
               max_tokens = ?, temperature = ?,
               input_hard_limit = ?, input_safety_margin = ?,
               updated_at = ?
               WHERE id = ? AND user_id = ?""",
            (
                data.get("name", existing["name"]),
                data.get("base_url", existing["base_url"]),
                data.get("api_key", existing["api_key"]),
                data.get("model", existing["model"]),
                data.get("max_tokens", existing.get("max_tokens")),
                data.get("temperature", existing.get("temperature")),
                data.get("input_hard_limit", existing.get("input_hard_limit")),
                data.get("input_safety_margin", existing.get("input_safety_margin")),
                now,
                preset_id, user_id,
            ),
        )
        conn.commit()
        return get_llm_preset(user_id, preset_id)
    finally:
        conn.close()


def delete_llm_preset(user_id: int, preset_id: int) -> bool:
    """Delete an LLM preset. Returns True if deleted."""
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM user_llm_presets WHERE id = ? AND user_id = ?",
            (preset_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Prompt Presets CRUD
# ---------------------------------------------------------------------------

def list_prompt_presets(user_id: int) -> list[dict]:
    """Return all prompt presets for a user, ordered by created_at desc."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM user_prompt_presets WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_prompt_preset(user_id: int, preset_id: int) -> Optional[dict]:
    """Return a single prompt preset, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM user_prompt_presets WHERE id = ? AND user_id = ?",
            (preset_id, user_id),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def create_prompt_preset(user_id: int, data: dict) -> dict:
    """Create a new prompt preset and return it."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO user_prompt_presets
               (user_id, name, prompt_content, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                user_id,
                data.get("name", "未命名提示词"),
                data.get("prompt_content", ""),
                now, now,
            ),
        )
        conn.commit()
        return get_prompt_preset(user_id, cur.lastrowid) or {}
    finally:
        conn.close()


def update_prompt_preset(user_id: int, preset_id: int, data: dict) -> Optional[dict]:
    """Update a prompt preset. Returns updated preset or None."""
    existing = get_prompt_preset(user_id, preset_id)
    if not existing:
        return None
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            """UPDATE user_prompt_presets SET
               name = ?, prompt_content = ?, updated_at = ?
               WHERE id = ? AND user_id = ?""",
            (
                data.get("name", existing["name"]),
                data.get("prompt_content", existing["prompt_content"]),
                now,
                preset_id, user_id,
            ),
        )
        conn.commit()
        return get_prompt_preset(user_id, preset_id)
    finally:
        conn.close()


def delete_prompt_preset(user_id: int, preset_id: int) -> bool:
    """Delete a prompt preset. Returns True if deleted."""
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM user_prompt_presets WHERE id = ? AND user_id = ?",
            (preset_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# Ensure tables exist on import
init_db()
