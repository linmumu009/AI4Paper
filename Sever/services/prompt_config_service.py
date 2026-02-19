"""
提示词配置服务层。

管理提示词配置的数据库存储和CRUD操作。
配置存储在 Sever/database/paper_analysis.db 的 prompt_config 表中。
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
    """初始化 prompt_config 表（如果不存在）。"""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prompt_config (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                remark        TEXT,
                prompt_content TEXT   NOT NULL,
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def list_configs() -> List[Dict[str, Any]]:
    """获取所有提示词配置列表。"""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM prompt_config ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_config(config_id: int) -> Optional[Dict[str, Any]]:
    """获取单个提示词配置。"""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM prompt_config WHERE id = ?", (config_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """创建新的提示词配置。
    
    Args:
        data: 配置数据字典，必须包含 name, prompt_content
        
    Returns:
        创建后的配置字典（包含id）
    """
    # 验证必填字段
    if "name" not in data or not data["name"]:
        raise ValueError("必填字段 name 不能为空")
    if "prompt_content" not in data or not data["prompt_content"]:
        raise ValueError("必填字段 prompt_content 不能为空")
    
    now = _now_iso()
    conn = _connect()
    try:
        cursor = conn.execute(
            """
            INSERT INTO prompt_config (
                name, remark, prompt_content, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data.get("remark"),
                data["prompt_content"],
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
    """更新提示词配置。
    
    Args:
        config_id: 配置ID
        data: 要更新的字段字典
        
    Returns:
        更新后的配置字典，如果配置不存在则返回None
    """
    # 验证必填字段（如果提供了）
    if "prompt_content" in data and not data["prompt_content"]:
        raise ValueError("prompt_content 不能为空")
    
    # 检查配置是否存在
    existing = get_config(config_id)
    if not existing:
        return None
    
    # 构建更新字段
    updates = []
    values = []
    for key in ["name", "remark", "prompt_content"]:
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
            f"UPDATE prompt_config SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
            values,
        )
        conn.commit()
        return get_config(config_id)
    finally:
        conn.close()


def delete_config(config_id: int) -> bool:
    """删除提示词配置。
    
    Returns:
        如果配置存在且已删除返回True，否则返回False
    """
    conn = _connect()
    try:
        cursor = conn.execute("DELETE FROM prompt_config WHERE id = ?", (config_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
