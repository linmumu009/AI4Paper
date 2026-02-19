from __future__ import annotations

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from openai import OpenAI

import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import (  # noqa: E402
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
    paper_assets_system_prompt,
    DATA_ROOT,
    SLLM,
)


# ---------------------------------------------------------------------------
# User-config helpers
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


def today_str() -> str:
    return datetime.now().date().isoformat()


def _global_sllm_connection() -> Tuple[str, str, str]:
    """Return (key, base_url, model) according to global SLLM switch."""
    if SLLM == 2:
        return (summary_gptgod_apikey or "").strip(), (summary_base_url_2 or "").strip(), summary_model_2
    if SLLM == 3:
        return (summary_apikey_3 or "").strip(), (summary_base_url_3 or "").strip(), summary_model_3
    return (qwen_api_key or "").strip(), (summary_base_url or "").strip(), summary_model


def make_client_for_user(user_id: Optional[int] = None) -> Tuple[OpenAI, Dict[str, Any]]:
    """Return (client, effective_cfg) honouring user overrides when *user_id* is given.

    effective_cfg keys: model, temperature, max_tokens, input_hard_limit,
    input_safety_margin, system_prompt.
    Falls back to SLLM-based global config when no user preset is found.
    """
    g_key, g_base, g_model = _global_sllm_connection()
    cfg: Dict[str, Any] = {
        "model": g_model,
        "temperature": summary_temperature,
        "max_tokens": summary_max_tokens,
        "input_hard_limit": summary_input_hard_limit,
        "input_safety_margin": summary_input_safety_margin,
        "system_prompt": paper_assets_system_prompt or "",
    }
    key: str = g_key
    base: str = g_base

    if user_id is not None:
        ucfg = _load_user_config(user_id)
        if ucfg:
            # paper_assets processes the output of paper_summary → reuse summary preset
            preset_id = ucfg.get("summary_llm_preset_id") or ucfg.get("llm_preset_id")
            preset = _resolve_llm_preset(user_id, preset_id) if preset_id else {}
            if preset:
                key = (preset.get("api_key") or key).strip()
                base = (preset.get("base_url") or base).strip()
                cfg["model"] = (preset.get("model") or cfg["model"]).strip()
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if preset.get(k) is not None:
                        cfg[k] = preset[k]
            else:
                key = (ucfg.get("llm_api_key") or key).strip()
                base = (ucfg.get("llm_base_url") or base).strip()
                cfg["model"] = (ucfg.get("llm_model") or cfg["model"]).strip()
                for k in ("temperature", "max_tokens", "input_hard_limit", "input_safety_margin"):
                    if ucfg.get(k) is not None:
                        cfg[k] = ucfg[k]

    if not key:
        raise SystemExit("paper_assets: no api_key available (global config or user preset)")
    if not base:
        raise SystemExit("paper_assets: no base_url available (global config or user preset)")
    client = OpenAI(api_key=key, base_url=base)
    return client, cfg


def make_client() -> OpenAI:
    """Legacy wrapper kept for compatibility; prefer make_client_for_user()."""
    client, _ = make_client_for_user(user_id=None)
    return client


def get_assets_model() -> str:
    """根据 SLLM 返回当前使用的模型名称（与 paper_summary 保持一致）。"""
    _, _, model = _global_sllm_connection()
    return model


def extract_arxiv_id(source: str) -> Optional[str]:
    if not source:
        return None
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", source)
    if not m:
        return None
    version = m.group(2) or ""
    return f"{m.group(1)}{version}"


def load_pdf_info_map(date_str: str) -> Dict[str, Dict[str, Any]]:
    """加载 pdf_info/<date>.json，按 arxiv_id 建立映射。"""
    info_path = Path(DATA_ROOT) / "pdf_info" / f"{date_str}.json"
    if not info_path.exists():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "") or "")
        arxiv_id = extract_arxiv_id(source)
        if not arxiv_id:
            continue
        out[arxiv_id] = item
    return out


def get_pdf_meta_for_id(pdf_info_map: Dict[str, Dict[str, Any]], paper_id: str) -> Optional[Dict[str, Any]]:
    if not paper_id:
        return None
    info = pdf_info_map.get(paper_id)
    if info is not None:
        return info
    # 再尝试去掉版本号匹配
    base_id = re.sub(r"v\d+$", "", paper_id)
    if base_id != paper_id:
        return pdf_info_map.get(base_id)
    return None


def parse_year(published: str) -> Optional[int]:
    if not published:
        return None
    m = re.match(r"(\d{4})", published.strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def build_url(paper_id: str) -> str:
    if not paper_id:
        return ""
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", paper_id):
        return f"https://arxiv.org/abs/{paper_id}"
    return ""


def ensure_blocks_structure(blocks: Any) -> Dict[str, Dict[str, List[str]]]:
    """确保 blocks 结构完整且类型正确。"""
    expected_keys = [
        "background",
        "objective",
        "method",
        "data",
        "experiment",
        "metrics",
        "results",
        "limitations",
    ]
    out: Dict[str, Dict[str, List[str]]] = {}
    if not isinstance(blocks, dict):
        blocks = {}
    for key in expected_keys:
        raw = blocks.get(key, {}) if isinstance(blocks, dict) else {}
        text = raw.get("text") if isinstance(raw, dict) else ""
        bullets = raw.get("bullets") if isinstance(raw, dict) else []
        if not isinstance(text, str):
            text = "" if text is None else str(text)
        if not isinstance(bullets, list):
            bullets = []
        norm_bullets: List[str] = []
        for b in bullets:
            if isinstance(b, str):
                s = b.strip()
            else:
                s = str(b).strip()
            if s:
                norm_bullets.append(s)
        out[key] = {"text": text.strip(), "bullets": norm_bullets}
    return out


def parse_json_from_text(text: str) -> Any:
    """从模型回复中尽量抠出 JSON 对象。"""
    if not text:
        return {}
    s = text.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    snippet = s[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return {}


def extract_blocks_with_llm(
    client: OpenAI,
    md_text: str,
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, List[str]]]:
    content = (md_text or "").strip()
    if not content:
        return ensure_blocks_structure({})
    cfg = effective_cfg or {}
    sys_prompt = (cfg.get("system_prompt") or paper_assets_system_prompt or "").strip()
    if not sys_prompt:
        raise SystemExit("paper_assets_system_prompt missing in config.config")

    hard_limit = int(cfg.get("input_hard_limit") or summary_input_hard_limit)
    safety_margin = int(cfg.get("input_safety_margin") or summary_input_safety_margin)
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(content, user_budget)

    kwargs: Dict[str, Any] = {}
    temp = cfg.get("temperature") if cfg else summary_temperature
    max_tok = cfg.get("max_tokens") if cfg else summary_max_tokens
    if temp is not None:
        kwargs["temperature"] = float(temp)
    if max_tok is not None:
        kwargs["max_tokens"] = int(max_tok)

    model_name = (cfg.get("model") or get_assets_model()) if cfg else get_assets_model()

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": "下面是某篇论文的中文摘要/笔记文本，请根据系统提示词只构造 blocks 字段的内容：\n\n" + user_content,
            },
        ],
        stream=False,
        **kwargs,
    )
    reply = resp.choices[0].message.content if resp.choices else ""
    obj = parse_json_from_text(reply)
    # 模型按 prompt 只输出 blocks 对象（8 个键在顶层）；兼容历史上可能返回 {"blocks": {...}} 的情况
    if isinstance(obj, dict) and "blocks" in obj and isinstance(obj["blocks"], dict):
        blocks_raw = obj["blocks"]
    else:
        blocks_raw = obj
    return ensure_blocks_structure(blocks_raw)


def list_md_files(in_dir: Path) -> List[Path]:
    return sorted(p for p in in_dir.glob("*.md") if p.is_file() and p.name != "full.md")


def resolve_date_and_input_dir(root: Path, explicit_date: str) -> Tuple[Path, str]:
    # 优先使用命令行 --date，其次 RUN_DATE 环境变量，否则回落到“今日或最新日期子目录”的逻辑
    date_arg = explicit_date.strip() if explicit_date else ""
    if not date_arg:
        env_date = os.environ.get("RUN_DATE", "").strip()
        date_arg = env_date

    if date_arg:
        in_dir = root / date_arg
        if not in_dir.exists():
            print(f"[PAPER_ASSETS] input dir not found for date={date_arg}: {in_dir}", flush=True)
            raise SystemExit(0)
        return in_dir, date_arg

    today = today_str()
    candidate = root / today
    if candidate.is_dir():
        return candidate, today

    subdirs: List[Path] = []
    for d in root.iterdir():
        if d.is_dir():
            name = d.name
            if len(name) == 10 and name[4] == "-" and name[7] == "-":
                subdirs.append(d)
    if subdirs:
        subdirs.sort(key=lambda p: p.name)
        last = subdirs[-1]
        return last, last.name

    return root, today


def process_one(
    client: OpenAI,
    md_path: Path,
    pdf_info_map: Dict[str, Dict[str, Any]],
    effective_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        paper_id = md_path.stem
        meta = get_pdf_meta_for_id(pdf_info_map, paper_id)
        title = str(meta.get("title", "") or "").strip() if meta else ""
        published = str(meta.get("published", "") or "").strip() if meta else ""
        year = parse_year(published) if published else None
        return {
            "paper_id": paper_id,
            "title": title,
            "url": build_url(paper_id),
            "year": year,
            "blocks": ensure_blocks_structure({}),
        }

    paper_id = md_path.stem
    meta = get_pdf_meta_for_id(pdf_info_map, paper_id)
    title = str(meta.get("title", "") or "").strip() if meta else ""
    published = str(meta.get("published", "") or "").strip() if meta else ""
    year = parse_year(published) if published else None

    blocks = extract_blocks_with_llm(client, text, effective_cfg)

    return {
        "paper_id": paper_id,
        "title": title,
        "url": build_url(paper_id),
        "year": year,
        "blocks": blocks,
    }


def run() -> None:
    ap = argparse.ArgumentParser("paper_assets")
    ap.add_argument("--input-dir", default=str(Path(DATA_ROOT) / "paper_summary" / "single"))
    ap.add_argument("--out-root", default=str(Path(DATA_ROOT) / "paper_assets"))
    ap.add_argument("--date", default="")
    ap.add_argument("--concurrency", type=int, default=summary_concurrency)
    ap.add_argument("--user-id", type=int, default=None, help="user id for per-user LLM preset override")
    args = ap.parse_args()

    in_root = Path(args.input_dir)
    if not in_root.exists():
        print(f"[PAPER_ASSETS] input root not found: {in_root}, skip paper_assets", flush=True)
        return

    try:
        in_dir, date_str = resolve_date_and_input_dir(in_root, args.date)
    except SystemExit:
        return

    files = list_md_files(in_dir)
    if not files:
        print(f"[PAPER_ASSETS] no md files in {in_dir}, skip paper_assets", flush=True)
        return

    print("============开始生成 paper_assets ============", flush=True)

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / f"{date_str}.jsonl"

    pdf_info_map = load_pdf_info_map(date_str)

    client, effective_cfg = make_client_for_user(args.user_id)
    workers = max(1, int(args.concurrency or 0))
    total = len(files)
    print(f"[PAPER_ASSETS] input_dir={in_dir} total={total} concurrency={workers} user_id={args.user_id}", flush=True)

    start = time.monotonic()
    done = 0
    errors = 0
    results: List[Dict[str, Any]] = []

    def task(p: Path) -> Dict[str, Any]:
        return process_one(client, p, pdf_info_map, effective_cfg)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {ex.submit(task, p): p for p in files}
        for fut in as_completed(future_map):
            src = future_map[fut]
            try:
                obj = fut.result()
                if obj:
                    results.append(obj)
            except Exception as e:
                errors += 1
                print(f"\r[PAPER_ASSETS] error on {src.name}: {e!r}", end="", flush=True)
            done += 1
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"\r[PAPER_ASSETS] progress done={done}/{total} errors={errors} rate={rate:.2f}/s", end="", flush=True)

    print()

    # 按 paper_id 排序写出 JSONL
    results.sort(key=lambda o: str(o.get("paper_id", "")))
    with out_path.open("w", encoding="utf-8") as f:
        for obj in results:
            f.write(json.dumps(obj, ensure_ascii=False))
            f.write("\n")

    print(f"[PAPER_ASSETS] out_path={out_path}", flush=True)
    print(f"[PAPER_ASSETS] total={total} written={len(results)} errors={errors}", flush=True)
    print("============结束生成 paper_assets ============", flush=True)


if __name__ == "__main__":
    run()

