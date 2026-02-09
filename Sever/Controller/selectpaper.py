import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config.config import DATA_ROOT, MANIFEST_FILENAME  # noqa: E402


def find_latest_json(root: Path) -> Tuple[Path, str]:
    if not root.exists():
        raise SystemExit(f"filter root not found: {root}")
    cand: List[Tuple[Path, str]] = []
    for p in root.rglob("*.json"):
        if not p.is_file():
            continue
        m = re.search(r"(\d{4}-\d{2}-\d{2})", p.stem)
        if not m:
            continue
        cand.append((p, m.group(1)))
    if not cand:
        raise SystemExit(f"no dated json found in {root}")
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


def extract_arxiv_id(item: Dict[str, Any]) -> str:
    src = str(item.get("source") or "")
    m = re.search(r"arxiv,\s*([0-9]+\.[0-9]+)", src)
    if m:
        return m.group(1)
    return ""


def run(args: argparse.Namespace) -> None:
    filter_root = Path(args.filter_root)
    raw_root = Path(args.raw_root)
    out_root = Path(args.out_root)
    if args.input:
        in_path = Path(args.input)
        if not in_path.exists():
            raise SystemExit(f"input file not found: {in_path}")
        m = re.search(r"(\d{4}-\d{2}-\d{2})", in_path.stem)
        date_str = m.group(1) if m else in_path.stem
    else:
        in_path, date_str = find_latest_json(filter_root)
    items = load_items(in_path)
    if not items:
        print("no items in filter json")
        return
    print("============开始拷贝精选论文 PDF==============", flush=True)
    out_dir = out_root / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(items)
    moved = 0
    skipped = 0
    missing = 0
    manifest_items: List[Dict[str, Any]] = []
    for idx, it in enumerate(items, 1):
        aid = extract_arxiv_id(it)
        if not aid:
            skipped += 1
            continue
        src = None
        candidates = []
        if date_str:
            candidates.append(raw_root / date_str / f"{aid}.pdf")
        candidates.append(raw_root / f"{aid}.pdf")
        for cand in candidates:
            if cand.exists():
                src = cand
                break
        if src is None:
            skipped += 1
            missing += 1
            manifest_items.append(
                {"arxiv_id": aid, "source_pdf": "", "selected_pdf": str(out_dir / f"{aid}.pdf"), "status": "missing"}
            )
            continue
        dst = out_dir / f"{aid}.pdf"
        if dst.exists():
            skipped += 1
            manifest_items.append(
                {"arxiv_id": aid, "source_pdf": str(src), "selected_pdf": str(dst), "status": "exists"}
            )
            continue
        shutil.move(str(src), str(dst))
        moved += 1
        manifest_items.append(
            {"arxiv_id": aid, "source_pdf": str(src), "selected_pdf": str(dst), "status": "moved"}
        )
        print(f"\r[move] {idx}/{total} moved={moved} skipped={skipped}", end="", flush=True)
    print()
    print("============结束拷贝精选论文 PDF==============", flush=True)
    manifest_path = out_dir / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(
            {
                "date": date_str,
                "total": total,
                "moved": moved,
                "skipped": skipped,
                "missing": missing,
                "items": manifest_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser("selectpaper")
    ap.add_argument("--filter-root", default=str(Path(DATA_ROOT) / "instutions_filter"))
    ap.add_argument("--raw-root", default=str(Path(DATA_ROOT) / "raw_pdf"))
    ap.add_argument("--out-root", default=str(Path(DATA_ROOT) / "selectedpaper"))
    ap.add_argument("--input", default="")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
