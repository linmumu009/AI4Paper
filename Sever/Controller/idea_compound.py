"""
Inspiration v2 — Layer D: Compound Interest Pipeline Step.

Steps combined:
  22. feedback_ingest — (handled by API endpoints, not batch)
  23. exemplar_mine — mine high-quality patterns from top candidates
  24. prompt_registry / eval_replay — snapshot current prompts + metrics
  25. benchmark_builder — build evaluation benchmark from questions
  26. regen_scheduler — (triggered separately via API or cron)

This script runs the "compounding" steps that turn each generation cycle
into reusable assets for the next cycle.

Usage:
    python idea_compound.py --date 2025-06-15 --user-id 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def _write_manifest(date_str: str, data: dict) -> None:
    """Write sentinel .jsonl file so app.py pipeline recognises this step as done."""
    root = os.path.dirname(os.path.dirname(__file__))
    from config.config import DATA_ROOT as _DATA_ROOT
    out_dir = os.path.join(root, _DATA_ROOT, "idea_compound")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date_str}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def run() -> None:
    ap = argparse.ArgumentParser("idea_compound")
    ap.add_argument("--date", default="")
    ap.add_argument("--user-id", type=int, default=None)
    args = ap.parse_args()

    date_str = args.date or os.environ.get("RUN_DATE", "") or datetime.now().date().isoformat()
    user_id = args.user_id or int(os.environ.get("PIPELINE_USER_ID", "0") or "0")

    if not user_id:
        print("[IDEA_COMPOUND] No user_id; skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "no_user_id", "date": date_str})
        return

    from services import idea_service

    print(f"============开始 灵感复利 (idea_compound) ============", flush=True)
    print(f"[IDEA_COMPOUND] date={date_str} user_id={user_id}", flush=True)

    # -----------------------------------------------------------------------
    # Step 23: Exemplar mining — find top published candidates and save as exemplars
    # -----------------------------------------------------------------------
    print("[IDEA_COMPOUND] Mining exemplars from top candidates...", flush=True)

    published = idea_service.list_candidates(user_id, status="published", limit=50)
    existing_exemplars = idea_service.list_exemplars(user_id, limit=500)
    existing_candidate_ids = {e.get("candidate_id") for e in existing_exemplars}

    new_exemplars = 0
    for c in published:
        if c["id"] in existing_candidate_ids:
            continue
        scores = c.get("scores", {})
        overall = float(scores.get("overall", 0))
        if overall >= 0.7:
            # Extract pattern
            pattern = {
                "title": c.get("title", ""),
                "goal": c.get("goal", ""),
                "mechanism": c.get("mechanism", ""),
                "strategy": c.get("strategy", ""),
                "tags": c.get("tags", []),
                "scores": scores,
            }
            idea_service.create_exemplar(
                user_id=user_id,
                candidate_id=c["id"],
                pattern=pattern,
                score=overall,
                notes=f"Auto-mined from published candidate on {date_str}",
            )
            new_exemplars += 1

    print(f"[IDEA_COMPOUND] New exemplars: {new_exemplars}", flush=True)

    # -----------------------------------------------------------------------
    # Step 24: Prompt version snapshot
    # -----------------------------------------------------------------------
    print("[IDEA_COMPOUND] Snapshotting prompt versions...", flush=True)

    # Read active prompts from config_service (prompts are now managed via
    # config.py / config.json, not as hardcoded constants in each module).
    from services import config_service as _cs
    _cfg_map: Dict[str, Any] = {}
    try:
        for g in _cs.get_config_with_groups().get("groups", []):
            for item in g.get("items", []):
                _cfg_map[item["key"]] = item["value"]
    except Exception:
        pass

    # Fallback to config.py defaults when config.json has no override
    import config.config as _cfg_defaults

    def _get_prompt(key: str) -> str:
        val = (_cfg_map.get(key) or "").strip()
        if not val:
            val = (getattr(_cfg_defaults, key, "") or "").strip()
        return val

    prompts = {
        "extraction":         _get_prompt("idea_ingest_system_prompt"),
        "question_generation": _get_prompt("idea_question_system_prompt"),
        "candidate_generation": _get_prompt("idea_candidate_system_prompt"),
        "review":             _get_prompt("idea_review_system_prompt"),
        "revision":           _get_prompt("idea_revise_system_prompt"),
    }

    stats = idea_service.get_stats(user_id)
    for stage, prompt_text in prompts.items():
        existing = idea_service.list_prompt_versions(user_id, stage=stage)
        # Only create new version if prompt changed
        if existing:
            latest = existing[0]
            if latest.get("prompt_text", "").strip() == prompt_text.strip():
                continue
        idea_service.create_prompt_version(
            user_id=user_id,
            stage=stage,
            prompt_text=prompt_text,
            metrics=stats,
        )

    print("[IDEA_COMPOUND] Prompt versions updated.", flush=True)

    # -----------------------------------------------------------------------
    # Step 25: Benchmark building
    # -----------------------------------------------------------------------
    print("[IDEA_COMPOUND] Building evaluation benchmark...", flush=True)

    questions = idea_service.list_questions(user_id, limit=100)
    if questions:
        # Create a benchmark for this date if we have questions
        benchmark_name = f"benchmark_{date_str}"
        existing_benchmarks = idea_service.list_benchmarks(user_id)
        existing_names = {b["name"] for b in existing_benchmarks}
        if benchmark_name not in existing_names:
            q_ids = [q["id"] for q in questions]
            idea_service.create_benchmark(
                user_id=user_id,
                name=benchmark_name,
                question_ids=q_ids,
                model_version=date_str,
            )
            print(f"[IDEA_COMPOUND] Created benchmark '{benchmark_name}' with {len(q_ids)} questions.", flush=True)
        else:
            print(f"[IDEA_COMPOUND] Benchmark '{benchmark_name}' already exists.", flush=True)
    else:
        print("[IDEA_COMPOUND] No questions to build benchmark.", flush=True)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    final_stats = idea_service.get_stats(user_id)
    print(f"[IDEA_COMPOUND] Stats: {json.dumps(final_stats, ensure_ascii=False)}", flush=True)
    print(f"============结束 灵感复利 (idea_compound) ============", flush=True)

    _write_manifest(date_str, {
        "status": "done",
        "date": date_str,
        "user_id": user_id,
        "new_exemplars": new_exemplars,
        "stats": final_stats,
    })


if __name__ == "__main__":
    run()
