from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple


ROOT = Path(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, str(ROOT))
from config.config import DATA_ROOT, ARXIV_JSON_DIR, PAPER_DEDUP_DIR, JSON_FILENAME_FMT  # noqa: E402

CONFIG_PATH = ROOT / "config" / "paperList.json"
DATA_DIR = ROOT / DATA_ROOT
ARXIV_LIST_DIR = DATA_DIR / "arxivList" / "md"
ARXIV_JSON_ROOT = ROOT / ARXIV_JSON_DIR
DEDUP_DIR = ROOT / PAPER_DEDUP_DIR


def load_existing() -> List[Dict[str, Any]]:
    if not CONFIG_PATH.exists():
        return []
    text = CONFIG_PATH.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def build_seen_keys(items: List[Dict[str, Any]]) -> set:
    seen = set()
    for item in items:
        title = str(item.get("title", "")).strip()
        source = str(item.get("source", "")).strip()
        if title or source:
            seen.add((title, source))
    return seen


def find_latest_md(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"arxiv list not found: {p}")
        return p
    if not ARXIV_LIST_DIR.exists():
        raise SystemExit(f"arxiv list dir not found: {ARXIV_LIST_DIR}")
    cands = sorted(ARXIV_LIST_DIR.glob("*.md"))
    if not cands:
        raise SystemExit(f"no markdown in {ARXIV_LIST_DIR}")
    return cands[-1]


def find_latest_json(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"arxiv json not found: {p}")
        return p
    if not ARXIV_JSON_ROOT.exists():
        raise SystemExit(f"arxiv json dir not found: {ARXIV_JSON_ROOT}")
    cands = sorted([p for p in ARXIV_JSON_ROOT.glob("*.json") if p.is_file()])
    if not cands:
        raise SystemExit(f"no json in {ARXIV_JSON_ROOT}")
    return cands[-1]


def load_json_papers(path: Path) -> Tuple[dict, List[Dict[str, Any]]]:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    try:
        obj = json.loads(text) if text else {}
    except json.JSONDecodeError:
        obj = {}
    if isinstance(obj, dict):
        papers = obj.get("papers") or []
    elif isinstance(obj, list):
        papers = obj
        obj = {"papers": papers}
    else:
        papers = []
        obj = {"papers": papers}
    papers = [p for p in papers if isinstance(p, dict)]
    return obj, papers


def parse_md(md_path: Path) -> List[Dict[str, str]]:
    lines = md_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    result: List[Dict[str, str]] = []
    current_title = ""
    current_source = ""
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("#"):
            continue
        if not line:
            continue
        if line[0].isdigit() and ". **" in line:
            if current_title or current_source:
                result.append({"title": current_title, "source": current_source})
                current_title = ""
                current_source = ""
            start = line.find("**")
            end = line.rfind("**")
            if start != -1 and end != -1 and end > start + 2:
                t = line[start + 2 : end].strip()
            else:
                t = line
            current_title = t
            continue
        if line.startswith("- arXiv: [") and "](" in line:
            start = line.find("[")
            end = line.find("]", start + 1)
            if start != -1 and end != -1 and end > start + 1:
                arxiv_id = line[start + 1 : end].strip()
                current_source = arxiv_id
            else:
                current_source = line
            continue
        if line.startswith("- Published:"):
            continue
        if line.startswith("## "):
            continue
    if current_title or current_source:
        result.append({"title": current_title, "source": current_source})
    return result


def filter_new_items(today_items: List[Dict[str, str]], seen: set) -> List[Dict[str, str]]:
    new_items: List[Dict[str, str]] = []
    for item in today_items:
        title = str(item.get("title", "")).strip()
        source = str(item.get("source", "")).strip()
        key = (title, source)
        if key in seen:
            continue
        new_items.append(item)
        seen.add(key)
    return new_items


def extract_date_from_name(name: str) -> str:
    m = re.search(r"\d{4}-\d{2}-\d{2}", name)
    return m.group(0) if m else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def append_to_config(existing: List[Dict[str, Any]], new_items: List[Dict[str, str]]) -> None:
    if not new_items:
        return
    now = datetime.now(timezone.utc).isoformat()
    for item in new_items:
        rec = {
            "title": str(item.get("title", "")).strip(),
            "source": str(item.get("source", "")).strip(),
            "writing_datetime": now,
        }
        existing.append(rec)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_blocks(lines: List[str]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    current_start = None
    current_title = ""
    current_source = ""
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if line[0].isdigit() and ". **" in line:
            if current_start is not None:
                blocks.append(
                    {
                        "start": current_start,
                        "end": idx,
                        "title": current_title,
                        "source": current_source,
                    }
                )
            current_start = idx
            current_source = ""
            start = line.find("**")
            end = line.rfind("**")
            if start != -1 and end != -1 and end > start + 2:
                t = line[start + 2 : end].strip()
            else:
                t = line
            current_title = t
            continue
        if current_start is not None and line.startswith("- arXiv: [") and "](" in line:
            start = line.find("[")
            end = line.find("]", start + 1)
            if start != -1 and end != -1 and end > start + 1:
                arxiv_id = line[start + 1 : end].strip()
                current_source = arxiv_id
            else:
                current_source = line
            continue
        if line.startswith("## "):
            if current_start is not None:
                blocks.append(
                    {
                        "start": current_start,
                        "end": idx,
                        "title": current_title,
                        "source": current_source,
                    }
                )
                current_start = None
                current_title = ""
                current_source = ""
            continue
    if current_start is not None:
        blocks.append(
            {
                "start": current_start,
                "end": len(lines),
                "title": current_title,
                "source": current_source,
            }
        )
    return blocks


def write_dedup_md(md_path: Path, new_items: List[Dict[str, str]]) -> None:
    lines = md_path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    keep_keys = {
        (str(item.get("title", "")).strip(), str(item.get("source", "")).strip())
        for item in new_items
    }
    blocks = collect_blocks(lines)
    out_lines: List[str] = []
    idx = 0
    for blk in blocks:
        start = int(blk["start"])
        end = int(blk["end"])
        title = str(blk.get("title", "")).strip()
        source = str(blk.get("source", "")).strip()
        while idx < start:
            out_lines.append(lines[idx])
            idx += 1
        key = (title, source)
        if key in keep_keys:
            out_lines.extend(lines[start:end])
        idx = end
    while idx < len(lines):
        out_lines.append(lines[idx])
        idx += 1
    DEDUP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DEDUP_DIR / md_path.name
    out_path.write_text("".join(out_lines), encoding="utf-8")


def run() -> None:
    ap = argparse.ArgumentParser("paperList_remove_duplications")
    ap.add_argument("--md", default="", help="arxiv list markdown path; default latest in data/arxivList/md")
    ap.add_argument("--json", default="", help="arxiv list json path; default latest in data/arxivList/json")
    ap.add_argument("--out-json", default="", help="output json path; default data/paperList_remove_duplications/<date>.json")
    args = ap.parse_args()

    json_path = find_latest_json(args.json if args.json else None)
    json_obj, papers = load_json_papers(json_path)
    existing = load_existing()
    seen = build_seen_keys(existing)

    today_items = []
    for p in papers:
        title = str(p.get("title", "")).strip()
        arxiv_id = str(p.get("arxiv_id", "")).strip()
        if title or arxiv_id:
            today_items.append({"title": title, "source": arxiv_id})
    new_items = filter_new_items(today_items, seen)
    append_to_config(existing, new_items)

    keep_keys = {(it["title"], it["source"]) for it in new_items}
    kept_papers = []
    for p in papers:
        key = (str(p.get("title", "")).strip(), str(p.get("arxiv_id", "")).strip())
        if key in keep_keys:
            kept_papers.append(p)

    out_obj = dict(json_obj) if isinstance(json_obj, dict) else {"papers": []}
    out_obj["papers"] = kept_papers
    out_obj["selected"] = len(kept_papers)
    out_obj["generated_utc"] = datetime.now(timezone.utc).isoformat()

    if args.out_json:
        out_json_path = Path(args.out_json)
    else:
        date_str = extract_date_from_name(json_path.name)
        out_json_path = DEDUP_DIR / datetime.strptime(date_str, "%Y-%m-%d").strftime(JSON_FILENAME_FMT)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.md:
        md_path = find_latest_md(args.md)
        write_dedup_md(md_path, new_items)


if __name__ == "__main__":
    run()
