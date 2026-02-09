import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List

from pypdf import PdfReader, PdfWriter

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config.config import (
    ARXIV_JSON_DIR,
    JSON_FILENAME_FMT,
    PDF_OUTPUT_DIR,
    PDF_PREVIEW_DIR,
    USER_AGENT,
    MANIFEST_FILENAME,
    PAPER_THEME_FILTER_DIR,
    LLM_SELECT_THEME_DIR,
)  # noqa: E402


def setup_logging():
    logger = logging.getLogger("pdf_split")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def find_latest_manifest(root_dir: str) -> str:
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(f"root dir not found: {root_dir}")
    latest = None
    latest_mtime = 0.0
    for dirpath, _, filenames in os.walk(root_dir):
        for name in filenames:
            if name != MANIFEST_FILENAME:
                continue
            full = os.path.join(dirpath, name)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            if mtime >= latest_mtime:
                latest = full
                latest_mtime = mtime
    if not latest:
        raise FileNotFoundError(f"manifest not found in {root_dir}")
    return latest


def resolve_json_path(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        return find_latest_manifest(PDF_OUTPUT_DIR)
    except FileNotFoundError:
        pass
    today = datetime.now().strftime(JSON_FILENAME_FMT)
    for base_dir in [PAPER_THEME_FILTER_DIR, LLM_SELECT_THEME_DIR, ARXIV_JSON_DIR]:
        candidate = os.path.join(base_dir, today)
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError("no json or manifest found for pdf_split")


def load_items_from_json(json_path: str):
    text = Path(json_path).read_text(encoding="utf-8", errors="ignore")
    try:
        obj = json.loads(text) if text.strip() else {}
    except Exception:
        obj = {}
    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        return obj.get("items") or [], str(obj.get("date") or "")
    if isinstance(obj, dict) and isinstance(obj.get("papers"), list):
        return obj.get("papers") or [], ""
    if isinstance(obj, list):
        return obj, ""
    return [], ""


def extract_date_str(path: str, fallback: str) -> str:
    m = re.search(r"\d{4}-\d{2}-\d{2}", os.path.basename(path))
    if m:
        return m.group(0)
    return fallback or datetime.now().strftime("%Y-%m-%d")


def split_pdf(in_path, out_path, pages, logger):
    if not os.path.exists(in_path):
        logger.warning("Source PDF not found, skip: %s", in_path)
        return False
    if os.path.exists(out_path):
        return False
    try:
        with open(in_path, "rb") as f:
            head = f.read(5)
        if not head.startswith(b"%PDF-"):
            logger.warning("Not a valid PDF header, skip: %s", in_path)
            return False
    except Exception as e:
        logger.error("Failed to inspect %s: %r", in_path, e)
        return False
    reader = PdfReader(in_path)
    writer = PdfWriter()
    count = min(pages, len(reader.pages))
    for i in range(count):
        writer.add_page(reader.pages[i])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        writer.write(f)
    return True


def run():
    logger = setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pages", type=int, default=2)
    args = ap.parse_args()

    json_path = resolve_json_path(args.json)
    items, date_hint = load_items_from_json(json_path)
    date_str = extract_date_str(json_path, date_hint)
    logger.info("Use json list: %s", json_path)
    print("============开始切分预览 PDF==============", flush=True)

    arxiv_ids: List[str] = []
    for it in items:
        aid = str(it.get("arxiv_id") or it.get("id") or "").strip()
        if not aid:
            src = str(it.get("source") or "")
            m = re.search(r"arxiv,?\s*([0-9]+\.[0-9]+)", src)
            if m:
                aid = m.group(1)
        if aid:
            arxiv_ids.append(aid)
    if args.limit is not None:
        arxiv_ids = arxiv_ids[: args.limit]

    total = len(arxiv_ids)
    logger.info("Total ids to split: %d", total)

    processed = 0
    skipped = 0
    missing = 0
    manifest_items: List[dict] = []

    for i, aid in enumerate(arxiv_ids, 1):
        src = os.path.join(PDF_OUTPUT_DIR, date_str, f"{aid}.pdf")
        dst = os.path.join(PDF_PREVIEW_DIR, date_str, f"{aid}.pdf")
        try:
            if not os.path.exists(src):
                missing += 1
                created = False
                status = "missing"
            else:
                created = split_pdf(src, dst, args.pages, logger)
                status = "created" if created else "skipped"
            if created:
                processed += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error("Failed to split %s: %r", aid, e)
            status = "error"
        manifest_items.append(
            {"arxiv_id": aid, "source_pdf": src, "preview_pdf": dst, "status": status}
        )
        msg = f"Splitting:【{i}/{total}】"
        if sys.stdout.isatty():
            sys.stdout.write(msg + "\r")
            sys.stdout.flush()
        else:
            print(msg, flush=True)

    if sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()
    logger.info("Done. created=%d, skipped=%d, missing=%d, total=%d", processed, skipped, missing, total)
    manifest_path = os.path.join(PDF_PREVIEW_DIR, date_str, MANIFEST_FILENAME)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "date": date_str,
                "total": total,
                "created": processed,
                "skipped": skipped,
                "missing": missing,
                "items": manifest_items,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info("Saved manifest: %s", manifest_path)
    print("============结束切分预览 PDF==============", flush=True)


if __name__ == "__main__":
    run()
