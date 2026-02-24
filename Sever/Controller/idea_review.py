"""
Inspiration v2 — Layer C: Review Pipeline Step.

Steps combined:
  15. consistency_check — fact check against evidence
  16. novelty_rank — score novelty vs existing ideas
  17. feasibility_rank — score engineering feasibility
  18. impact_rank — score potential impact
  19. multi_critic — 3-perspective voting
  20. revise_loop — auto-revise based on critique
  21. insight_publish — final scoring + status update

Usage:
    python idea_review.py --date 2025-06-15 --user-id 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import config.config as _config_module  # noqa: E402
from config.config import (  # noqa: E402
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
    """Resolve a prompt for a specific module with the standard priority chain."""
    preset_id = ucfg.get(module_preset_key) or ucfg.get("prompt_preset_id")
    if preset_id:
        content = _resolve_prompt_preset(user_id, preset_id)
        if content:
            return content
    user_text = (ucfg.get(user_text_key) or "").strip()
    if user_text:
        return user_text
    return (getattr(_config_module, config_var_name, "") or "").strip()


def _make_client(user_id: Optional[int] = None,
                 module: str = "review") -> Tuple[Optional[OpenAI], Dict[str, Any]]:
    """Create OpenAI client for a specific idea_review phase.

    module: "review" | "revise"

    Priority for LLM credentials:
      1. System-level per-phase: idea_review_* / idea_revise_*
      2. System-level global fallback: idea_generate_*
      3. Per-user settings (presets / manual)
    """
    # Map module → system config variable prefix
    _SYS_PREFIX = {
        "review": "idea_review",
        "revise": "idea_revise",
    }
    sys_pfx = _SYS_PREFIX.get(module, "idea_review")

    cfg: Dict[str, Any] = {
        "model": "",
        "temperature": 0.5,  # Lower temperature for review (more consistent)
        "max_tokens": 4096,
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
        _sys_temp = getattr(_config_module, "idea_generate_temperature", 0.7)
        if _sys_temp != 0.7:
            cfg["temperature"] = _sys_temp
        cfg["input_hard_limit"] = getattr(_config_module, "idea_generate_input_hard_limit", 129024)
        cfg["input_safety_margin"] = getattr(_config_module, "idea_generate_input_safety_margin", 4096)
        print(f"[IDEA_REVIEW] Using system-level {sys_pfx}/idea_generate config.", flush=True)
    elif user_id is not None:
        # --- 2. Fallback: per-user settings ---
        ucfg = _load_user_config(user_id)
        if ucfg:
            module_llm_key = f"{module}_llm_preset_id"  # "review_llm_preset_id" or "revise_llm_preset_id"
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
            cfg["_ucfg"] = ucfg
        if key:
            print(f"[IDEA_REVIEW] Using per-user idea_generate config (user_id={user_id}).", flush=True)

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
    return {}


# ---------------------------------------------------------------------------
# Review prompt (steps 15-19 combined into one multi-critic call)
# ---------------------------------------------------------------------------

def review_candidate(
    client: OpenAI, cfg: Dict[str, Any], candidate: Dict[str, Any],
    user_id: int = 0,
) -> Dict[str, Any]:
    """Run multi-critic review on a single candidate."""
    user_content = (
        f"标题: {candidate.get('title', '')}\n"
        f"目标: {candidate.get('goal', '')}\n"
        f"机制: {candidate.get('mechanism', '')}\n"
        f"风险: {candidate.get('risks', '')}\n"
        f"策略: {candidate.get('strategy', '')}\n"
        f"标签: {candidate.get('tags', [])}\n"
    )
    ucfg = cfg.get("_ucfg", {})
    review_prompt = _resolve_prompt(
        ucfg, user_id,
        module_preset_key="review_prompt_preset_id",
        user_text_key="review_system_prompt",
        config_var_name="idea_review_system_prompt",
    )
    return _call_llm_json(client, cfg, review_prompt, user_content)


# ---------------------------------------------------------------------------
# Revision prompt (step 20)
# ---------------------------------------------------------------------------

def revise_candidate(
    client: OpenAI, cfg: Dict[str, Any], candidate: Dict[str, Any], review: Dict[str, Any],
    user_id: int = 0,
) -> Dict[str, Any]:
    """Auto-revise a candidate based on review feedback."""
    # Build feedback summary from review
    feedback_parts = []
    for role in ("researcher", "engineer", "reviewer"):
        role_data = review.get(role, {})
        if role_data.get("cons"):
            feedback_parts.append(f"{role} 不足: {'; '.join(role_data['cons'])}")
        if role_data.get("suggestions"):
            feedback_parts.append(f"{role} 建议: {'; '.join(role_data['suggestions'])}")

    feedback_text = "\n".join(feedback_parts) if feedback_parts else "无具体反馈"

    user_content = (
        f"## 原始灵感\n"
        f"标题: {candidate.get('title', '')}\n"
        f"目标: {candidate.get('goal', '')}\n"
        f"机制: {candidate.get('mechanism', '')}\n"
        f"风险: {candidate.get('risks', '')}\n\n"
        f"## 评审反馈\n{feedback_text}"
    )

    ucfg = cfg.get("_ucfg", {})
    revise_prompt = _resolve_prompt(
        ucfg, user_id,
        module_preset_key="revise_prompt_preset_id",
        user_text_key="revise_system_prompt",
        config_var_name="idea_revise_system_prompt",
    )
    return _call_llm_json(client, cfg, revise_prompt, user_content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _write_manifest(date_str: str, data: dict) -> None:
    """Write sentinel .jsonl file so app.py pipeline recognises this step as done."""
    root = os.path.dirname(os.path.dirname(__file__))
    from config.config import DATA_ROOT as _DATA_ROOT
    out_dir = os.path.join(root, _DATA_ROOT, "idea_review")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date_str}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def run() -> None:
    ap = argparse.ArgumentParser("idea_review")
    ap.add_argument("--date", default="")
    ap.add_argument("--user-id", type=int, default=None)
    ap.add_argument("--min-score", type=float, default=0.0,
                     help="Only process candidates with overall score < this (0 = all)")
    args = ap.parse_args()

    date_str = args.date or os.environ.get("RUN_DATE", "") or datetime.now().date().isoformat()
    user_id = args.user_id or int(os.environ.get("PIPELINE_USER_ID", "0") or "0")
    if not user_id:
        print("[IDEA_REVIEW] No user_id; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "no_user_id", "date": date_str})
        return

    # Each phase gets its own independent client (1:1 model+prompt)
    rv_client, rv_cfg = _make_client(user_id, module="review")
    rs_client, rs_cfg = _make_client(user_id, module="revise")

    if not rv_client:
        print("[IDEA_REVIEW] LLM not configured for review phase; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "llm_not_configured", "date": date_str, "user_id": user_id})
        return
    if not rs_client:
        print("[IDEA_REVIEW] LLM not configured for revise phase; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "llm_not_configured", "date": date_str, "user_id": user_id})
        return

    from services import idea_service

    # Get draft candidates that haven't been reviewed yet
    candidates = idea_service.list_candidates(user_id, status="draft", limit=100)
    if not candidates:
        print("[IDEA_REVIEW] No draft candidates to review.", flush=True)
        _write_manifest(date_str, {"status": "done", "date": date_str, "user_id": user_id,
                                   "reviewed": 0, "revised": 0, "published": 0})
        return

    print(f"============开始 灵感评审 (idea_review) ============", flush=True)
    print(f"[IDEA_REVIEW] user_id={user_id} candidates={len(candidates)}", flush=True)

    reviewed = 0
    revised = 0
    published = 0

    for i, c in enumerate(candidates):
        cid = c["id"]
        print(f"[IDEA_REVIEW] [{i+1}/{len(candidates)}] Reviewing: {c.get('title', '')[:60]}...", flush=True)

        try:
            # Step 15-19: Multi-critic review (uses review-phase model)
            review = review_candidate(rv_client, rv_cfg, c, user_id=user_id)
            scores = review.get("scores", {})
            verdict = review.get("verdict", "revise")

            # Save scores to candidate
            idea_service.update_candidate(
                cid, user_id,
                scores=scores,
                revision_entry={
                    "type": "review",
                    "scores": scores,
                    "verdict": verdict,
                    "summary": review.get("summary", ""),
                },
            )
            reviewed += 1

            overall = float(scores.get("overall", 0))

            # Step 20: Auto-revise if verdict is "revise" and score is moderate (uses revise-phase model)
            if verdict == "revise" and 0.3 <= overall <= 0.8:
                print(f"[IDEA_REVIEW]   → Revising (score={overall:.2f})...", flush=True)
                revision = revise_candidate(rs_client, rs_cfg, c, review, user_id=user_id)
                if revision.get("title"):
                    idea_service.update_candidate(
                        cid, user_id,
                        title=revision.get("title", c["title"]),
                        goal=revision.get("goal", c["goal"]),
                        mechanism=revision.get("mechanism", c["mechanism"]),
                        risks=revision.get("risks", c["risks"]),
                        status="review",
                        revision_entry={
                            "type": "auto_revise",
                            "changes": revision,
                        },
                    )
                    revised += 1

            # Step 21: Publish if high score
            if verdict == "approve" or overall >= 0.7:
                idea_service.update_candidate(
                    cid, user_id, status="published",
                )
                published += 1
                print(f"[IDEA_REVIEW]   → Published (score={overall:.2f})", flush=True)
            elif verdict == "reject" or overall < 0.3:
                idea_service.update_candidate(
                    cid, user_id, status="archived",
                )
                print(f"[IDEA_REVIEW]   → Archived (score={overall:.2f})", flush=True)
            else:
                if c["status"] == "draft":
                    idea_service.update_candidate(cid, user_id, status="review")

        except Exception as e:
            print(f"[IDEA_REVIEW]   → error: {e!r}", flush=True)

    print(f"[IDEA_REVIEW] reviewed={reviewed} revised={revised} published={published}", flush=True)
    print(f"============结束 灵感评审 (idea_review) ============", flush=True)

    _write_manifest(date_str, {
        "status": "done",
        "date": date_str,
        "user_id": user_id,
        "reviewed": reviewed,
        "revised": revised,
        "published": published,
    })


if __name__ == "__main__":
    run()
