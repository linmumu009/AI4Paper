from __future__ import annotations

import argparse
import html
import json
import os
import re
import textwrap
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import DATA_ROOT  # noqa: E402


@dataclass
class RenderConfig:
    dpi: int = 220
    save_cover: bool = True
    layout_engine: str = "pil"  # "pil" | "html" (Chromium) | "reportlab" (deterministic PDF)
    caption_font_size: int = 60  # 默认字体大小
    caption_max_lines: int = 3
    caption_bar_padding: int = 10
    caption_bg: tuple[int, int, int] = (245, 245, 245)
    caption_color: tuple[int, int, int] = (0, 0, 0)
    caption_font_path: str = ""
    masonry_columns: int = 2
    masonry_padding_ratio: float = 0.03  # 页面边距 3% (保持不变)
    masonry_gutter_ratio: float = 0.15   # 图片间距 15% (3倍间距，图片会相应缩小)
    masonry_target_fill: float = 0.96
    masonry_scale_max: float = 1.25
    tiles_per_page: int = 3
    wide_ratio: float = 1.3
    nonwhite_min_ratio: float = 0.02
    edge_density_max: float = 0.22
    textlike_edge_max: float = 0.18
    remove_embedded_caption: bool = True
    caption_strip_ratio: float = 0.0  # 默认不盲目裁剪，只在有明确bbox时裁剪
    caption_strip_max_ratio: float = 0.45
    caption_strip_min_px: int = 0  # 默认不盲目裁剪
    caption_image_spacing: int = 0  # 设为0表示使用与图片间距相同的gutter比例
    image_padding_ratio: float = 0.05  # 给图片加白边，防止边缘内容被裁剪（5%）
    results_only: bool = True
    heading_positive: list[str] = field(
        default_factory=lambda: [
            "results",
            "experiments",
            "evaluation",
            "ablation",
            "analysis",
            "benchmark",
        ]
    )
    heading_negative: list[str] = field(
        default_factory=lambda: [
            "method",
            "approach",
            "architecture",
            "model",
        ]
    )
    caption_positive: list[str] = field(
        default_factory=lambda: [
            "result",
            "experiment",
            "ablation",
            "evaluation",
            "performance",
            "accuracy",
            "roc",
            "ece",
            "benchmark",
        ]
    )
    caption_negative: list[str] = field(default_factory=list)


def today_str() -> str:
    return datetime.now().date().isoformat()


def select_date_dir(root: Path, date_str: str) -> tuple[Path, str]:
    if date_str:
        return root / date_str, date_str
    today = today_str()
    candidate = root / today
    if candidate.is_dir():
        return candidate, today
    subdirs = [d for d in root.iterdir() if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)]
    if subdirs:
        subdirs.sort(key=lambda p: p.name)
        return subdirs[-1], subdirs[-1].name
    return root, today


def list_paper_dirs(root: Path) -> list[Path]:
    return sorted([p for p in root.iterdir() if p.is_dir()])


def find_md_path(paper_dir: Path, stem: str) -> Path | None:
    direct = paper_dir / f"{stem}.md"
    if direct.exists():
        return direct
    full_md = paper_dir / "full.md"
    if full_md.exists():
        return full_md
    md_files = sorted(paper_dir.glob("*.md"))
    return md_files[0] if md_files else None


def parse_md_images(md_path: Path) -> list[dict[str, str]]:
    image_re = re.compile(r"!\[.*?\]\((.*?)\)")
    caption_re = re.compile(r"(figure|fig\.?|图)\s*\d+", re.IGNORECASE)
    heading_re = re.compile(r"^#+\s+")

    entries: list[dict[str, str]] = []
    pending: list[int] = []
    heading = ""
    lines = md_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line in lines:
        raw = line.strip()
        if heading_re.match(raw):
            heading = heading_re.sub("", raw).strip()
        m = image_re.search(raw)
        if m:
            rel = m.group(1).strip()
            idx = len(entries)
            entries.append({"image_rel": rel, "heading": heading, "caption": ""})
            pending.append(idx)
            continue
        if caption_re.search(raw):
            if pending:
                # 对 caption 进行纯化验证
                purified_caption, is_valid = purify_caption(raw)
                caption_text = purified_caption if is_valid else raw  # 如果纯化失败，保留原始文本（可能是 md 格式不同）
                for idx in pending:
                    entries[idx]["caption"] = caption_text
                pending = []
    return entries


def parse_content_items(content_path: Path) -> tuple[list[dict], list[dict]]:
    """
    解析 mineru 的 content_list.json。
    返回: (figures, captions)
    - figures: 包含 page_idx, bbox, img_path, image_caption
    - captions: 包含 page_idx, bbox, text（从 image_caption 提取）
    """
    try:
        data = json.loads(content_path.read_text(encoding="utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return [], []
    if not isinstance(data, list):
        return [], []
    figures: list[dict] = []
    captions: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").lower()
        bbox = item.get("bbox")
        page_idx = int(item.get("page_idx", 0) or 0)
        if not (isinstance(bbox, list) and len(bbox) == 4):
            continue
        # 修复：使用 type == "image" 而不是 type == "figure"
        if item_type == "image":
            img_path = str(item.get("img_path", "") or "").strip()
            image_caption = item.get("image_caption", [])
            # 从 image_caption 数组中提取 caption（取第一个非空元素）
            caption_text = ""
            if isinstance(image_caption, list) and len(image_caption) > 0:
                for cap in image_caption:
                    if isinstance(cap, str) and cap.strip():
                        caption_text = cap.strip()
                        break
            
            # 保存 figure 信息，包括 img_path 和 image_caption
            figure_data = {
                "page_idx": page_idx,
                "bbox": bbox,
                "img_path": img_path,
                "image_caption": image_caption,  # 保存原始数组
                "has_caption": bool(caption_text),  # 标记是否有 caption
            }
            figures.append(figure_data)
            
            # 如果有 caption，也添加到 captions 列表（用于后续匹配）
            if caption_text:
                captions.append({
                    "page_idx": page_idx,
                    "bbox": bbox,
                    "text": caption_text,
                    "img_path": img_path,  # 保存关联的 img_path
                })
    figures.sort(key=lambda x: (x["page_idx"], x["bbox"][1], x["bbox"][0]))
    captions.sort(key=lambda x: (x["page_idx"], x["bbox"][1], x["bbox"][0]))
    return figures, captions


def _horizontal_overlap(a: list[float], b: list[float]) -> float:
    ax0, _, ax1, _ = a
    bx0, _, bx1, _ = b
    inter = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    denom = max(1.0, min(ax1 - ax0, bx1 - bx0))
    return inter / denom


def match_figures_to_captions(figures: list[dict], captions: list[dict]) -> dict[int, dict]:
    matched: dict[int, dict] = {}
    for i, fig in enumerate(figures):
        fpage = fig["page_idx"]
        fbbox = fig["bbox"]
        best = None
        best_score = None
        for cap in captions:
            if cap["page_idx"] != fpage:
                continue
            cbbox = cap["bbox"]
            if cbbox[1] < fbbox[3]:
                continue
            overlap = _horizontal_overlap(fbbox, cbbox)
            if overlap < 0.2:
                continue
            dist = cbbox[1] - fbbox[3]
            score = dist - overlap * 10.0
            if best_score is None or score < best_score:
                best = cap
                best_score = score
        if best:
            matched[i] = best
    return matched


def assign_missing_captions(entries: list[dict[str, str]], fallback_captions: list[str]) -> None:
    idx = 0
    for entry in entries:
        if entry["caption"]:
            continue
        if idx < len(fallback_captions):
            entry["caption"] = fallback_captions[idx]
            idx += 1


def group_figures_by_proximity(entries: list[dict], figures: list[dict], captions: list[dict]) -> list[dict]:
    """
    将属于同一个 Figure 的多个子图分组。
    
    分组策略（优先级从高到低）：
    1. 强绑定：从 caption 文本中提取 figure 编号，相同编号的归为一组
    2. 次强绑定：同一页内，如果某个 image 的 image_caption 为空，查找附近有 caption 的 image
    3. 弱绑定：同一页内，bbox 垂直/水平相邻、宽度/高度相近，且其中一个有 caption，另一个没有
    
    返回：分组后的 figure groups 列表
    """
    if not entries:
        return []
    
    # 先匹配 figures 到 captions
    matched = match_figures_to_captions(figures, captions) if figures and captions else {}
    
    # 构建 img_path -> figure 的映射（用于匹配 entries 和 figures）
    figure_by_path: dict[str, dict] = {}
    for i, fig in enumerate(figures):
        img_path = fig.get("img_path", "")
        if img_path:
            normalized_path = _normalize_path(img_path)
            if normalized_path:
                figure_by_path[normalized_path] = fig
                fig["_index"] = i
    
    # 为每个 entry 关联 figure 信息（基于 img_path 匹配）
    entry_figures: list[dict] = []
    for i, entry in enumerate(entries):
        raw_caption = entry.get("caption", "").strip()
        if raw_caption:
            purified_caption, is_valid = purify_caption(raw_caption)
        else:
            purified_caption, is_valid = ("", False)
        entry_fig = {
            "entry": entry,
            "entry_idx": i,
            "figure_idx": None,
            "figure_bbox": entry.get("figure_bbox"),
            "page_idx": entry.get("figure_page_idx"),
            "caption": purified_caption,
            "caption_bbox": entry.get("caption_bbox"),
            "caption_valid": is_valid,
            "figure_number": None,
            "img_path": entry.get("img_path", ""),  # 保存 img_path
            "has_caption": is_valid,  # 标记是否有可信 caption
        }
        
        # 通过 img_path 匹配到 figures
        entry_image_rel = entry.get("image_rel", "")
        if entry_image_rel:
            normalized_entry_path = _normalize_path(entry_image_rel)
            matched_figure = None
            for fig_path, fig in figure_by_path.items():
                if normalized_entry_path == fig_path:
                    matched_figure = fig
                    break
                # 文件名匹配
                entry_filename = Path(entry_image_rel).name
                fig_filename = Path(fig_path).name
                if entry_filename and fig_filename and entry_filename == fig_filename:
                    matched_figure = fig
                    break
            
            if matched_figure:
                entry_fig["figure_idx"] = matched_figure.get("_index")
                entry_fig["figure_bbox"] = matched_figure["bbox"]
                entry_fig["page_idx"] = matched_figure["page_idx"]
                entry_fig["img_path"] = matched_figure.get("img_path", "")
                
                # 如果 entry 还没有可信 caption，尝试从 figure 的 image_caption 获取
                if not entry_fig["caption_valid"]:
                    image_caption = matched_figure.get("image_caption", [])
                    if isinstance(image_caption, list) and len(image_caption) > 0:
                        for cap in image_caption:
                            if isinstance(cap, str) and cap.strip():
                                purified_caption, is_valid = purify_caption(cap.strip())
                                if is_valid:
                                    entry_fig["caption"] = purified_caption
                                    entry_fig["has_caption"] = True
                                    entry_fig["caption_valid"] = True
                                    # image_caption 没有独立 bbox，用 figure_bbox 兜底
                                    entry_fig["caption_bbox"] = matched_figure.get("bbox")
                                    break
                
                # 如果匹配到 caption，使用匹配的 caption
                fig_index = matched_figure.get("_index")
                if fig_index is not None and fig_index in matched:
                    raw_cap = matched[fig_index]["text"]
                    purified_caption, is_valid = purify_caption(str(raw_cap))
                    if is_valid:
                        # 只有当已有 caption 不可信，或 figure 编号一致时才覆盖
                        if (not entry_fig["caption_valid"]) or (
                            extract_figure_number(entry_fig.get("caption", "")) == extract_figure_number(purified_caption)
                        ):
                            entry_fig["caption"] = purified_caption
                            entry_fig["caption_bbox"] = matched[fig_index]["bbox"]
                            entry_fig["has_caption"] = True
                            entry_fig["caption_valid"] = True
        
        # 提取 figure 编号（用于强绑定分组）
        caption_text = entry_fig.get("caption", "")
        if caption_text and entry_fig.get("caption_valid"):
            entry_fig["figure_number"] = extract_figure_number(str(caption_text))
        
        entry_figures.append(entry_fig)
    
    # Stage 0: 传播 figure_number（处理 caption 出现在图组中间的情况）
    # 在同页内，按阅读顺序把紧邻的无编号图吸附到最近的 figure_number
    by_page_all: dict[int, list[dict]] = {}
    for entry_fig in entry_figures:
        page = entry_fig.get("page_idx", 0) or 0
        by_page_all.setdefault(page, []).append(entry_fig)

    for page, page_entries in by_page_all.items():
        page_entries.sort(key=lambda e: e.get("figure_bbox", [0, 0, 0, 0])[1] if e.get("figure_bbox") else 0)
        # 估算页面高度，用于距离阈值
        page_max_y = 0.0
        for e in page_entries:
            bbox = e.get("figure_bbox")
            if isinstance(bbox, list) and len(bbox) == 4:
                page_max_y = max(page_max_y, float(bbox[3]))
        page_height = page_max_y if page_max_y > 0 else 1000.0
        max_vert_gap = page_height * 0.18
        min_horiz_overlap = 0.18
        last_number = None
        last_bbox = None
        for e in page_entries:
            bbox = e.get("figure_bbox")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                continue
            if e.get("figure_number") is not None:
                last_number = e.get("figure_number")
                last_bbox = bbox
                continue
            # 仅对无编号且无可信 caption 的图做吸附
            if e.get("caption_valid"):
                last_number = None
                last_bbox = None
                continue
            if last_number is not None and last_bbox is not None:
                vert_dist = _vertical_distance(last_bbox, bbox)
                overlap = _horizontal_overlap(last_bbox, bbox)
                if 0 <= vert_dist <= max_vert_gap and overlap >= min_horiz_overlap:
                    e["figure_number"] = last_number

    # Stage 1: 强绑定分组 - 按 (page, figure_number) 分组
    groups_by_number: dict[tuple[int, int], list[dict]] = {}
    ungrouped: list[dict] = []
    
    for entry_fig in entry_figures:
        if entry_fig["figure_number"] is not None:
            num = entry_fig["figure_number"]
            page = entry_fig.get("page_idx", 0) or 0
            key = (int(page), int(num))
            if key not in groups_by_number:
                groups_by_number[key] = []
            groups_by_number[key].append(entry_fig)
        else:
            ungrouped.append(entry_fig)
    
    # Stage 2: 次强绑定分组 - 处理 image_caption 为空的子图
    # 同一页内，如果某个 image 的 image_caption 为空，查找附近有 caption 的 image
    # 按页面分组处理
    by_page: dict[int, list[dict]] = {}
    for entry_fig in ungrouped:
        page = entry_fig.get("page_idx", 0)
        if page not in by_page:
            by_page[page] = []
        by_page[page].append(entry_fig)
    
    # 对每页内的 entry 进行分组
    for page, page_entries in by_page.items():
        if len(page_entries) <= 1:
            continue
        
        # 按 y 坐标排序（从上到下）
        page_entries.sort(key=lambda e: e.get("figure_bbox", [0, 0, 0, 0])[1] if e.get("figure_bbox") else 0)
        
        # 次强绑定：垂直相邻、宽度相近，且其中一个有 caption，另一个没有
        i = 0
        while i < len(page_entries):
            current = page_entries[i]
            current_bbox = current.get("figure_bbox")
            if not current_bbox:
                i += 1
                continue
            
            # 查找可以合并的后续 entry
            group = [current]
            j = i + 1
            while j < len(page_entries):
                candidate = page_entries[j]
                candidate_bbox = candidate.get("figure_bbox")
                if not candidate_bbox:
                    j += 1
                    continue
                
                # 检查垂直距离和宽度相似度
                vert_dist = _vertical_distance(current_bbox, candidate_bbox)
                width_sim = _width_similarity(current_bbox, candidate_bbox)
                
                # 垂直相邻（间距 < 页面高度的 10%，假设页面高度约 800-1000）
                page_height = 1000  # 估算值，实际可以从 PDF 获取
                if vert_dist < page_height * 0.1 and width_sim > 0.8:
                    # 检查 caption 情况：其中一个有 caption，另一个没有
                    current_has_caption = current.get("has_caption", False)
                    candidate_has_caption = candidate.get("has_caption", False)
                    
                    # 如果 candidate 有 caption 而 current 没有，或者 candidate 的 caption 在更下方
                    candidate_caption_bbox = candidate.get("caption_bbox")
                    if candidate_caption_bbox is None:
                        candidate_caption_bbox = [0, 0, 0, 0]
                    
                    if (not current_has_caption and candidate_has_caption) or \
                       (current_has_caption and candidate_has_caption and 
                        candidate_caption_bbox[1] > current_bbox[3]):
                        group.append(candidate)
                        current = candidate  # 更新 current 为最新的
                        current_bbox = candidate_bbox
                        j += 1
                    elif current_has_caption and not candidate_has_caption:
                        # current 有 caption，candidate 没有，也可以合并（candidate 是子图）
                        group.append(candidate)
                        current = candidate
                        current_bbox = candidate_bbox
                        j += 1
                    else:
                        break
                else:
                    break
            
            # 如果找到多个，创建一个新组
            if len(group) > 1:
                # 找到最底部的 caption 作为整组的 caption
                group_caption = ""
                group_caption_bbox = None
                for g in group:
                    if g.get("caption") and g.get("caption_bbox"):
                        cap_y = g["caption_bbox"][1]
                        if not group_caption_bbox or cap_y > group_caption_bbox[1]:
                            group_caption = g["caption"]
                            group_caption_bbox = g["caption_bbox"]
                
                # 创建新组
                group_num = len(groups_by_number) + len(by_page) + 1000  # 使用大数字避免冲突
                groups_by_number[group_num] = group
                
                # 从 ungrouped 中移除已分组的
                for g in group:
                    if g in ungrouped:
                        ungrouped.remove(g)
            
            i = j
    
    # Stage 3: 弱绑定 - 水平相邻、高度相近（左右布局）
    # 对剩余的 ungrouped，检查水平布局
    # 同一页内，bbox 水平相邻、高度相近，且其中一个有 caption，另一个没有
    remaining_by_page: dict[int, list[dict]] = {}
    for entry_fig in ungrouped:
        page = entry_fig.get("page_idx", 0)
        if page not in remaining_by_page:
            remaining_by_page[page] = []
        remaining_by_page[page].append(entry_fig)
    
    for page, page_entries in remaining_by_page.items():
        if len(page_entries) <= 1:
            continue
        
        # 按 x 坐标排序（从左到右）
        page_entries.sort(key=lambda e: e.get("figure_bbox", [0, 0, 0, 0])[0] if e.get("figure_bbox") else 0)
        
        i = 0
        while i < len(page_entries):
            current = page_entries[i]
            current_bbox = current.get("figure_bbox")
            if not current_bbox:
                i += 1
                continue
            
            group = [current]
            j = i + 1
            while j < len(page_entries):
                candidate = page_entries[j]
                candidate_bbox = candidate.get("figure_bbox")
                if not candidate_bbox:
                    j += 1
                    continue
                
                # 检查水平距离和高度相似度
                # 水平距离：current 右边界到 candidate 左边界的距离
                horiz_dist = candidate_bbox[0] - current_bbox[2]
                height_sim = _height_similarity(current_bbox, candidate_bbox)
                
                # 水平相邻（间距 < 页面宽度的 5%）且高度相近
                page_width = 800  # 估算值
                if 0 < horiz_dist < page_width * 0.05 and height_sim > 0.8:
                    # 检查 caption 情况：其中一个有 caption，另一个没有
                    current_has_caption = current.get("has_caption", False)
                    candidate_has_caption = candidate.get("has_caption", False)
                    
                    # 如果其中一个有 caption，另一个没有，可以合并
                    if (current_has_caption and not candidate_has_caption) or \
                       (not current_has_caption and candidate_has_caption):
                        group.append(candidate)
                        current = candidate
                        current_bbox = candidate_bbox
                        j += 1
                    else:
                        break
                else:
                    break
            
            if len(group) > 1:
                # 创建新组
                group_num = len(groups_by_number) + len(remaining_by_page) + 2000
                groups_by_number[group_num] = group
                
                # 从 ungrouped 中移除已分组的
                for g in group:
                    if g in ungrouped:
                        ungrouped.remove(g)
            
            i = j
    
    # 构建最终的分组结果
    result_groups: list[dict] = []
    for group_num, group_entries in groups_by_number.items():
        if isinstance(group_num, tuple) and len(group_num) == 2:
            group_id = f"{group_num[0]}-{group_num[1]}"
        else:
            group_id = group_num
        # 找到整组的 caption（最底部的那个）
        group_caption = ""
        group_caption_bbox = None
        group_page = None
        
        for entry_fig in group_entries:
            # 简化条件：只要有 caption 就使用，不再严格要求 caption_bbox 和 caption_valid
            entry_caption = entry_fig.get("caption", "").strip()
            if entry_caption:
                cap_bbox = entry_fig.get("caption_bbox")
                cap_y = cap_bbox[1] if cap_bbox and len(cap_bbox) >= 2 else 0
                if not group_caption or (cap_bbox and (not group_caption_bbox or cap_y > group_caption_bbox[1])):
                    group_caption = entry_caption
                    group_caption_bbox = cap_bbox
            
            if group_page is None:
                group_page = entry_fig.get("page_idx", 0)
        
        result_groups.append({
            "group_id": group_id,
            "images": group_entries,
            "caption": group_caption,
            "caption_bbox": group_caption_bbox,
            "page_idx": group_page,
        })
    
    # 剩余的单个 entry 也作为独立组
    for entry_fig in ungrouped:
        result_groups.append({
            "group_id": len(result_groups) + 3000,
            "images": [entry_fig],
            "caption": entry_fig.get("caption", ""),
            "caption_bbox": entry_fig.get("caption_bbox"),
            "page_idx": entry_fig.get("page_idx", 0),
        })

    # Stage 4: 按页面做“连通合并”，尽量不要把一个 Figure 拆成多个 tile
    # 说明：这一步会更激进，可能把相邻 Figure 合并到一起（你选择了 B 策略）。
    groups_by_page2: dict[int, list[dict]] = {}
    for g in result_groups:
        page = int(g.get("page_idx", 0) or 0)
        groups_by_page2.setdefault(page, []).append(g)

    merged_all: list[dict] = []
    for page, gs in groups_by_page2.items():
        if len(gs) <= 1:
            merged_all.extend(gs)
            continue

        gb: list[list[float] | None] = []
        page_w = 0.0
        page_h = 0.0
        for g in gs:
            bboxes: list[list[float]] = []
            for img in g.get("images", []):
                bb = img.get("figure_bbox")
                if isinstance(bb, list) and len(bb) == 4:
                    bboxes.append(bb)
            ub = _bbox_union(bboxes)
            gb.append(ub)
            if ub:
                page_w = max(page_w, float(ub[2]))
                page_h = max(page_h, float(ub[3]))

        parent = list(range(len(gs)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(len(gs)):
            for j in range(i + 1, len(gs)):
                if gb[i] is None or gb[j] is None:
                    continue
                if _should_merge_group_bboxes(gb[i], gb[j], page_w, page_h):
                    union(i, j)

        comps: dict[int, list[int]] = {}
        for i in range(len(gs)):
            comps.setdefault(find(i), []).append(i)

        comp_idx = 0
        for _, idxs in comps.items():
            comp_idx += 1
            images: list[dict] = []
            for i in idxs:
                images.extend(gs[i].get("images", []))

            # caption：优先取“最底部的可信 caption”
            best_caption = ""
            best_caption_bbox = None
            for img in images:
                img_caption = img.get("caption", "").strip()
                if img_caption:
                    cb = img.get("caption_bbox")
                    # 如果有 caption_bbox，使用它来判断位置；否则也接受 caption
                    if cb and isinstance(cb, list) and len(cb) == 4:
                        if best_caption_bbox is None or cb[1] > best_caption_bbox[1]:
                            best_caption = img_caption
                            best_caption_bbox = cb
                    elif not best_caption:
                        # 如果没有 caption_bbox 但这是第一个有 caption 的，也使用它
                        best_caption = img_caption
                        best_caption_bbox = None

            merged_all.append(
                {
                    "group_id": f"p{page}-m{comp_idx}",
                    "images": images,
                    "caption": best_caption,
                    "caption_bbox": best_caption_bbox,
                    "page_idx": page,
                }
            )

    def _group_sort_key(g: dict) -> tuple[int, float, float]:
        page = int(g.get("page_idx", 0) or 0)
        bboxes: list[list[float]] = []
        for img in g.get("images", []):
            bb = img.get("figure_bbox")
            if isinstance(bb, list) and len(bb) == 4:
                bboxes.append(bb)
        ub = _bbox_union(bboxes) or [0.0, 0.0, 0.0, 0.0]
        return (page, float(ub[1]), float(ub[0]))

    merged_all.sort(key=_group_sort_key)
    return merged_all


def _normalize_path(path: str) -> str:
    """规范化路径，用于匹配"""
    if not path:
        return ""
    # 统一使用正斜杠，去除开头的斜杠
    path = path.replace("\\", "/").strip("/")
    return path


def assign_captions_by_bbox(entries: list[dict[str, str]], figures: list[dict], captions: list[dict], paper_dir: Path) -> None:
    """
    改进的caption匹配：通过img_path匹配figures到entries，然后关联captions。
    优先保留md中已有的caption，避免顺序填充导致的错配。
    """
    if not figures:
        return
    
    # 先匹配figures到captions（基于bbox和空间位置）
    matched = match_figures_to_captions(figures, captions) if captions else {}
    
    # 通过 img_path 匹配 entries 和 figures
    # 构建 img_path -> figure 的映射
    figure_by_path: dict[str, dict] = {}
    for i, fig in enumerate(figures):
        img_path = fig.get("img_path", "")
        if img_path:
            normalized_path = _normalize_path(img_path)
            if normalized_path:
                figure_by_path[normalized_path] = fig
                # 也保存索引，用于匹配 caption
                fig["_index"] = i
    
    # 将匹配结果关联到entries
    for entry in entries:
        entry_image_rel = entry.get("image_rel", "")
        if not entry_image_rel:
            continue
        
        # 规范化 entry 的 image_rel 路径
        normalized_entry_path = _normalize_path(entry_image_rel)
        
        # 查找匹配的 figure
        matched_figure = None
        for fig_path, fig in figure_by_path.items():
            # 路径匹配：可以是完全匹配，或者文件名匹配
            if normalized_entry_path == fig_path:
                matched_figure = fig
                break
            # 文件名匹配（处理路径差异）
            entry_filename = Path(entry_image_rel).name
            fig_filename = Path(fig_path).name
            if entry_filename and fig_filename and entry_filename == fig_filename:
                matched_figure = fig
                break
        
        if matched_figure:
            # 添加figure的bbox信息
            entry["figure_bbox"] = matched_figure["bbox"]
            entry["figure_page_idx"] = matched_figure["page_idx"]
            entry["img_path"] = matched_figure.get("img_path", "")  # 保存 img_path
            
            # 优先保留md中已有的caption
            if entry.get("caption"):
                continue
            
            # 如果figure有匹配的caption，则使用（并纯化）
            fig_index = matched_figure.get("_index")
            if fig_index is not None and fig_index in matched:
                raw_caption = matched[fig_index]["text"]
                purified_caption, is_valid = purify_caption(raw_caption)
                if is_valid:
                    entry["caption"] = purified_caption
                    entry["caption_bbox"] = matched[fig_index]["bbox"]
                else:
                    # caption 不可信，清空（避免正文污染）
                    entry["caption"] = ""
                    if "caption_bbox" in entry:
                        entry["caption_bbox"] = None
            else:
                # 如果 figure 本身有 image_caption，也尝试使用
                image_caption = matched_figure.get("image_caption", [])
                if isinstance(image_caption, list) and len(image_caption) > 0:
                    for cap in image_caption:
                        if isinstance(cap, str) and cap.strip():
                            raw_caption = cap.strip()
                            purified_caption, is_valid = purify_caption(raw_caption)
                            if is_valid:
                                entry["caption"] = purified_caption
                                # 使用 figure 的 bbox 作为 caption_bbox（因为 caption 在 image_caption 中）
                                entry["caption_bbox"] = matched_figure["bbox"]
                            break


def has_keyword(text: str, keywords: Iterable[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def extract_figure_number(caption: str) -> int | None:
    """
    从 caption 文本中提取 figure 编号。
    例如："Figure 8: ..." -> 8, "Fig. 3:" -> 3
    """
    if not caption:
        return None
    # 匹配 Figure/Fig/图 + 数字
    pattern = r"(?:Figure|Fig\.?|图|Table|表)\s*(\d+)"
    match = re.search(pattern, caption, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except (ValueError, IndexError):
            return None
    return None


def purify_caption(text: str) -> tuple[str, bool]:
    """
    纯化 caption 文本，确保是可信的 caption（不是正文段落）。
    
    返回: (purified_text, is_valid)
    - is_valid=True: caption 符合模式（包含 Figure X: 等）
    - is_valid=False: 不符合模式，可能是正文段落
    """
    if not text:
        return "", False
    
    text = text.strip()
    
    # 验证规则：必须包含 Figure|Fig|图|Table|表 + 编号
    figure_pattern = r"(?:Figure|Fig\.?|图|Table|表)\s*\d+"
    has_figure_prefix = bool(re.search(figure_pattern, text, re.IGNORECASE))
    
    # 放宽限制：如果文本以 Figure 开头，认为是有效的 caption
    if not has_figure_prefix:
        # 检查是否以 Figure 相关词汇开头（不一定带编号）
        loose_pattern = r"^(?:Figure|Fig\.?|图|Table|表)"
        if not re.search(loose_pattern, text, re.IGNORECASE):
            return "", False
    
    # 截断规则：从 Figure X: 开始，截断到合理位置
    # 找到 Figure X: 的位置
    match = re.search(figure_pattern, text, re.IGNORECASE)
    if match:
        start_pos = match.start()
        # 从 Figure X: 开始
        text = text[start_pos:]
    
    # 截断到：遇到空行 + 首字母大写且非续行，或超过 5 行
    lines = text.split('\n')
    purified_lines = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            # 遇到空行，检查下一行是否是新的段落开始
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and next_line[0].isupper() and len(next_line) > 10:
                    # 可能是新段落，截断到这里
                    break
            continue
        
        # 检查是否是 section heading 风格（全大写或编号标题）
        if re.match(r'^[A-Z][A-Z\s]+$', line) or re.match(r'^\d+\.\s+[A-Z]', line):
            # 可能是 section heading，截断
            break
        
        purified_lines.append(line)
        
        # 最多保留 5 行
        if len(purified_lines) >= 5:
            break
    
    purified = '\n'.join(purified_lines).strip()
    
    # 再次验证：确保仍然包含 figure 模式
    if re.search(figure_pattern, purified, re.IGNORECASE):
        return purified, True
    
    return "", False


def _vertical_distance(bbox1: list[float], bbox2: list[float]) -> float:
    """计算两个 bbox 之间的垂直距离（下边界到上边界的距离）"""
    if len(bbox1) < 4 or len(bbox2) < 4:
        return float('inf')
    # bbox格式: [x0, y0, x1, y1]
    # 垂直距离：bbox1的下边界(y1) 到 bbox2的上边界(y0)
    return bbox2[1] - bbox1[3]


def _width_similarity(bbox1: list[float], bbox2: list[float]) -> float:
    """计算两个 bbox 的宽度相似度（0-1，1表示完全相同）"""
    if len(bbox1) < 4 or len(bbox2) < 4:
        return 0.0
    w1 = bbox1[2] - bbox1[0]
    w2 = bbox2[2] - bbox2[0]
    if w1 == 0 or w2 == 0:
        return 0.0
    return 1.0 - abs(w1 - w2) / max(w1, w2)


def _height_similarity(bbox1: list[float], bbox2: list[float]) -> float:
    """计算两个 bbox 的高度相似度（0-1，1表示完全相同）"""
    if len(bbox1) < 4 or len(bbox2) < 4:
        return 0.0
    h1 = bbox1[3] - bbox1[1]
    h2 = bbox2[3] - bbox2[1]
    if h1 == 0 or h2 == 0:
        return 0.0
    return 1.0 - abs(h1 - h2) / max(h1, h2)


def _bbox_union(bboxes: list[list[float]]) -> list[float] | None:
    valid = [b for b in bboxes if isinstance(b, list) and len(b) == 4]
    if not valid:
        return None
    x0 = min(float(b[0]) for b in valid)
    y0 = min(float(b[1]) for b in valid)
    x1 = max(float(b[2]) for b in valid)
    y1 = max(float(b[3]) for b in valid)
    return [x0, y0, x1, y1]


def _bbox_vertical_gap(a: list[float], b: list[float]) -> float:
    if b[1] >= a[3]:
        return b[1] - a[3]
    if a[1] >= b[3]:
        return a[1] - b[3]
    return 0.0


def _bbox_horizontal_gap(a: list[float], b: list[float]) -> float:
    if b[0] >= a[2]:
        return b[0] - a[2]
    if a[0] >= b[2]:
        return a[0] - b[2]
    return 0.0


def _should_merge_group_bboxes(a: list[float], b: list[float], page_w: float, page_h: float) -> bool:
    """
    Aggressive merge heuristic: treat as connected if close in either direction with
    reasonable overlap/alignment. This favors not splitting a multi-panel figure.
    """
    if not (isinstance(a, list) and isinstance(b, list) and len(a) == 4 and len(b) == 4):
        return False
    page_w = max(1.0, float(page_w))
    page_h = max(1.0, float(page_h))
    vgap = _bbox_vertical_gap(a, b)
    hgap = _bbox_horizontal_gap(a, b)
    hover = _horizontal_overlap(a, b)
    ay0, ay1 = float(a[1]), float(a[3])
    by0, by1 = float(b[1]), float(b[3])
    y_inter = max(0.0, min(ay1, by1) - max(ay0, by0))
    y_denom = max(1.0, min(ay1 - ay0, by1 - by0))
    yover = y_inter / y_denom

    if vgap <= page_h * 0.18 and (hover >= 0.12 or hgap <= page_w * 0.08):
        return True
    if hgap <= page_w * 0.08 and (yover >= 0.12 or vgap <= page_h * 0.10):
        return True
    if vgap == 0.0 and hgap == 0.0:
        return True
    return False


def keep_entry(entry: dict[str, str], cfg: RenderConfig) -> tuple[bool, str]:
    heading = entry.get("heading", "")
    caption = entry.get("caption", "")
    heading_pos = has_keyword(heading, cfg.heading_positive)
    heading_neg = has_keyword(heading, cfg.heading_negative)
    caption_pos = has_keyword(caption, cfg.caption_positive)
    caption_neg = has_keyword(caption, cfg.caption_negative)

    if not cfg.results_only:
        return True, "all_figures"
    if caption_pos:
        return True, "caption_positive"
    if heading_pos and not caption_neg:
        return True, "heading_positive"
    if heading_neg and not caption_pos:
        return False, "heading_negative"
    return False, "no_results_signal"


def load_caption_font(cfg: RenderConfig):
    if cfg.caption_font_path:
        p = Path(cfg.caption_font_path)
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), cfg.caption_font_size)
            except Exception:
                pass
    
    # 尝试系统字体路径（Windows）
    system_font_paths = []
    if os.name == 'nt':  # Windows
        windows_fonts = Path("C:/Windows/Fonts")
        if windows_fonts.exists():
            # 按优先级尝试常见字体
            system_font_paths = [
                windows_fonts / "arial.ttf",
                windows_fonts / "Arial.ttf",
                windows_fonts / "calibri.ttf",
                windows_fonts / "Calibri.ttf",
                windows_fonts / "tahoma.ttf",
                windows_fonts / "Tahoma.ttf",
                windows_fonts / "segoeui.ttf",
                windows_fonts / "SegoeUI.ttf",
            ]
    
    # 尝试系统字体路径
    for font_path in system_font_paths:
        if font_path.exists():
            try:
                return ImageFont.truetype(str(font_path), cfg.caption_font_size)
            except Exception:
                continue
    
    # 尝试直接使用字体名称（PIL 可能会在系统路径中查找）
    for fallback in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "calibri.ttf", "simhei.ttf", "simsun.ttc"):
        try:
            return ImageFont.truetype(fallback, cfg.caption_font_size)
        except Exception:
            continue
    
    # 最后的 fallback：使用默认字体（但大小可能不准确）
    # 注意：ImageFont.load_default() 不支持自定义大小，这是最后的备选方案
    return ImageFont.load_default()


def wrap_lines(text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return []
    img = Image.new("RGB", (max_width, 1))
    draw = ImageDraw.Draw(img)
    lines: list[str] = []
    current: list[str] = []
    truncated = False
    for w in words:
        test = " ".join(current + [w])
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current.append(w)
            continue
        if current:
            lines.append(" ".join(current))
        current = [w]
        if len(lines) >= max_lines:
            truncated = True
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    if truncated and lines:
        last = lines[-1]
        ellipsis = "..."
        while draw.textbbox((0, 0), last + ellipsis, font=font)[2] > max_width and last:
            last = last[:-1].rstrip()
        lines[-1] = last + ellipsis if last else ellipsis
    return lines


def render_caption_bar(text: str, width: int, cfg: RenderConfig) -> Image.Image | None:
    if not text:
        return None
    font = load_caption_font(cfg)
    max_width = max(1, width - cfg.caption_bar_padding * 2)
    lines = wrap_lines(text, font, max_width, cfg.caption_max_lines)
    if not lines:
        return None
    img = Image.new("RGB", (width, 1))
    draw = ImageDraw.Draw(img)
    line_heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
    text_h = sum(line_heights) + (len(lines) - 1) * 2
    bar_h = text_h + cfg.caption_bar_padding * 2
    bar = Image.new("RGB", (width, bar_h), cfg.caption_bg)
    draw = ImageDraw.Draw(bar)
    y = cfg.caption_bar_padding
    for line, lh in zip(lines, line_heights):
        draw.text((cfg.caption_bar_padding, y), line, fill=cfg.caption_color, font=font)
        y += lh + 2
    return bar


def is_text_like(tile: Image.Image, cfg: RenderConfig) -> bool:
    small = tile.resize((256, 256), Image.LANCZOS)
    gray = small.convert("L")
    hist = gray.histogram()
    total = sum(hist)
    if total == 0:
        return True
    white = sum(hist[245:])
    nonwhite_ratio = 1.0 - white / float(total)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_mean = ImageStat.Stat(edges).mean[0] / 255.0
    if nonwhite_ratio < cfg.nonwhite_min_ratio:
        return True
    if edge_mean > cfg.edge_density_max and nonwhite_ratio < 0.2:
        return True
    if edge_mean > cfg.textlike_edge_max and nonwhite_ratio < 0.12:
        return True
    return False


def compose_figure_group(group: dict, paper_dir: Path, cfg: RenderConfig) -> tuple[Image.Image, str]:
    """
    将 figure group 内的子图拼接成一个 tile。
    
    输入：
    - group: 包含 images 列表（每个 image 是 entry_fig 字典）
    - paper_dir: 论文目录
    - cfg: 配置
    
    输出：
    - (composed_image, caption_text): 拼接后的图片（纯图，不含caption）和 caption 文本
    
    子图拼接策略：
    - 如果 2 张子图且宽度相近（差异 < 20%）：竖向 stack（上下布局）
    - 如果 2 张子图且高度相近（差异 < 20%）：横向排列（左右布局）
    - 如果多张：使用小型 justified rows 算法
    """
    images = group.get("images", [])
    if not images:
        raise ValueError("Group has no images")
    
    # 如果子图数量超过2个，只取第一个作为代表（避免合成后图片过小）
    # 这样可以保证每个图片有足够的显示空间，标签清晰可见
    if len(images) > 2:
        images = images[:1]  # 只取第一个图片
    
    if len(images) == 1:
        # 单个图片，直接加载
        entry_fig = images[0]
        entry = entry_fig["entry"]
        # 优先使用 img_path（来自 content_list.json），否则使用 image_rel（来自 md）
        img_path_str = entry_fig.get("img_path") or entry.get("img_path") or entry.get("image_rel", "")
        if not img_path_str:
            raise FileNotFoundError(f"No image path found for entry")
        
        img_path = (paper_dir / img_path_str).resolve()
        if not img_path.exists():
            raise FileNotFoundError(f"Image not found: {img_path}")
        
        fig = Image.open(img_path).convert("RGB")
        fig = strip_embedded_caption(fig, entry, cfg)
        fig = add_image_padding(fig, cfg)  # 添加白边防止边缘内容被裁剪
        caption = group.get("caption", "")
        return fig, caption
    
    # 加载所有子图
    subfigs: list[Image.Image] = []
    subfig_sizes: list[tuple[int, int]] = []
    
    for entry_fig in images:
        entry = entry_fig["entry"]
        # 优先使用 img_path（来自 content_list.json），否则使用 image_rel（来自 md）
        img_path_str = entry_fig.get("img_path") or entry.get("img_path") or entry.get("image_rel", "")
        if not img_path_str:
            continue  # 跳过没有路径的图片
        
        img_path = (paper_dir / img_path_str).resolve()
        if not img_path.exists():
            continue  # 跳过不存在的图片
        
        try:
            fig = Image.open(img_path).convert("RGB")
            fig = strip_embedded_caption(fig, entry, cfg)
            fig = add_image_padding(fig, cfg)  # 添加白边防止边缘内容被裁剪
            subfigs.append(fig)
            subfig_sizes.append(fig.size)
        except Exception:
            continue  # 跳过加载失败的图片
    
    if not subfigs:
        raise ValueError("No valid images in group")
    
    if len(subfigs) == 1:
        caption = group.get("caption", "")
        return subfigs[0], caption
    
    # 判断布局方式
    if len(subfigs) == 2:
        w1, h1 = subfig_sizes[0]
        w2, h2 = subfig_sizes[1]
        
        width_sim = 1.0 - abs(w1 - w2) / max(w1, w2) if max(w1, w2) > 0 else 0.0
        height_sim = 1.0 - abs(h1 - h2) / max(h1, h2) if max(h1, h2) > 0 else 0.0
        
        if width_sim > 0.8:
            # 宽度相近，竖向 stack（上下布局）
            target_w = max(w1, w2)
            scale1 = target_w / w1 if w1 > 0 else 1.0
            scale2 = target_w / w2 if w2 > 0 else 1.0
            
            new_h1 = int(h1 * scale1)
            new_h2 = int(h2 * scale2)
            
            img1 = subfigs[0].resize((target_w, new_h1), Image.Resampling.LANCZOS)
            img2 = subfigs[1].resize((target_w, new_h2), Image.Resampling.LANCZOS)
            
            spacing = 10  # 子图之间的间距
            total_h = new_h1 + spacing + new_h2
            composed = Image.new("RGB", (target_w, total_h), "white")
            composed.paste(img1, (0, 0))
            composed.paste(img2, (0, new_h1 + spacing))
            
            caption = group.get("caption", "")
            return composed, caption
        
        elif height_sim > 0.8:
            # 高度相近，横向排列（左右布局）
            target_h = max(h1, h2)
            scale1 = target_h / h1 if h1 > 0 else 1.0
            scale2 = target_h / h2 if h2 > 0 else 1.0
            
            new_w1 = int(w1 * scale1)
            new_w2 = int(w2 * scale2)
            
            img1 = subfigs[0].resize((new_w1, target_h), Image.Resampling.LANCZOS)
            img2 = subfigs[1].resize((new_w2, target_h), Image.Resampling.LANCZOS)
            
            spacing = 10  # 子图之间的间距
            total_w = new_w1 + spacing + new_w2
            composed = Image.new("RGB", (total_w, target_h), "white")
            composed.paste(img1, (0, 0))
            composed.paste(img2, (new_w1 + spacing, 0))
            
            caption = group.get("caption", "")
            return composed, caption
    
    # 多张图片：使用简单的网格布局
    # 计算合适的列数（尽量接近正方形）
    num_images = len(subfigs)
    cols = int(num_images ** 0.5) + (1 if num_images ** 0.5 != int(num_images ** 0.5) else 0)
    cols = max(2, min(cols, 3))  # 最多3列
    rows = (num_images + cols - 1) // cols
    
    # 计算每张图片的目标尺寸（保持宽高比，统一高度）
    max_h = max(h for _, h in subfig_sizes)
    target_h = max_h
    
    scaled_images: list[Image.Image] = []
    scaled_widths: list[int] = []
    
    for fig, (w, h) in zip(subfigs, subfig_sizes):
        scale = target_h / h if h > 0 else 1.0
        new_w = int(w * scale)
        scaled_img = fig.resize((new_w, target_h), Image.Resampling.LANCZOS)
        scaled_images.append(scaled_img)
        scaled_widths.append(new_w)
    
    # 按行布局
    row_widths: list[int] = []
    for r in range(rows):
        start_idx = r * cols
        end_idx = min(start_idx + cols, num_images)
        row_w = sum(scaled_widths[start_idx:end_idx]) + (end_idx - start_idx - 1) * 10  # 10px 间距
        row_widths.append(row_w)
    
    total_w = max(row_widths) if row_widths else 0
    total_h = rows * target_h + (rows - 1) * 10  # 10px 行间距
    
    composed = Image.new("RGB", (total_w, total_h), "white")
    
    y_offset = 0
    for r in range(rows):
        start_idx = r * cols
        end_idx = min(start_idx + cols, num_images)
        row_w = row_widths[r]
        x_offset = (total_w - row_w) // 2  # 居中对齐
        
        for i in range(start_idx, end_idx):
            img = scaled_images[i]
            composed.paste(img, (x_offset, y_offset))
            x_offset += img.width + 10  # 10px 间距
        
        y_offset += target_h + 10  # 10px 行间距
    
    caption = group.get("caption", "")
    return composed, caption


def add_image_padding(fig: Image.Image, cfg: RenderConfig) -> Image.Image:
    """
    给图片添加白色边框 padding，防止边缘内容（如轴标签）在缩放/裁剪过程中被截断。
    """
    if cfg.image_padding_ratio <= 0:
        return fig
    
    # 计算 padding 大小（基于图片短边）
    min_dim = min(fig.width, fig.height)
    padding = max(1, int(min_dim * cfg.image_padding_ratio))
    
    # 创建带白边的新图片
    new_w = fig.width + 2 * padding
    new_h = fig.height + 2 * padding
    padded = Image.new("RGB", (new_w, new_h), "white")
    padded.paste(fig, (padding, padding))
    
    return padded


def strip_embedded_caption(fig: Image.Image, entry: dict, cfg: RenderConfig) -> Image.Image:
    """
    去除图片中嵌入的caption和正文，确保tile是纯图，不夹带正文。
    关键原则：图像区域和caption区域永远是两个独立排版块，caption只在图外占位，绝不画进图里。
    """
    if not cfg.remove_embedded_caption:
        return fig
    
    # 关键修复：确保tile是纯图，不夹带正文
    # 如果有外部caption，必须去除图片中的caption（避免重复）
    # 即使没有外部caption，也应该去除图片底部的文本区域（可能是正文或caption）
    entry_caption = entry.get("caption", "").strip()
    has_external_caption = bool(entry_caption)
    
    fig_bbox = entry.get("figure_bbox")
    cap_bbox = entry.get("caption_bbox")
    
    # 如果有明确的caption bbox，精确去除
    if isinstance(fig_bbox, list) and isinstance(cap_bbox, list) and len(fig_bbox) == 4 and len(cap_bbox) == 4:
        fig_w = max(1.0, fig_bbox[2] - fig_bbox[0])
        fig_h = max(1.0, fig_bbox[3] - fig_bbox[1])
        scale_x = fig.width / fig_w
        scale_y = fig.height / fig_h
        x0 = int(max(0.0, (cap_bbox[0] - fig_bbox[0]) * scale_x))
        y0 = int(max(0.0, (cap_bbox[1] - fig_bbox[1]) * scale_y))
        x1 = int(min(fig.width, (cap_bbox[2] - fig_bbox[0]) * scale_x))
        y1 = int(min(fig.height, (cap_bbox[3] - fig_bbox[1]) * scale_y))
        if x1 > x0 and y1 > y0:
            # 如果有外部caption，必须去除图片中的caption（避免重复）
            # 即使没有外部caption，如果caption在底部且高度较小，也应该去除（可能是正文）
            caption_height_ratio = (y1 - y0) / fig.height
            if has_external_caption or (y0 > fig.height * 0.85 and caption_height_ratio < 0.15):
                # 去除caption区域，确保tile是纯图
                masked = fig.copy()
                draw = ImageDraw.Draw(masked)
                draw.rectangle([x0, y0, x1, y1], fill="white")
                return masked
            # 如果caption不在最底部或高度较大，可能是复合图的总caption，不去除
            return fig
    
    # 没有明确的bbox时，不要盲目裁剪！
    # 盲目裁剪会切掉图表的轴标签、图例等重要信息
    # 只有在有明确bbox信息时才进行裁剪
    return fig


def choose_columns(tiles: list[Image.Image], cfg: RenderConfig) -> int:
    return max(1, cfg.masonry_columns)


def pack_tiles_hybrid(tiles: list[Image.Image], captions: list[str], canvas_size: tuple[int, int], cfg: RenderConfig):
    """
    改进的hybrid布局：按高度装箱分页，而不是固定tiles_per_page。
    宽图（aspect_ratio >= wide_ratio）占整行，其余做两列布局。
    严格保证tile宽度不超过列宽，避免重叠。
    """
    if not tiles:
        return [], []
    canvas_w, canvas_h = canvas_size
    padding = max(1, int(canvas_w * cfg.masonry_padding_ratio))
    gutter = max(1, int(canvas_w * cfg.masonry_gutter_ratio))
    available_w = max(1, canvas_w - 2 * padding)
    available_h = max(1, canvas_h - 2 * padding)
    col_w = (available_w - gutter) / 2.0

    def scaled_size(img: Image.Image, target_w: float) -> tuple[int, int]:
        """计算缩放后尺寸，确保宽度不超过target_w"""
        scale = target_w / float(img.width)
        w = max(1, int(img.width * scale))
        h = max(1, int(img.height * scale))
        # 确保宽度不超过target_w
        if w > target_w:
            scale = target_w / float(img.width)
            w = int(target_w)
            h = max(1, int(img.height * scale))
        return w, h

    pages: list[Image.Image] = []
    stats: list[dict[str, float]] = []
    current: list[dict] = []
    used_h = 0.0

    def flush_page():
        if not current:
            return
        page = Image.new("RGB", (canvas_w, canvas_h), "white")
        content_area = 0.0
        
        # 计算页面内容的总高度（用于垂直居中）
        total_content_height = 0.0
        if len(current) > 0:
            # 找到最后一个元素的位置和高度
            last_item = current[-1]
            last_y = last_item["y"]
            last_h = last_item["h"]
            last_caption = last_item.get("caption", "")
            caption_spacing = cfg.caption_image_spacing if cfg.caption_image_spacing > 0 else gutter
            last_caption_h = 0
            if last_caption:
                temp_bar = render_caption_bar(last_caption, int(last_item["w"]), cfg)
                if temp_bar:
                    last_caption_h = temp_bar.height + caption_spacing
            total_content_height = last_y + last_h + last_caption_h
        
        # 对于单图页面，如果内容高度小于可用高度，垂直居中
        vertical_offset = 0.0
        if len(current) == 1 and total_content_height > 0:
            available_h = canvas_h - 2 * padding
            # 对于单图页面，如果内容高度明显小于可用高度（小于80%），进行垂直居中
            if total_content_height < available_h * 0.8:
                # 计算垂直居中偏移：将内容从顶部偏移到中间
                vertical_offset = (available_h - total_content_height) / 2.0
                # 确保偏移不为负
                vertical_offset = max(0.0, vertical_offset)
        
        for p in current:
            tile = p["tile"]
            caption = p.get("caption", "")
            resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", 3))
            # 计算实际渲染位置和尺寸（应用垂直居中偏移）
            x = int(p["x"] + padding)
            y = int(p["y"] + padding + vertical_offset)
            x_final = max(0, x)
            y_final = max(0, y)
            w_plan = int(p["w"])
            h_plan = int(p["h"])
            
            # 关键原则：图像区域和caption区域永远是两个独立排版块
            # caption只在图外占位，绝不画进图里
            
            # 计算caption所需空间（使用计划宽度，确保文本完整）
            caption_space = 0
            # 如果 caption_image_spacing 为 0，使用与图片相同的 gutter 间距
            caption_spacing = cfg.caption_image_spacing if cfg.caption_image_spacing > 0 else gutter
            if caption:
                temp_bar = render_caption_bar(caption, w_plan, cfg)
                if temp_bar:
                    # caption是独立的块，需要完整的空间（高度+间距）
                    caption_space = temp_bar.height + caption_spacing
            
            # 计算图片实际可渲染尺寸（考虑边界和caption空间）
            # 图片和caption是独立的块，图片不能占用caption的空间
            max_w = canvas_w - x_final
            max_h_for_image = canvas_h - y_final - caption_space  # 图片高度不能占用caption空间
            
            # 关键修复：如果图片放不下，等比例缩小而不是裁剪！
            # 这样可以保证图片完整显示（包括轴标签等）
            w_final = w_plan
            h_final = h_plan
            
            # 检查是否需要缩小以适应可用空间
            if w_plan > max_w or h_plan > max_h_for_image:
                # 计算需要的缩放比例（取较小的比例以确保两个方向都能放下）
                scale_w = max_w / w_plan if w_plan > max_w else 1.0
                scale_h = max_h_for_image / h_plan if h_plan > max_h_for_image else 1.0
                scale = min(scale_w, scale_h)
                
                # 应用等比例缩放
                w_final = max(1, int(w_plan * scale))
                h_final = max(1, int(h_plan * scale))
            
            # 渲染图片区域（独立的排版块）
            if w_final > 0 and h_final > 0:
                tile_img = tile.resize((w_final, h_final), resample)
                page.paste(tile_img, (x_final, y_final))
                content_area += float(w_final) * float(h_final)
                
                # 渲染caption区域（独立的排版块，在图外）
                if caption:
                    # 使用计划宽度w_plan，确保caption文本有足够的宽度显示
                    caption_width = w_plan
                    bar = render_caption_bar(caption, caption_width, cfg)
                    if bar:
                        # caption位置：图片下方 + 间距（caption绝不画进图里）
                        caption_y = y_final + h_final + caption_spacing
                        caption_x = x_final
                        
                        # 确保caption不会超出画布，避免覆盖下方内容
                        if caption_y + bar.height > canvas_h:
                            # caption会超出画布，需要调整
                            # 方案：如果还有空间，向上调整caption位置（减少图片高度）
                            max_caption_y = canvas_h - bar.height
                            if max_caption_y > y_final:
                                # 可以向上调整，减少图片高度，为caption留出空间
                                h_final = max(1, max_caption_y - y_final - caption_spacing)
                                # 重新渲染图片（调整后的高度）
                                tile_img = tile.resize((w_final, h_final), resample)
                                page.paste(tile_img, (x_final, y_final))
                                caption_y = y_final + h_final + caption_spacing
                            else:
                                # 没有足够空间，不渲染caption（避免覆盖）
                                bar = None
                        
                        if bar:
                            # 边界保护：如果caption bar超出右边界，调整x坐标
                            if caption_x + bar.width > canvas_w:
                                caption_x = max(0, canvas_w - bar.width)
                            
                            # 确保caption在画布内才渲染（caption是独立的块）
                            if caption_y + bar.height <= canvas_h and caption_x + bar.width <= canvas_w:
                                page.paste(bar, (caption_x, caption_y))
                                content_area += float(bar.width) * float(bar.height)
        fill_ratio = content_area / float(canvas_w * canvas_h) if canvas_w * canvas_h else 0.0
        pages.append(page)
        stats.append({"tiles": len(current), "fill_ratio": fill_ratio, "height_used": used_h})

    pending_left: Image.Image | None = None
    pending_left_caption: str = ""
    for idx, tile in enumerate(tiles):
        caption = captions[idx] if idx < len(captions) else ""
        ratio = tile.width / max(1.0, tile.height)
        if ratio >= cfg.wide_ratio:
            # 宽图：先处理pending的图（如果有）
            if pending_left is not None:
                w, h = scaled_size(pending_left, col_w)
                bar_h = 0
                caption_spacing = cfg.caption_image_spacing if cfg.caption_image_spacing > 0 else gutter
                if pending_left_caption:
                    bar = render_caption_bar(pending_left_caption, int(w), cfg)
                    if bar:
                        bar_h = bar.height + caption_spacing  # caption是独立的块，需要完整空间
                total_h = h + bar_h  # 图片高度 + caption高度（独立块）
                # 按高度装箱：如果放不下就换页
                # 关键修复：确保包括caption在内的总高度不会超出可用空间
                if used_h + total_h > available_h and used_h > 0:
                    flush_page()
                    current.clear()
                    used_h = 0.0
                x = max(0.0, (available_w - w) / 2.0)  # 确保x >= 0
                current.append({"tile": pending_left, "caption": pending_left_caption, "x": x, "y": used_h, "w": w, "h": h})
                used_h += total_h + gutter
                pending_left = None
                pending_left_caption = ""
            # 处理当前宽图
            w, h = scaled_size(tile, available_w)
            # 确保宽度不超过available_w
            w = min(w, int(available_w))
            bar_h = 0
            caption_spacing = cfg.caption_image_spacing if cfg.caption_image_spacing > 0 else gutter
            if caption:
                bar = render_caption_bar(caption, int(w), cfg)
                if bar:
                    bar_h = bar.height + caption_spacing  # caption是独立的块，需要完整空间
            total_h = h + bar_h  # 图片高度 + caption高度（独立块）
            # 按高度装箱：如果放不下就换页
            # 关键修复：确保包括caption在内的总高度不会超出可用空间
            if used_h + total_h > available_h and used_h > 0:
                flush_page()
                current.clear()
                used_h = 0.0
            current.append({"tile": tile, "caption": caption, "x": 0.0, "y": used_h, "w": w, "h": h})
            used_h += total_h + gutter
        else:
            # 窄图：两列布局
            if pending_left is None:
                pending_left = tile
                pending_left_caption = caption
            else:
                w1, h1 = scaled_size(pending_left, col_w)
                w2, h2 = scaled_size(tile, col_w)
                # 确保宽度不超过列宽
                w1 = min(w1, int(col_w))
                w2 = min(w2, int(col_w))
                bar_h1 = 0
                caption_spacing = cfg.caption_image_spacing if cfg.caption_image_spacing > 0 else gutter
                if pending_left_caption:
                    bar1 = render_caption_bar(pending_left_caption, int(w1), cfg)
                    if bar1:
                        bar_h1 = bar1.height + caption_spacing  # caption是独立的块
                bar_h2 = 0
                if caption:
                    bar2 = render_caption_bar(caption, int(w2), cfg)
                    if bar2:
                        bar_h2 = bar2.height + caption_spacing  # caption是独立的块
                # 行高取两列中较大的（图片+caption，都是独立块）
                row_h = max(h1 + bar_h1, h2 + bar_h2)
                # 按高度装箱：如果放不下就换页
                # 关键修复：确保包括caption在内的总高度不会超出可用空间
                if used_h + row_h > available_h and used_h > 0:
                    flush_page()
                    current.clear()
                    used_h = 0.0
                current.append({"tile": pending_left, "caption": pending_left_caption, "x": 0.0, "y": used_h, "w": w1, "h": h1})
                current.append({"tile": tile, "caption": caption, "x": col_w + gutter, "y": used_h, "w": w2, "h": h2})
                used_h += row_h + gutter
                pending_left = None
                pending_left_caption = ""

    # 处理最后剩余的pending图
    if pending_left is not None:
        w, h = scaled_size(pending_left, col_w)
        w = min(w, int(col_w))  # 确保宽度不超过列宽
        bar_h = 0
        caption_spacing = cfg.caption_image_spacing if cfg.caption_image_spacing > 0 else gutter
        if pending_left_caption:
            bar = render_caption_bar(pending_left_caption, int(w), cfg)
            if bar:
                bar_h = bar.height + caption_spacing  # caption是独立的块，需要完整空间
        total_h = h + bar_h  # 图片高度 + caption高度（独立块）
        # 按高度装箱：如果放不下就换页
        # 关键修复：确保包括caption在内的总高度不会超出可用空间
        if used_h + total_h > available_h and used_h > 0:
            flush_page()
            current.clear()
            used_h = 0.0
        x = max(0.0, (available_w - w) / 2.0)  # 确保x >= 0
        current.append({"tile": pending_left, "caption": pending_left_caption, "x": x, "y": used_h, "w": w, "h": h})
        used_h += total_h + gutter

    flush_page()
    return pages, stats


def _px_to_css_px(px: float, dpi: int) -> float:
    """
    Convert "image pixel at dpi" to CSS px.
    CSS px is 1/96 inch. Image px is 1/dpi inch.
    """
    if dpi <= 0:
        return float(px)
    return float(px) * 96.0 / float(dpi)


def _path_to_file_url(p: Path) -> str:
    # Path.as_uri() handles Windows paths correctly (file:///D:/...)
    return p.resolve().as_uri()


def _write_html_masonry_document(
    html_path: Path,
    tiles_dir: Path,
    tile_files: list[str],
    captions: list[str],
    tile_is_wide: list[bool],
    canvas_size_px: tuple[int, int],
    cfg: RenderConfig,
) -> None:
    """
    Write a single HTML document that paginates into fixed-size pages when printed.
    Layout:
      - multi-column flow
      - .wide tiles span all columns
      - figure kept intact (no split across columns/pages where possible)
    """
    canvas_w_px, canvas_h_px = canvas_size_px
    w_in = canvas_w_px / float(cfg.dpi)
    h_in = canvas_h_px / float(cfg.dpi)

    padding_px = max(1, int(canvas_w_px * cfg.masonry_padding_ratio))
    gutter_px = max(1, int(canvas_w_px * cfg.masonry_gutter_ratio))
    padding_css = _px_to_css_px(padding_px, cfg.dpi)
    gutter_css = _px_to_css_px(gutter_px, cfg.dpi)

    # Match PIL-ish caption sizing in physical units.
    caption_font_css = max(8.0, _px_to_css_px(cfg.caption_font_size, cfg.dpi))
    caption_pad_css = max(2.0, _px_to_css_px(cfg.caption_bar_padding, cfg.dpi))

    # Use a safe default font stack, keep it consistent across machines.
    css = f"""
    @page {{
      size: {w_in:.6f}in {h_in:.6f}in;
      margin: 0;
    }}

    html, body {{
      margin: 0;
      padding: 0;
      background: white;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}

    body {{
      padding: {padding_css:.3f}px;
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
                   Arial, "Noto Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: #000;
    }}

    main {{
      column-count: {max(1, int(cfg.masonry_columns))};
      column-gap: {gutter_css:.3f}px;
      column-fill: auto;
    }}

    figure.tile {{
      margin: 0 0 {gutter_css:.3f}px 0;
      padding: 0;
      break-inside: avoid;
      page-break-inside: avoid;
      overflow: hidden;
    }}

    figure.tile.wide {{
      column-span: all;
    }}

    figure.tile img {{
      width: 100%;
      height: auto;
      display: block;
      background: #fff;
    }}

    figure.tile figcaption {{
      margin-top: {_px_to_css_px(cfg.caption_image_spacing, cfg.dpi):.3f}px;
      padding: {caption_pad_css:.3f}px;
      background: rgb({cfg.caption_bg[0]}, {cfg.caption_bg[1]}, {cfg.caption_bg[2]});
      color: rgb({cfg.caption_color[0]}, {cfg.caption_color[1]}, {cfg.caption_color[2]});
      font-size: {caption_font_css:.3f}px;
      line-height: 1.22;
      box-sizing: border-box;
      break-inside: avoid;
      page-break-inside: avoid;
      overflow: hidden;
      display: -webkit-box;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: {max(1, int(cfg.caption_max_lines))};
    }}
    """
    css = textwrap.dedent(css).strip()

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8" />')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1" />')
    parts.append("<title>select_image layout</title>")
    parts.append("<style>")
    parts.append(css)
    parts.append("</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<main>")

    for i, fname in enumerate(tile_files):
        is_wide = tile_is_wide[i] if i < len(tile_is_wide) else False
        cap = captions[i] if i < len(captions) else ""
        cls = "tile wide" if is_wide else "tile"
        # Use relative path under the HTML file.
        src = urllib.parse.quote(f"{tiles_dir.name}/{fname}")
        parts.append(f'<figure class="{cls}">')
        parts.append(f'<img src="{src}" />')
        if cap:
            parts.append(f"<figcaption>{html.escape(cap)}</figcaption>")
        parts.append("</figure>")

    parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")

    html_path.write_text("\n".join(parts), encoding="utf-8")


def _print_html_to_pdf(html_path: Path, pdf_path: Path, canvas_size_px: tuple[int, int], cfg: RenderConfig) -> None:
    """
    Use Playwright+Chromium to print the HTML into a fixed-size PDF.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Playwright is required for --layout-engine html.\n"
            "Install:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium\n"
            f"Import error: {e!r}"
        ) from e

    canvas_w_px, canvas_h_px = canvas_size_px
    w_in = canvas_w_px / float(cfg.dpi)
    h_in = canvas_h_px / float(cfg.dpi)

    url = _path_to_file_url(html_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle")
        page.emulate_media(media="print")
        page.pdf(
            path=str(pdf_path),
            print_background=True,
            width=f"{w_in:.6f}in",
            height=f"{h_in:.6f}in",
            margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"},
            prefer_css_page_size=True,
        )
        browser.close()


def render_tiles_via_html_to_png(
    tiles: list[Image.Image],
    captions: list[str],
    canvas_size_px: tuple[int, int],
    out_dir: Path,
    cfg: RenderConfig,
    start_idx: int,
) -> list[dict[str, float]]:
    """
    Render tiles into paginated PNG pages via:
      tiles -> local PNG files -> HTML/CSS -> Chromium print PDF -> PyMuPDF rasterize PNG
    Returns per-page stats (basic).
    """
    if not tiles:
        return []

    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)

    tile_files: list[str] = []
    tile_is_wide: list[bool] = []
    for i, tile in enumerate(tiles):
        fname = f"tile_{i:04d}.png"
        tile.save(tiles_dir / fname)
        tile_files.append(fname)
        ratio = tile.width / max(1.0, float(tile.height))
        tile_is_wide.append(ratio >= cfg.wide_ratio)

    html_path = out_dir / "layout.html"
    pdf_path = out_dir / "layout.pdf"
    _write_html_masonry_document(
        html_path=html_path,
        tiles_dir=tiles_dir,
        tile_files=tile_files,
        captions=captions,
        tile_is_wide=tile_is_wide,
        canvas_size_px=canvas_size_px,
        cfg=cfg,
    )

    _print_html_to_pdf(html_path=html_path, pdf_path=pdf_path, canvas_size_px=canvas_size_px, cfg=cfg)

    # Rasterize each PDF page into PNGs matching the cover dpi.
    doc = fitz.open(pdf_path)
    zoom = cfg.dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    stats: list[dict[str, float]] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.save(out_dir / f"{(start_idx + i):02d}.png")
        stats.append({"page": float(i + 1), "tiles": float(len(tiles))})
    doc.close()
    return stats


def _wrap_lines_pdf(text: str, font_name: str, font_size_pt: float, max_width_pt: float, max_lines: int) -> list[str]:
    """
    Wrap text into lines by measuring with ReportLab stringWidth.
    """
    try:
        from reportlab.pdfbase import pdfmetrics  # type: ignore
    except Exception:
        # Fallback: rough wrap by character count
        max_chars = max(1, int(max_width_pt / max(font_size_pt, 1.0) * 1.6))
        lines = textwrap.wrap(text, width=max_chars)
        return lines[:max_lines]

    words = text.replace("\n", " ").split()
    if not words:
        return []
    lines: list[str] = []
    current: list[str] = []
    truncated = False
    for w in words:
        test = " ".join(current + [w])
        if pdfmetrics.stringWidth(test, font_name, font_size_pt) <= max_width_pt:
            current.append(w)
            continue
        if current:
            lines.append(" ".join(current))
        current = [w]
        if len(lines) >= max_lines:
            truncated = True
            break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    if truncated and lines:
        last = lines[-1]
        ellipsis = "..."
        while pdfmetrics.stringWidth(last + ellipsis, font_name, font_size_pt) > max_width_pt and last:
            last = last[:-1].rstrip()
        lines[-1] = (last + ellipsis) if last else ellipsis
    return lines


def _pack_tiles_justified_rows(
    tiles: list[Image.Image],
    captions: list[str],
    canvas_size_px: tuple[int, int],
    cfg: RenderConfig,
) -> list[list[dict[str, float]]]:
    """
    Justified-rows layout with explicit pagination.
    Returns pages -> rows -> placement dicts (all coords in px from content top-left).
    """
    canvas_w_px, canvas_h_px = canvas_size_px
    padding_px = max(1, int(canvas_w_px * cfg.masonry_padding_ratio))
    gutter_px = max(1, int(canvas_w_px * cfg.masonry_gutter_ratio))
    available_w = max(1, canvas_w_px - 2 * padding_px)
    available_h = max(1, canvas_h_px - 2 * padding_px)

    target_row_h = max(80, int(available_w / max(1.0, (cfg.masonry_columns + 0.5))))
    pages: list[list[dict[str, float]]] = []
    current_page: list[dict[str, float]] = []
    used_h = 0.0

    def flush_page():
        nonlocal current_page, used_h
        if current_page:
            pages.append(current_page)
        current_page = []
        used_h = 0.0

    row_tiles: list[tuple[int, float]] = []
    row_ratio_sum = 0.0

    def emit_row(row_tiles_local: list[tuple[int, float]], row_ratio_sum_local: float, row_height: float):
        nonlocal used_h, current_page
        if not row_tiles_local:
            return
        row_count = len(row_tiles_local)
        total_row_w = row_height * row_ratio_sum_local + gutter_px * max(0, row_count - 1)
        if total_row_w > 0:
            scale = available_w / total_row_w
        else:
            scale = 1.0
        row_h = row_height * scale

        placements: list[dict[str, float]] = []
        x = 0.0
        max_tile_total_h = 0.0
        for idx, ratio in row_tiles_local:
            w = row_h * ratio
            h = row_h
            cap = captions[idx] if idx < len(captions) else ""
            # estimate caption height in px based on line count
            if cap:
                max_width_pt = (w * 72.0 / cfg.dpi) - (cfg.caption_bar_padding * 2 * 72.0 / cfg.dpi)
                font_size_pt = cfg.caption_font_size * 72.0 / cfg.dpi
                lines = _wrap_lines_pdf(cap, "Helvetica", font_size_pt, max(1.0, max_width_pt), cfg.caption_max_lines)
                line_h_px = (cfg.caption_font_size * 1.22)
                text_h_px = max(1, len(lines)) * line_h_px
                cap_h_px = text_h_px + cfg.caption_bar_padding * 2
                cap_total_px = cap_h_px + cfg.caption_image_spacing
            else:
                cap_h_px = 0.0
                cap_total_px = 0.0
            max_tile_total_h = max(max_tile_total_h, h + cap_total_px)
            placements.append(
                {
                    "tile_idx": float(idx),
                    "x": x,
                    "y": used_h,
                    "w": w,
                    "h": h,
                    "cap_h": cap_h_px,
                }
            )
            x += w + gutter_px

        # paginate
        if used_h + max_tile_total_h > available_h and used_h > 0:
            flush_page()
            # reset y positions for new page
            for p in placements:
                p["y"] = used_h

        current_page.extend(placements)
        used_h += max_tile_total_h + gutter_px

    for i, tile in enumerate(tiles):
        ratio = tile.width / max(1.0, float(tile.height))
        if ratio >= cfg.wide_ratio:
            if row_tiles:
                emit_row(
                    row_tiles,
                    row_ratio_sum,
                    (available_w - gutter_px * (len(row_tiles) - 1)) / max(row_ratio_sum, 1.0),
                )
                row_tiles = []
                row_ratio_sum = 0.0
            # wide tile occupies full row
            row_tiles = [(i, ratio)]
            row_ratio_sum = ratio
            emit_row(row_tiles, row_ratio_sum, available_w / max(ratio, 1e-6))
            row_tiles = []
            row_ratio_sum = 0.0
            continue

        row_tiles.append((i, ratio))
        row_ratio_sum += ratio
        if len(row_tiles) >= 1:
            row_h = (available_w - gutter_px * (len(row_tiles) - 1)) / max(row_ratio_sum, 1.0)
            if row_h <= target_row_h * 1.15:
                emit_row(row_tiles, row_ratio_sum, row_h)
                row_tiles = []
                row_ratio_sum = 0.0

    if row_tiles:
        row_h = (available_w - gutter_px * (len(row_tiles) - 1)) / max(row_ratio_sum, 1.0)
        emit_row(row_tiles, row_ratio_sum, row_h)

    if current_page:
        pages.append(current_page)
    return pages


def render_tiles_via_reportlab_to_png(
    tiles: list[Image.Image],
    captions: list[str],
    canvas_size_px: tuple[int, int],
    out_dir: Path,
    cfg: RenderConfig,
    start_idx: int,
) -> list[dict[str, float]]:
    """
    Deterministic layout: justified rows -> ReportLab PDF -> PyMuPDF rasterize PNG.
    """
    if not tiles:
        return []

    try:
        from reportlab.pdfgen import canvas as rl_canvas  # type: ignore
        from reportlab.lib.utils import ImageReader  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "ReportLab is required for --layout-engine reportlab.\n"
            "Install:\n"
            "  pip install reportlab\n"
            f"Import error: {e!r}"
        ) from e

    tiles_dir = out_dir / "tiles_reportlab"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    tile_paths: list[Path] = []
    for i, tile in enumerate(tiles):
        fname = f"tile_{i:04d}.png"
        path = tiles_dir / fname
        tile.save(path)
        tile_paths.append(path)

    pages = _pack_tiles_justified_rows(tiles, captions, canvas_size_px, cfg)

    canvas_w_px, canvas_h_px = canvas_size_px
    w_pt = canvas_w_px * 72.0 / cfg.dpi
    h_pt = canvas_h_px * 72.0 / cfg.dpi
    padding_px = max(1, int(canvas_w_px * cfg.masonry_padding_ratio))
    padding_pt = padding_px * 72.0 / cfg.dpi
    gutter_px = max(1, int(canvas_w_px * cfg.masonry_gutter_ratio))
    gutter_pt = gutter_px * 72.0 / cfg.dpi

    pdf_path = out_dir / "layout_reportlab.pdf"
    c = rl_canvas.Canvas(str(pdf_path), pagesize=(w_pt, h_pt))

    font_name = "Helvetica"
    font_size_pt = cfg.caption_font_size * 72.0 / cfg.dpi
    pad_pt = cfg.caption_bar_padding * 72.0 / cfg.dpi
    caption_spacing_pt = cfg.caption_image_spacing * 72.0 / cfg.dpi

    for page_idx, placements in enumerate(pages):
        for p in placements:
            idx = int(p["tile_idx"])
            if idx < 0 or idx >= len(tile_paths):
                continue
            img_path = tile_paths[idx]
            x_px = padding_px + p["x"]
            y_px_top = padding_px + p["y"]
            w_px = p["w"]
            h_px = p["h"]

            # Convert to bottom-left coordinates in points
            x = x_px * 72.0 / cfg.dpi
            y = (canvas_h_px - (y_px_top + h_px)) * 72.0 / cfg.dpi
            w = w_px * 72.0 / cfg.dpi
            h = h_px * 72.0 / cfg.dpi

            c.drawImage(ImageReader(str(img_path)), x, y, width=w, height=h, preserveAspectRatio=False, mask="auto")

            cap = captions[idx] if idx < len(captions) else ""
            if cap:
                cap_h_px = p.get("cap_h", 0.0)
                if cap_h_px > 0:
                    cap_h_pt = cap_h_px * 72.0 / cfg.dpi
                    cap_x = x
                    cap_y_top_px = y_px_top + h_px + cfg.caption_image_spacing
                    cap_y = (canvas_h_px - (cap_y_top_px + cap_h_px)) * 72.0 / cfg.dpi
                    cap_w = w

                    # background rect
                    c.setFillColorRGB(cfg.caption_bg[0] / 255.0, cfg.caption_bg[1] / 255.0, cfg.caption_bg[2] / 255.0)
                    c.rect(cap_x, cap_y, cap_w, cap_h_pt, stroke=0, fill=1)

                    # text
                    c.setFillColorRGB(cfg.caption_color[0] / 255.0, cfg.caption_color[1] / 255.0, cfg.caption_color[2] / 255.0)
                    c.setFont(font_name, font_size_pt)
                    max_width_pt = max(1.0, cap_w - pad_pt * 2)
                    lines = _wrap_lines_pdf(cap, font_name, font_size_pt, max_width_pt, cfg.caption_max_lines)
                    line_h_pt = font_size_pt * 1.22
                    text_x = cap_x + pad_pt
                    text_y = cap_y + cap_h_pt - pad_pt - line_h_pt
                    for line in lines:
                        c.drawString(text_x, text_y, line)
                        text_y -= line_h_pt

        c.showPage()

    c.save()

    # Rasterize to PNG
    doc = fitz.open(pdf_path)
    zoom = cfg.dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    stats: list[dict[str, float]] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.save(out_dir / f"{(start_idx + i):02d}.png")
        stats.append({"page": float(i + 1), "tiles": float(len(tiles))})
    doc.close()
    return stats


def pack_tiles_masonry(tiles: list[Image.Image], canvas_size: tuple[int, int], cfg: RenderConfig):
    if not tiles:
        return [], []
    canvas_w, canvas_h = canvas_size
    padding = max(1, int(canvas_w * cfg.masonry_padding_ratio))
    gutter = max(1, int(canvas_w * cfg.masonry_gutter_ratio))
    cols = choose_columns(tiles, cfg)
    available_w = max(1, canvas_w - 2 * padding - gutter * (cols - 1))
    col_w = available_w / float(cols)
    available_h = max(1, canvas_h - 2 * padding)
    per_page = max(1, cfg.tiles_per_page)

    pages: list[Image.Image] = []
    stats: list[dict[str, float]] = []
    idx = 0

    def layout_page(page_tiles: list[Image.Image], scale: float):
        col_heights = [0.0 for _ in range(cols)]
        placements: list[dict[str, object]] = []
        for tile in page_tiles:
            base_scale = col_w / float(tile.width)
            # 修复：确保最终宽度不超过列宽
            # scale_fit应该同时考虑宽度和高度约束，但宽度约束必须严格
            height_scale = available_h / float(tile.height) if tile.height > 0 else base_scale
            # 关键修复：宽度缩放不能超过base_scale（即不能超过列宽）
            # 高度缩放可以更大，但宽度必须受限于列宽
            width_scale = base_scale * min(scale, 1.0)  # scale只影响高度，不影响宽度
            height_scale_unconstrained = base_scale * scale
            # 取两者中较小的，但确保宽度不超过列宽
            scale_fit = min(width_scale, height_scale_unconstrained, height_scale)
            # 再次确保宽度不超过列宽
            tw = max(1, int(tile.width * scale_fit))
            th = max(1, int(tile.height * scale_fit))
            # 强制约束：如果宽度超过列宽，重新计算
            if tw > col_w:
                scale_fit = col_w / float(tile.width)
                tw = int(col_w)
                th = max(1, int(tile.height * scale_fit))
            col_idx = min(range(cols), key=lambda i: col_heights[i])
            y = col_heights[col_idx]
            # 确保x坐标不会导致重叠
            x = max(0.0, col_idx * (col_w + gutter) + (col_w - tw) / 2.0)
            # 确保不会超出列边界
            x = min(x, col_idx * (col_w + gutter) + col_w - tw)
            placements.append({"x": x, "y": y, "w": tw, "h": th, "tile": tile})
            col_heights[col_idx] += th + gutter
        return placements, col_heights

    while idx < len(tiles):
        page_tiles = tiles[idx : idx + per_page]
        idx += len(page_tiles)
        placements, col_heights = layout_page(page_tiles, 1.0)
        h_used = max(col_heights) if col_heights else 0.0
        if h_used > 0:
            target = cfg.masonry_target_fill * available_h
            if h_used < target:
                scale = min(cfg.masonry_scale_max, target / h_used)
                placements, col_heights = layout_page(page_tiles, scale)
                h_used = max(col_heights) if col_heights else h_used

        if len(page_tiles) == 1 and placements:
            tile = page_tiles[0]
            scale_fit = min(available_w / float(tile.width), available_h / float(tile.height))
            tw = max(1, int(tile.width * scale_fit))
            th = max(1, int(tile.height * scale_fit))
            placements = [{"x": (available_w - tw) / 2, "y": (available_h - th) / 2, "w": tw, "h": th, "tile": tile}]
            h_used = th

        page = Image.new("RGB", (canvas_w, canvas_h), "white")
        content_area = 0.0
        for p in placements:
            tile_img = p.get("tile")
            if isinstance(tile_img, Image.Image):
                if hasattr(Image, "Resampling"):
                    resample = Image.Resampling.LANCZOS
                else:
                    resample = getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", 3))
                w = float(p["w"])
                h = float(p["h"])
                x = float(p["x"])
                y = float(p["y"])
                # 边界保护：确保不会超出画布
                x_final = max(0, int(x + padding))
                y_final = max(0, int(y + padding))
                w_final = min(int(w), canvas_w - x_final)
                h_final = min(int(h), canvas_h - y_final)
                if w_final > 0 and h_final > 0:
                    tile = tile_img.resize((w_final, h_final), resample)
                    page.paste(tile, (x_final, y_final))
                    content_area += w_final * h_final
        pages.append(page)
        fill_ratio = content_area / float(canvas_w * canvas_h) if canvas_w * canvas_h else 0.0
        stats.append({"tiles": len(placements), "fill_ratio": fill_ratio, "height_used": h_used})

    return pages, stats


def render_first_page(pdf_path: Path, dpi: int) -> Image.Image:
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def resolve_output_dir(file_list_root: Path, date_str: str, stem: str) -> Path:
    return file_list_root / date_str / stem


def process_paper(paper_dir: Path, pdf_path: Path, out_dir: Path, cfg: RenderConfig):
    stem = paper_dir.name
    md_path = find_md_path(paper_dir, stem)
    if md_path is None:
        return {"stem": stem, "error": "md_not_found"}
    entries = parse_md_images(md_path)
    content_path = next(iter(paper_dir.glob("*_content_list.json")), None)
    figures: list[dict] = []
    captions: list[dict] = []
    if content_path:
        figures, captions = parse_content_items(content_path)
        # 改进：优先使用bbox匹配，不再使用顺序填充（这是错配的根源）
        assign_captions_by_bbox(entries, figures, captions, paper_dir)
        # 移除顺序填充逻辑，避免错配
        # if captions:
        #     assign_missing_captions(entries, [c["text"] for c in captions])

    # Stage 1: 分组逻辑 - 将属于同一个 Figure 的子图分组
    figure_groups = group_figures_by_proximity(entries, figures, captions)

    out_dir.mkdir(parents=True, exist_ok=True)
    cover = render_first_page(pdf_path, cfg.dpi)
    canvas_size = cover.size
    if cfg.save_cover:
        cover.save(out_dir / "01.png")

    tiles: list[Image.Image] = []
    captions_list: list[str] = []
    skipped: dict[str, int] = {}
    matched_meta: list[dict] = []
    used = 0
    
    # Stage 2: 处理每个 figure group
    for group in figure_groups:
        group_images = group.get("images", [])
        if not group_images:
            continue
        
        # 检查 group 是否应该保留（基于第一个 entry 的 heading 和 caption）
        first_entry = group_images[0].get("entry", {})
        keep, reason = keep_entry(first_entry, cfg)
        if not keep:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        
        # Stage 3: 拼接 group 内的子图
        try:
            composed_image, group_caption = compose_figure_group(group, paper_dir, cfg)
        except (FileNotFoundError, ValueError) as e:
            skipped["group_compose_error"] = skipped.get("group_compose_error", 0) + 1
            continue
        except Exception:
            skipped["group_compose_error"] = skipped.get("group_compose_error", 0) + 1
            continue
        
        # 检查是否是文本类图片
        if is_text_like(composed_image, cfg):
            skipped["text_like"] = skipped.get("text_like", 0) + 1
            continue
        
        # 对 group caption 进行最终纯化验证
        purified_caption, is_valid = purify_caption(group_caption)
        if not is_valid:
            # Caption 不可信，清空（避免正文污染）
            purified_caption = ""
        
        tiles.append(composed_image)
        captions_list.append(purified_caption)
        
        # 记录元数据
        image_rels = [img.get("entry", {}).get("image_rel", "") for img in group_images]
        matched_meta.append(
            {
                "group_id": group.get("group_id"),
                "image_rel": image_rels[0] if image_rels else "",  # 主图
                "image_rels": image_rels,  # 所有子图
                "heading": first_entry.get("heading", ""),
                "caption": purified_caption,
                "keep_reason": reason,
                "num_subfigures": len(group_images),
            }
        )
        used += 1

    start_idx = 2 if cfg.save_cover else 1
    page_stats: list[dict[str, float]] = []
    if cfg.layout_engine == "reportlab":
        try:
            page_stats = render_tiles_via_reportlab_to_png(tiles, captions_list, canvas_size, out_dir, cfg, start_idx=start_idx)
        except Exception as e:
            print(f"[SELECT_IMAGE] reportlab layout failed ({e!r}), fallback to PIL layout", flush=True)
            cfg.layout_engine = "pil"

    if cfg.layout_engine == "html":
        try:
            page_stats = render_tiles_via_html_to_png(tiles, captions_list, canvas_size, out_dir, cfg, start_idx=start_idx)
        except Exception as e:
            # Fail safe: fall back to legacy PIL layout if HTML engine is unavailable.
            print(f"[SELECT_IMAGE] html layout failed ({e!r}), fallback to PIL layout", flush=True)
            cfg.layout_engine = "pil"

    if cfg.layout_engine != "html":
        pages, page_stats = pack_tiles_hybrid(tiles, captions_list, canvas_size, cfg)
        for i, page in enumerate(pages, start=start_idx):
            page.save(out_dir / f"{i:02d}.png")

    report = {
        "stem": stem,
        "total_entries": len(entries),
        "used": used,
        "skipped": skipped,
        "pages": page_stats,
        "layout_engine": cfg.layout_engine,
        "items": matched_meta,
        "output_dir": str(out_dir),
    }
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def run() -> None:
    ap = argparse.ArgumentParser("select_image_mineru")
    ap.add_argument("--date", default="")
    ap.add_argument("--mineru-root", default=str(Path(DATA_ROOT) / "selectedpaper_to_mineru"))
    ap.add_argument("--pdf-root", default=str(Path(DATA_ROOT) / "selectedpaper"))
    ap.add_argument("--output-root", default="")
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--no-cover", dest="save_cover", action="store_false", default=True)
    ap.add_argument("--layout-engine", choices=["pil", "html", "reportlab"], default="pil", help="page layout engine for later pages")
    ap.add_argument("--caption-font-size", type=int, default=60)
    ap.add_argument("--caption-max-lines", type=int, default=3)
    ap.add_argument("--caption-font-path", default="")
    ap.add_argument("--tiles-per-page", type=int, default=3)
    ap.add_argument("--columns", type=int, default=2)
    ap.add_argument("--padding-ratio", type=float, default=0.03)
    ap.add_argument("--gutter-ratio", type=float, default=0.015)
    ap.add_argument("--target-fill", type=float, default=0.96)
    ap.add_argument("--scale-max", type=float, default=1.25)
    ap.add_argument("--wide-ratio", type=float, default=1.3)
    ap.add_argument("--nonwhite-min-ratio", type=float, default=0.02)
    ap.add_argument("--edge-density-max", type=float, default=0.22)
    ap.add_argument("--textlike-edge-max", type=float, default=0.18)
    ap.add_argument("--caption-strip-ratio", type=float, default=0.22)
    ap.add_argument("--caption-strip-max-ratio", type=float, default=0.45)
    ap.add_argument("--caption-strip-min-px", type=int, default=12)
    ap.add_argument("--caption-image-spacing", type=int, default=12, help="间距（像素）between image and caption blocks")
    ap.add_argument("--keep-embedded-caption", dest="remove_embedded_caption", action="store_false", default=True)
    ap.add_argument("--all-figures", dest="results_only", action="store_false", default=True)
    ap.add_argument("--heading-positive", default="results,experiments,evaluation,ablation,analysis,benchmark")
    ap.add_argument("--heading-negative", default="method,approach,architecture,model")
    ap.add_argument("--caption-positive", default="result,experiment,ablation,evaluation,performance,accuracy,roc,ece,benchmark")
    ap.add_argument("--caption-negative", default="")
    args = ap.parse_args()

    mineru_root = Path(args.mineru_root)
    mineru_dir, date_str = select_date_dir(mineru_root, args.date)
    pdf_root = Path(args.pdf_root) / date_str
    output_root = Path(args.output_root) if args.output_root else Path(DATA_ROOT) / "select_image"

    cfg = RenderConfig(
        dpi=args.dpi,
        save_cover=args.save_cover,
        layout_engine=args.layout_engine,
        caption_font_size=args.caption_font_size,
        caption_max_lines=args.caption_max_lines,
        caption_font_path=args.caption_font_path,
        masonry_columns=args.columns,
        masonry_padding_ratio=args.padding_ratio,
        masonry_gutter_ratio=args.gutter_ratio,
        masonry_target_fill=args.target_fill,
        masonry_scale_max=args.scale_max,
        tiles_per_page=args.tiles_per_page,
        wide_ratio=args.wide_ratio,
        nonwhite_min_ratio=args.nonwhite_min_ratio,
        edge_density_max=args.edge_density_max,
        textlike_edge_max=args.textlike_edge_max,
        remove_embedded_caption=args.remove_embedded_caption,
        caption_strip_ratio=args.caption_strip_ratio,
        caption_strip_max_ratio=args.caption_strip_max_ratio,
        caption_strip_min_px=args.caption_strip_min_px,
        caption_image_spacing=args.caption_image_spacing,
        results_only=args.results_only,
        heading_positive=[k.strip() for k in args.heading_positive.split(",") if k.strip()],
        heading_negative=[k.strip() for k in args.heading_negative.split(",") if k.strip()],
        caption_positive=[k.strip() for k in args.caption_positive.split(",") if k.strip()],
        caption_negative=[k.strip() for k in args.caption_negative.split(",") if k.strip()],
    )

    if not mineru_dir.exists():
        raise SystemExit(f"mineru dir not found: {mineru_dir}")
    if not pdf_root.exists():
        raise SystemExit(f"pdf dir not found: {pdf_root}")

    print("============开始选择论文图片==============", flush=True)
    reports = []
    for paper_dir in list_paper_dirs(mineru_dir):
        stem = paper_dir.name
        pdf_path = pdf_root / f"{stem}.pdf"
        if not pdf_path.exists():
            reports.append({"stem": stem, "error": "pdf_not_found"})
            continue
        out_dir = resolve_output_dir(output_root, date_str, stem)
        report = process_paper(paper_dir, pdf_path, out_dir, cfg)
        reports.append(report)

    summary = {
        "date": date_str,
        "total": len(reports),
        "success": sum(1 for r in reports if not r.get("error")),
        "reports": reports,
    }
    summary_path = output_root / date_str / f"select_image_{date_str}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SELECT_IMAGE] done total={summary['total']} success={summary['success']} summary={summary_path}")
    print("============结束选择论文图片==============", flush=True)


if __name__ == "__main__":
    run()
