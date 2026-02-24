"""
Inspiration v2 — Layer A: Asset Extraction Pipeline Step.

Reads MinerU / summary products for all papers of a given date,
extracts structured "idea atoms" (Claim / Method / Setup / Limitation)
via LLM, and persists them into the SQLite database.

Steps combined:
  1. idea_ingest  — locate MinerU / summary markdown
  2. paper_sectionize — (done by LLM prompt; sections embedded in extraction)
  3-6. claim/method/experiment/limitation extraction — single LLM call
  7. taxonomy_tag — (done in same extraction call)
  8. idea_atomize — batch insert into DB
  9. evidence_index — evidence snippets stored in atom records
  10. idea_index_build — FTS5 triggers auto-maintain the index

Usage (standalone):
    python idea_ingest.py --date 2025-06-15

Usage (via app.py pipeline):
    Automatically invoked as a pipeline step with --date and --user-id.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# Allow importing from Sever root
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
    idea_generate_concurrency,
)


def _sys_model_cfg() -> tuple[str, str, str]:
    """Return (base_url, api_key, model) for the ingest phase.
    
    Tries idea_ingest_* first; falls back to idea_generate_* global.
    Reads live from _config_module so admin edits to config.json take effect.
    """
    base = (getattr(_config_module, "idea_ingest_base_url", "") or "").strip()
    key  = (getattr(_config_module, "idea_ingest_api_key",  "") or "").strip()
    mdl  = (getattr(_config_module, "idea_ingest_model",    "") or "").strip()
    if base and key and mdl:
        return base, key, mdl
    # Fall back to global
    base = (getattr(_config_module, "idea_generate_base_url", "") or "").strip()
    key  = (getattr(_config_module, "idea_generate_api_key",  "") or "").strip()
    mdl  = (getattr(_config_module, "idea_generate_model",    "") or "").strip()
    return base, key, mdl


# ---------------------------------------------------------------------------
# LLM config helpers (system config first, user settings as fallback)
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


def _make_client(user_id: Optional[int] = None) -> Tuple[Optional[OpenAI], Dict[str, Any]]:
    """Create OpenAI client for idea generation.

    Priority:
      1. System-level config (idea_generate_* in config.py / config.json)
      2. Per-user settings (user_settings_service, idea_generate feature)

    cfg["system_prompt"] is resolved with the same priority:
      system config (idea_ingest_system_prompt) → user prompt preset override.
    """
    cfg: Dict[str, Any] = {
        "model": "",
        "temperature": 0.7,
        "max_tokens": 8192,
        "input_hard_limit": 129024,
        "input_safety_margin": 4096,
        # Prompt: read live from config module at call-time so that admin edits
        # to database/config.json take effect without restarting the process.
        "system_prompt": (getattr(_config_module, "idea_ingest_system_prompt", "") or "").strip(),
    }
    key = ""
    base = ""

    # --- 1. Try system-level config (per-module → global fallback) ---
    sys_base, sys_key, sys_model = _sys_model_cfg()
    if sys_base and sys_key and sys_model:
        base = sys_base
        key = sys_key
        cfg["model"] = sys_model
        cfg["max_tokens"] = getattr(_config_module, "idea_generate_max_tokens", 8192)
        cfg["temperature"] = getattr(_config_module, "idea_generate_temperature", 0.7)
        cfg["input_hard_limit"] = getattr(_config_module, "idea_generate_input_hard_limit", 129024)
        cfg["input_safety_margin"] = getattr(_config_module, "idea_generate_input_safety_margin", 4096)
        print("[IDEA_INGEST] Using system-level idea_ingest/idea_generate config.", flush=True)
    elif user_id is not None:
        # --- 2. Fallback: per-user settings ---
        ucfg = _load_user_config(user_id)
        if ucfg:
            preset_id = ucfg.get("llm_preset_id")
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

            # --- Prompt override: per-user prompt preset ---
            prompt_preset_id = ucfg.get("prompt_preset_id")
            if prompt_preset_id:
                content = _resolve_prompt_preset(user_id, prompt_preset_id)
                if content:
                    cfg["system_prompt"] = content

        if key:
            print(f"[IDEA_INGEST] Using per-user idea_generate config (user_id={user_id}).", flush=True)

    if not key or not base or not cfg["model"]:
        return None, cfg

    client = OpenAI(api_key=key, base_url=base)
    return client, cfg


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def _approx_tokens(text: str) -> int:
    return len(text.encode("utf-8", errors="ignore")) if text else 0


def _crop(text: str, budget: int) -> str:
    b = text.encode("utf-8", errors="ignore")
    if len(b) <= budget:
        return text
    return b[:budget].decode("utf-8", errors="ignore")


def _read_file(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

def _extract_atoms_llm(
    client: OpenAI, cfg: Dict[str, Any], content: str,
) -> List[Dict[str, Any]]:
    """Call LLM to extract atoms from paper content.

    Uses cfg["system_prompt"] which is resolved from:
      config.py/config.json (idea_ingest_system_prompt) → user prompt preset.
    """
    system_prompt = cfg.get("system_prompt") or getattr(_config_module, "idea_ingest_system_prompt", "") or ""
    hard_limit = int(cfg.get("input_hard_limit", 129024))
    safety_margin = int(cfg.get("input_safety_margin", 4096))
    limit_total = hard_limit - safety_margin
    sys_tokens = _approx_tokens(system_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = _crop(content, user_budget)

    kwargs: Dict[str, Any] = {}
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = float(cfg["temperature"])
    if cfg.get("max_tokens") is not None:
        kwargs["max_tokens"] = int(cfg["max_tokens"])

    # Try with response_format=json_object first (forces valid JSON output).
    # Fall back to plain text if the model/endpoint doesn't support it.
    text = ""
    used_json_mode = False
    try:
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            stream=False,
            **kwargs,
        )
        text = resp.choices[0].message.content if resp.choices else ""
        used_json_mode = True
    except Exception as e:
        # Endpoint may not support response_format; fall back silently.
        print(f"[IDEA_INGEST][DEBUG] json_object mode failed ({e}), retrying without it.", flush=True)
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

    atoms = _parse_atoms(text)
    if not atoms:
        preview = (text or "").strip()[:300].replace("\n", "\\n")
        print(
            f"[IDEA_INGEST][DEBUG] 0 atoms parsed. model={cfg.get('model')} "
            f"json_mode={used_json_mode} resp_len={len(text)} preview={preview!r}",
            flush=True,
        )
    return atoms


def _fix_json_string(raw: str) -> str:
    """Fix common LLM JSON issues: bare newlines / tabs inside string values."""
    # Replace literal newlines/tabs inside JSON string values with their
    # escaped counterparts.  We scan character-by-character to be safe.
    result: List[str] = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(ch)
        else:
            result.append(ch)
    return "".join(result)


def _extract_partial_atoms(s: str) -> List[Dict[str, Any]]:
    """Best-effort extraction: grab every complete {...} atom object found."""
    atoms: List[Dict[str, Any]] = []
    # Find all top-level atom objects by matching balanced braces.
    depth = 0
    obj_start = -1
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                snippet = s[obj_start:i + 1]
                try:
                    obj = json.loads(_fix_json_string(snippet))
                    if isinstance(obj, dict) and obj.get("type") and obj.get("content"):
                        atoms.append(obj)
                except json.JSONDecodeError:
                    pass
                obj_start = -1
    return atoms


def _parse_atoms(text: str) -> List[Dict[str, Any]]:
    """Parse LLM response into atom list."""
    if not text:
        return []
    s = text.strip()
    # Try JSON object (standard path)
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end > start:
        candidate = s[start:end + 1]
        # First try as-is
        try:
            obj = json.loads(candidate)
            atoms = obj.get("atoms") or obj.get("items") or []
            if atoms:
                return atoms
            # Maybe flat structure with type keys
            result = []
            for key in ("claims", "methods", "setups", "limitations", "tags"):
                items = obj.get(key, [])
                for item in items:
                    if isinstance(item, str):
                        result.append({"type": key.rstrip("s"), "content": item})
                    elif isinstance(item, dict):
                        item.setdefault("type", key.rstrip("s"))
                        result.append(item)
            if result:
                return result
        except json.JSONDecodeError as e:
            print(f"[IDEA_INGEST][DEBUG] JSON object parse failed: {e}. snippet='{s[start:start+200]}'", flush=True)
        # Retry after fixing bare newlines in strings
        try:
            fixed = _fix_json_string(candidate)
            obj = json.loads(fixed)
            atoms = obj.get("atoms") or obj.get("items") or []
            if atoms:
                print("[IDEA_INGEST][DEBUG] JSON recovered after string-fix.", flush=True)
                return atoms
        except json.JSONDecodeError:
            pass
        # Last resort: extract individual complete atom objects
        partial = _extract_partial_atoms(s[start:])
        if partial:
            print(f"[IDEA_INGEST][DEBUG] Partial extraction recovered {len(partial)} atoms.", flush=True)
            return partial
    # Try JSON array
    start = s.find("[")
    end = s.rfind("]")
    if start != -1 and end > start:
        candidate = s[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            print(f"[IDEA_INGEST][DEBUG] JSON array parse failed: {e}.", flush=True)
        try:
            return json.loads(_fix_json_string(candidate))
        except json.JSONDecodeError:
            pass
    return []


# ---------------------------------------------------------------------------
# Paper discovery
# ---------------------------------------------------------------------------

def _find_papers_for_date(date_str: str) -> List[Dict[str, str]]:
    """Find all papers for a date in file_collect/<date>/."""
    fc_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), DATA_ROOT, "file_collect", date_str)
    if not os.path.isdir(fc_dir):
        return []
    papers = []
    for name in sorted(os.listdir(fc_dir)):
        paper_dir = os.path.join(fc_dir, name)
        if not os.path.isdir(paper_dir):
            continue
        # Look for content file
        content_file = None
        for suffix in ("_mineru.md", "_summary.md", "_limit.md"):
            candidate = os.path.join(paper_dir, f"{name}{suffix}")
            if os.path.isfile(candidate):
                content_file = candidate
                break
        if content_file:
            papers.append({
                "paper_id": name,
                "content_file": content_file,
                "source_file": os.path.basename(content_file),
            })
    return papers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_one(
    client: OpenAI,
    cfg: Dict[str, Any],
    paper: Dict[str, str],
    user_id: int,
    date_str: str,
) -> Tuple[str, int]:
    """Extract atoms for one paper. Returns (paper_id, atom_count)."""
    from services import idea_service

    paper_id = paper["paper_id"]
    content = _read_file(paper["content_file"])
    if not content or not content.strip():
        return paper_id, 0

    # Delete existing atoms for re-extraction
    idea_service.delete_atoms_for_paper(user_id, paper_id)

    # Extract
    raw_atoms = _extract_atoms_llm(client, cfg, content)

    # Normalize and batch insert
    batch = []
    for a in raw_atoms:
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
            "source_file": paper.get("source_file", ""),
        })

    count = idea_service.create_atoms_batch(user_id, batch) if batch else 0
    return paper_id, count


def _write_manifest(date_str: str, data: dict) -> None:
    """Write sentinel .jsonl file so app.py pipeline recognises this step as done."""
    root = os.path.dirname(os.path.dirname(__file__))
    out_dir = os.path.join(root, DATA_ROOT, "idea_ingest")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date_str}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def run() -> None:
    ap = argparse.ArgumentParser("idea_ingest")
    ap.add_argument("--date", default="")
    ap.add_argument("--user-id", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=3)
    args = ap.parse_args()

    date_str = args.date or os.environ.get("RUN_DATE", "") or datetime.now().date().isoformat()
    user_id = args.user_id or int(os.environ.get("PIPELINE_USER_ID", "0") or "0")

    if not user_id:
        print("[IDEA_INGEST] No user_id provided; skipping idea extraction.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "no_user_id", "date": date_str})
        return

    papers = _find_papers_for_date(date_str)
    if not papers:
        print(f"[IDEA_INGEST] No papers found for date={date_str}, skipping.", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "no_papers", "date": date_str})
        return

    client, cfg = _make_client(user_id)
    if not client:
        print("[IDEA_INGEST] LLM not configured for idea_generate; skipping.", flush=True)
        print("[IDEA_INGEST] 提示：请在「管理后台 → 系统配置」应用 idea_generate 模型配置，或在「个人中心 → 功能配置」为 idea_generate 配置 LLM 后重新运行。", flush=True)
        _write_manifest(date_str, {"status": "skipped", "reason": "llm_not_configured", "date": date_str, "user_id": user_id})
        return

    total = len(papers)
    workers = max(1, min(args.concurrency, total))
    print(f"============开始 灵感原子抽取 (idea_ingest) ============", flush=True)
    print(f"[IDEA_INGEST] date={date_str} papers={total} concurrency={workers} user_id={user_id}", flush=True)

    start = time.monotonic()
    done = 0
    errors = 0
    total_atoms = 0

    def task(p: Dict[str, str]) -> Tuple[str, int]:
        return process_one(client, cfg, p, user_id, date_str)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {ex.submit(task, p): p for p in papers}
        for fut in as_completed(future_map):
            src = future_map[fut]
            try:
                pid, count = fut.result()
                total_atoms += count
                print(f"\r[IDEA_INGEST] {pid}: {count} atoms", end="", flush=True)
            except Exception as e:
                errors += 1
                print(f"\r[IDEA_INGEST] error on {src['paper_id']}: {e!r}", end="", flush=True)
            done += 1
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"\r[IDEA_INGEST] progress done={done}/{total} atoms={total_atoms} errors={errors} rate={rate:.2f}/s", end="", flush=True)

    print()
    print(f"[IDEA_INGEST] total={total} atoms_created={total_atoms} errors={errors}", flush=True)
    print(f"============结束 灵感原子抽取 (idea_ingest) ============", flush=True)

    _write_manifest(date_str, {
        "status": "done",
        "date": date_str,
        "user_id": user_id,
        "total_papers": total,
        "total_atoms": total_atoms,
        "errors": errors,
    })


if __name__ == "__main__":
    run()
