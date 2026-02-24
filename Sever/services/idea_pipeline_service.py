"""
Inspiration Generation v2 – pipeline orchestration service.

Provides high-level functions called by API endpoints to:
  - Run atom extraction for a paper / date
  - Generate questions from limitation atoms
  - Retrieve relevant atoms and generate inspiration candidates
  - Run the review pipeline (consistency, novelty, feasibility, impact, critic)
  - Revise candidates and publish
  - Generate execution plans from candidates

All LLM interactions use the same pattern as compare_service.py:
  - Read user settings (feature="idea_generate")
  - Resolve LLM preset if configured
  - Stream or batch call via OpenAI-compatible API

This service is stateless; all persistence goes through idea_service.py.
"""

import json
import os
from typing import Any, Generator, Optional

from openai import OpenAI


# ---------------------------------------------------------------------------
# Lazy service imports (avoid circular imports at module level)
# ---------------------------------------------------------------------------

_idea_service = None
_user_settings_service = None
_user_presets_service = None


def _get_idea_service():
    global _idea_service
    if _idea_service is None:
        from services import idea_service as _is
        _idea_service = _is
    return _idea_service


def _get_user_settings_service():
    global _user_settings_service
    if _user_settings_service is None:
        from services import user_settings_service as _us
        _user_settings_service = _us
    return _user_settings_service


def _get_user_presets_service():
    global _user_presets_service
    if _user_presets_service is None:
        from services import user_presets_service as _up
        _user_presets_service = _up
    return _user_presets_service


# ---------------------------------------------------------------------------
# File system helpers
# ---------------------------------------------------------------------------

_SEVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILE_COLLECT_DIR = os.path.join(_SEVER_ROOT, "data", "file_collect")
_IDEA_DATA_DIR = os.path.join(_SEVER_ROOT, "data", "idea")


def _find_paper_dir(paper_id: str) -> Optional[str]:
    """Search all date directories under file_collect/ for a paper_id folder."""
    if not os.path.isdir(_FILE_COLLECT_DIR):
        return None
    for date_dir in sorted(os.listdir(_FILE_COLLECT_DIR), reverse=True):
        paper_dir = os.path.join(_FILE_COLLECT_DIR, date_dir, paper_id)
        if os.path.isdir(paper_dir):
            return paper_dir
    return None


def _read_file(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _approx_tokens(text: str) -> int:
    return len(text.encode("utf-8", errors="ignore")) if text else 0


def _crop(text: str, budget: int) -> str:
    b = text.encode("utf-8", errors="ignore")
    if len(b) <= budget:
        return text
    return b[:budget].decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# LLM client helpers
# ---------------------------------------------------------------------------

_FEATURE = "idea_generate"

# Mapping: module name → (user settings prompt key, config.py variable name)
# Each phase has its own independent 1:1 model+prompt pair
_MODULE_PROMPT_MAP = {
    "ingest":            ("ingest_system_prompt",    "idea_ingest_system_prompt"),
    "combine_question":  ("question_system_prompt",  "idea_question_system_prompt"),
    "combine_candidate": ("candidate_system_prompt", "idea_candidate_system_prompt"),
    "review":            ("review_system_prompt",    "idea_review_system_prompt"),
    "revise":            ("revise_system_prompt",    "idea_revise_system_prompt"),
    "plan":              ("plan_system_prompt",      "idea_plan_system_prompt"),
    "eval":              ("eval_system_prompt",      "idea_eval_system_prompt"),
}

# Mapping: module name → user settings per-phase LLM preset ID key
_MODULE_LLM_PRESET_KEY = {
    "ingest":            "ingest_llm_preset_id",
    "combine_question":  "question_llm_preset_id",
    "combine_candidate": "candidate_llm_preset_id",
    "review":            "review_llm_preset_id",
    "revise":            "revise_llm_preset_id",
    "plan":              "plan_llm_preset_id",
    "eval":              "eval_llm_preset_id",
}

_MODULE_PROMPT_PRESET_KEY = {
    "ingest":            "ingest_prompt_preset_id",
    "combine_question":  "question_prompt_preset_id",
    "combine_candidate": "candidate_prompt_preset_id",
    "review":            "review_prompt_preset_id",
    "revise":            "revise_prompt_preset_id",
    "plan":              "plan_prompt_preset_id",
    "eval":              "eval_prompt_preset_id",
}

# Mapping: module name → system config prefix for model variables
# Each phase gets its own 1:1 model prefix (falls back to idea_generate_* global)
_MODULE_SYS_CFG_PREFIX = {
    "ingest":            "idea_ingest",
    "combine_question":  "idea_question",
    "combine_candidate": "idea_candidate",
    "review":            "idea_review",
    "revise":            "idea_revise",
    "plan":              "idea_plan",
    "eval":              "idea_eval",
}


def _get_llm_config(user_id: int, module: str = "ingest") -> dict:
    """Load LLM settings for idea generation, resolving per-module presets.

    Priority for LLM credentials:
      1. Module-specific LLM preset (e.g. ingest_llm_preset_id)  [user]
      2. Global LLM preset (llm_preset_id)                        [user]
      3. Manual llm_base_url / llm_api_key / llm_model            [user]
      4. System config: per-module (e.g. idea_ingest_base_url)    [system]
      5. System config: global fallback (idea_generate_base_url)  [system]

    Priority for system_prompt:
      1. Module-specific prompt preset (e.g. ingest_prompt_preset_id)
      2. Global prompt preset (prompt_preset_id)
      3. User settings per-phase text override (e.g. ingest_system_prompt)
      4. config.py variable for this phase (e.g. idea_ingest_system_prompt)
      5. Legacy system_prompt field in user settings (backward compat, ingest only)
    """
    import config.config as _cfg_mod

    us = _get_user_settings_service()
    ups = _get_user_presets_service()
    cfg = us.get_settings(user_id, _FEATURE)

    # --- Resolve LLM: module-specific preset → global preset → manual user config ---
    module_llm_key = _MODULE_LLM_PRESET_KEY.get(module, "llm_preset_id")
    llm_preset_id = cfg.get(module_llm_key) or cfg.get("llm_preset_id")
    if llm_preset_id:
        preset = ups.get_llm_preset(user_id, int(llm_preset_id))
        if preset:
            cfg["llm_base_url"] = preset.get("base_url", "")
            cfg["llm_api_key"] = preset.get("api_key", "")
            cfg["llm_model"] = preset.get("model", "")
            for k in ("max_tokens", "temperature", "input_hard_limit", "input_safety_margin"):
                if preset.get(k) is not None:
                    cfg[k] = preset[k]

    # --- If no user credentials found, fall back to system config ---
    if not ((cfg.get("llm_base_url") or "").strip()
            and (cfg.get("llm_api_key") or "").strip()
            and (cfg.get("llm_model") or "").strip()):
        sys_pfx = _MODULE_SYS_CFG_PREFIX.get(module, "idea_generate")
        sys_base = (getattr(_cfg_mod, f"{sys_pfx}_base_url", "") or "").strip()
        sys_key  = (getattr(_cfg_mod, f"{sys_pfx}_api_key",  "") or "").strip()
        sys_mdl  = (getattr(_cfg_mod, f"{sys_pfx}_model",    "") or "").strip()
        if not (sys_base and sys_key and sys_mdl):
            sys_base = (getattr(_cfg_mod, "idea_generate_base_url", "") or "").strip()
            sys_key  = (getattr(_cfg_mod, "idea_generate_api_key",  "") or "").strip()
            sys_mdl  = (getattr(_cfg_mod, "idea_generate_model",    "") or "").strip()
        if sys_base and sys_key and sys_mdl:
            cfg["llm_base_url"] = sys_base
            cfg["llm_api_key"]  = sys_key
            cfg["llm_model"]    = sys_mdl
            cfg.setdefault("max_tokens",          getattr(_cfg_mod, "idea_generate_max_tokens", 8192))
            cfg.setdefault("temperature",          getattr(_cfg_mod, "idea_generate_temperature", 0.7))
            cfg.setdefault("input_hard_limit",     getattr(_cfg_mod, "idea_generate_input_hard_limit", 129024))
            cfg.setdefault("input_safety_margin",  getattr(_cfg_mod, "idea_generate_input_safety_margin", 4096))

    # --- Resolve system_prompt ---
    # 1. Module-specific prompt preset
    module_prompt_key = _MODULE_PROMPT_PRESET_KEY.get(module, "prompt_preset_id")
    prompt_preset_id = cfg.get(module_prompt_key) or cfg.get("prompt_preset_id")
    if prompt_preset_id:
        p_preset = ups.get_prompt_preset(user_id, int(prompt_preset_id))
        if p_preset and p_preset.get("prompt_content"):
            cfg["system_prompt"] = p_preset["prompt_content"]
            return cfg

    # 2. Per-phase text override in user settings
    user_settings_prompt_key, config_var_name = _MODULE_PROMPT_MAP.get(
        module, ("system_prompt", "idea_ingest_system_prompt")
    )
    user_phase_prompt = (cfg.get(user_settings_prompt_key) or "").strip()
    if user_phase_prompt:
        cfg["system_prompt"] = user_phase_prompt
        return cfg

    # 3. Backward compat: for ingest, also check legacy system_prompt field
    if module == "ingest":
        legacy = (cfg.get("system_prompt") or "").strip()
        if legacy:
            return cfg

    # 4. config.py variable for this phase
    sys_prompt = (getattr(_cfg_mod, config_var_name, "") or "").strip()
    if sys_prompt:
        cfg["system_prompt"] = sys_prompt
        return cfg

    # 5. Leave system_prompt as whatever is in cfg (could be empty)
    return cfg


def _make_client(cfg: dict) -> Optional[OpenAI]:
    """Create OpenAI client from config dict. Returns None if missing credentials."""
    url = (cfg.get("llm_base_url") or "").strip()
    key = (cfg.get("llm_api_key") or "").strip()
    if not url or not key:
        return None
    return OpenAI(api_key=key, base_url=url)


def _check_credentials(cfg: dict) -> Optional[str]:
    """Return an error message if LLM credentials are missing, else None."""
    url = (cfg.get("llm_base_url") or "").strip()
    key = (cfg.get("llm_api_key") or "").strip()
    model = (cfg.get("llm_model") or "").strip()
    if not url or not key or not model:
        return "请先在「个人中心 → 灵感生成」中配置 LLM 的 URL、API Key 和 Model，或选择一个模型预设。"
    return None


def _call_llm(
    client: OpenAI,
    cfg: dict,
    system_prompt: str,
    user_content: str,
    stream: bool = False,
) -> Any:
    """Call LLM with token budget control. Returns response (stream or not)."""
    model = (cfg.get("llm_model") or "").strip()
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    limit_total = hard_limit - safety_margin
    sys_tokens = _approx_tokens(system_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = _crop(user_content, user_budget)

    kwargs: dict = {}
    temperature = cfg.get("temperature")
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    max_tokens = cfg.get("max_tokens")
    if max_tokens is not None:
        kwargs["max_tokens"] = int(max_tokens)

    return client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=stream,
        **kwargs,
    )


def _call_llm_json(client: OpenAI, cfg: dict, system_prompt: str, user_content: str) -> dict:
    """Call LLM and parse JSON from response."""
    model = (cfg.get("llm_model") or "").strip()
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    limit_total = hard_limit - safety_margin
    sys_tokens = _approx_tokens(system_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content_cropped = _crop(user_content, user_budget)

    kwargs: dict = {"response_format": {"type": "json_object"}}
    temperature = cfg.get("temperature")
    if temperature is not None:
        kwargs["temperature"] = float(temperature)
    max_tokens = cfg.get("max_tokens")
    if max_tokens is not None:
        kwargs["max_tokens"] = int(max_tokens)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content_cropped},
        ],
        **kwargs,
    )
    text = resp.choices[0].message.content if resp.choices else ""
    return _parse_json(text)


def _parse_json(text: str) -> dict:
    """Extract JSON object from LLM text response."""
    if not text:
        return {}
    s = text.strip()
    # Try to find JSON block
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except json.JSONDecodeError:
            pass
    # Try JSON array
    start = s.find("[")
    end = s.rfind("]")
    if start != -1 and end > start:
        try:
            return {"items": json.loads(s[start:end + 1])}
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# SSE streaming helpers
# ---------------------------------------------------------------------------

def _sse_error(msg: str) -> Generator[str, None, None]:
    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _sse_stream_llm(client: OpenAI, cfg: dict, system_prompt: str, user_content: str) -> Generator[str, None, None]:
    """Stream LLM response as SSE events."""
    try:
        response = _call_llm(client, cfg, system_prompt, user_content, stream=True)
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                yield f"data: {json.dumps(text, ensure_ascii=False)}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps(f'生成失败: {exc}', ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# A. Atom extraction (on-demand from API)
# ---------------------------------------------------------------------------

def extract_atoms_for_paper(
    user_id: int,
    paper_id: str,
    date_str: str = "",
) -> dict:
    """
    Extract idea atoms from a paper's full text / summary.
    Returns {"atoms": [...], "count": N} on success, {"error": "..."} on failure.
    """
    isvc = _get_idea_service()
    cfg = _get_llm_config(user_id, module="ingest")
    err = _check_credentials(cfg)
    if err:
        return {"error": err}

    client = _make_client(cfg)
    if not client:
        return {"error": "LLM 客户端创建失败"}

    # Load paper content
    paper_dir = _find_paper_dir(paper_id)
    if not paper_dir:
        return {"error": f"找不到论文目录: {paper_id}"}

    # Prefer MinerU full text, fall back to summary
    content = _read_file(os.path.join(paper_dir, f"{paper_id}_mineru.md"))
    if not content:
        content = _read_file(os.path.join(paper_dir, f"{paper_id}_summary.md"))
    if not content:
        content = _read_file(os.path.join(paper_dir, f"{paper_id}_limit.md"))
    if not content:
        return {"error": f"找不到论文内容: {paper_id}"}

    # Delete existing atoms for this paper (re-extraction)
    isvc.delete_atoms_for_paper(user_id, paper_id)

    # system_prompt is fully resolved by _get_llm_config(module="ingest"):
    #   1. User per-module prompt preset (ingest_prompt_preset_id)
    #   2. Global prompt preset (prompt_preset_id)
    #   3. User settings ingest_system_prompt text
    #   4. Legacy system_prompt text (backward compat)
    #   5. config.py idea_ingest_system_prompt (admin-editable)
    system_prompt = cfg.get("system_prompt") or ""
    result = _call_llm_json(client, cfg, system_prompt, content)

    atoms_data = result.get("atoms") or result.get("items") or []
    if not atoms_data and isinstance(result, dict):
        # Maybe the model returned a flat structure
        for key in ("claims", "methods", "experiments", "limitations"):
            if key in result:
                for item in result[key]:
                    if isinstance(item, str):
                        atoms_data.append({"type": key.rstrip("s"), "content": item})
                    elif isinstance(item, dict):
                        item.setdefault("type", key.rstrip("s"))
                        atoms_data.append(item)

    # Normalize and save
    batch = []
    for a in atoms_data:
        if isinstance(a, str):
            a = {"type": "claim", "content": a}
        batch.append({
            "paper_id": paper_id,
            "date_str": date_str,
            "atom_type": a.get("type", "claim"),
            "content": a.get("content", ""),
            "tags": a.get("tags", []),
            "evidence": a.get("evidence", []),
            "section": a.get("section", ""),
            "source_file": f"{paper_id}_mineru.md",
        })

    count = isvc.create_atoms_batch(user_id, batch) if batch else 0
    return {"atoms": batch, "count": count}


# ---------------------------------------------------------------------------
# B. Question generation
# ---------------------------------------------------------------------------

def generate_questions(user_id: int, limit: int = 10) -> dict:
    """Generate research questions from limitation / setup atoms."""
    isvc = _get_idea_service()
    cfg = _get_llm_config(user_id, module="combine_question")
    err = _check_credentials(cfg)
    if err:
        return {"error": err}

    client = _make_client(cfg)
    if not client:
        return {"error": "LLM 客户端创建失败"}

    # Gather limitation atoms
    limitation_atoms = isvc.list_atoms(user_id=user_id, atom_type="limitation", limit=50)
    if not limitation_atoms:
        # Fall back to all atom types
        limitation_atoms = isvc.list_atoms(user_id=user_id, limit=50)
    if not limitation_atoms:
        return {"error": "没有可用的灵感原子，请先提取论文原子。"}

    # Build context
    atoms_text = "\n\n".join(
        f"[{a['atom_type'].upper()}] (paper: {a['paper_id']})\n{a['content']}"
        for a in limitation_atoms
    )

    system_prompt = cfg.get("system_prompt") or ""
    result = _call_llm_json(client, cfg, system_prompt, atoms_text)
    questions = result.get("questions") or result.get("items") or []

    created = []
    for q in questions:
        if isinstance(q, str):
            q = {"question": q, "strategy": "general"}
        qobj = isvc.create_question(
            user_id=user_id,
            question_text=q.get("question", ""),
            source_atom_ids=[a["id"] for a in limitation_atoms[:5]],
            strategy=q.get("strategy", "general"),
            context=q.get("context"),
        )
        created.append(qobj)

    return {"questions": created, "count": len(created)}


# ---------------------------------------------------------------------------
# B. Candidate generation (streaming)
# ---------------------------------------------------------------------------

def stream_generate_candidates(
    user_id: int,
    question_id: int | None = None,
    custom_question: str = "",
    strategies: list[str] | None = None,
) -> Generator[str, None, None]:
    """Generate inspiration candidates as SSE stream."""
    isvc = _get_idea_service()
    cfg = _get_llm_config(user_id, module="combine_candidate")
    err = _check_credentials(cfg)
    if err:
        yield from _sse_error(err)
        return

    client = _make_client(cfg)
    if not client:
        yield from _sse_error("LLM 客户端创建失败")
        return

    # Get question text
    question_text = custom_question
    if question_id:
        q = isvc.get_question(question_id)
        if q:
            question_text = q["question_text"]

    if not question_text:
        yield from _sse_error("请提供一个研究问题或选择一个已生成的问题。")
        return

    # Retrieve relevant atoms
    atoms = isvc.search_atoms_fts(question_text, user_id=user_id, limit=20)
    if not atoms:
        atoms = isvc.list_atoms(user_id=user_id, limit=20)

    atoms_context = "\n\n".join(
        f"[ATOM-{a['id']}] [{a['atom_type'].upper()}] (paper: {a['paper_id']})\n{a['content']}"
        for a in atoms
    )

    strategies = strategies or ["transfer", "stitch", "counterfactual", "patch", "resource_constrained"]
    strategies_text = ", ".join(strategies)

    user_content = (
        f"## 研究问题\n{question_text}\n\n"
        f"## 可用灵感原子\n{atoms_context}\n\n"
        f"## 要求使用的策略\n{strategies_text}"
    )

    system_prompt = cfg.get("system_prompt") or ""
    yield from _sse_stream_llm(client, cfg, system_prompt, user_content)


# ---------------------------------------------------------------------------
# C. Review (streaming)
# ---------------------------------------------------------------------------

def stream_review_candidate(
    user_id: int,
    candidate_id: int,
) -> Generator[str, None, None]:
    """Run multi-critic review on a candidate as SSE stream."""
    isvc = _get_idea_service()
    cfg = _get_llm_config(user_id, module="review")
    err = _check_credentials(cfg)
    if err:
        yield from _sse_error(err)
        return

    client = _make_client(cfg)
    if not client:
        yield from _sse_error("LLM 客户端创建失败")
        return

    candidate = isvc.get_candidate(candidate_id)
    if not candidate:
        yield from _sse_error("灵感候选不存在")
        return

    user_content = (
        f"## 灵感候选\n"
        f"标题: {candidate['title']}\n"
        f"目标: {candidate['goal']}\n"
        f"机制: {candidate['mechanism']}\n"
        f"风险: {candidate['risks']}\n"
    )

    system_prompt = cfg.get("system_prompt") or ""
    yield from _sse_stream_llm(client, cfg, system_prompt, user_content)


# ---------------------------------------------------------------------------
# C. Revise candidate (streaming)
# ---------------------------------------------------------------------------

def stream_revise_candidate(
    user_id: int,
    candidate_id: int,
    review_feedback: str = "",
) -> Generator[str, None, None]:
    """Auto-revise a candidate based on review feedback as SSE stream."""
    isvc = _get_idea_service()
    cfg = _get_llm_config(user_id, module="revise")
    err = _check_credentials(cfg)
    if err:
        yield from _sse_error(err)
        return

    client = _make_client(cfg)
    if not client:
        yield from _sse_error("LLM 客户端创建失败")
        return

    candidate = isvc.get_candidate(candidate_id)
    if not candidate:
        yield from _sse_error("灵感候选不存在")
        return

    user_content = (
        f"## 原始灵感\n"
        f"标题: {candidate['title']}\n"
        f"目标: {candidate['goal']}\n"
        f"机制: {candidate['mechanism']}\n"
        f"风险: {candidate['risks']}\n\n"
        f"## 评审反馈\n{review_feedback}"
    )

    system_prompt = cfg.get("system_prompt") or ""
    yield from _sse_stream_llm(client, cfg, system_prompt, user_content)


# ---------------------------------------------------------------------------
# Plan generation (streaming)
# ---------------------------------------------------------------------------

def stream_generate_plan(
    user_id: int,
    candidate_id: int,
) -> Generator[str, None, None]:
    """Generate an execution plan for a candidate as SSE stream."""
    isvc = _get_idea_service()
    cfg = _get_llm_config(user_id, module="plan")
    err = _check_credentials(cfg)
    if err:
        yield from _sse_error(err)
        return

    client = _make_client(cfg)
    if not client:
        yield from _sse_error("LLM 客户端创建失败")
        return

    candidate = isvc.get_candidate(candidate_id)
    if not candidate:
        yield from _sse_error("灵感候选不存在")
        return

    user_content = (
        f"## 灵感候选\n"
        f"标题: {candidate['title']}\n"
        f"目标: {candidate['goal']}\n"
        f"机制: {candidate['mechanism']}\n"
        f"风险: {candidate['risks']}\n"
    )

    system_prompt = cfg.get("system_prompt") or ""
    yield from _sse_stream_llm(client, cfg, system_prompt, user_content)


# ---------------------------------------------------------------------------
# Eval replay (streaming)
# ---------------------------------------------------------------------------

def stream_eval_replay(
    user_id: int,
    question_ids: list[int],
) -> Generator[str, None, None]:
    """Re-run question set and compare against historical results (SSE)."""
    isvc = _get_idea_service()
    cfg = _get_llm_config(user_id, module="eval")
    err = _check_credentials(cfg)
    if err:
        yield from _sse_error(err)
        return

    client = _make_client(cfg)
    if not client:
        yield from _sse_error("LLM 客户端创建失败")
        return

    questions = []
    for qid in question_ids:
        q = isvc.get_question(qid)
        if q:
            questions.append(q)

    if not questions:
        yield from _sse_error("没有找到对应的问题。")
        return

    questions_text = "\n\n".join(
        f"Q{i+1}: {q['question_text']}"
        for i, q in enumerate(questions)
    )

    system_prompt = cfg.get("system_prompt") or ""
    yield from _sse_stream_llm(client, cfg, system_prompt, questions_text)


# ---------------------------------------------------------------------------
# System prompts (built-in defaults — kept for reference only)
# ---------------------------------------------------------------------------
# All prompts below have been migrated to config.py as configurable variables:
#   idea_ingest_system_prompt, idea_question_system_prompt,
#   idea_candidate_system_prompt, idea_review_system_prompt,
#   idea_revise_system_prompt, idea_plan_system_prompt, idea_eval_system_prompt
# _get_llm_config(user_id, module=...) resolves system_prompt with the
# following priority:
#   per-module prompt preset → global prompt preset →
#   user settings text override → config.py variable

_QUESTION_GENERATION_PROMPT = """\
你是一个「研究问题生成器」。根据提供的灵感原子（主要是局限性和方法），生成有价值的研究问题。

每个问题应该：
1. 基于具体的原子内容，不要泛泛而谈
2. 有明确的研究方向和可操作性
3. 标注使用的策略

策略类型：
- transfer: A方法 → B任务/数据
- stitch: A的组件 + B的训练策略
- counterfactual: 若换指标/数据分布会怎样
- patch: 针对limitation提方案
- resource_constrained: 低算力/低数据/低延迟版本

输出格式：只输出 JSON {"questions": [{"question": "...", "strategy": "...", "context": {...}}]}
生成 5-10 个问题。
"""

_CANDIDATE_GENERATION_PROMPT = """\
你是一个「科研灵感生成器」。根据给定的研究问题和灵感原子，生成高质量的灵感候选。

对于每个灵感候选，请输出：

### 💡 灵感标题
一句话概括灵感

### 🎯 目标与适用场景
这个灵感要解决什么问题？适用于什么场景？

### ⚙️ 核心机制
具体怎么做？描述可落地的技术方案。引用相关原子编号（如 ATOM-1, ATOM-5）。

### 📊 需要的证据
验证这个灵感需要什么实验？用到哪些数据集和指标？

### ⚠️ 风险与假设
这个灵感依赖什么假设？有什么风险？

### 📈 预期影响
如果成功，预期提升多少？对什么领域有价值？

请按照上述 5 种策略（迁移/缝合/反事实/修补/资源约束）各生成 1-2 个灵感。
使用中文输出，专有名词保留英文。
"""

_REVIEW_PROMPT = """\
你是一个「灵感评审委员会」，包含三个视角：

1. 🔬 研究者视角（Researcher）：评估学术新颖性、理论完备性
2. 🛠️ 工程师视角（Engineer）：评估工程可行性、资源需求、实现复杂度
3. 👨‍🏫 审稿人视角（Reviewer）：评估论文发表潜力、实验说服力

对给定的灵感候选，请从三个视角分别给出：
- 评分（0-1，保留两位小数）
- 优点（2-3条）
- 不足（2-3条）
- 改进建议（1-2条）

最后给出：
- 综合评分（0-1）
- 是否建议采纳（是/否/修改后采纳）
- 一句话总评

使用中文输出，Markdown 格式。
"""

_REVISE_PROMPT = """\
你是一个「灵感修订助手」。根据评审反馈，对灵感候选进行修订。

修订原则：
1. 保留原始灵感的核心思路
2. 针对评审指出的不足进行改进
3. 补充缺失的细节（实验设计、数据需求等）
4. 降低风险项的影响

请输出修订后的完整灵感，格式与原始灵感相同：
- 标题
- 目标与适用场景
- 核心机制（具体改进了什么）
- 需要的证据
- 风险与假设（修订后的）
- 预期影响

使用中文输出，Markdown 格式。
"""

_PLAN_GENERATION_PROMPT = """\
你是一个「实验计划生成器」。根据灵感候选，生成详细的可执行实验计划。

请输出结构化计划：

### 📋 实验计划概述
一段话概括整个实验目标和思路。

### 🏁 里程碑
- M1: [描述] — 预计时间
- M2: [描述] — 预计时间
- ...

### 📊 评估指标
列出具体的评估指标和基线。

### 💾 数据需求
- 需要什么数据集？
- 数据量要求？
- 如何获取？

### 🔬 消融实验
列出关键的消融实验。

### 💰 资源需求
- GPU/计算需求
- 时间估算
- 人力需求

### ⏰ 时间线
详细的周/月计划。

使用中文输出，Markdown 格式。
"""

_EVAL_REPLAY_PROMPT = """\
你是一个「灵感评测回放器」。对给定的问题集重新生成灵感，用于与历史版本对比。

请对每个问题：
1. 生成 1 个最优灵感候选
2. 简要说明你的思路
3. 给出自评分（0-1）

输出格式使用 Markdown。
"""
