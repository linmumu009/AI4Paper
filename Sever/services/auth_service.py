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
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


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
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                username       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                password_hash  TEXT    NOT NULL,
                salt           TEXT    NOT NULL,
                role           TEXT    NOT NULL DEFAULT 'user',
                tier           TEXT    NOT NULL DEFAULT 'free',
                phone          TEXT    UNIQUE,
                phone_verified INTEGER NOT NULL DEFAULT 0,
                created_at     TEXT    NOT NULL,
                updated_at     TEXT    NOT NULL,
                last_login_at  TEXT
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
    if "phone" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN phone TEXT")
    if "phone_verified" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN phone_verified INTEGER NOT NULL DEFAULT 0")
    if "nickname" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN nickname TEXT DEFAULT ''")
    if "is_phone_auto_created" not in existing:
        conn.execute("ALTER TABLE auth_users ADD COLUMN is_phone_auto_created INTEGER DEFAULT 0")
    conn.execute("UPDATE auth_users SET role = 'user' WHERE role IS NULL OR role = ''")
    conn.execute("UPDATE auth_users SET tier = 'free' WHERE tier IS NULL OR tier = ''")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_phone ON auth_users(phone)")


def _cleanup_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (_now_iso(),))


def _mask_phone(phone: Optional[str]) -> Optional[str]:
    """将手机号中间四位替换为 *，如 138****1234"""
    if not phone or len(phone) != 11:
        return phone
    return phone[:3] + "****" + phone[7:]


def _row_user_public(row: sqlite3.Row) -> dict:
    keys = row.keys()
    raw_phone = row["phone"] if "phone" in keys else None
    password_hash = row["password_hash"] if "password_hash" in keys else ""
    has_password = bool(password_hash and password_hash.strip())
    return {
        "id": row["id"],
        "username": row["username"],
        "nickname": row["nickname"] if "nickname" in keys else "",
        "role": row["role"],
        "tier": row["tier"],
        "phone": _mask_phone(raw_phone),
        "phone_verified": bool(row["phone_verified"]) if "phone_verified" in keys else False,
        "is_phone_auto_created": bool(row["is_phone_auto_created"]) if "is_phone_auto_created" in keys else False,
        "has_password": has_password,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
    }


def _validate_phone(phone: str) -> str:
    p = (phone or "").strip()
    if not _PHONE_RE.fullmatch(p):
        raise HTTPException(status_code=400, detail="请输入有效的中国大陆手机号")
    return p


def auto_register_by_phone(phone: str) -> dict:
    """
    通过手机号自动创建账号（用于一体化登录/注册）。
    自动生成用户名，不设置密码，标记为手机号自动创建账号。
    """
    p = _validate_phone(phone)
    now = _now_iso()
    suffix = secrets.token_hex(2)
    auto_username = f"u_{p[-4:]}_{suffix}"
    conn = _connect()
    try:
        for _ in range(5):
            try:
                cur = conn.execute(
                    """
                    INSERT INTO auth_users
                      (username, password_hash, salt, phone, phone_verified,
                       nickname, is_phone_auto_created, created_at, updated_at)
                    VALUES (?, '', '', ?, 1, '', 1, ?, ?)
                    """,
                    (auto_username, p, now, now),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (cur.lastrowid,)).fetchone()
                return _row_user_public(row)
            except sqlite3.IntegrityError as exc:
                err_msg = str(exc).lower()
                if "username" in err_msg:
                    suffix = secrets.token_hex(2)
                    auto_username = f"u_{p[-4:]}_{suffix}"
                    continue
                if "phone" in err_msg or "unique" in err_msg:
                    row = conn.execute("SELECT * FROM auth_users WHERE phone = ?", (p,)).fetchone()
                    if row:
                        return _row_user_public(row)
                raise HTTPException(status_code=409, detail="自动注册失败，请稍后重试") from exc
        raise HTTPException(status_code=500, detail="自动注册失败：无法生成唯一用户名")
    finally:
        conn.close()


def register_user(username: str, password: str, phone: Optional[str] = None) -> dict:
    """
    注册用户。
    phone: 若提供则存入数据库并标记为已验证（调用方负责在注册前通过 sms_service 完成验证）。
    """
    uname = _validate_username(username)
    pwd = _validate_password(password)
    validated_phone: Optional[str] = None
    if phone:
        validated_phone = _validate_phone(phone)
    now = _now_iso()
    salt = secrets.token_bytes(16)
    pw_hash = _hash_password(pwd, salt)
    conn = _connect()
    try:
        try:
            cur = conn.execute(
                """
                INSERT INTO auth_users (username, password_hash, salt, phone, phone_verified, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (uname, pw_hash, salt.hex(), validated_phone, 1 if validated_phone else 0, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            err_msg = str(exc).lower()
            if "username" in err_msg or "unique" in err_msg and "phone" not in err_msg:
                raise HTTPException(status_code=409, detail="用户名已存在") from exc
            if validated_phone and ("phone" in err_msg or "unique" in err_msg):
                raise HTTPException(status_code=409, detail="该手机号已绑定其他账号") from exc
            raise HTTPException(status_code=409, detail="用户名或手机号已存在") from exc
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_user_public(row)
    finally:
        conn.close()


def get_user_by_phone(phone: str) -> Optional[dict]:
    """按手机号查找用户，返回公开信息或 None。"""
    p = (phone or "").strip()
    if not p:
        return None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE phone = ?", (p,)).fetchone()
        if row is None:
            return None
        return _row_user_public(row)
    finally:
        conn.close()


def login_by_phone(phone: str) -> Optional[dict]:
    """
    通过手机号登录（验证码已由调用方校验）。
    更新 last_login_at 并返回用户公开信息。
    """
    p = (phone or "").strip()
    if not p:
        return None
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE phone = ?", (p,)).fetchone()
        if row is None:
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


def _extract_session_id(request: Request) -> str:
    """从 Cookie 或 Authorization header 中提取 session_id。

    优先使用 Cookie（Web 同域场景）；Cookie 不存在时回退到
    ``Authorization: Bearer <session_id>``（桌面端跨域场景）。
    """
    sid = request.cookies.get(SESSION_COOKIE_NAME, "")
    if sid:
        return sid
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""


def require_user(request: Request) -> dict:
    session_id = _extract_session_id(request)
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


def update_user_profile(
    user_id: int,
    nickname: Optional[str] = None,
    username: Optional[str] = None,
) -> dict:
    """
    更新用户昵称和/或用户名。
    username 若提供，必须满足格式要求且不重复。
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        updates: list[str] = []
        params: list = []

        if nickname is not None:
            clean_nick = nickname.strip()[:64]
            updates.append("nickname = ?")
            params.append(clean_nick)

        if username is not None:
            new_uname = _validate_username(username)
            if new_uname.lower() != row["username"].lower():
                existing = conn.execute(
                    "SELECT id FROM auth_users WHERE username = ? AND id != ?",
                    (new_uname, user_id),
                ).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="用户名已被占用")
            updates.append("username = ?")
            params.append(new_uname)
            if row["is_phone_auto_created"]:
                updates.append("is_phone_auto_created = 0")

        if not updates:
            return _row_user_public(row)

        now = _now_iso()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(user_id)

        conn.execute(
            f"UPDATE auth_users SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def check_username_available(username: str, exclude_user_id: Optional[int] = None) -> dict:
    """
    检查用户名是否可用。
    返回 {"available": bool, "message": str}
    """
    if not _USERNAME_RE.match(username):
        return {"available": False, "message": "用户名格式不合法，仅支持字母/数字/._-，长度 3-32 位"}
    conn = _connect()
    try:
        if exclude_user_id is not None:
            row = conn.execute(
                "SELECT id FROM auth_users WHERE username = ? AND id != ?",
                (username, exclude_user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM auth_users WHERE username = ?",
                (username,),
            ).fetchone()
        if row:
            return {"available": False, "message": "用户名已被占用"}
        return {"available": True, "message": "用户名可用"}
    finally:
        conn.close()


def set_user_password(user_id: int, password: str) -> dict:
    """
    为手机号用户首次设置密码（当前必须无密码才能调用）。
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        if row["password_hash"] and row["password_hash"].strip():
            raise HTTPException(status_code=400, detail="该账号已设置密码，请使用修改密码功能")
        pwd = _validate_password(password)
        salt = secrets.token_bytes(16)
        pw_hash = _hash_password(pwd, salt)
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (pw_hash, salt.hex(), now, user_id),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def change_user_password(user_id: int, old_password: str, new_password: str) -> dict:
    """
    修改已有密码（需验证旧密码）。
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        if not row["password_hash"] or not row["password_hash"].strip():
            raise HTTPException(status_code=400, detail="该账号尚未设置密码，请使用设置密码功能")
        salt = bytes.fromhex(row["salt"])
        actual = _hash_password(old_password.strip(), salt)
        if not hmac.compare_digest(actual, row["password_hash"]):
            raise HTTPException(status_code=400, detail="旧密码错误")
        new_pwd = _validate_password(new_password)
        new_salt = secrets.token_bytes(16)
        new_hash = _hash_password(new_pwd, new_salt)
        now = _now_iso()
        conn.execute(
            "UPDATE auth_users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (new_hash, new_salt.hex(), now, user_id),
        )
        conn.commit()
        refreshed = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        return _row_user_public(refreshed)
    finally:
        conn.close()


def get_user_profile(user_id: int) -> Optional[dict]:
    """获取用户完整资料（含 has_password 等）。"""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM auth_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return _row_user_public(row)
    finally:
        conn.close()


# Ensure tables exist on import
init_auth_db()
