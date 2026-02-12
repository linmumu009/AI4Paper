"""
User settings service layer.

Stores per-user, per-feature configuration in the ``user_settings`` table
(same SQLite database as auth / KB).

Table schema
------------
    user_settings (
        user_id   INTEGER NOT NULL,
        feature   TEXT    NOT NULL,          -- e.g. 'compare', 'paper_summary'
        settings_json TEXT NOT NULL DEFAULT '{}',
        updated_at    TEXT NOT NULL,
        PRIMARY KEY (user_id, feature)
    )

Each *feature* has its own set of default values defined in ``_FEATURE_DEFAULTS``.
``get_settings`` merges stored values on top of those defaults so that the
caller always receives a complete dict.
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


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the user_settings table if it does not exist."""
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id       INTEGER NOT NULL,
                feature       TEXT    NOT NULL,
                settings_json TEXT    NOT NULL DEFAULT '{}',
                updated_at    TEXT    NOT NULL,
                PRIMARY KEY (user_id, feature)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Default values per feature
# ---------------------------------------------------------------------------

# Keys that should NEVER be filled with defaults (user must provide them).
_NO_DEFAULT_KEYS: dict[str, set[str]] = {
    "compare": {"llm_base_url", "llm_api_key", "llm_model"},
    "inspiration": {"llm_base_url", "llm_api_key", "llm_model"},
}

_COMPARE_SYSTEM_PROMPT_DEFAULT = """\
你是一位资深的科研助手，擅长对多篇学术论文进行横向对比分析。

用户会提供 2-5 篇论文的摘要/结构化信息。请你从以下维度进行全面的对比分析，输出结构清晰的 Markdown 报告：

## 输出格式要求
请按以下结构输出（使用 Markdown 格式）：

### 📋 论文概览
用表格列出每篇论文的标题、机构、核心贡献（一句话）。

### 🔬 研究问题对比
比较各论文要解决的核心问题，找出共同关注点和差异点。

### 🛠️ 方法论差异
对比各论文采用的技术路线、模型架构、关键机制，分析各自的优势和局限。

### 📊 实验与结果比较
（如果有可用数据）对比实验设置、数据集、评估指标和实验结果。

### 🔗 互补性与关联
分析这些论文之间的学术关联：是否解决同一问题的不同方案？是否构成上下游关系？方法是否可以互相借鉴？

### 💡 综合建议
给出综合评价：哪篇论文的方法最有潜力？如果要开展后续研究，可以从这些论文中获取哪些启发？

## 要求
- 保持客观、学术性的语言风格
- 使用中文撰写，专有名词（模型名、数据集名、指标名）保留英文
- 如果某个维度信息不足，简要说明并跳过，不要编造
- 控制总篇幅在 1500 字以内
"""

_INSPIRATION_SYSTEM_PROMPT_DEFAULT = """\
你是一位富有创造力的科研灵感助手，擅长从多篇论文的关联中发现新的研究灵感和创新方向。

用户会提供若干条灵感涌现记录，每条包含标题、摘要和相关论文信息。请你综合分析这些灵感条目，深入挖掘其中的潜在联系，并输出结构清晰的 Markdown 报告：

## 输出格式要求
请按以下结构输出（使用 Markdown 格式）：

### 💡 灵感概览
简要总结用户选中的灵感条目，概括它们各自的核心思路。

### 🔗 跨领域关联
分析这些灵感之间是否存在深层次的技术关联或方法互补，找出可以互相融合的点。

### 🚀 研究方向建议
基于这些灵感的交叉点，提出 2-3 个具体的、可操作的研究方向或项目构想，包括：
- 研究问题是什么
- 可能采用的技术路线
- 预期的创新点和价值

### 📋 可行性评估
对提出的研究方向进行简要的可行性分析，包括技术难度、数据需求、潜在挑战等。

### 🎯 下一步行动
给出具体的行动建议：应该先读哪些论文、先做哪些实验、需要什么资源等。

## 要求
- 注重创新性和启发性，鼓励跨领域思考
- 使用中文撰写，专有名词（模型名、数据集名、指标名）保留英文
- 建议要具体、可操作，避免空泛的建议
- 控制总篇幅在 1500 字以内
"""

_FEATURE_DEFAULTS: dict[str, dict[str, Any]] = {
    "compare": {
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 1.0,
        "max_tokens": 4096,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        "data_source": "summary",
        "system_prompt": _COMPARE_SYSTEM_PROMPT_DEFAULT,
    },
    "inspiration": {
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 1.0,
        "max_tokens": 4096,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        "system_prompt": _INSPIRATION_SYSTEM_PROMPT_DEFAULT,
    },
    # Future features can be added here:
    # "paper_summary": { ... },
    # "theme_filter": { ... },
}


def get_defaults(feature: str) -> dict[str, Any]:
    """Return the default values for *feature* (empty dict if unknown)."""
    return dict(_FEATURE_DEFAULTS.get(feature, {}))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def get_settings(user_id: int, feature: str) -> dict[str, Any]:
    """
    Return the merged settings for a user + feature.

    - Keys that have defaults are filled in when the user has not set them.
    - Keys in ``_NO_DEFAULT_KEYS`` are returned as-is (empty string if unset).
    """
    defaults = get_defaults(feature)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT settings_json FROM user_settings WHERE user_id = ? AND feature = ?",
            (user_id, feature),
        ).fetchone()
        user_vals: dict[str, Any] = {}
        if row:
            try:
                user_vals = json.loads(row["settings_json"])
            except (json.JSONDecodeError, TypeError):
                user_vals = {}

        # Merge: user values override defaults
        merged = dict(defaults)
        merged.update(user_vals)

        # For "no-default" keys, do NOT fill from defaults — keep user value
        no_defaults = _NO_DEFAULT_KEYS.get(feature, set())
        for key in no_defaults:
            merged[key] = user_vals.get(key, "")

        return merged
    finally:
        conn.close()


def get_raw_settings(user_id: int, feature: str) -> dict[str, Any]:
    """Return only the user-provided settings (no defaults merged)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT settings_json FROM user_settings WHERE user_id = ? AND feature = ?",
            (user_id, feature),
        ).fetchone()
        if row:
            try:
                return json.loads(row["settings_json"])
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    finally:
        conn.close()


def save_settings(user_id: int, feature: str, settings: dict[str, Any]) -> dict[str, Any]:
    """
    Upsert settings for a user + feature.

    Returns the merged settings after saving.
    """
    now = _now_iso()
    settings_str = json.dumps(settings, ensure_ascii=False)
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO user_settings (user_id, feature, settings_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, feature) DO UPDATE SET
                settings_json = excluded.settings_json,
                updated_at    = excluded.updated_at
            """,
            (user_id, feature, settings_str, now),
        )
        conn.commit()
    finally:
        conn.close()

    return get_settings(user_id, feature)


# Ensure table exists on import
init_db()
