from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import (
    qwen_api_key,
    summary_base_url,
    summary_model,
    summary_base_url_2,
    summary_gptgod_apikey,
    summary_model_2,
    summary_base_url_3,
    summary_apikey_3,
    summary_model_3,
    summary_max_tokens,
    summary_temperature,
    summary_input_hard_limit,
    summary_input_safety_margin,
    summary_concurrency,
    system_prompt,
    DATA_ROOT,
    SLLM,
)


# ---------------------------------------------------------------------------
# User‑override helpers
# ---------------------------------------------------------------------------

def _load_user_config(user_id: int) -> Dict[str, Any]:
    """Load merged paper_recommend settings for *user_id*.

    Returns an empty dict when the user has no overrides (or on any error),
    so the caller can safely fall back to config.py defaults.
    """
    try:
        from services.user_settings_service import get_settings
        return get_settings(user_id, "paper_recommend")
    except Exception:
        return {}


def _resolve_llm_preset(user_id: int, preset_id: Any) -> Dict[str, Any]:
    """Fetch an LLM preset row; returns empty dict on miss."""
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
    """Fetch a prompt preset's content; returns empty string on miss."""
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


def make_client_for_user(user_id: Optional[int] = None) -> Tuple[OpenAI, Dict[str, Any]]:
    """Return (client, effective_cfg) honouring user overrides when *user_id* is given.

    ``effective_cfg`` contains the resolved values for ``system_prompt``,
    ``temperature``, ``max_tokens``, ``input_hard_limit``, ``input_safety_margin``,
    and ``model`` so that callers don't have to look them up again.
    """
    # Start from config.py defaults
    cfg: Dict[str, Any] = {
        "system_prompt": system_prompt,
        "temperature": summary_temperature,
        "max_tokens": summary_max_tokens,
        "input_hard_limit": summary_input_hard_limit,
        "input_safety_margin": summary_input_safety_margin,
    }

    key: str = ""
    base: str = ""
    model: str = ""

    if user_id is not None:
        ucfg = _load_user_config(user_id)
        if ucfg:
            # LLM connection — module-specific preset first, then generic fallback
            preset_id = ucfg.get("summary_llm_preset_id") or ucfg.get("llm_preset_id")
            preset = _resolve_llm_preset(user_id, preset_id) if preset_id else {}
            if preset:
                key = (preset.get("api_key") or "").strip()
                base = (preset.get("base_url") or "").strip()
                model = (preset.get("model") or "").strip()
                if preset.get("temperature") is not None:
                    cfg["temperature"] = preset["temperature"]
                if preset.get("max_tokens") is not None:
                    cfg["max_tokens"] = preset["max_tokens"]
                if preset.get("input_hard_limit") is not None:
                    cfg["input_hard_limit"] = preset["input_hard_limit"]
                if preset.get("input_safety_margin") is not None:
                    cfg["input_safety_margin"] = preset["input_safety_margin"]
            else:
                key = (ucfg.get("llm_api_key") or "").strip()
                base = (ucfg.get("llm_base_url") or "").strip()
                model = (ucfg.get("llm_model") or "").strip()
                if ucfg.get("temperature") is not None:
                    cfg["temperature"] = ucfg["temperature"]
                if ucfg.get("max_tokens") is not None:
                    cfg["max_tokens"] = ucfg["max_tokens"]
                if ucfg.get("input_hard_limit") is not None:
                    cfg["input_hard_limit"] = ucfg["input_hard_limit"]
                if ucfg.get("input_safety_margin") is not None:
                    cfg["input_safety_margin"] = ucfg["input_safety_margin"]

            # Prompt — preset takes priority
            prompt_preset_id = ucfg.get("prompt_preset_id")
            prompt_content = _resolve_prompt_preset(user_id, prompt_preset_id) if prompt_preset_id else ""
            if prompt_content:
                cfg["system_prompt"] = prompt_content
            elif ucfg.get("system_prompt"):
                cfg["system_prompt"] = ucfg["system_prompt"]

    # If user config didn't provide LLM credentials, fall back to config.py
    if not key or not base:
        if SLLM == 2:
            key = (summary_gptgod_apikey or "").strip()
            base = (summary_base_url_2 or "").strip()
            model = summary_model_2
        elif SLLM == 3:
            key = (summary_apikey_3 or "").strip()
            base = (summary_base_url_3 or "").strip()
            model = summary_model_3
        else:
            key = (qwen_api_key or "").strip()
            base = (summary_base_url or "").strip()
            model = summary_model
    elif not model:
        # User provided key/base but no model — use config.py default model
        if SLLM == 2:
            model = summary_model_2
        elif SLLM == 3:
            model = summary_model_3
        else:
            model = summary_model

    if not key:
        raise SystemExit("LLM API key missing (neither user preset nor config.py)")
    if not base:
        raise SystemExit("LLM base URL missing (neither user preset nor config.py)")

    cfg["model"] = model
    return OpenAI(api_key=key, base_url=base), cfg


def approx_input_tokens(text: str) -> int:
    if not text:
        return 0
    return len(text.encode("utf-8", errors="ignore"))


def crop_to_input_tokens(text: str, limit_tokens: int) -> str:
    budget = int(limit_tokens)
    if budget <= 0:
        return ""
    b = text.encode("utf-8", errors="ignore")
    if len(b) <= budget:
        return text
    return b[:budget].decode("utf-8", errors="ignore")


def list_md_files(root: Path) -> List[Path]:
    return sorted(root.rglob("*.md"))


def today_str() -> str:
    return datetime.now().date().isoformat()


def write_gather(single_dir: Path, gather_dir: Path, date_str: str) -> Path:
    files = list_md_files(single_dir)
    gather_dir.mkdir(parents=True, exist_ok=True)
    gather_path = gather_dir / f"{date_str}.txt"
    with gather_path.open("w", encoding="utf-8") as f:
        first = True
        for p in files:
            text = p.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            if not first:
                f.write("\n")
            first = False
            f.write("#" * 100 + "\n")
            f.write(f"{p.name}\n")
            f.write("#" * 100 + "\n")
            f.write(text)
            f.write("\n")
    return gather_path


def make_client() -> OpenAI:
    """Legacy entry-point – creates a client using config.py (no user overrides)."""
    client, _ = make_client_for_user(user_id=None)
    return client


def summarize_one(
    client: OpenAI,
    md_path: Path,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, str]:
    md_text = md_path.read_text(encoding="utf-8", errors="ignore")
    if not md_text.strip():
        return md_path, ""

    # Use effective_cfg when available (user-overridden); else config.py defaults
    ecfg = effective_cfg or {}
    sys_prompt = ecfg.get("system_prompt") or system_prompt
    hard_limit = int(ecfg.get("input_hard_limit") or summary_input_hard_limit)
    safety_margin = int(ecfg.get("input_safety_margin") or summary_input_safety_margin)
    temp = ecfg.get("temperature") if ecfg.get("temperature") is not None else summary_temperature
    max_tok = ecfg.get("max_tokens") if ecfg.get("max_tokens") is not None else summary_max_tokens
    model_name = ecfg.get("model") or (summary_model_2 if SLLM == 2 else summary_model_3 if SLLM == 3 else summary_model)

    user_content = md_text
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(user_content, user_budget)

    kwargs: Dict[str, Any] = {}
    if temp is not None:
        kwargs["temperature"] = float(temp)
    if max_tok is not None:
        kwargs["max_tokens"] = int(max_tok)

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        **kwargs,
    )
    content = resp.choices[0].message.content if resp.choices else ""
    if not content:
        return md_path, ""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("🌐来源"):
            arxiv_id = md_path.stem
            lines[i] = f"🌐来源：arXiv,{arxiv_id}"
            break
    content = normalize_summary_format("\n".join(lines))
    return md_path, content


def normalize_summary_format(text: str) -> str:
    if not text.strip():
        return text

    lines = text.splitlines()
    section_headers = ("🛎️", "📝", "🔎", "💡")

    def is_section_header(line: str) -> bool:
        s = line.strip()
        return any(s.startswith(h) for h in section_headers)

    # Ensure the first line uses "笔记标题："
    first_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_idx = idx
            break
    if first_idx is None:
        return text

    first = lines[first_idx].strip()
    if first.startswith("笔记标题"):
        rest = first[len("笔记标题"):].lstrip()
        if rest.startswith(":") or rest.startswith("："):
            rest = rest[1:].lstrip()
        lines[first_idx] = f"笔记标题：{rest}".rstrip()
    elif first.startswith("标题"):
        rest = first[len("标题"):].lstrip()
        if rest.startswith(":") or rest.startswith("："):
            rest = rest[1:].lstrip()
        lines[first_idx] = f"笔记标题：{rest}".rstrip()
    elif is_section_header(first) or first.startswith("🔸"):
        lines.insert(first_idx, "笔记标题：")
    else:
        lines[first_idx] = f"笔记标题：{first}".rstrip()

    # Insert a blank line before each section header
    out: List[str] = []
    for line in lines:
        s = line.strip()
        if is_section_header(s):
            if out and out[-1].strip():
                out.append("")
        out.append(line.rstrip())

    return "\n".join(out).rstrip() + "\n"


def run() -> None:
    ap = argparse.ArgumentParser("paper_summary")
    ap.add_argument("--input-dir", default=str(Path(DATA_ROOT) / "selectedpaper_to_mineru"))
    ap.add_argument("--out-root", default=str(Path(DATA_ROOT) / "paper_summary"))
    ap.add_argument("--date", default="")
    ap.add_argument("--concurrency", type=int, default=summary_concurrency)
    ap.add_argument("--user-id", type=int, default=None, help="User ID for per-user config overrides")
    args = ap.parse_args()

    in_root = Path(args.input_dir)
    if not in_root.exists():
        print(f"[SUMMARY] input dir not found: {in_root}, skip paper_summary", flush=True)
        return

    if args.date:
        in_dir = in_root / args.date
        if not in_dir.exists():
            print(f"[SUMMARY] input dir not found: {in_dir}, skip paper_summary", flush=True)
            return
        date_str = args.date
    else:
        today = today_str()
        candidate = in_root / today
        if candidate.is_dir():
            in_dir = candidate
            date_str = today
        else:
            subdirs = []
            for d in in_root.iterdir():
                if d.is_dir():
                    name = d.name
                    if len(name) == 10 and name[4] == "-" and name[7] == "-":
                        subdirs.append(d)
            if subdirs:
                subdirs.sort(key=lambda p: p.name)
                in_dir = subdirs[-1]
                date_str = in_dir.name
            else:
                in_dir = in_root
                date_str = today

    files = list_md_files(in_dir)
    if not files:
        print(f"[SUMMARY] no md files in {in_dir}, skip paper_summary", flush=True)
        return
    print("============开始生成精选论文中文摘要==============", flush=True)

    out_root = Path(args.out_root)
    single_dir = out_root / "single" / date_str
    gather_dir = out_root / "gather" / date_str
    single_dir.mkdir(parents=True, exist_ok=True)

    to_run: List[Path] = []
    for p in files:
        out_path = single_dir / f"{p.stem}.md"
        if out_path.exists():
            continue
        to_run.append(p)

    total = len(to_run)
    if total == 0:
        gather_path = write_gather(single_dir, gather_dir, date_str)
        print(f"[SUMMARY] all files already summarized, single_dir={single_dir}", flush=True)
        print(f"[SUMMARY] gather_path={gather_path}", flush=True)
        return

    client, effective_cfg = make_client_for_user(user_id=args.user_id)
    workers = max(1, int(args.concurrency or 0))
    print(f"[SUMMARY] input_dir={in_dir} total={total} concurrency={workers} user_id={args.user_id}", flush=True)

    start = time.monotonic()
    done = 0
    empty = 0

    def task(md_path: Path) -> Tuple[Path, str]:
        path, content = summarize_one(client, md_path, effective_cfg=effective_cfg)
        if not content.strip():
            return path, ""
        out_path = single_dir / f"{path.stem}.md"
        out_path.write_text(content, encoding="utf-8")
        return path, content

    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {ex.submit(task, p): p for p in to_run}
        for fut in as_completed(future_map):
            src = future_map[fut]
            try:
                _, content = fut.result()
                if not content.strip():
                    empty += 1
            except Exception as e:
                print(f"\r[SUMMARY] error on {src.name}: {e!r}", end="", flush=True)
            done += 1
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"\r[SUMMARY] progress done={done}/{total} empty={empty} rate={rate:.2f}/s", end="", flush=True)

    print()
    gather_path = write_gather(single_dir, gather_dir, date_str)
    print(f"[SUMMARY] single_dir={single_dir}", flush=True)
    print(f"[SUMMARY] gather_path={gather_path}", flush=True)
    print("============结束生成精选论文中文摘要==============", flush=True)


if __name__ == "__main__":
    run()
