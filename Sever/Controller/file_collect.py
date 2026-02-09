from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import DATA_ROOT, FILE_COLLECT_DIR  # noqa: E402


def today_str() -> str:
    return datetime.now().date().isoformat()


def select_date_dir(root: Path, date_str: str) -> Tuple[Path, str]:
    if date_str:
        return root / date_str, date_str
    today = today_str()
    candidate = root / today
    if candidate.is_dir():
        return candidate, today
    subdirs = []
    for d in root.iterdir():
        if d.is_dir():
            name = d.name
            if len(name) == 10 and name[4] == "-" and name[7] == "-":
                subdirs.append(d)
    if subdirs:
        subdirs.sort(key=lambda p: p.name)
        return subdirs[-1], subdirs[-1].name
    return root, today


def extract_arxiv_id(source: str) -> Optional[str]:
    if not source:
        return None
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", source)
    if not m:
        return None
    version = m.group(2) or ""
    return f"{m.group(1)}{version}"


def load_pdf_info_map(info_path: Path) -> Dict[str, Dict[str, Any]]:
    if not info_path.exists():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, list):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "") or "")
        arxiv_id = extract_arxiv_id(source)
        if not arxiv_id:
            continue
        out[arxiv_id] = item
    return out


def match_pdf_info(pdf_info_map: Dict[str, Dict[str, Any]], file_id: str) -> Optional[Dict[str, Any]]:
    if file_id in pdf_info_map:
        return pdf_info_map[file_id]
    if re.search(r"v\d+$", file_id):
        no_version = re.sub(r"v\d+$", "", file_id)
        return pdf_info_map.get(no_version)
    return None


def copy_if_exists(src: Path, dst: Path, missing: List[str]) -> None:
    if not src.exists():
        missing.append(str(src))
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def run() -> None:
    ap = argparse.ArgumentParser("file_collect")
    ap.add_argument("--date", default="", help="Date string in YYYY-MM-DD format. If not provided, uses today or latest available date.")
    args = ap.parse_args()

    # 确定日期
    date_str = args.date.strip() if args.date else today_str()
    if not date_str:
        date_str = today_str()
    
    # 从流程中的实际输出目录读取
    # 1. PDF 文件：从 selectedpaper 目录读取
    pdf_dir = Path(DATA_ROOT) / "selectedpaper" / date_str
    if not pdf_dir.exists():
        print(f"[FILE_COLLECT] selectedpaper dir not found: {pdf_dir}, skip", flush=True)
        return
    
    # 2. MD 文件：从 paper_summary 和 summary_limit 读取
    paper_summary_dir = Path(DATA_ROOT) / "paper_summary" / "single" / date_str
    summary_limit_dir = Path(DATA_ROOT) / "summary_limit" / "single" / date_str
    
    # 3. pdf_info.json：从 pdf_info 目录读取
    pdf_info_path = Path(DATA_ROOT) / "pdf_info" / f"{date_str}.json"
    pdf_info_map = load_pdf_info_map(pdf_info_path) if pdf_info_path.exists() else {}
    
    # 4. 图片文件：从 select_image 目录读取
    select_image_root = Path(DATA_ROOT) / "select_image"
    select_image_dir, _ = select_date_dir(select_image_root, date_str)

    # 输出根目录
    out_root = Path(FILE_COLLECT_DIR) / date_str
    out_root.mkdir(parents=True, exist_ok=True)

    # 查找所有 PDF 文件
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[FILE_COLLECT] no PDF files found in {pdf_dir}, skip", flush=True)
        return

    missing: List[str] = []
    processed = 0

    print(f"[FILE_COLLECT] date={date_str} total_pdfs={len(pdf_files)}", flush=True)

    for pdf_file in pdf_files:
        paper_id = pdf_file.stem
        
        # 创建输出目录
        paper_out_dir = out_root / paper_id
        paper_out_dir.mkdir(parents=True, exist_ok=True)

        # 1. 复制 PDF 文件
        pdf_dst = paper_out_dir / f"{paper_id}.pdf"
        copy_if_exists(pdf_file, pdf_dst, missing)
        if pdf_dst.exists():
            print(f"[FILE_COLLECT] copied PDF: {paper_id}.pdf", flush=True)

        # 2. 复制对应的 MD 文件
        # 2.1 从 paper_summary 复制，命名为 {paper_id}_summary.md
        summary_src = paper_summary_dir / f"{paper_id}.md"
        if summary_src.exists():
            summary_dst = paper_out_dir / f"{paper_id}_summary.md"
            copy_if_exists(summary_src, summary_dst, missing)
            if summary_dst.exists():
                print(f"[FILE_COLLECT] copied MD: {paper_id}_summary.md", flush=True)
        
        # 2.2 从 summary_limit 复制，命名为 {paper_id}_limit.md
        limit_src = summary_limit_dir / f"{paper_id}.md"
        if limit_src.exists():
            limit_dst = paper_out_dir / f"{paper_id}_limit.md"
            copy_if_exists(limit_src, limit_dst, missing)
            if limit_dst.exists():
                print(f"[FILE_COLLECT] copied MD: {paper_id}_limit.md", flush=True)

        # 3. 复制 pdf_info.json
        info = match_pdf_info(pdf_info_map, paper_id)
        if info:
            info_path = paper_out_dir / "pdf_info.json"
            info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[FILE_COLLECT] copied pdf_info.json: {paper_id}", flush=True)

        # 4. 复制对应的 PNG 文件（0X.png 格式）
        image_src_dir = select_image_dir / paper_id
        if image_src_dir.exists() and image_src_dir.is_dir():
            image_dst_dir = paper_out_dir / "image"
            image_dst_dir.mkdir(parents=True, exist_ok=True)
            
            # 匹配 0X.png 格式的文件（如 01.png, 02.png, ..., 09.png）
            png_pattern = re.compile(r"^0[0-9]\.png$")
            png_files = [f for f in image_src_dir.iterdir() if f.is_file() and png_pattern.match(f.name)]
            
            if png_files:
                for png_file in sorted(png_files):
                    png_dst = image_dst_dir / png_file.name
                    copy_if_exists(png_file, png_dst, missing)
                    if png_dst.exists():
                        print(f"[FILE_COLLECT] copied PNG: {paper_id}/image/{png_file.name}", flush=True)

        processed += 1

    print(f"[FILE_COLLECT] date={date_str} processed={processed} out_root={out_root}", flush=True)
    if missing:
        print(f"[FILE_COLLECT] missing={len(missing)}", flush=True)
        for item in missing:
            print(f"[FILE_COLLECT] missing: {item}", flush=True)


if __name__ == "__main__":
    run()
