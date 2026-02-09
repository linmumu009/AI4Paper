import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.config import DATA_ROOT  # noqa: E402


def find_latest_json(root: Path) -> Tuple[Path, str]:
    if not root.exists():
        raise SystemExit(f"input root not found: {root}")
    result = find_latest_json_optional(root)
    if result is None:
        raise SystemExit(f"no dated json found in {root}")
    return result


def find_latest_json_optional(root: Path) -> Optional[Tuple[Path, str]]:
    if not root.exists():
        raise SystemExit(f"input root not found: {root}")
    cand: List[Tuple[Path, str]] = []
    for p in root.iterdir():
        if not p.is_file():
            continue
        if not p.name.lower().endswith(".json"):
            continue
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.json", p.name)
        if not m:
            continue
        cand.append((p, m.group(1)))
    if not cand:
        return None
    cand.sort(key=lambda x: x[1], reverse=True)
    return cand[0]


def load_items(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        obj = json.loads(text)
    except Exception as e:
        raise SystemExit(f"invalid json: {path}: {e}")
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        return [obj]
    return []


def run(args: argparse.Namespace) -> None:
    root = Path(args.input_root)
    if args.input:
        in_path = Path(args.input)
        if not in_path.exists():
            raise SystemExit(f"input file not found: {in_path}")
        date_str = in_path.stem
    else:
        result = find_latest_json_optional(root)
        if result is None:
            date_str = datetime.now().date().isoformat()
            out_root = Path(args.output_root)
            out_dir = out_root / date_str
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{date_str}.json"
            out_path.write_text("[]", encoding="utf-8")
            print(f"[FILTER] no dated json in {root}, wrote empty result for {date_str}", flush=True)
            print("============结束筛选大机构论文==============", flush=True)
            return
        in_path, date_str = result
    print("============开始筛选大机构论文==============", flush=True)
    items = load_items(in_path)
    kept = [it for it in items if bool(it.get("is_large"))]
    if args.output:
        out_path = Path(args.output)
        out_dir = out_path.parent
    else:
        out_root = Path(args.output_root)
        out_dir = out_root / date_str
        out_path = out_dir / f"{date_str}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    total = len(items)
    kept_count = len(kept)
    dropped = total - kept_count
    print(f"[FILTER] total={total} kept={kept_count} dropped={dropped}", flush=True)
    print("============结束筛选大机构论文==============", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser("instutions_filter")
    ap.add_argument("--input-root", default=str(Path(DATA_ROOT) / "pdf_info"))
    ap.add_argument("--input", default="")
    ap.add_argument("--output-root", default=str(Path(DATA_ROOT) / "instutions_filter"))
    ap.add_argument("--output", default="")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
