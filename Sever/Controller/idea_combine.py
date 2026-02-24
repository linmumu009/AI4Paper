"""
Inspiration v2 — Layer B: Combination Pipeline Step.

Steps combined:
  11. question_generator — mine questions from limitation atoms
  12. idea_retrieve — retrieve relevant atoms for each question
  13. insight_generate — multi-strategy candidate generation
  14. Output structured IdeaCandidate records

Usage:
    python idea_combine.py --date 2025-06-15 --user-id 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import config.config as _config_module  # noqa: E402
from config.config import (  # noqa: E402
    DATA_ROOT,
    idea_generate_base_url,
    idea_generate_api_key,
    idea_generate_model,
    idea_generate_max_tokens,
    idea_generate_temperature,
    idea_generate_input_hard_limit,
    idea_generate_input_safety_margin,
)


# ---------------------------------------------------------------------------
# LLM config (system config first, user settings as fallback)
# ---------------------------------------------------------------------------

def _load_user_config(user_id: int) -> Dict[str, Any]:
    try:
        from services.user_settings_service import get_settings
        return get_settings(user_id, "idea_generate")
    except Exception:
        return {}


def _resolve_llm_preset(user_id: int, preset_id: Any) -> Dict[str, Any]:
    try:
        pid = int(preset_id)
    except (TypeError, ValueError):
        return {}
    try:
        from services.user_presets_service import get_llm_preset
        return get_llm_preset(user_id, pid) or {}
    except Exception:
        return {}


def _resolve_prompt_preset(user_id: int, preset_id: Any) -> str:
    """Resolve a user prompt preset to its content string."""
    try:
        pid = int(preset_id)
    except (TypeError, ValueError):
        return ""
    try:
        from services.user_presets_service import get_prompt_preset
        p = get_prompt_preset(user_id, pid)
        return (p or {}).get("prompt_content", "")
    except Exception:
        return ""


def _resolve_prompt(ucfg: Dict[str, Any], user_id: int,
                    module_preset_key: str, user_text_key: str,
                    config_var_name: str) -> str:
    """Resolve a prompt for a specific module with the standard priority chain.

    Priority:
      1. Module-specific prompt preset
      2. Global prompt preset
      3. User settings per-phase text override
      4. config.py variable
    """
    # 1. Module-specific prompt preset
    preset_id = ucfg.get(module_preset_key) or ucfg.get("prompt_preset_id")
    if preset_id:
        content = _resolve_prompt_preset(user_id, preset_id)
        if content:
            return content
    # 2. Per-phase text override in user settings
    user_text = (ucfg.get(user_text_key) or "").strip()
    if user_text:
        return user_text
    # 3. config.py variable
    return (getattr(_config_module, config_var_name, "") or "").strip()


def _make_client(user_id: Optional[int] = None,
                 module: str = "question") -> Tuple[Optional[OpenAI], Dict[str, Any]]:
    """Create OpenAI client for a specific idea_combine phase.

    module: "question" | "candidate"

    Priority for LLM credentials:
      1. System-level per-phase: idea_question_* / idea_candidate_*
      2. System-level global fallback: idea_generate_*
      3. Per-user settings (presets / manual)
    """
    # Map module → system config variable prefix
    _SYS_PREFIX = {
        "question":  "idea_question",
        "candidate": "idea_candidate",
    }
    sys_pfx = _SYS_PREFIX.get(module, "idea_question")

    cfg: Dict[str, Any] = {
        "model": "",
        "temperature": 0.7,
        "max_tokens": 8192,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
    }
    key = ""
    base = ""

    # --- 1. Try system-level config (per-phase → global fallback) ---
    sys_base = (getattr(_config_module, f"{sys_pfx}_base_url", "") or "").strip()
    sys_key  = (getattr(_config_module, f"{sys_pfx}_api_key",  "") or "").strip()
    sys_model= (getattr(_config_module, f"{sys_pfx}_model",    "") or "").strip()
    if not (sys_base and sys_key and sys_model):
        sys_base = (getattr(_config_module, "idea_generate_base_url", "") or "").strip()
        sys_key  = (getattr(_config_module, "idea_generate_api_key",  "") or "").strip()
        sys_model= (getattr(_config_module, "idea_generate_model",    "") or "").strip()
    if sys_base and sys_key and sys_model:
        base = sys_base
        key = sys_key
        cfg["model"] = sys_model
        cfg["max_tokens"] = getattr(_config_module, "idea_generate_max_tokens", 8192)
        cfg["temperature"] = getattr(_config_module, "idea_generate_temperature", 0.7)
        cfg["input_hard_limit"] = getattr(_config_module, "idea_generate_input_hard_limit", 129024)
        cfg["input_safety_margin"] = getattr(_config_module, "idea_generate_input_safety_margin", 4096)
        print(f"[IDEA_COMBINE] Using system-level {sys_pfx}/idea_generate config.", flush=True)
    elif user_id is not None:
        # --- 2. Fallback: per-user settings ---
        ucfg = _load_user_config(user_id)
        if ucfg:
            # Per-phase user preset key (matches ProfileSettings form keys)
            module_llm_key = f"{module}_llm_preset_id"  # "question_llm_preset_id" or "candidate_llm_preset_id"
            preset_id = ucfg.get(module_llm_key) or ucfg.get("llm_preset_id")
            preset = _resolve_llm_preset(user_id, preset_id) if preset_id else {}
            if preset:
                key = (preset.get("api_key") or "").strip()
                base = (preset.get("base_url") or "").strip()
                cfg["model"] = (preset.get("model") or "").strip()
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if preset.get(k) is not None:
                        cfg[k] = preset[k]
            else:
                key = (ucfg.get("llm_api_key") or "").strip()
                base = (ucfg.get("llm_base_url") or "").strip()
                cfg["model"] = (ucfg.get("llm_model") or "").strip()
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if ucfg.get(k) is not None:
                        cfg[k] = ucfg[k]
            # Store ucfg for prompt resolution later
            cfg["_ucfg"] = ucfg
        if key:
            print(f"[IDEA_COMBINE] Using per-user idea_generate config (user_id={user_id}).", flush=True)

    if not key or not base or not cfg["model"]:
        return None, cfg
    return OpenAI(api_key=key, base_url=base), cfg


def _approx_tokens(text: str) -> int:
    return len(text.encode("utf-8", errors="ignore")) if text else 0


def _crop(text: str, budget: int) -> str:
    b = text.encode("utf-8", errors="ignore")
    return text if len(b) <= budget else b[:budget].decode("utf-8", errors="ignore")


def _call_llm_json(
    client: OpenAI, cfg: Dict[str, Any], system_prompt: str, user_content: str,
) -> Dict[str, Any]:
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    limit_total = hard_limit - safety_margin
    sys_tokens = _approx_tokens(system_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = _crop(user_content, user_budget)

    kwargs: Dict[str, Any] = {}
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = float(cfg["temperature"])
    if cfg.get("max_tokens") is not None:
        kwargs["max_tokens"] = int(cfg["max_tokens"])

    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        **kwargs,
    )
    text = resp.choices[0].message.content if resp.choices else ""
    return _parse_json(text)


def _parse_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    s = text.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except json.JSONDecodeError:
            pass
    start = s.find("[")
    end = s.rfind("]")
    if start != -1 and end > start:
        try:
            return {"items": json.loads(s[start:end + 1])}
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# Step 11: Question generation
# ---------------------------------------------------------------------------

def generate_questions(
    client: OpenAI, cfg: Dict[str, Any], user_id: int,
) -> List[Dict[str, Any]]:
    from services import idea_service

    # Gather limitation and method atoms
    atoms = idea_service.list_atoms(user_id=user_id, atom_type="limitation", limit=30)
    atoms += idea_service.list_atoms(user_id=user_id, atom_type="method", limit=20)
    if not atoms:
        atoms = idea_service.list_atoms(user_id=user_id, limit=50)
    if not atoms:
        return []

    atoms_text = "\n\n".join(
        f"[{a['atom_type'].upper()}] (paper: {a['paper_id']})\n{a['content']}"
        for a in atoms[:50]
    )

    # Resolve system prompt for question generation
    ucfg = cfg.get("_ucfg", {})
    question_prompt = _resolve_prompt(
        ucfg, user_id,
        module_preset_key="combine_question_prompt_preset_id",
        user_text_key="combine_question_prompt",
        config_var_name="idea_question_system_prompt",
    )
    result = _call_llm_json(client, cfg, question_prompt, atoms_text)
    questions_raw = result.get("questions") or result.get("items") or []

    created = []
    for q in questions_raw:
        if isinstance(q, str):
            q = {"question": q, "strategy": "general"}
        qobj = idea_service.create_question(
            user_id=user_id,
            question_text=q.get("question", ""),
            source_atom_ids=[a["id"] for a in atoms[:5]],
            strategy=q.get("strategy", "general"),
            context={"raw_context": q.get("context", "")},
        )
        created.append(qobj)

    return created


# ---------------------------------------------------------------------------
# Step 12-14: Retrieve + generate candidates
# ---------------------------------------------------------------------------

def generate_candidates_for_question(
    client: OpenAI,
    cfg: Dict[str, Any],
    user_id: int,
    question: Dict[str, Any],
) -> List[Dict[str, Any]]:
    from services import idea_service

    q_text = question.get("question_text", "")
    q_id = question.get("id")

    # Retrieve relevant atoms (FTS first, fallback to recent)
    try:
        atoms = idea_service.search_atoms_fts(q_text, user_id=user_id, limit=20)
    except Exception:
        atoms = []
    if not atoms:
        atoms = idea_service.list_atoms(user_id=user_id, limit=20)
    if not atoms:
        return []

    atoms_context = "\n\n".join(
        f"[ATOM-{a['id']}] [{a['atom_type'].upper()}] (paper: {a['paper_id']})\n{a['content']}"
        for a in atoms
    )

    user_content = f"## 研究问题\n{q_text}\n\n## 可用灵感原子\n{atoms_context}"
    # Resolve system prompt for candidate generation
    ucfg = cfg.get("_ucfg", {})
    candidate_prompt = _resolve_prompt(
        ucfg, user_id,
        module_preset_key="combine_candidate_prompt_preset_id",
        user_text_key="combine_candidate_prompt",
        config_var_name="idea_candidate_system_prompt",
    )
    result = _call_llm_json(client, cfg, candidate_prompt, user_content)
    candidates_raw = result.get("candidates") or result.get("items") or []

    created = []
    for c in candidates_raw:
        if isinstance(c, str):
            continue
        cobj = idea_service.create_candidate(
            user_id=user_id,
            title=c.get("title", "未命名灵感"),
            goal=c.get("goal", ""),
            mechanism=c.get("mechanism", ""),
            risks=c.get("risks", ""),
            strategy=c.get("strategy", ""),
            question_id=q_id,
            tags=c.get("tags", []),
            input_atom_ids=c.get("input_atom_ids", []),
        )
        created.append(cobj)

    return created


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _write_manifest(date_str: str, data: dict) -> None:
    """Write sentinel .jsonl file so app.py pipeline recognises this step as done."""
    root = os.path.dirname(os.path.dirname(__file__))
    from config.config import DATA_ROOT as _DATA_ROOT
    out_dir = os.path.join(root, _DATA_ROOT, "idea_combine")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date_str}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def run() -> None:
    ap = argparse.ArgumentParser("idea_combine")
    ap.add_argument("--date", default="")
    ap.add_argument("--user-id", type=int, default=None)
    args = ap.parse_args()

    date_str = args.date or os.environ.get("RUN_DATE", "") or datetime.now().date().isoformat()
    user_id = args.user_id or int(os.environ.get("PIPELINE_USER_ID", "0") or "0")

    if not user_id:
        print("[IDEA_COMBINE] No user_id; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "no_user_id", "date": date_str})
        return

    # Each phase gets its own independent client (1:1 model+prompt)
    q_client, q_cfg = _make_client(user_id, module="question")
    c_client, c_cfg = _make_client(user_id, module="candidate")

    if not q_client:
        print("[IDEA_COMBINE] LLM not configured for question generation; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "llm_not_configured", "date": date_str, "user_id": user_id})
        return
    if not c_client:
        print("[IDEA_COMBINE] LLM not configured for candidate generation; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "llm_not_configured", "date": date_str, "user_id": user_id})
        return

    from services import idea_service

    # Check we have atoms to work with
    atom_count = idea_service.count_atoms(user_id)
    if atom_count == 0:
        print("[IDEA_COMBINE] No atoms found; run idea_ingest first.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "no_atoms", "date": date_str, "user_id": user_id})
        return

    print(f"============开始 灵感组合 (idea_combine) ============", flush=True)
    print(f"[IDEA_COMBINE] date={date_str} user_id={user_id} atoms={atom_count}", flush=True)

    # Idempotency: remove questions and candidates created today before re-generating
    q_del = idea_service.delete_questions_for_date(user_id, date_str)
    c_del = idea_service.delete_candidates_for_date(user_id, date_str)
    if q_del or c_del:
        print(f"[IDEA_COMBINE] Idempotency: removed {q_del} old questions, {c_del} old candidates for {date_str}.", flush=True)

    # Step 11: Generate questions (using question-phase model)
    print("[IDEA_COMBINE] Generating research questions...", flush=True)
    questions = generate_questions(q_client, q_cfg, user_id)
    print(f"[IDEA_COMBINE] Generated {len(questions)} questions.", flush=True)

    if not questions:
        print("[IDEA_COMBINE] No questions generated; stopping.", flush=True)
        _write_manifest(date_str, {"status": "done", "date": date_str, "user_id": user_id,
                                   "total_questions": 0, "total_candidates": 0})
        return

    # Step 12-14: Generate candidates for each question (using candidate-phase model)
    total_candidates = 0
    for i, q in enumerate(questions):
        print(f"[IDEA_COMBINE] Q{i+1}/{len(questions)}: {q.get('question_text', '')[:80]}...", flush=True)
        try:
            candidates = generate_candidates_for_question(c_client, c_cfg, user_id, q)
            total_candidates += len(candidates)
            print(f"[IDEA_COMBINE]   → {len(candidates)} candidates", flush=True)
        except Exception as e:
            print(f"[IDEA_COMBINE]   → error: {e!r}", flush=True)

    print(f"[IDEA_COMBINE] Total: {len(questions)} questions, {total_candidates} candidates", flush=True)
    print(f"============结束 灵感组合 (idea_combine) ============", flush=True)

    _write_manifest(date_str, {
        "status": "done",
        "date": date_str,
        "user_id": user_id,
        "total_questions": len(questions),
        "total_candidates": total_candidates,
    })


if __name__ == "__main__":
    run()
