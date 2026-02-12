"""
Authentication service layer.

Provides:
- User registration / credential verification
- Server-side session management
- FastAPI dependency for authenticated user
"""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

SESSION_COOKIE_NAME = "session_id"
SESSION_EXPIRE_DAYS = 7
SESSION_TOUCH_HOURS = 24
PBKDF2_ROUNDS = 200_000
VALID_TIERS = {"free", "pro", "pro_plus"}
VALID_ROLES = {"user", "admin", "superadmin"}

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return digest.hex()


def _normalize_username(username: str) -> str:
    return (username or "").strip()


def _validate_username(username: str) -> str:
    normalized = _normalize_username(username)
    if not _USERNAME_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail="用户名需为 3-32 位，仅支持字母、数字、下划线、点、连字符",
        )
    return normalized


def _validate_password(password: str) -> str:
    pwd = (password or "").strip()
    if len(pwd) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少 8 位")
    if len(pwd) > 128:
        raise HTTPException(status_code=400, detail="密码长度不能超过 128 位")
    return pwd


def init_auth_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT    NOT NULL,
                salt          TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT 'user',
                tier          TEXT    NOT NULL DEFAULT 'free',
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_id   TEXT    PRIMARY KEY,
                user_id      INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                created_at   TEXT    NOT NULL,
                expires_at   TEXT    NOT NULL,
                last_seen_at TEXT    NOT NULL,
                ip           TEXT,
                user_agent   TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);
            """
        )
        _ensure_auth_user_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_auth_user_columns(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(auth_users)").fetchall()
    existing = {r["name"] for r in rows}
    if "role" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    if "tier" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN tier TEXT NOT NULL DEFAULT 'free'")
    conn.execute("UPDATE auth_users SET role = 'user' WHERE role IS NULL OR role = ''")
    conn.execute("UPDATE auth_users SET tier = 'free' WHERE tier IS NULL OR tier = ''")


def _cleanup_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (_now_iso(),))


def _row_user_public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "tier": row["tier"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
    }


def register_user(username: str, password: str) -> dict:
    uname = _validate_username(username)
    pwd = _validate_password(password)
    now = _now_iso()
    salt = secrets.token_bytes(16)
    pw_hash = _hash_password(pwd, salt)
    conn = _connect()
    try:
        try:
            cur = conn.execute(
                """
                INSERT INTO auth_users (username, password_hash, salt, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (uname, pw_hash, salt.hex(), now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="用户名已存在") from exc
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_user_public(row)
    finally:
        conn.close()


def verify_credentials(username: str, password: str) -> Optional[dict]:
    uname = _normalize_username(username)
    pwd = (password or "").strip()
    if not uname or not pwd:
        return None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE username = ?", (uname,)).fetchone()
        if row is None:
            return None
        salt = bytes.fromhex(row["salt"])
        expected = row["password_hash"]
        actual = _hash_password(pwd, salt)
        if not hmac.compare_digest(actual, expected):
            return None
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (now, now, row["id"]),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (row["id"],)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def create_session(
    user_id: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    session_id = secrets.token_urlsafe(48)
    now_dt = _now()
    now = now_dt.isoformat()
    expires = (now_dt + timedelta(days=SESSION_EXPIRE_DAYS)).isoformat()
    conn = _connect()
    try:
        _cleanup_expired_sessions(conn)
        conn.execute(
            """
            INSERT INTO auth_sessions (session_id, user_id, created_at, expires_at, last_seen_at, ip, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, user_id, now, expires, now, ip, user_agent),
        )
        conn.commit()
        return {"session_id": session_id, "expires_at": expires}
    finally:
        conn.close()


def delete_session(session_id: str) -> None:
    if not session_id:
        return
    conn = _connect()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def get_user_by_session(session_id: str, touch: bool = True) -> Optional[dict]:
    if not session_id:
        return None
    conn = _connect()
    try:
        _cleanup_expired_sessions(conn)
        row = conn.execute(
            """
            SELECT s.session_id, s.expires_at, s.last_seen_at, u.*
            FROM auth_sessions s
            JOIN auth_users u ON u.id = s.user_id
            WHERE s.session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None

        expires_at = _parse_iso(row["expires_at"])
        now_dt = _now()
        if expires_at <= now_dt:
            conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return None

        if touch:
            last_seen = _parse_iso(row["last_seen_at"])
            if now_dt - last_seen >= timedelta(hours=SESSION_TOUCH_HOURS):
                conn.execute(
                    "UPDATE auth_sessions SET last_seen_at = ? WHERE session_id = ?",
                    (now_dt.isoformat(), session_id),
                )
                conn.commit()

        return _row_user_public(row)
    finally:
        conn.close()


def require_user(request: Request) -> dict:
    session_id = request.cookies.get(SESSION_COOKIE_NAME, "")
    user = get_user_by_session(session_id)
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_admin_user(request: Request) -> dict:
    """Require admin or superadmin role."""
    user = require_user(request)
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def require_superadmin_user(request: Request) -> dict:
    """Require superadmin role."""
    user = require_user(request)
    if user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return user


def list_users() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, username, role, tier, created_at, updated_at, last_login_at
            FROM auth_users
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_user_tier(user_id: int, tier: str) -> Optional[dict]:
    if tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail="非法 tier 值")
    conn = _connect()
    try:
        conn.execute(
            "UPDATE auth_users SET tier = ?, updated_at = ? WHERE id = ?",
            (tier, _now_iso(), user_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return _row_user_public(row)
    finally:
        conn.close()


def update_user_role(user_id: int, role: str) -> Optional[dict]:
    """Update a user's role (superadmin only)."""
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="非法角色值，允许: user, admin, superadmin")
    conn = _connect()
    try:
        conn.execute(
            "UPDATE auth_users SET role = ?, updated_at = ? WHERE id = ?",
            (role, _now_iso(), user_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return _row_user_public(row)
    finally:
        conn.close()


# Ensure tables exist on import
init_auth_db()
