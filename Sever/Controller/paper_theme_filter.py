from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

ROOT = Path(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, str(ROOT))

from config.config import DATA_ROOT  # noqa: E402


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("paper_theme_filter")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    log_root = ROOT / "logs" / datetime.now().strftime("%Y-%m-%d")
    log_root.mkdir(parents=True, exist_ok=True)
    log_file = log_root / (datetime.now().strftime("%H%M%S") + "_paper_theme_filter.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s " + fmt._fmt))
    logger.addHandler(fh)
    return logger


def find_latest_json(root: Path, explicit: Optional[str]) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise SystemExit(f"json not found: {p}")
        return p
    if not root.exists():
        raise SystemExit(f"json dir not found: {root}")
    files = sorted([p for p in root.glob("*.json") if p.is_file()])
    if not files:
        raise SystemExit(f"no json in {root}")
    return files[-1]


def load_json_papers(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
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


def run() -> None:
    logger = setup_logging()
    print("============开始主题相关性过滤==============", flush=True)
    ap = argparse.ArgumentParser("paper_theme_filter")
    ap.add_argument("--json", default=None, help="input json from llm_select_theme")
    ap.add_argument("--outdir", default=None, help="output dir (default data/paper_theme_filter)")
    ap.add_argument("--threshold", type=float, default=0.85, help="score threshold to keep (default 0.85)")
    args = ap.parse_args()

    input_dir = ROOT / DATA_ROOT / "llm_select_theme"
    json_path = find_latest_json(input_dir, args.json)
    out_dir = Path(args.outdir) if args.outdir else ROOT / DATA_ROOT / "paper_theme_filter"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / Path(json_path.name).with_suffix(".json").name

    meta_obj, papers = load_json_papers(json_path)
    if not papers:
        out_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning("No paper records found; wrote original json to %s", out_path)
        return

    kept: List[Dict[str, Any]] = []
    total = len(papers)
    for idx, p in enumerate(papers, 1):
        score = float(p.get("theme_relevant_score", 0.0) or 0.0)
        if score >= float(args.threshold):
            kept.append(p)
        sys.stdout.write(f"\r[PROGRESS] filtering {idx}/{total}")
        sys.stdout.flush()
    print()

    kept_count = len(kept)
    filtered_count = total - kept_count
    meta_obj["papers"] = kept
    meta_obj["selected"] = kept_count
    meta_obj["generated_utc"] = datetime.utcnow().isoformat() + "Z"
    out_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved: %s", out_path)
    print(f"[INFO] Kept: {kept_count}, Filtered: {filtered_count}", flush=True)
    print("============结束主题相关性过滤==============", flush=True)


if __name__ == "__main__":
    run()
