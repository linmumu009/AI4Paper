from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from openai import OpenAI

ROOT = Path(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, str(ROOT))

from config.config import (  # noqa: E402
    DATA_ROOT,
    qwen_api_key,
    theme_select_base_url,
    theme_select_model,
    theme_select_max_tokens,
    theme_select_temperature,
    theme_select_concurrency,
    theme_select_system_prompt,
    PAPER_DEDUP_DIR,
)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("llm_select_theme")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    log_root = ROOT / "logs" / datetime.now().strftime("%Y-%m-%d")
    log_root.mkdir(parents=True, exist_ok=True)
    log_file = log_root / (datetime.now().strftime("%H%M%S") + "_llm_select_theme.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s " + fmt._fmt))
    logger.addHandler(fh)
    return logger


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


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


@dataclass
class PaperRecord:
    title: str
    abstract: str
    arxiv_id: str


def make_client() -> OpenAI:
    key = (qwen_api_key or "").strip()
    if not key:
        raise SystemExit("qwen_api_key missing in config.config")
    base = (theme_select_base_url or "").strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    return OpenAI(api_key=key, base_url=base)


def build_user_prompt(title: str, abstract: str) -> str:
    if abstract:
        return f"标题：{title}\n摘要：{abstract}"
    return f"标题：{title}\n摘要：无"


def parse_score(text: str) -> float:
    if not text:
        return 0.0
    m = re.search(r"([0-1](?:\.\d+)?)", text)
    if not m:
        return 0.0
    try:
        val = float(m.group(1))
    except ValueError:
        return 0.0
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def score_one(client: OpenAI, block: PaperRecord) -> float:
    user_content = build_user_prompt(block.title, block.abstract)
    kwargs = {}
    if theme_select_temperature is not None:
        kwargs["temperature"] = float(theme_select_temperature)
    if theme_select_max_tokens is not None:
        kwargs["max_tokens"] = int(theme_select_max_tokens)
    resp = client.chat.completions.create(
        model=theme_select_model,
        messages=[
            {"role": "system", "content": theme_select_system_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        **kwargs,
    )
    content = resp.choices[0].message.content if resp.choices else ""
    return parse_score(content)


def run() -> None:
    logger = setup_logging()
    print("============开始主题相关性评分==============", flush=True)
    ap = argparse.ArgumentParser("llm_select_theme")
    ap.add_argument("--json", default=None, help="input json from paperList_remove_duplications")
    ap.add_argument("--outdir", default=None, help="output dir (default data/llm_select_theme)")
    args = ap.parse_args()

    input_dir = ROOT / PAPER_DEDUP_DIR
    json_path = find_latest_json(input_dir, args.json)
    out_dir = Path(args.outdir) if args.outdir else ROOT / DATA_ROOT / "llm_select_theme"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / Path(json_path.name).with_suffix(".json").name

    meta_obj, papers = load_json_papers(json_path)
    records: List[PaperRecord] = []
    for p in papers:
        title = normalize_text(str(p.get("title", "")))
        abstract = normalize_text(str(p.get("summary", "")))
        arxiv_id = str(p.get("arxiv_id", "")).strip()
        records.append(PaperRecord(title=title, abstract=abstract, arxiv_id=arxiv_id))
    if not records:
        out_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning("No paper records found; wrote original json to %s", out_path)
        return

    client = make_client()
    scores: Dict[str, float] = {}
    workers = max(1, int(theme_select_concurrency or 1))
    logger.info("Scoring %d paper(s) with %d worker(s)", len(records), workers)

    total = len(records)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(score_one, client, blk): blk for blk in records}
        for future in as_completed(future_map):
            blk = future_map[future]
            try:
                score = future.result()
            except Exception as exc:
                logger.warning("Score failed for %s: %r", blk.title, exc)
                score = 0.0
            scores[blk.arxiv_id or blk.title] = score
            done += 1
            sys.stdout.write(f"\r[PROGRESS] scoring {done}/{total}")
            sys.stdout.flush()
            time.sleep(0.05)
    print()

    for p in papers:
        key = str(p.get("arxiv_id", "")).strip() or str(p.get("title", "")).strip()
        if key in scores:
            p["theme_relevant_score"] = round(float(scores[key]), 3)

    meta_obj["papers"] = papers
    meta_obj["selected"] = len(papers)
    meta_obj["generated_utc"] = datetime.utcnow().isoformat() + "Z"
    out_path.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved: %s", out_path)
    print("============结束主题相关性评分==============", flush=True)


if __name__ == "__main__":
    run()
