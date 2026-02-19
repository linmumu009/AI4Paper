"""
大模型配置服务层。

管理大模型配置的数据库存储和CRUD操作。
配置存储在 Sever/database/paper_analysis.db 的 llm_config 表中。
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")


def _connect() -> sqlite3.Connection:
    """创建数据库连接。"""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    """返回当前时间的ISO格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """初始化 llm_config 表（如果不存在）。"""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS llm_config (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                username          TEXT,
                name              TEXT    NOT NULL,
                remark            TEXT,
                base_url          TEXT    NOT NULL,
                api_key           TEXT    NOT NULL,
                model             TEXT    NOT NULL,
                max_tokens         INTEGER,
                temperature       REAL,
                concurrency       INTEGER,
                input_hard_limit  INTEGER,
                input_safety_margin INTEGER,
                endpoint          TEXT,
                completion_window TEXT,
                out_root          TEXT,
                jsonl_root        TEXT,
                created_at        TEXT    NOT NULL,
                updated_at        TEXT    NOT NULL
            );
            """
        )
        # 迁移：为已存在的旧表补充 username 列
        _ensure_llm_config_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_llm_config_columns(conn: sqlite3.Connection) -> None:
    """为旧版 llm_config 表补充缺失列（向后兼容迁移）。"""
    rows = conn.execute("PRAGMA table_info(llm_config)").fetchall()
    existing = {r["name"] for r in rows}
    if "username" not in existing:
        conn.execute("ALTER TABLE llm_config ADD COLUMN username TEXT")


def list_configs(username: Optional[str] = None) -> List[Dict[str, Any]]:
    """获取模型配置列表。

    Args:
        username: 若指定则只返回该用户的配置；None 时返回全部。
    """
    conn = _connect()
    try:
        if username is not None:
            rows = conn.execute(
                "SELECT * FROM llm_config WHERE username = ? ORDER BY created_at DESC",
                (username,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM llm_config ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_config(config_id: int) -> Optional[Dict[str, Any]]:
    """获取单个模型配置。"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM llm_config WHERE id = ?", (config_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """创建新的模型配置。
    
    Args:
        data: 配置数据字典，必须包含 name, base_url, api_key, model；
              可选 username 字段以绑定特定用户。
        
    Returns:
        创建后的配置字典（包含id）
    """
    # 验证必填字段
    required_fields = ["name", "base_url", "api_key", "model"]
    for field in required_fields:
        if field not in data or not data[field]:
            raise ValueError(f"必填字段 {field} 不能为空")
    
    now = _now_iso()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO llm_config (
                username, name, remark, base_url, api_key, model,
                max_tokens, temperature, concurrency,
                input_hard_limit, input_safety_margin,
                endpoint, completion_window, out_root, jsonl_root,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("username"),
                data["name"],
                data.get("remark"),
                data["base_url"],
                data["api_key"],
                data["model"],
                data.get("max_tokens"),
                data.get("temperature"),
                data.get("concurrency"),
                data.get("input_hard_limit"),
                data.get("input_safety_margin"),
                data.get("endpoint"),
                data.get("completion_window"),
                data.get("out_root"),
                data.get("jsonl_root"),
                now,
                now,
            ),
        )
        conn.commit()
        config_id = cursor.lastrowid
        return get_config(config_id)
    finally:
        conn.close()


def update_config(config_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新模型配置。
    
    Args:
        config_id: 配置ID
        data: 要更新的字段字典
        
    Returns:
        更新后的配置字典，如果配置不存在则返回None
    """
    # 验证必填字段（如果提供了）
    if "base_url" in data and not data["base_url"]:
        raise ValueError("base_url 不能为空")
    if "api_key" in data and not data["api_key"]:
        raise ValueError("api_key 不能为空")
    if "model" in data and not data["model"]:
        raise ValueError("model 不能为空")
    
    # 检查配置是否存在
    existing = get_config(config_id)
    if not existing:
        return None
    
    # 构建更新字段
    updates = []
    values = []
    for key in [
        "username", "name", "remark", "base_url", "api_key", "model",
        "max_tokens", "temperature", "concurrency",
        "input_hard_limit", "input_safety_margin",
        "endpoint", "completion_window", "out_root", "jsonl_root"
    ]:
        if key in data:
            updates.append(f"{key} = ?")
            values.append(data[key])
    
    if not updates:
        return existing
    
    values.append(_now_iso())  # updated_at
    values.append(config_id)  # WHERE条件
    
    conn = _connect()
    try:
        conn.execute(
            f"UPDATE llm_config SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
            values,
        )
        conn.commit()
        return get_config(config_id)
    finally:
        conn.close()


def delete_config(config_id: int) -> bool:
    """删除模型配置。
    
    Returns:
        如果配置存在且已删除返回True，否则返回False
    """
    conn = _connect()
    try:
        cursor = conn.execute("DELETE FROM llm_config WHERE id = ?", (config_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
