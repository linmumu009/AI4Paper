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


def seed_default_idea_llm_configs() -> int:
    """为灵感生成的 7 个阶段写入默认 qwen-plus 模型配置并应用到 config.json。

    逻辑与 prompt_config_service.seed_default_idea_prompts 一致：
    - 仅当同名条目不存在时才插入（幂等）。
    - 插入后自动调用 config_service.update_config 将对应的
      idea_<phase>_base_url / api_key / model 写入 config.json，
      使管理员后台 detectLlmSelections() 能立刻匹配到。
    - 如果 qwen_api_key 未设置，仍会写入 base_url / model，
      api_key 留空（等管理员手动填写后页面会自动匹配）。

    Returns: 新插入的条目数量。
    """
    import sys as _sys
    import os as _os
    _base = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _base not in _sys.path:
        _sys.path.insert(0, _base)

    try:
        import config.config as _cfg
    except ImportError:
        return 0

    _QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    _QWEN_API_KEY  = (getattr(_cfg, "qwen_api_key", "") or "").strip()
    _QWEN_MODEL    = "qwen-plus"

    # (llm_config.name, remark, phase_prefix_for_config_key)
    # phase_prefix → config.py 变量前缀：idea_<prefix>_base_url / api_key / model
    _SEED_DEFS = [
        ("灵感·原子抽取模型 [默认]",    "原子抽取阶段 (idea_ingest)",          "idea_ingest"),
        ("灵感·研究问题生成模型 [默认]", "研究问题生成阶段 (idea_question)",     "idea_question"),
        ("灵感·候选生成模型 [默认]",     "灵感候选生成阶段 (idea_candidate)",    "idea_candidate"),
        ("灵感·评审模型 [默认]",         "灵感评审阶段 (idea_review)",           "idea_review"),
        ("灵感·修订模型 [默认]",         "灵感修订阶段 (idea_revise)",           "idea_revise"),
        ("灵感·实验计划模型 [默认]",     "实验计划生成阶段 (idea_plan)",         "idea_plan"),
        ("灵感·评测回放模型 [默认]",     "评测回放阶段 (idea_eval)",             "idea_eval"),
    ]

    now = _now_iso()
    conn = _connect()
    inserted = 0
    config_updates: Dict[str, Any] = {}

    try:
        for name, remark, phase_pfx in _SEED_DEFS:
            # 幂等：已存在则跳过插入
            row = conn.execute(
                "SELECT id, base_url, api_key, model FROM llm_config WHERE name = ?",
                (name,),
            ).fetchone()

            if not row:
                conn.execute(
                    """
                    INSERT INTO llm_config (
                        name, remark, base_url, api_key, model,
                        max_tokens, temperature, input_hard_limit, input_safety_margin,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name, remark,
                        _QWEN_BASE_URL, _QWEN_API_KEY, _QWEN_MODEL,
                        8192, 0.7, 129024, 4096,
                        now, now,
                    ),
                )
                inserted += 1
                saved_url   = _QWEN_BASE_URL
                saved_model = _QWEN_MODEL
            else:
                saved_url   = row["base_url"]
                saved_model = row["model"]

        conn.commit()
    finally:
        conn.close()

    # 应用到 config.json —— 让 detectLlmSelections 能立刻匹配
    try:
        from services import config_service as _cs
        current = _cs.get_config_with_groups()
        all_vals: Dict[str, Any] = {}
        for g in current.get("groups", []):
            for item in g.get("items", []):
                all_vals[item["key"]] = item["value"]

        for _name, _remark, phase_pfx in _SEED_DEFS:
            url_key   = f"{phase_pfx}_base_url"
            model_key = f"{phase_pfx}_model"
            # 只要 base_url 或 model 未设置就覆写（api_key 从 config.py 读取，不强制写入空值）
            if not (all_vals.get(url_key) or "").strip():
                config_updates[url_key] = _QWEN_BASE_URL
            if not (all_vals.get(model_key) or "").strip():
                config_updates[model_key] = _QWEN_MODEL
            # api_key 仅当有值时才写
            api_key_cfg = f"{phase_pfx}_api_key"
            if _QWEN_API_KEY and not (all_vals.get(api_key_cfg) or "").strip():
                config_updates[api_key_cfg] = _QWEN_API_KEY

        if config_updates:
            _cs.update_config(config_updates)
    except Exception as e:
        print(f"[WARN] seed_default_idea_llm_configs: failed to write config updates: {e}")

    return inserted


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
