#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Download arXiv PDFs from a JSON list and validate integrity.

Typical usage:
  python .\pdf_download.py --json .\papers.json --outdir .\pdfs

If you must use proxy from environment variables:
  python .\pdf_download.py --json .\papers.json --outdir .\pdfs --use-proxy
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Set, Optional, Tuple, Dict, Any

import requests


# ------------- Logging -------------
def setup_logging(log_file: str = "pdf_download.log") -> logging.Logger:
    logger = logging.getLogger("pdfdl")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("[%(levelname)s] %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s " + fmt._fmt))
    logger.addHandler(fh)

    return logger


# ------------- arXiv id parsing -------------
# New style: 0704.0001, 2101.12345, 2307.01234v2 (we'll strip vN)
NEW_ID_RE = re.compile(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", re.IGNORECASE)

# Old style: cs/0112017, hep-th/9901001v3 (strip vN)
OLD_ID_RE = re.compile(r"\b([a-z\-]+(?:\.[a-z\-]+)?\/\d{7})(?:v\d+)?\b", re.IGNORECASE)

# arXiv abs/pdf links: https://arxiv.org/abs/xxxx or .../pdf/xxxx.pdf
LINK_RE = re.compile(r"arxiv\.org/(abs|pdf)/([^\s\)]+)", re.IGNORECASE)


def normalize_arxiv_id(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"v\d+$", "", raw, flags=re.IGNORECASE)  # remove version suffix
    raw = raw.replace(".pdf", "")
    return raw


def extract_arxiv_ids_from_text(text: str) -> List[str]:
    ids: Set[str] = set()

    for m in NEW_ID_RE.finditer(text):
        ids.add(normalize_arxiv_id(m.group(1)))

    for m in OLD_ID_RE.finditer(text):
        ids.add(normalize_arxiv_id(m.group(1)))

    for m in LINK_RE.finditer(text):
        path = m.group(2)
        # path can be like 2401.01234v2 or cs/0112017v1.pdf
        path = path.split("?")[0].split("#")[0]
        path = path.replace(".pdf", "")
        # if path contains extra segments, keep last two for old style (cat/id) or last for new
        # examples:
        #   pdf/2401.01234v2 -> "2401.01234v2"
        #   abs/cs/0112017v1  -> "cs/0112017v1"
        path = path.strip("/")
        # If it's old style, it will contain "/"
        if "/" in path:
            # keep last two segments (e.g. "cs/0112017v1")
            segs = path.split("/")
            path = "/".join(segs[-2:])
        else:
            # new style: just last segment
            segs = path.split("/")
            path = segs[-1]
        ids.add(normalize_arxiv_id(path))

    return sorted(ids)


def extract_arxiv_ids_from_md(md_path: str) -> List[str]:
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    return extract_arxiv_ids_from_text(text)


# ------------- PDF validation -------------
def is_probably_pdf(path: str) -> bool:
    """
    Weak but practical integrity checks:
    - starts with %PDF-
    - contains %%EOF near the end (not guaranteed for all PDFs, but very common)
    """
    try:
        size = os.path.getsize(path)
        if size < 1024:  # too small to be real arXiv PDF
            return False

        with open(path, "rb") as f:
            head = f.read(5)
            if not head.startswith(b"%PDF-"):
                return False

            # read last 2KB (or whole file if smaller)
            tail_len = 2048
            if size > tail_len:
                f.seek(-tail_len, os.SEEK_END)
            else:
                f.seek(0)
            tail = f.read()
            return b"%%EOF" in tail
    except Exception:
        return False


@dataclass
class DownloadResult:
    arxiv_id: str
    ok: bool
    reason: str
    out_path: str


def build_pdf_url(arxiv_id: str) -> str:
    # arXiv accepts both new/old style IDs in this format
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def download_one_pdf(
    session: requests.Session,
    arxiv_id: str,
    out_path: str,
    logger: logging.Logger,
    retries: int = 5,
    timeout: int = 60,
) -> DownloadResult:
    urls = [
        f"https://arxiv.org/pdf/{arxiv_id}.pdf?download=1",
        f"https://export.arxiv.org/pdf/{arxiv_id}.pdf",
    ]
    tmp_path = out_path + ".part"

    backoff = 1.0
    last_reason = "unknown"

    for attempt in range(1, retries + 1):
        try:
            session.get(
                f"https://arxiv.org/abs/{arxiv_id}",
                headers={"Accept": "text/html", "Referer": "https://arxiv.org/"},
                timeout=timeout,
            )
            time.sleep(0.2)
            for url in urls:
                logger.debug("Downloading %s (attempt %d/%d): %s", arxiv_id, attempt, retries, url)
                r = session.get(
                    url,
                    headers={"Accept": "application/pdf", "Referer": "https://arxiv.org/"},
                    stream=True,
                    timeout=timeout,
                )
                status = r.status_code
                if status >= 400:
                    last_reason = f"HTTP {status}"
                    if status in (429, 500, 502, 503, 504):
                        raise requests.HTTPError(last_reason)
                    continue
                ct = (r.headers.get("Content-Type", "") or "").lower()
                if "pdf" not in ct:
                    last_reason = f"Non-PDF Content-Type: {ct}"
                    continue
                expected_len = r.headers.get("Content-Length")
                expected = int(expected_len) if expected_len and expected_len.isdigit() else None
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                written = 0
                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 14):
                        if not chunk:
                            continue
                        f.write(chunk)
                        written += len(chunk)
                if expected is not None and written != expected:
                    last_reason = f"Size mismatch expected={expected} written={written}"
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    continue
                if not is_probably_pdf(tmp_path):
                    last_reason = "PDF validation failed"
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    continue
                os.replace(tmp_path, out_path)
                return DownloadResult(arxiv_id, True, "ok", out_path)

        except Exception as e:
            last_reason = f"{type(e).__name__}: {e}"
            logger.warning("Failed %s: %s", arxiv_id, last_reason)

            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

            if attempt < retries:
                time.sleep(min(backoff, 20))
                backoff *= 2
            else:
                break

    return DownloadResult(arxiv_id, False, last_reason, out_path)


#
import argparse
import logging
import os
import re
import sys
from datetime import datetime

import requests

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config.config import (
    OUTPUT_DIR,
    ARXIV_JSON_DIR,
    LLM_SELECT_THEME_DIR,
    PAPER_THEME_FILTER_DIR,
    JSON_FILENAME_FMT,
    PDF_OUTPUT_DIR,
    USER_AGENT,
    MANIFEST_FILENAME,
)  # noqa: E402
from Controller.http_session import build_session


def setup_logging():
    logger = logging.getLogger("pdf_download")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def detect_latest_json(root_dir: str):
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(f"json dir not found: {root_dir}")
    files = [f for f in os.listdir(root_dir) if f.endswith(".json")]
    if not files:
        raise FileNotFoundError(f"No .json files found in {root_dir}")
    full = [os.path.join(root_dir, f) for f in files]
    full.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return full[0]


def resolve_json_path(args_json: Optional[str]) -> str:
    if args_json:
        return args_json

    today = datetime.now().strftime(JSON_FILENAME_FMT)
    for base_dir in [PAPER_THEME_FILTER_DIR, LLM_SELECT_THEME_DIR, ARXIV_JSON_DIR]:
        candidate = os.path.join(base_dir, today)
        if os.path.isfile(candidate):
            return candidate

    for base_dir in [PAPER_THEME_FILTER_DIR, LLM_SELECT_THEME_DIR, ARXIV_JSON_DIR]:
        try:
            return detect_latest_json(base_dir)
        except FileNotFoundError:
            continue

    raise FileNotFoundError(
        f"No json found in {PAPER_THEME_FILTER_DIR}, {LLM_SELECT_THEME_DIR} or {ARXIV_JSON_DIR}"
    )


def parse_arxiv_ids_from_json(json_path: str) -> List[str]:
    try:
        text = Path(json_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    try:
        obj = json.loads(text) if text.strip() else {}
    except Exception:
        return []
    items: List[Dict[str, Any]] = []
    if isinstance(obj, dict):
        if isinstance(obj.get("papers"), list):
            items = [x for x in obj.get("papers") if isinstance(x, dict)]
        elif isinstance(obj.get("items"), list):
            items = [x for x in obj.get("items") if isinstance(x, dict)]
    elif isinstance(obj, list):
        items = [x for x in obj if isinstance(x, dict)]

    ids: List[str] = []
    for it in items:
        arxiv_id = str(it.get("arxiv_id") or it.get("id") or "").strip()
        if not arxiv_id:
            src = str(it.get("source") or "")
            m = re.search(r"arxiv,?\s*([0-9]+\.[0-9]+)", src)
            if m:
                arxiv_id = m.group(1)
        if arxiv_id:
            ids.append(arxiv_id)
    return ids


def extract_date_str(path: str) -> str:
    m = re.search(r"\d{4}-\d{2}-\d{2}", os.path.basename(path))
    if m:
        return m.group(0)
    return datetime.now().strftime("%Y-%m-%d")


def download_pdf(session, arxiv_id, out_path, logger):
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf?download=1"
    logger.info("Download %s -> %s", arxiv_id, out_path)
    try:
        session.get(
            f"https://arxiv.org/abs/{arxiv_id}",
            headers={"Accept": "text/html", "Referer": "https://arxiv.org/"},
            timeout=60,
        )
        time.sleep(0.3)
    except Exception:
        pass
    r = session.get(
        url,
        headers={"Accept": "application/pdf", "Referer": "https://arxiv.org/"},
        stream=True,
        timeout=60,
    )
    r.raise_for_status()
    ct = r.headers.get("Content-Type", "").lower()
    if "pdf" not in ct:
        logger.error(
            "Non-PDF response for %s: Content-Type=%s (可能是 arXiv 的人机验证页面)，跳过写入。",
            arxiv_id,
            ct,
        )
        return False
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 14):
            if not chunk:
                continue
            f.write(chunk)
    return True


def run():
    logger = setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    json_path = resolve_json_path(args.json)

    logger.info("Use json list: %s", json_path)
    date_str = extract_date_str(json_path)
    print("============开始下载原始 PDF 列表==============", flush=True)

    arxiv_ids = parse_arxiv_ids_from_json(json_path)
    if args.limit is not None:
        arxiv_ids = arxiv_ids[: args.limit]

    total = len(arxiv_ids)
    logger.info("Total ids to download: %d", total)

    session = build_session()

    downloaded = 0
    skipped = 0
    invalid = 0

    results: List[DownloadResult] = []
    for i, aid in enumerate(arxiv_ids, 1):
        out_path = os.path.join(PDF_OUTPUT_DIR, date_str, f"{aid}.pdf")
        if os.path.exists(out_path):
            try:
                with open(out_path, "rb") as f:
                    head = f.read(5)
                if head.startswith(b"%PDF-"):
                    skipped += 1
                else:
                    logger.warning("Existing file is not valid PDF, will re-download: %s", out_path)
                    res = download_one_pdf(session, aid, out_path, logger, retries=5, timeout=60)
                    results.append(res)
                    if res.ok:
                        downloaded += 1
                    else:
                        invalid += 1
            except Exception as e:
                logger.error("Failed to inspect existing %s: %r", out_path, e)
                invalid += 1
        else:
            try:
                res = download_one_pdf(session, aid, out_path, logger, retries=5, timeout=60)
                results.append(res)
                if res.ok:
                    downloaded += 1
                else:
                    invalid += 1
            except Exception as e:
                logger.error("Failed to download %s: %r", aid, e)
                invalid += 1
        msg = f"Downloading:【{i}/{total}】"
        if sys.stdout.isatty():
            sys.stdout.write(msg + "\r")
            sys.stdout.flush()
        else:
            print(msg, flush=True)

        time.sleep(0.8)
    if sys.stdout.isatty():
        sys.stdout.write("\n")
        sys.stdout.flush()
    logger.info(
        "Done. downloaded=%d, skipped(valid)=%d, invalid(non-pdf)=%d, total=%d",
        downloaded,
        skipped,
        invalid,
        total,
    )
    manifest_items = [
        {"arxiv_id": r.arxiv_id, "ok": r.ok, "reason": r.reason, "pdf_path": r.out_path}
        for r in results
    ]
    manifest = {
        "date": date_str,
        "total": total,
        "downloaded": downloaded,
        "skipped": skipped,
        "invalid": invalid,
        "items": manifest_items,
    }
    manifest_path = os.path.join(PDF_OUTPUT_DIR, date_str, MANIFEST_FILENAME)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("Saved manifest: %s", manifest_path)
    print("============结束下载原始 PDF 列表==============", flush=True)


if __name__ == "__main__":
    run()
