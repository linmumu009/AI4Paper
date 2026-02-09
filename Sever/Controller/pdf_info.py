import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.config import qwen_api_key as CFG_QWEN_KEY  # noqa: E402
from config.config import org_base_url as CFG_BASE_URL  # noqa: E402
from config.config import org_model as CFG_MODEL  # noqa: E402
from config.config import org_temperature as CFG_TEMPERATURE  # noqa: E402
from config.config import org_max_tokens as CFG_MAX_TOKENS  # noqa: E402
from config.config import pdf_info_system_prompt as CFG_INFO_PROMPT  # noqa: E402
from config.config import DATA_ROOT, PAPER_THEME_FILTER_DIR  # noqa: E402
from config.config import pdf_info_concurrency  # noqa: E402


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def find_latest_date_dir(root: Path) -> Tuple[Path, str]:
    cand: List[Tuple[Path, str]] = []
    if not root.exists():
        return root / today_str(), today_str()
    for d in root.iterdir():
        if not d.is_dir():
            continue
        m = re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)
        if not m:
            continue
        cand.append((d, d.name))
    if not cand:
        return root / today_str(), today_str()
    cand.sort(key=lambda x: x[1], reverse=True)
    return cand[0][0], cand[0][1]


def list_md_files(in_dir: Path) -> List[Path]:
    return sorted([p for p in in_dir.glob("*.md") if p.is_file()])


def read_text_clip(path: Path, max_chars: int = 120000) -> str:
    t = path.read_text(encoding="utf-8", errors="ignore")
    if len(t) > max_chars:
        return t[:max_chars]
    return t


def find_latest_json(root: Path) -> Path:
    if not root.exists():
        raise SystemExit(f"json dir not found: {root}")
    files = sorted([p for p in root.glob("*.json") if p.is_file()])
    if not files:
        raise SystemExit(f"no json in {root}")
    return files[-1]


def parse_arxiv_json(json_path: Path) -> Dict[str, Dict[str, str]]:
    text = json_path.read_text(encoding="utf-8", errors="ignore")
    try:
        obj = json.loads(text) if text.strip() else {}
    except Exception:
        obj = {}
    papers = obj.get("papers") if isinstance(obj, dict) else None
    papers = papers if isinstance(papers, list) else []
    meta: Dict[str, Dict[str, str]] = {}
    for p in papers:
        if not isinstance(p, dict):
            continue
        arxiv_id = str(p.get("arxiv_id") or "").strip()
        if not arxiv_id:
            continue
        title = str(p.get("title") or "").strip()
        published = str(p.get("published_utc") or p.get("published") or "").strip()
        meta[arxiv_id] = {
            "title": title,
            "published": published,
            "source": f"arxiv, {arxiv_id}",
        }
    return meta


def call_qwen(api_key: str, base_url: str, model: str, system_prompt: str, user_content: str, temperature: float, max_tokens: int) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": float(temperature) if temperature is not None else 1.0,
        "max_tokens": int(max_tokens) if max_tokens is not None else 1024,
        "stream": False,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=(20, 120))
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        return "{}"
    choices = data.get("choices") or []
    if not choices:
        return "{}"
    msg = choices[0].get("message") or {}
    content = msg.get("content") or ""
    return content or "{}"


def parse_json_or_fallback(text: str) -> Dict[str, Any]:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {
        "instution": "",
        "is_large": False,
        "abstract": "",
    }


def run(args: argparse.Namespace) -> None:
    preview_root = Path(args.in_md_root)
    preview_dir, date_dir = find_latest_date_dir(preview_root)
    arxiv_json_path = Path(args.arxiv_json) if args.arxiv_json else None
    if arxiv_json_path and not arxiv_json_path.exists():
        raise SystemExit(f"missing arxiv json file: {arxiv_json_path}")
    if not arxiv_json_path:
        candidate = Path(PAPER_THEME_FILTER_DIR) / f"{date_dir}.json"
        if candidate.exists():
            arxiv_json_path = candidate
        else:
            arxiv_json_path = find_latest_json(Path(PAPER_THEME_FILTER_DIR))
    meta_map = parse_arxiv_json(arxiv_json_path)
    out_root = ensure_dir(Path(args.outdir))
    out_path = out_root / f"{date_dir}.json"
    md_files = list_md_files(preview_dir)
    if not md_files:
        print(f"no md files in {preview_dir}, skip pdf_info", flush=True)
        out_path.write_text("[]", encoding="utf-8")
        print("[process] 0/0")
        return
    print("============开始调用大模型做机构识别==============", flush=True)
    system_prompt = (CFG_INFO_PROMPT or "").strip()
    api_key = (CFG_QWEN_KEY or "").strip()
    base_url = (CFG_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1").strip()
    model = (CFG_MODEL or "qwen-plus").strip()
    temperature = CFG_TEMPERATURE if CFG_TEMPERATURE is not None else 1.0
    max_tokens = CFG_MAX_TOKENS if CFG_MAX_TOKENS is not None else 1024
    agg: List[Dict[str, Any]] = []
    if out_path.exists():
        try:
            agg_text = out_path.read_text(encoding="utf-8", errors="ignore")
            obj = json.loads(agg_text)
            if isinstance(obj, list):
                agg = obj
        except Exception:
            agg = []
    existing_ids: set[str] = set()
    if agg:
        for it in agg:
            src = str(it.get("source") or "")
            m = re.search(r"arxiv,\s*([0-9]+\.[0-9]+)", src)
            if m:
                existing_ids.add(m.group(1))
    if agg:
        dedup: Dict[str, Dict[str, Any]] = {}
        for it in agg:
            src = str(it.get("source") or "")
            m = re.search(r"arxiv,\s*([0-9]+\.[0-9]+)", src)
            if m:
                dedup[m.group(1)] = it
        agg = list(dedup.values())
        out_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    remaining_files = [p for p in md_files if p.stem not in existing_ids]
    if args.limit and args.limit > 0:
        remaining_files = remaining_files[: args.limit]
    total = len(remaining_files)
    processed = 0
    errors = 0
    if total == 0:
        print(f"[process] 0/0")
        return

    workers = max(1, int(getattr(args, "concurrency", 1) or 1))
    print(f"[process] total={total} concurrency={workers}", flush=True)
    start = time.monotonic()

    def task(p: Path) -> Tuple[str, Dict[str, Any] | None, str]:
        arxiv_id = p.stem
        try:
            content = read_text_clip(p, max_chars=args.max_chars)
            user_content = f"文件名：{p.name}\n文本：\n{content}"
            out_text = call_qwen(api_key, base_url, model, system_prompt, user_content, temperature, max_tokens)
            obj_small = parse_json_or_fallback(out_text)
            meta = meta_map.get(arxiv_id, {"title": "", "source": f"arxiv, {arxiv_id}", "published": ""})
            item = {
                "title": meta.get("title", ""),
                "source": meta.get("source", ""),
                "published": meta.get("published", ""),
                "instution": obj_small.get("instution", ""),
                "is_large": bool(obj_small.get("is_large", False)),
                "abstract": obj_small.get("abstract", ""),
            }
            return arxiv_id, item, ""
        except Exception as e:
            return arxiv_id, None, repr(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(task, p) for p in remaining_files]
        for fut in concurrent.futures.as_completed(futures):
            try:
                arxiv_id, item, err = fut.result()
            except Exception as e:
                processed += 1
                errors += 1
                elapsed = time.monotonic() - start
                rate = processed / elapsed if elapsed > 0 else 0.0
                print(f"\r[process] {processed}/{total} err={errors} rate={rate:.2f}/s", end="", flush=True)
                continue

            processed += 1
            if item is None:
                errors += 1
            else:
                agg.append(item)
                out_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
            elapsed = time.monotonic() - start
            rate = processed / elapsed if elapsed > 0 else 0.0
            print(f"\r[process] {processed}/{total} err={errors} rate={rate:.2f}/s", end="", flush=True)
    print()
    print("============结束机构识别与信息写入==============", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser("pdf_info")
    ap.add_argument("--in-md-root", default=str(Path(DATA_ROOT) / "preview_pdf_to_mineru"))
    ap.add_argument("--outdir", default=str(Path(DATA_ROOT) / "pdf_info"))
    ap.add_argument("--arxiv-json", default="")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=pdf_info_concurrency)
    ap.add_argument("--max-chars", type=int, default=120000)
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
