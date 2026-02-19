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
    "compare": {"llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id"},
    "inspiration": {"llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id"},
    "paper_recommend": {
        "llm_base_url", "llm_api_key", "llm_model", "llm_preset_id", "prompt_preset_id",
        # Per-module LLM preset IDs
        "theme_select_llm_preset_id", "org_llm_preset_id",
        "summary_llm_preset_id", "summary_limit_llm_preset_id",
        # Per-module prompt preset IDs
        "theme_select_prompt_preset_id", "org_prompt_preset_id",
        "summary_prompt_preset_id",
        "summary_limit_prompt_intro_preset_id", "summary_limit_prompt_method_preset_id",
        "summary_limit_prompt_findings_preset_id", "summary_limit_prompt_opinion_preset_id",
        # MinerU 服务密钥
        "mineru_token",
    },
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

_PAPER_RECOMMEND_SYSTEM_PROMPT_DEFAULT = (
    "你是一个论文笔记助手，请阅读论文内容，严格按照格式写这篇论文的笔记，"
    "不要带有markdown格式，字数控制在900字以内。格式如下："
    "笔记标题：（10个字左右的中文短句说明论文的贡献）\n"
    "🛎️文章简介\n"
    "🔸研究问题：（用一个问句描述论文试图解决什么问题）\n"
    "🔸主要贡献：（一句话回答这篇论文有什么贡献）\n"
    "📝重点思路 （逐条写论文的研究方法是什么，每一条都以🔸开头）\n"
    "🔎分析总结 （逐条写论文通过实验分析得到了哪些结论，每一条都以🔸开头）\n"
    "💡个人观点\n"
    "（总结论文的创新点）"
)

_PAPER_RECOMMEND_LIMIT_PROMPT_INTRO = (
    "你是一名严谨的学术论文摘要编辑。你的任务是把用户提供的【文章简介】压缩成更短的版本。\n"
    "硬性规则：\n"
    "只允许基于原文改写与删减，禁止新增论文未明确出现的数字、结论、因果解释、背景信息。\n"
    "必须保留两件事：①研究问题（1句内）②主要贡献/做了什么（1句内）。\n"
    "删除所有修饰、铺垫、泛化评价（如\"很有意义/非常重要\"）。\n"
    "输出 2 句中文，整体不超过 180 字（按去空白字符计）。\n"
    "只输出压缩后的正文，不要标题、不要字数说明、不要解释。"
)

_PAPER_RECOMMEND_LIMIT_PROMPT_METHOD = (
    "你是一名学术方法部分的精炼编辑。你的任务是把用户提供的【重点思路】压缩到更短、更\"信息密度高\"的版本。\n"
    "硬性规则：\n"
    "只允许删减与同义改写，禁止新增论文未明确出现的实验设置、对比对象、指标、结论与数字。\n"
    "只保留\"怎么做\"的关键动作：benchmark/数据/任务设计/训练或评测策略（优先保留带数字/专有名词的信息）。\n"
    "输出格式固定为 最多 4 条，每条以\"🔸\"开头，每条 1 句。\n"
    "整体不超过 280 字（去空白字符计）。\n"
    "只输出压缩后的条目，不要额外说明。"
)

_PAPER_RECOMMEND_LIMIT_PROMPT_FINDINGS = (
    "你是一名结果与结论部分的审稿式编辑。你的任务是把用户提供的【分析总结】压缩为更短的\"关键发现列表\"。\n"
    "硬性规则：\n"
    "只允许删减与同义改写，禁止新增论文未明确出现的解释、推断、因果链、建议或外延应用。\n"
    "必须保留最核心的 2–4 个发现（优先保留：一致性变化、失败模式、能力对比、训练方式影响）。\n"
    "输出格式固定为 最多 4 条，每条以\"🔸\"开头，每条 1 句，句子尽量短。\n"
    "整体不超过 280 字（去空白字符计）。\n"
    "只输出压缩后的条目，不要总结段、不要字数说明。"
)

_PAPER_RECOMMEND_LIMIT_PROMPT_OPINION = (
    "你是一名克制、保真的学术评论编辑。你的任务是把用户提供的【个人观点】压缩为极短版本。\n"
    "硬性规则：\n"
    "只允许基于原文观点做删减与改写，禁止新增论文未提到的价值判断、应用场景、改进建议或任何推断性结论。\n"
    "允许保留\"评价框架\"，但措辞必须克制（避免\"必然/革命性/全面提升\"等强断言）。\n"
    "输出 1–2 句中文，整体不超过 160 字（去空白字符计）。\n"
    "只输出压缩后的正文，不要标题、不要解释、不要字数说明。"
)

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
    "paper_recommend": {
        # --- LLM 连接配置 ---
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "temperature": 1.0,
        "max_tokens": 2048,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        # --- 提示词配置 ---
        "system_prompt": _PAPER_RECOMMEND_SYSTEM_PROMPT_DEFAULT,
        "summary_limit_prompt_intro": _PAPER_RECOMMEND_LIMIT_PROMPT_INTRO,
        "summary_limit_prompt_method": _PAPER_RECOMMEND_LIMIT_PROMPT_METHOD,
        "summary_limit_prompt_findings": _PAPER_RECOMMEND_LIMIT_PROMPT_FINDINGS,
        "summary_limit_prompt_opinion": _PAPER_RECOMMEND_LIMIT_PROMPT_OPINION,
        # --- 字数上限 ---
        "section_limit_intro": 170,
        "section_limit_method": 270,
        "section_limit_findings": 270,
        "section_limit_opinion": 150,
        "headline_limit": 18,
    },
    # Future features can be added here:
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
