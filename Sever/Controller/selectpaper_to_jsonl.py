from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import (  # noqa: E402
    summary_batch_endpoint,
    summary_batch_jsonl_root,
    summary_batch_model,
    summary_batch_system_prompt,
    summary_batch_temperature,
    DATA_ROOT,
)


def list_md_files(root: Path) -> List[Path]:
    return sorted(root.glob("*.md"))


def today_str() -> str:
    return datetime.now().date().isoformat()


def build_custom_id(stem: str, used: Dict[str, int]) -> str:
    if stem not in used:
        used[stem] = 1
        return stem
    used[stem] += 1
    return f"{stem}-{used[stem]}"


def run() -> None:
    ap = argparse.ArgumentParser("selectpaper_to_jsonl")
    ap.add_argument("--input-dir", default=str(Path(DATA_ROOT) / "selectedpaper_to_mineru"))
    ap.add_argument("--out-root", default=str(summary_batch_jsonl_root))
    ap.add_argument("--date", default="")
    args = ap.parse_args()

    in_root = Path(args.input_dir)
    if not in_root.exists():
        print(f"[JSONL] input dir not found: {in_root}, skip", flush=True)
        return

    if args.date:
        in_dir = in_root / args.date
        if not in_dir.exists():
            print(f"[JSONL] input dir not found: {in_dir}, skip", flush=True)
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
        print(f"[JSONL] no md files in {in_dir}, skip", flush=True)
        return

    out_root = Path(args.out_root)
    out_dir = out_root / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.jsonl"

    used_ids: Dict[str, int] = {}
    with out_path.open("w", encoding="utf-8") as f:
        for p in files:
            md_text = p.read_text(encoding="utf-8", errors="ignore")
            custom_id = build_custom_id(p.stem, used_ids)
            line = {
                "custom_id": custom_id,
                "method": "POST",
                "url": summary_batch_endpoint,
                "body": {
                    "model": summary_batch_model,
                    "messages": [
                        {"role": "system", "content": summary_batch_system_prompt},
                        {"role": "user", "content": md_text},
                    ],
                    "temperature": summary_batch_temperature,
                },
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    print(f"[JSONL] saved: {out_path}", flush=True)


if __name__ == "__main__":
    run()
