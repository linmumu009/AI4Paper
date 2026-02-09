"""
Data service layer for reading paper data from the file system.

Primary data source: data/file_collect/{date}/{paper_id}/
  - {paper_id}_limit.md   → parsed into structured paper summary
  - pdf_info.json          → institution, is_large, abstract
  - image/*.png            → paper figure images

Secondary sources (for relevance scores):
  - data/llm_select_theme/{date}.json → theme_relevant_score
"""

import json
import os
import re
from collections import Counter
from typing import Any, Optional

# Resolve paths relative to the Sever/ directory
_SEVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_ROOT = os.path.join(_SEVER_ROOT, "data")
_DB_ROOT = os.path.join(_SEVER_ROOT, "database")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_json(path: str) -> Any:
    """Read and parse a JSON file. Returns None if file doesn't exist."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_text(path: str) -> Optional[str]:
    """Read a text file. Returns None if file doesn't exist."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_jsonl(path: str) -> list[dict]:
    """Read a JSONL file. Returns empty list if file doesn't exist."""
    if not os.path.isfile(path):
        return []
    results: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return results


# ---------------------------------------------------------------------------
# _limit.md parser
# ---------------------------------------------------------------------------

def _parse_limit_md(text: str, paper_id: str) -> dict:
    """
    Parse a _limit.md file into a structured dict.

    Expected format:
        机构：短标题
        📖标题：English Title
        🌐来源：arxiv, 2602.xxxxx

        🛎️文章简介
        🔸研究问题:...
        🔸主要贡献:...

        📝重点思路
        🔸...
        🔸...

        🔎分析总结
        🔸...
        🔸...

        💡个人观点
        ...
    """
    lines = text.strip().splitlines()
    if not lines:
        return {"paper_id": paper_id}

    result: dict[str, Any] = {"paper_id": paper_id}

    # --- Line 1: "机构：短标题" or "机构:短标题" ---
    headline = lines[0].strip()
    # Split on first : or ：
    m = re.split(r'[:：]', headline, maxsplit=1)
    if len(m) == 2:
        result["institution"] = m[0].strip()
        result["short_title"] = m[1].strip()
    else:
        result["short_title"] = headline

    # --- Remaining lines: extract fields ---
    result["📖标题"] = ""
    result["🌐来源"] = ""
    result["🛎️文章简介"] = {"🔸研究问题": "", "🔸主要贡献": ""}
    result["📝重点思路"] = []
    result["🔎分析总结"] = []
    result["💡个人观点"] = ""

    current_section = None  # which section we're in

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue

        # Field: 📖标题：...
        if stripped.startswith("📖标题"):
            val = re.split(r'[:：]', stripped, maxsplit=1)
            result["📖标题"] = val[1].strip() if len(val) > 1 else ""
            current_section = None
            continue

        # Field: 🌐来源：...
        if stripped.startswith("🌐来源"):
            val = re.split(r'[:：]', stripped, maxsplit=1)
            result["🌐来源"] = val[1].strip() if len(val) > 1 else ""
            current_section = None
            continue

        # Section headers
        if "🛎️文章简介" in stripped:
            current_section = "intro"
            continue
        if "📝重点思路" in stripped:
            current_section = "methods"
            continue
        if "🔎分析总结" in stripped:
            current_section = "findings"
            continue
        if "💡个人观点" in stripped:
            current_section = "opinion"
            continue

        # Section content
        if current_section == "intro":
            if "研究问题" in stripped:
                val = re.split(r'[:：]', stripped, maxsplit=1)
                result["🛎️文章简介"]["🔸研究问题"] = val[1].strip() if len(val) > 1 else stripped
            elif "主要贡献" in stripped:
                val = re.split(r'[:：]', stripped, maxsplit=1)
                result["🛎️文章简介"]["🔸主要贡献"] = val[1].strip() if len(val) > 1 else stripped

        elif current_section == "methods":
            result["📝重点思路"].append(stripped)

        elif current_section == "findings":
            result["🔎分析总结"].append(stripped)

        elif current_section == "opinion":
            # Opinion can be multi-line, concatenate
            if result["💡个人观点"]:
                result["💡个人观点"] += stripped
            else:
                result["💡个人观点"] = stripped

    return result


# ---------------------------------------------------------------------------
# file_collect directory reader
# ---------------------------------------------------------------------------

def _get_file_collect_dir(date: str) -> str:
    return os.path.join(_DATA_ROOT, "file_collect", date)


def _find_limit_md(paper_dir: str, paper_id: str) -> Optional[str]:
    """Find the _limit.md file in a paper directory."""
    # Try exact name first
    exact = os.path.join(paper_dir, f"{paper_id}_limit.md")
    if os.path.isfile(exact):
        return exact
    # Fallback: find any file with _limit in name
    if os.path.isdir(paper_dir):
        for f in os.listdir(paper_dir):
            if "_limit" in f and f.endswith(".md"):
                return os.path.join(paper_dir, f)
    return None


def _list_paper_images(paper_dir: str) -> list[str]:
    """List image filenames in a paper's image/ subdirectory."""
    img_dir = os.path.join(paper_dir, "image")
    if not os.path.isdir(img_dir):
        return []
    images = sorted([
        f for f in os.listdir(img_dir)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
    ])
    return images


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_dates() -> list[str]:
    """Return sorted list of dates that have file_collect data available."""
    fc_dir = os.path.join(_DATA_ROOT, "file_collect")
    if not os.path.isdir(fc_dir):
        return []
    dates = [
        d for d in os.listdir(fc_dir)
        if os.path.isdir(os.path.join(fc_dir, d))
        and len(d) == 10  # YYYY-MM-DD
    ]
    dates.sort(reverse=True)
    return dates


def get_papers_by_date(
    date: str,
    search: Optional[str] = None,
    institution: Optional[str] = None,
) -> list[dict]:
    """
    Get all papers for a given date from file_collect.
    Each paper is parsed from {paper_id}_limit.md + pdf_info.json.
    """
    fc_date_dir = _get_file_collect_dir(date)
    if not os.path.isdir(fc_date_dir):
        return []

    papers: list[dict] = []
    for paper_id in os.listdir(fc_date_dir):
        paper_dir = os.path.join(fc_date_dir, paper_id)
        if not os.path.isdir(paper_dir):
            continue

        # Find and parse _limit.md
        limit_path = _find_limit_md(paper_dir, paper_id)
        if limit_path is None:
            continue
        md_text = _read_text(limit_path)
        if md_text is None:
            continue

        data = _parse_limit_md(md_text, paper_id)

        # Merge pdf_info.json (institution, is_large, abstract)
        pdf_info = _read_json(os.path.join(paper_dir, "pdf_info.json"))
        if pdf_info:
            # pdf_info.json has the authoritative institution/is_large
            if pdf_info.get("instution"):
                data["institution"] = pdf_info["instution"]
            data["is_large_institution"] = pdf_info.get("is_large", False)
            data["abstract"] = pdf_info.get("abstract", "")

        # List images
        data["images"] = _list_paper_images(paper_dir)
        data["image_count"] = len(data["images"])

        papers.append(data)

    # Merge theme relevance scores
    theme_scores = _load_theme_scores(date)
    if theme_scores:
        for p in papers:
            pid = p.get("paper_id", "")
            p["relevance_score"] = theme_scores.get(pid)

    # Apply search filter
    if search:
        q = search.lower()
        papers = [
            p for p in papers
            if q in p.get("📖标题", "").lower()
            or q in p.get("short_title", "").lower()
            or q in p.get("paper_id", "").lower()
            or q in p.get("institution", "").lower()
        ]

    # Apply institution filter
    if institution:
        q = institution.lower()
        papers = [
            p for p in papers
            if q in p.get("institution", "").lower()
        ]

    return papers


def get_paper_detail(paper_id: str) -> Optional[dict]:
    """
    Get full detail for a single paper from file_collect.
    Searches across all dates.
    """
    fc_root = os.path.join(_DATA_ROOT, "file_collect")
    if not os.path.isdir(fc_root):
        return None

    # Search across dates (newest first)
    for date_dir in sorted(os.listdir(fc_root), reverse=True):
        paper_dir = os.path.join(fc_root, date_dir, paper_id)
        if not os.path.isdir(paper_dir):
            continue

        limit_path = _find_limit_md(paper_dir, paper_id)
        if limit_path is None:
            continue
        md_text = _read_text(limit_path)
        if md_text is None:
            continue

        data = _parse_limit_md(md_text, paper_id)

        # Merge pdf_info.json
        pdf_info = _read_json(os.path.join(paper_dir, "pdf_info.json"))
        if pdf_info:
            if pdf_info.get("instution"):
                data["institution"] = pdf_info["instution"]
            data["is_large_institution"] = pdf_info.get("is_large", False)
            data["abstract"] = pdf_info.get("abstract", "")

        # Images
        images = _list_paper_images(paper_dir)

        # Load paper_assets if available
        assets_data = _load_paper_assets(date_dir)
        paper_assets = assets_data.get(paper_id)

        # Merge theme score
        theme_scores = _load_theme_scores(date_dir)
        if theme_scores:
            data["relevance_score"] = theme_scores.get(paper_id)

        return {
            "summary": data,
            "paper_assets": paper_assets,
            "date": date_dir,
            "images": images,
            "arxiv_url": f"https://arxiv.org/abs/{paper_id}",
            "pdf_url": f"https://arxiv.org/pdf/{paper_id}",
        }

    return None


def get_daily_digest(date: str) -> dict:
    """
    Build a daily digest from file_collect data.
    """
    papers = get_papers_by_date(date)
    total = len(papers)

    # Institution distribution
    institutions = [p.get("institution", "未知") for p in papers]
    inst_counter = Counter(institutions)
    inst_distribution = [
        {"name": name, "count": count}
        for name, count in inst_counter.most_common()
    ]

    # Count large institution papers
    large_count = sum(
        1 for p in papers if p.get("is_large_institution", False)
    )

    # Average relevance score
    scores = [
        p["relevance_score"] for p in papers
        if p.get("relevance_score") is not None
    ]
    avg_score = sum(scores) / len(scores) if scores else None

    return {
        "date": date,
        "total_papers": total,
        "large_institution_count": large_count,
        "avg_relevance_score": round(avg_score, 3) if avg_score is not None else None,
        "institution_distribution": inst_distribution,
        "papers": papers,
    }


def get_pipeline_status(date: str) -> list[dict]:
    """Check which pipeline steps have completed for a given date."""
    step_outputs = {
        "arxiv_search": os.path.join(_DATA_ROOT, "arxivList", "md", f"{date}.md"),
        "paperList_remove_duplications": os.path.join(_DATA_ROOT, "paperList_remove_duplications", f"{date}.json"),
        "llm_select_theme": os.path.join(_DATA_ROOT, "llm_select_theme", f"{date}.json"),
        "paper_theme_filter": os.path.join(_DATA_ROOT, "paper_theme_filter", f"{date}.json"),
        "pdf_download": os.path.join(_DATA_ROOT, "raw_pdf", date, "_manifest.json"),
        "pdf_split": os.path.join(_DATA_ROOT, "preview_pdf", date, "_manifest.json"),
        "pdfsplite_to_minerU": os.path.join(_DATA_ROOT, "preview_pdf_to_mineru", date, "_manifest.json"),
        "pdf_info": os.path.join(_DATA_ROOT, "pdf_info", f"{date}.json"),
        "instutions_filter": os.path.join(_DATA_ROOT, "instutions_filter", date, f"{date}.json"),
        "selectpaper": os.path.join(_DATA_ROOT, "selectedpaper", date, "_manifest.json"),
        "selectedpaper_to_mineru": os.path.join(_DATA_ROOT, "selectedpaper_to_mineru", date, "_manifest.json"),
        "paper_summary": os.path.join(_DATA_ROOT, "paper_summary", "single", date),
        "summary_limit": os.path.join(_DATA_ROOT, "summary_limit", "single", date),
        "select_image": os.path.join(_DATA_ROOT, "select_image", date, f"select_image_{date}.json"),
        "file_collect": os.path.join(_DATA_ROOT, "file_collect", date),
        "paper_assets": os.path.join(_DATA_ROOT, "paper_assets", f"{date}.jsonl"),
    }

    steps_order = [
        "arxiv_search", "paperList_remove_duplications", "llm_select_theme",
        "paper_theme_filter", "pdf_download", "pdf_split",
        "pdfsplite_to_minerU", "pdf_info", "instutions_filter",
        "selectpaper", "selectedpaper_to_mineru", "paper_summary",
        "summary_limit", "select_image", "file_collect", "paper_assets",
    ]

    result = []
    for step in steps_order:
        path = step_outputs[step]
        done = os.path.isfile(path) or os.path.isdir(path)
        result.append({"step": step, "completed": done})
    return result


# ---------------------------------------------------------------------------
# Internal helpers for secondary data sources
# ---------------------------------------------------------------------------

def _load_theme_scores(date: str) -> dict[str, float]:
    """Load relevance scores from llm_select_theme JSON."""
    path = os.path.join(_DATA_ROOT, "llm_select_theme", f"{date}.json")
    data = _read_json(path)
    if data is None:
        return {}
    papers_list = []
    if isinstance(data, dict):
        papers_list = data.get("papers", [])
    elif isinstance(data, list):
        papers_list = data

    scores: dict[str, float] = {}
    for item in papers_list:
        if not isinstance(item, dict):
            continue
        pid = item.get("arxiv_id", item.get("source", ""))
        score = item.get("theme_relevant_score", item.get("score"))
        if pid and score is not None:
            try:
                scores[pid] = float(score)
            except (ValueError, TypeError):
                pass
    return scores


def _load_paper_assets(date: str) -> dict[str, dict]:
    """Load paper assets JSONL, indexed by paper_id."""
    path = os.path.join(_DATA_ROOT, "paper_assets", f"{date}.jsonl")
    items = _read_jsonl(path)
    result = {}
    for item in items:
        pid = item.get("paper_id", "")
        if pid:
            result[pid] = item
    return result
