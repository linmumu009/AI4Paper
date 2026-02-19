from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, List, Tuple, Optional, Dict

from openai import OpenAI

import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import (  # noqa: E402
    qwen_api_key,
    summary_limit_base_url,
    summary_limit_model,
    summary_limit_max_tokens,
    summary_limit_temperature,
    summary_limit_input_hard_limit,
    summary_limit_input_safety_margin,
    summary_limit_concurrency,
    summary_limit_section_limit_intro,
    summary_limit_section_limit_method,
    summary_limit_section_limit_findings,
    summary_limit_section_limit_opinion,
    summary_limit_headline_limit,
    summary_limit_prompt_intro,
    summary_limit_prompt_method,
    summary_limit_prompt_findings,
    summary_limit_prompt_opinion,
    summary_limit_prompt_structure_check,
    summary_limit_prompt_structure_rewrite,
    summary_limit_prompt_headline,
    summary_limit_url_2,
    summary_limit_gptgod_apikey,
    summary_limit_model_2,
    summary_limit_url_3,
    summary_limit_apikey_3,
    summary_limit_model_3,
    DATA_ROOT,
    SLLM,
)


SECTION_LABELS = {
    "intro": ("🛎️文章简介", "文章简介"),
    "method": ("📝重点思路", "重点思路"),
    "findings": ("🔎分析总结", "分析总结"),
    "opinion": ("💡个人观点", "个人观点"),
}

# Default section limits / prompts from config.py  (may be overridden per-user)
SECTION_LIMITS_DEFAULT: Dict[str, int] = {
    "intro": summary_limit_section_limit_intro,
    "method": summary_limit_section_limit_method,
    "findings": summary_limit_section_limit_findings,
    "opinion": summary_limit_section_limit_opinion,
}

SECTION_PROMPTS_DEFAULT: Dict[str, str] = {
    "intro": summary_limit_prompt_intro,
    "method": summary_limit_prompt_method,
    "findings": summary_limit_prompt_findings,
    "opinion": summary_limit_prompt_opinion,
}

# Module-level aliases kept for backward-compat (used by functions that
# don't receive an explicit effective_cfg).
SECTION_LIMITS = dict(SECTION_LIMITS_DEFAULT)
SECTION_PROMPTS = dict(SECTION_PROMPTS_DEFAULT)


# ---------------------------------------------------------------------------
# User‑override helpers  (mirrors paper_summary.py)
# ---------------------------------------------------------------------------

def _load_user_config(user_id: int) -> Dict[str, Any]:
    try:
        from services.user_settings_service import get_settings
        return get_settings(user_id, "paper_recommend")
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


def build_effective_cfg(user_id: Optional[int] = None) -> Dict[str, Any]:
    """Return a dict with all effective config values for summary_limit.

    When *user_id* is ``None`` every value comes straight from config.py.
    """
    cfg: Dict[str, Any] = {
        "temperature": summary_limit_temperature,
        "max_tokens": summary_limit_max_tokens,
        "input_hard_limit": summary_limit_input_hard_limit,
        "input_safety_margin": summary_limit_input_safety_margin,
        "headline_limit": summary_limit_headline_limit,
        "section_limits": dict(SECTION_LIMITS_DEFAULT),
        "section_prompts": dict(SECTION_PROMPTS_DEFAULT),
    }

    key: str = ""
    base: str = ""
    model: str = ""

    if user_id is not None:
        ucfg = _load_user_config(user_id)
        if ucfg:
            # LLM connection — module-specific preset first, then generic fallback
            preset_id = ucfg.get("summary_limit_llm_preset_id") or ucfg.get("llm_preset_id")
            preset = _resolve_llm_preset(user_id, preset_id) if preset_id else {}
            if preset:
                key = (preset.get("api_key") or "").strip()
                base = (preset.get("base_url") or "").strip()
                model = (preset.get("model") or "").strip()
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if preset.get(k) is not None:
                        cfg[k] = preset[k]
            else:
                key = (ucfg.get("llm_api_key") or "").strip()
                base = (ucfg.get("llm_base_url") or "").strip()
                model = (ucfg.get("llm_model") or "").strip()
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if ucfg.get(k) is not None:
                        cfg[k] = ucfg[k]

            # Section limits
            limit_map = {
                "intro": "section_limit_intro",
                "method": "section_limit_method",
                "findings": "section_limit_findings",
                "opinion": "section_limit_opinion",
            }
            for sec, ukey in limit_map.items():
                if ucfg.get(ukey) is not None:
                    cfg["section_limits"][sec] = int(ucfg[ukey])
            if ucfg.get("headline_limit") is not None:
                cfg["headline_limit"] = int(ucfg["headline_limit"])

            # Section prompts
            prompt_map = {
                "intro": "summary_limit_prompt_intro",
                "method": "summary_limit_prompt_method",
                "findings": "summary_limit_prompt_findings",
                "opinion": "summary_limit_prompt_opinion",
            }
            for sec, ukey in prompt_map.items():
                if ucfg.get(ukey):
                    cfg["section_prompts"][sec] = ucfg[ukey]

    # Resolve LLM credentials (fall back to config.py)
    if not key or not base:
        if SLLM == 2:
            key = (summary_limit_gptgod_apikey or "").strip()
            base = (summary_limit_url_2 or "").strip()
            model = summary_limit_model_2
        elif SLLM == 3:
            key = (summary_limit_apikey_3 or "").strip()
            base = (summary_limit_url_3 or "").strip()
            model = summary_limit_model_3
        else:
            key = (qwen_api_key or "").strip()
            base = (summary_limit_base_url or "").strip()
            model = summary_limit_model
    elif not model:
        if SLLM == 2:
            model = summary_limit_model_2
        elif SLLM == 3:
            model = summary_limit_model_3
        else:
            model = summary_limit_model

    if not key:
        raise SystemExit("LLM API key missing (summary_limit)")
    if not base:
        raise SystemExit("LLM base URL missing (summary_limit)")

    cfg["api_key"] = key
    cfg["base_url"] = base
    cfg["model"] = model
    return cfg


def make_client_from_cfg(cfg: Dict[str, Any]) -> OpenAI:
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])


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
    return sorted(root.glob("*.md"))


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
    """Legacy entry-point – creates a client using config.py defaults."""
    cfg = build_effective_cfg(user_id=None)
    return make_client_from_cfg(cfg)


def get_summary_limit_model(cfg: Optional[Dict[str, Any]] = None) -> str:
    """Return the model name to use, honouring *cfg* overrides."""
    if cfg and cfg.get("model"):
        return cfg["model"]
    if SLLM == 2:
        return summary_limit_model_2
    if SLLM == 3:
        return summary_limit_model_3
    return summary_limit_model


def non_ws_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def normalize_heading(line: str) -> str:
    raw = line.strip()
    raw = re.sub(r"^#+\s*", "", raw)
    raw = re.sub(r"^[^\w\u4e00-\u9fff]+", "", raw)
    raw = raw.lstrip(":：- ").strip()
    return raw


def heading_key(line: str) -> Optional[str]:
    norm = normalize_heading(line)
    for key, labels in SECTION_LABELS.items():
        if norm.startswith(labels[0]) or norm.startswith(labels[1]):
            return key
    return None


def split_sections(lines: List[str]) -> Tuple[List[str], List[Tuple[str, str, List[str]]]]:
    prefix: List[str] = []
    sections: List[Tuple[str, str, List[str]]] = []
    current_key: Optional[str] = None
    current_heading: str = ""
    current_lines: List[str] = []

    for line in lines:
        key = heading_key(line)
        if key:
            if current_key:
                sections.append((current_key, current_heading, current_lines))
            elif current_lines:
                prefix.extend(current_lines)
            current_key = key
            current_heading = line
            current_lines = []
            continue
        if current_key is None:
            prefix.append(line)
        else:
            current_lines.append(line)

    if current_key:
        sections.append((current_key, current_heading, current_lines))
    return prefix, sections


def ensure_section_spacing(text: str) -> str:
    if not text.strip():
        return text
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        if heading_key(line):
            if out and out[-1].strip():
                out.append("")
        out.append(line)
    return "\n".join(out).rstrip() + "\n"


def normalize_style(text: str) -> str:
    lines = text.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw:
            out.append("")
            i += 1
            continue
        if re.match(r"^-{3,}\s*$", raw):
            i += 1
            continue
        line = re.sub(r"^#+\s*", "", raw).strip()
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = line.replace("：", ":")

        m = re.match(r"^(?:📖\s*)?标题\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            out.append(f"📖标题：{m.group(1).strip()}")
            i += 1
            continue
        m = re.match(r"^(?:🌐\s*)?(?:来源|source)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            out.append(f"🌐来源：{m.group(1).strip()}")
            i += 1
            continue
        m = re.match(r"^(?:机构|作者机构|单位|机构名)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            out.append(f"{m.group(1).strip()}")
            i += 1
            continue

        if re.match(r"^(?:机构|作者机构|单位|机构名)$", line, re.IGNORECASE):
            content = ""
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate:
                    content = re.sub(r"\*\*(.*?)\*\*", r"\1", candidate)
                    break
                j += 1
            out.append(content)
            i = j + 1
            continue
        if re.match(r"^标题$", line, re.IGNORECASE):
            content = ""
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate:
                    content = re.sub(r"\*\*(.*?)\*\*", r"\1", candidate)
                    break
                j += 1
            out.append(f"📖标题：{content}" if content else "📖标题：")
            i = j + 1
            continue
        if re.match(r"^(?:来源|source)$", line, re.IGNORECASE):
            content = ""
            j = i + 1
            while j < len(lines):
                candidate = lines[j].strip()
                if candidate:
                    content = re.sub(r"\*\*(.*?)\*\*", r"\1", candidate)
                    break
                j += 1
            out.append(f"🌐来源：{content}" if content else "🌐来源：")
            i = j + 1
            continue

        key = heading_key(line)
        if key == "intro":
            if out and out[-1].strip():
                out.append("")
            out.append("🛎️文章简介")
            i += 1
            continue
        if key == "method":
            if out and out[-1].strip():
                out.append("")
            out.append("📝重点思路")
            i += 1
            continue
        if key == "findings":
            if out and out[-1].strip():
                out.append("")
            out.append("🔎分析总结")
            i += 1
            continue
        if key == "opinion":
            if out and out[-1].strip():
                out.append("")
            out.append("💡个人观点")
            i += 1
            continue

        if re.match(r"^(?:[-*•]|🔹|🔸)\s*", line) or re.match(r"^\d+[.)]\s*", line):
            content = re.sub(r"^(?:[-*•]|🔹|🔸)\s*", "", line)
            content = re.sub(r"^\d+[.)]\s*", "", content)
            content = re.sub(r"\*\*(.*?)\*\*", r"\1", content).strip()
            if content:
                out.append(f"🔸{content}")
            i += 1
            continue

        out.append(line)
        i += 1
    return "\n".join(out).strip() + "\n"


def rewrite_block(
    client: OpenAI,
    text: str,
    sys_prompt: str,
    limit_chars: int,
    max_retries: int = 3,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> str:
    ecfg = effective_cfg or {}
    content = text.strip()
    if not content:
        return content
    for _ in range(max_retries):
        hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
        safety_margin = int(ecfg.get("input_safety_margin") or summary_limit_input_safety_margin)
        limit_total = hard_limit - safety_margin
        sys_tokens = approx_input_tokens(sys_prompt)
        user_budget = max(1, limit_total - sys_tokens)
        user_content = crop_to_input_tokens(content, user_budget)
        temp = ecfg.get("temperature") if ecfg.get("temperature") is not None else summary_limit_temperature
        max_tok = ecfg.get("max_tokens") if ecfg.get("max_tokens") is not None else summary_limit_max_tokens
        kwargs: Dict[str, Any] = {}
        if temp is not None:
            kwargs["temperature"] = float(temp)
        if max_tok is not None:
            kwargs["max_tokens"] = int(max_tok)
        resp = client.chat.completions.create(
            model=get_summary_limit_model(ecfg),
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=False,
            **kwargs,
        )
        new_text = resp.choices[0].message.content if resp.choices else ""
        if not new_text:
            new_text = content
        content = new_text.strip()
        if non_ws_len(content) <= limit_chars:
            break
    return content


def compress_headline(
    client: OpenAI,
    text: str,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> str:
    ecfg = effective_cfg or {}
    sys_prompt = (summary_limit_prompt_headline or "").strip()
    content = text.strip()
    if not sys_prompt or not content:
        return text
    hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
    safety_margin = int(ecfg.get("input_safety_margin") or summary_limit_input_safety_margin)
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(content, user_budget)
    max_tok = ecfg.get("max_tokens") if ecfg.get("max_tokens") is not None else summary_limit_max_tokens
    resp = client.chat.completions.create(
        model=get_summary_limit_model(ecfg),
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        max_tokens=max_tok or 2048,
        temperature=0,
    )
    new_text = resp.choices[0].message.content if resp.choices else ""
    return new_text.strip() if new_text else text


def apply_headline_limit(
    client: OpenAI,
    lines: List[str],
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> List[str]:
    ecfg = effective_cfg or {}
    hl_limit = int(ecfg.get("headline_limit") or summary_limit_headline_limit)
    title_idx = None
    for idx, line in enumerate(lines):
        if line.strip().startswith("📖标题"):
            title_idx = idx
            break
    if title_idx is None:
        return lines
    for prev_idx in range(title_idx - 1, -1, -1):
        candidate = lines[prev_idx].strip()
        if not candidate:
            continue
        if non_ws_len(candidate) <= hl_limit:
            return lines
        lines[prev_idx] = compress_headline(client, candidate, effective_cfg=ecfg) + "\n"
        return lines
    return lines


def extract_arxiv_id(source: str) -> Optional[str]:
    if not source:
        return None
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", source)
    if not m:
        return None
    version = m.group(2) or ""
    return f"{m.group(1)}{version}"


def load_pdf_info_map(date_str: str) -> Dict[str, Dict[str, str]]:
    info_path = Path(DATA_ROOT) / "pdf_info" / f"{date_str}.json"
    if not info_path.exists():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "") or "")
        arxiv_id = extract_arxiv_id(source)
        if not arxiv_id:
            continue
        out[arxiv_id] = item
    return out


def inject_pdf_info(text: str, md_path: Path, pdf_info_map: Dict[str, Dict[str, str]]) -> str:
    if not text.strip() or not pdf_info_map:
        return text
    key = md_path.stem
    info = pdf_info_map.get(key)
    if info is None:
        key_no_version = re.sub(r"v\d+$", "", key)
        info = pdf_info_map.get(key_no_version)
    if not info:
        return text

    title = str(info.get("title", "") or "").strip()
    source = str(info.get("source", "") or "").strip()
    instution = str(info.get("instution", "") or "").strip()

    lines = text.splitlines()
    first_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_idx = idx
            break
    if first_idx is None:
        first_idx = 0
        lines.insert(0, "笔记标题：")

    first_line = lines[first_idx].strip()
    if instution:
        if first_line.startswith("笔记标题"):
            rest = first_line[len("笔记标题"):].lstrip("：:")
            lines[first_idx] = f"{instution}：{rest}".rstrip()
        elif first_line.startswith("标题"):
            rest = first_line[len("标题"):].lstrip("：:")
            lines[first_idx] = f"{instution}：{rest}".rstrip()
        else:
            lines[first_idx] = f"{instution}：{first_line}".rstrip()

    # Remove existing title/source lines before the first section header
    top_end = len(lines)
    for idx, line in enumerate(lines):
        if heading_key(line):
            top_end = idx
            break
    filtered: List[str] = []
    for idx, line in enumerate(lines):
        if idx < top_end:
            s = line.strip()
            if s.startswith("📖标题") or s.startswith("标题") or s.startswith("🌐来源") or s.lower().startswith("source") or s.startswith("来源"):
                continue
        filtered.append(line)
    lines = filtered

    insert_lines: List[str] = []
    if title:
        insert_lines.append(f"📖标题：{title}")
    if source:
        insert_lines.append(f"🌐来源：{source}")

    if insert_lines:
        insert_at = min(first_idx + 1, len(lines))
        lines[insert_at:insert_at] = insert_lines

    return "\n".join(lines).rstrip() + "\n"


def structure_matches_example(
    client: OpenAI,
    text: str,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> bool:
    ecfg = effective_cfg or {}
    sys_prompt = (summary_limit_prompt_structure_check or "").strip()
    if not sys_prompt:
        return True
    content = text.strip()
    if not content:
        return False
    hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
    safety_margin = int(ecfg.get("input_safety_margin") or summary_limit_input_safety_margin)
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(content, user_budget)
    resp = client.chat.completions.create(
        model=get_summary_limit_model(ecfg),
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        max_tokens=8,
        temperature=0,
    )
    reply = resp.choices[0].message.content.strip().upper() if resp.choices else ""
    return reply.startswith("YES")


def restructure_to_example(
    client: OpenAI,
    text: str,
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> str:
    ecfg = effective_cfg or {}
    sys_prompt = (summary_limit_prompt_structure_rewrite or "").strip()
    if not sys_prompt:
        return text
    content = text.strip()
    if not content:
        return text
    hard_limit = int(ecfg.get("input_hard_limit") or summary_limit_input_hard_limit)
    safety_margin = int(ecfg.get("input_safety_margin") or summary_limit_input_safety_margin)
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(content, user_budget)
    max_tok = ecfg.get("max_tokens") if ecfg.get("max_tokens") is not None else summary_limit_max_tokens
    resp = client.chat.completions.create(
        model=get_summary_limit_model(ecfg),
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        max_tokens=max_tok or 2048,
        temperature=0,
    )
    new_text = resp.choices[0].message.content if resp.choices else ""
    return new_text.strip() if new_text else text


def process_one(
    client: OpenAI,
    md_path: Path,
    out_path: Path,
    pdf_info_map: Dict[str, Dict[str, str]],
    *,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, str]:
    ecfg = effective_cfg or {}
    sec_limits = ecfg.get("section_limits", SECTION_LIMITS_DEFAULT)
    sec_prompts = ecfg.get("section_prompts", SECTION_PROMPTS_DEFAULT)

    text = md_path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        out_path.write_text("", encoding="utf-8")
        return md_path, ""
    status = "copied"
    text = inject_pdf_info(text, md_path, pdf_info_map)
    base_text = normalize_style(text)
    lines = base_text.splitlines(keepends=True)
    lines = apply_headline_limit(client, lines, effective_cfg=ecfg)
    base_text = "".join(lines)
    if structure_matches_example(client, base_text, effective_cfg=ecfg):
        prefix, sections = split_sections(lines)
        if sections:
            out_lines: List[str] = []
            out_lines.extend(prefix)
            rewritten_any = False
            for key, heading, content_lines in sections:
                if out_lines and out_lines[-1].strip():
                    out_lines.append("\n")
                out_lines.append(heading)
                block_text = "".join(content_lines).strip()
                limit = sec_limits.get(key, 0)
                if limit and non_ws_len(block_text) > limit:
                    sys_prompt = sec_prompts.get(key, "")
                    if sys_prompt:
                        block_text = rewrite_block(
                            client, block_text, sys_prompt, limit_chars=limit,
                            effective_cfg=ecfg,
                        )
                        rewritten_any = True
                if block_text:
                    if not block_text.endswith("\n"):
                        block_text += "\n"
                    out_lines.append(block_text)
            out_text = ensure_section_spacing("".join(out_lines))
            status = "rewritten" if rewritten_any else "copied"
    else:
        out_text = restructure_to_example(client, base_text, effective_cfg=ecfg)
        out_text = ensure_section_spacing(normalize_style(out_text))
        status = "rewritten"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding="utf-8")
    return md_path, status


def run() -> None:
    ap = argparse.ArgumentParser("summary_limit")
    ap.add_argument("--input-dir", default=str(Path(DATA_ROOT) / "paper_summary" / "single"))
    ap.add_argument("--out-root", default=str(Path(DATA_ROOT) / "summary_limit"))
    ap.add_argument("--date", default="")
    ap.add_argument("--concurrency", type=int, default=summary_limit_concurrency)
    ap.add_argument("--user-id", type=int, default=None, help="User ID for per-user config overrides")
    args = ap.parse_args()

    in_root = Path(args.input_dir)
    if not in_root.exists():
        print(f"[SUMMARY_LIMIT] input dir not found: {in_root}, skip summary_limit", flush=True)
        return

    if args.date:
        in_dir = in_root / args.date
        if not in_dir.exists():
            print(f"[SUMMARY_LIMIT] input dir not found: {in_dir}, skip summary_limit", flush=True)
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
        print(f"[SUMMARY_LIMIT] no md files in {in_dir}, skip summary_limit", flush=True)
        return
    print("============开始生成 summary_limit ============", flush=True)

    out_root = Path(args.out_root)
    single_dir = out_root / "single" / date_str
    gather_dir = out_root / "gather" / date_str
    single_dir.mkdir(parents=True, exist_ok=True)

    pdf_info_map = load_pdf_info_map(date_str)

    to_run: List[Path] = []
    for p in files:
        out_path = single_dir / f"{p.stem}.md"
        if out_path.exists():
            continue
        to_run.append(p)

    total = len(to_run)
    if total == 0:
        gather_path = write_gather(single_dir, gather_dir, date_str)
        print(f"[SUMMARY_LIMIT] all files already processed, single_dir={single_dir}", flush=True)
        print(f"[SUMMARY_LIMIT] gather_path={gather_path}", flush=True)
        return

    ecfg = build_effective_cfg(user_id=args.user_id)
    client = make_client_from_cfg(ecfg)
    workers = max(1, int(args.concurrency or 0))
    print(f"[SUMMARY_LIMIT] input_dir={in_dir} total={total} concurrency={workers} user_id={args.user_id}", flush=True)

    start = time.monotonic()
    done = 0
    empty = 0
    copied = 0
    rewritten = 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {
            ex.submit(process_one, client, p, single_dir / f"{p.stem}.md", pdf_info_map, effective_cfg=ecfg): p
            for p in to_run
        }
        for fut in as_completed(future_map):
            src = future_map[fut]
            try:
                _, status = fut.result()
                if not status:
                    empty += 1
                elif status == "copied":
                    copied += 1
                elif status == "rewritten":
                    rewritten += 1
            except Exception as e:
                print(f"\r[SUMMARY_LIMIT] error on {src.name}: {e!r}", end="", flush=True)
            done += 1
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"\r[SUMMARY_LIMIT] progress done={done}/{total} empty={empty} rate={rate:.2f}/s", end="", flush=True)

    print()
    gather_path = write_gather(single_dir, gather_dir, date_str)
    print(
        f"[SUMMARY_LIMIT] stats copied<=950={copied} rewritten={rewritten}",
        flush=True,
    )
    print(f"[SUMMARY_LIMIT] single_dir={single_dir}", flush=True)
    print(f"[SUMMARY_LIMIT] gather_path={gather_path}", flush=True)
    print("============结束生成 summary_limit ============", flush=True)


if __name__ == "__main__":
    run()
