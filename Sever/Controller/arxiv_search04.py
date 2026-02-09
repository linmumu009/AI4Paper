#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
import json
import re
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, date, time as dtime, timedelta, timezone
from typing import List, Optional, Tuple

import requests
import feedparser
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
from config.config import (
    API_URL,
    SEARCH_CATEGORIES,
    REQUESTS_UA,
    OUTPUT_DIR,
    ARXIV_JSON_DIR,
    FILENAME_FMT,
    JSON_FILENAME_FMT,
    PAGE_SIZE_DEFAULT,
    MAX_PAPERS_DEFAULT,
    SLEEP_DEFAULT,
    USE_PROXY_DEFAULT,
    RETRY_COUNT,
    PROGRESS_SINGLE_LINE,
)
from Controller.http_session import build_session

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:
    ZoneInfo = None

ARXIV_API = API_URL


def setup_logging():
    logger = logging.getLogger("arxiv")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("[%(levelname)s] %(message)s")

    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    project_root = os.path.dirname(os.path.dirname(__file__))
    log_root = os.path.join(project_root, "logs")
    date_dir = datetime.now().strftime("%Y-%m-%d")
    log_dir = os.path.join(log_root, date_dir)
    os.makedirs(log_dir, exist_ok=True)
    start_name = datetime.now().strftime("%H%M%S") + ".log"
    fh = logging.FileHandler(os.path.join(log_dir, start_name), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s " + fmt._fmt))
    logger.addHandler(fh)

    return logger


def arxiv_id_from_entry_url(entry_id_url: str) -> str:
    m = re.search(r"/abs/([^v]+)(v\d+)?$", entry_id_url)
    return m.group(1) if m else entry_id_url


def entry_published_utc_dt(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        dt_utc = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    else:
        dt_utc = datetime.fromisoformat(entry.published.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(timezone.utc)


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse_entry_authors(entry) -> List[str]:
    authors = []
    for a in getattr(entry, "authors", None) or []:
        # feedparser 里 a 可能是 dict / FeedParserDict / 对象，兼容取法
        name = ""
        if isinstance(a, dict):
            name = a.get("name", "")
        else:
            name = (
                getattr(a, "name", "")
                or (getattr(a, "get", None) and a.get("name"))
                or ""
            )
        name = normalize_text(name)
        if name:
            authors.append(name)
    return authors


def parse_entry_summary(entry) -> str:
    return normalize_text(
        getattr(entry, "summary", "") or getattr(entry, "description", "")
    )


def _parse_utc_datetime(s: str, *, is_end: bool) -> datetime:
    s = s.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if is_end:
            dt = dt + timedelta(days=1)
        return dt

    iso = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def local_midnight_as_utc(anchor_tz: str, anchor_date: date) -> datetime:
    if ZoneInfo is None:
        raise RuntimeError("zoneinfo not available; cannot convert local midnight to UTC.")
    tz = ZoneInfo(anchor_tz)
    dt_local = datetime.combine(anchor_date, dtime(0, 0), tzinfo=tz)
    return dt_local.astimezone(timezone.utc)


def compute_window_by_midnight_anchor(
    *,
    anchor_tz: str,
    days: int,
    anchor_date_str: Optional[str],
) -> Tuple[datetime, datetime]:
    if days <= 0:
        raise ValueError("days must be positive")
    if ZoneInfo is None:
        raise RuntimeError("zoneinfo not available; cannot compute anchor-based window.")

    tz = ZoneInfo(anchor_tz)
    if anchor_date_str:
        anchor_date = date.fromisoformat(anchor_date_str)
    else:
        anchor_date = datetime.now(tz).date()

    end_utc = local_midnight_as_utc(anchor_tz, anchor_date)
    start_utc = end_utc - timedelta(days=days)
    return start_utc, end_utc


def _floor_to_minute(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    return dt.replace(second=0, microsecond=0)


def _ceil_to_minute(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    if dt.second == 0 and dt.microsecond == 0:
        return dt
    dt = dt + timedelta(minutes=1)
    return dt.replace(second=0, microsecond=0)


def _to_arxiv_minute_str(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y%m%d%H%M")


def build_submitted_date_clause(start_utc: datetime, end_utc: datetime) -> str:
    start_s = _to_arxiv_minute_str(_floor_to_minute(start_utc))
    end_s = _to_arxiv_minute_str(_ceil_to_minute(end_utc))
    return f"submittedDate:[{start_s} TO {end_s}]"


_ARXIV_FIELD_PREFIX_RE = re.compile(
    r"\b(?:ti|au|abs|co|jr|cat|rn|all|id|submittedDate|lastUpdatedDate)\s*:",
    re.IGNORECASE,
)
_ARXIV_BOOL_OR_GROUP_RE = re.compile(r"\b(?:AND|OR|ANDNOT)\b|[()\[\]]", re.IGNORECASE)


def is_advanced_arxiv_query(q: str) -> bool:
    q = (q or "").strip()
    if not q:
        return False
    return bool(_ARXIV_FIELD_PREFIX_RE.search(q) or _ARXIV_BOOL_OR_GROUP_RE.search(q))


def semantic_query_to_all_clause(q: str) -> str:
    q = (q or "").strip()
    if not q:
        return ""

    tokens: List[Tuple[str, bool]] = []
    for m in re.finditer(r'"([^"]+)"|(\S+)', q):
        if m.group(1) is not None:
            tokens.append((m.group(1), True))
        else:
            tokens.append((m.group(2), False))

    cleaned: List[Tuple[str, bool]] = []
    for t, is_phrase in tokens:
        t = t.strip()
        if t:
            cleaned.append((t, is_phrase))

    if not cleaned:
        return ""

    parts: List[str] = []
    for t, is_phrase in cleaned:
        if is_phrase:
            parts.append(f'all:"{t}"')
        else:
            parts.append(f"all:{t}")

    return " AND ".join(parts)


def build_text_clause(user_query: str) -> str:
    user_query = (user_query or "").strip()
    if not user_query:
        return ""
    if is_advanced_arxiv_query(user_query):
        return user_query
    return semantic_query_to_all_clause(user_query)


def build_category_clause(categories: List[str]) -> str:
    cats = [c.strip() for c in (categories or []) if c.strip()]
    if not cats:
        return ""
    inner = " OR ".join([f"cat:{c}" for c in cats])
    return f"({inner})"


def build_search_query(
    *,
    categories: List[str],
    user_query: str,
    start_utc: datetime,
    end_utc: datetime,
) -> str:
    clauses: List[str] = []
    cat_clause = build_category_clause(categories)
    if cat_clause:
        clauses.append(cat_clause)
    text_clause = build_text_clause(user_query)
    if text_clause:
        clauses.append(f"({text_clause})")
    date_clause = build_submitted_date_clause(start_utc, end_utc)
    clauses.append(date_clause)
    return " AND ".join(clauses)


def fetch_page_with_retry(session: requests.Session, params: dict, logger, retries: int = 5):
    backoff = 1.0
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            r = session.get(ARXIV_API, params=params, timeout=60)
            r.raise_for_status()
            return feedparser.parse(r.text)
        except Exception as e:
            last_exc = e
            logger.warning("Request failed (attempt %d/%d): %s", attempt, retries, repr(e))
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
    raise last_exc


@dataclass
class Paper:
    title: str
    published_utc: datetime
    arxiv_id: str
    link: str
    authors: List[str]
    summary: str


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", "-q", default="", help="自然语言 or 高级表达式（ti:/abs:/AND/...）。自然语言将按 all: 逐词 AND 处理。")
    ap.add_argument("--categories", "-c", default=",".join(SEARCH_CATEGORIES), help="逗号分隔的分类，如 cs.AI,cs.LG")
    ap.add_argument("--start", required=False, default="", help="UTC 起始：YYYY-MM-DD 或 ISO8601（如 2026-01-19T00:00:00Z）")
    ap.add_argument("--end", required=False, default="", help="UTC 结束（右开）：YYYY-MM-DD 或 ISO8601。若是 YYYY-MM-DD，则解释为“包含该日”，自动+1天")
    ap.add_argument("--anchor-tz", default="Asia/Shanghai", help="锚定时区：以该时区的当天 00:00 换算为 UTC 作为 end")
    ap.add_argument("--days", type=int, default=1, help="当未提供 start/end 时，从锚定 00:00 往前推 days 天")
    ap.add_argument("--anchor-date", default="", help="锚定日期 YYYY-MM-DD（按 anchor-tz 的这天 00:00 作为 end）；为空则用 anchor-tz 的今天")
    ap.add_argument("--last-hours", type=float, default=None, help="可选：当未提供 start/end 时，用 now_utc - last_hours 到 now_utc（与锚定 00:00 互斥）")
    ap.add_argument("--page-size", type=int, default=PAGE_SIZE_DEFAULT, help="每页数量（<=2000）")
    ap.add_argument("--max-papers", type=int, default=MAX_PAPERS_DEFAULT, help="最多返回多少篇")
    ap.add_argument("--sleep", type=float, default=SLEEP_DEFAULT, help="分页间隔秒数（建议 >=3，尊重 arXiv）")
    ap.add_argument("--retries", type=int, default=RETRY_COUNT, help="请求失败重试次数（指数退避）")
    ap.add_argument("--no-single-line-progress", action="store_true", help="禁用单行进度显示")
    ap.add_argument("--user-agent", default=REQUESTS_UA, help="User-Agent（建议改成你自己的标识）")
    ap.add_argument("--use-proxy", action="store_true", default=USE_PROXY_DEFAULT, help="是否允许读取环境变量代理")
    ap.add_argument("--out", default="", help="输出 markdown 文件路径；为空则写入 data/arxivList/md")
    ap.add_argument("--out-json", default="", help="输出 json 文件路径；为空则写入 data/arxivList/json")
    return ap.parse_args()


def run():
    print("START arxiv_search.py", flush=True)
    logger = setup_logging()
    args = parse_args()

    used_anchor_window = False
    anchor_date_for_name: Optional[date] = None

    if args.start.strip() and args.end.strip():
        start_utc = _parse_utc_datetime(args.start, is_end=False)
        end_utc = _parse_utc_datetime(args.end, is_end=True)
    else:
        if args.last_hours is not None:
            end_utc = datetime.now(timezone.utc)
            start_utc = end_utc - timedelta(hours=float(args.last_hours))
        else:
            used_anchor_window = True
            if ZoneInfo is not None:
                tz = ZoneInfo(str(args.anchor_tz))
                if args.anchor_date.strip():
                    anchor_date_for_name = date.fromisoformat(args.anchor_date.strip())
                else:
                    anchor_date_for_name = datetime.now(tz).date()
            start_utc, end_utc = compute_window_by_midnight_anchor(
                anchor_tz=str(args.anchor_tz),
                days=int(args.days),
                anchor_date_str=(args.anchor_date.strip() or None),
            )

    if end_utc <= start_utc:
        raise SystemExit(f"end must be greater than start (start={start_utc.isoformat()} end={end_utc.isoformat()})")

    categories = [c.strip() for c in (args.categories or "").split(",") if c.strip()]
    search_query = build_search_query(
        categories=categories,
        user_query=args.query,
        start_utc=start_utc,
        end_utc=end_utc,
    )

    logger.info("Timezone: %s", "UTC")
    logger.info(
        "Window  : %s -> %s",
        start_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        end_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    session = build_session(prefer_env_proxy=bool(args.use_proxy))
    if args.user_agent:
        session.headers.update({"User-Agent": str(args.user_agent)})
    logger.info("Proxy from env enabled: %s", bool(args.use_proxy))

    results: List[Paper] = []
    start_idx = 0
    page_size = max(1, min(args.page_size, 2000))
    candidates = 0
    pages = 0
    print("============开始获取初始可下载列表==============", flush=True)

    while len(results) < args.max_papers:
        pages += 1
        msg = f"[INFO] Fetch page 【{pages}】 (start={start_idx}, max_results={page_size}) ..."
        single_line = PROGRESS_SINGLE_LINE and (not bool(args.no_single_line_progress)) and sys.stdout.isatty()
        if single_line:
            sys.stdout.write(msg + "\r")
            sys.stdout.flush()
        else:
            print(msg, flush=True)

        params = {
            "search_query": search_query,
            "start": start_idx,
            "max_results": page_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        feed = fetch_page_with_retry(session, params, logger, retries=int(args.retries))

        if not feed.entries:
            logger.info("No entries returned; stopping.")
            break

        for entry in feed.entries:
            pub_utc = entry_published_utc_dt(entry)
            if start_utc <= pub_utc < end_utc:
                candidates += 1

                title = normalize_text(getattr(entry, "title", ""))
                summary = parse_entry_summary(entry)
                authors = parse_entry_authors(entry)

                arxiv_id = arxiv_id_from_entry_url(entry.id)
                link = f"https://arxiv.org/abs/{arxiv_id}"

                results.append(
                    Paper(
                        title=title,
                        published_utc=pub_utc,
                        arxiv_id=arxiv_id,
                        link=link,
                        authors=authors,
                        summary=summary,
                    )
                )

                if len(results) >= args.max_papers:
                    break

        start_idx += page_size
        time.sleep(args.sleep)

    print()
    print("============结束获取初始可下载列表==============", flush=True)
    results.sort(key=lambda p: p.published_utc, reverse=True)

    out_path = args.out.strip()
    if not out_path:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        if used_anchor_window and anchor_date_for_name is not None:
            out_filename = anchor_date_for_name.strftime(FILENAME_FMT)
        else:
            out_filename = datetime.now(timezone.utc).strftime(FILENAME_FMT)
        out_path = os.path.join(OUTPUT_DIR, out_filename)

    out_json_path = args.out_json.strip()
    if not out_json_path:
        if args.out.strip():
            out_json_path = os.path.splitext(out_path)[0] + ".json"
        else:
            os.makedirs(ARXIV_JSON_DIR, exist_ok=True)
            if used_anchor_window and anchor_date_for_name is not None:
                out_json_name = anchor_date_for_name.strftime(JSON_FILENAME_FMT)
            else:
                out_json_name = datetime.now(timezone.utc).strftime(JSON_FILENAME_FMT)
            out_json_path = os.path.join(ARXIV_JSON_DIR, out_json_name)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# arXiv daily papers\n\n")
        f.write("- Timezone: `UTC`\n")
        f.write(
            f"- Window: **{start_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}** to **{end_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}**\n"
        )
        f.write(f"- Candidates in window: **{candidates}**\n")
        f.write(f"- Selected: **{len(results)}**\n")
        f.write(f"- search_query: `{search_query}`\n\n")

        if not results:
            f.write("_No matching papers found in this window._\n")
        else:
            for i, p in enumerate(results, 1):
                pub_str = p.published_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
                f.write(f"{i}. **{p.title}**  \n")
                f.write(f"   - Published: `{pub_str}`  \n")
                f.write(f"   - arXiv: [{p.arxiv_id}]({p.link})  \n")

                if p.authors:
                    f.write(f"   - Authors: {', '.join(p.authors)}  \n")
                else:
                    f.write("   - Authors: _N/A_  \n")

                if p.summary:
                    f.write("   - Abstract:\n")
                    f.write("     <details><summary>Show</summary>\n\n")
                    f.write(f"     {p.summary}\n\n")
                    f.write("     </details>\n\n")
                else:
                    f.write("   - Abstract: _N/A_\n\n")

    os.makedirs(os.path.dirname(out_json_path) or ".", exist_ok=True)
    json_payload = {
        "timezone": "UTC",
        "window_start_utc": start_utc.isoformat(),
        "window_end_utc": end_utc.isoformat(),
        "candidates_in_window": candidates,
        "selected": len(results),
        "search_query": search_query,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "papers": [
            {
                "title": p.title,
                "published_utc": p.published_utc.isoformat(),
                "arxiv_id": p.arxiv_id,
                "link": p.link,
                "authors": p.authors,
                "summary": p.summary,
            }
            for p in results
        ],
    }
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(json_payload, f, ensure_ascii=False, indent=2)

    logger.info("Candidates in window: %d", candidates)
    logger.info("Selected papers     : %d", len(results))
    logger.info("Saved markdown to   : %s", out_path)
    logger.info("Saved json to       : %s", out_json_path)
    print("END arxiv_search.py", flush=True)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("FATAL ERROR:\n" + traceback.format_exc(), flush=True)
        raise
