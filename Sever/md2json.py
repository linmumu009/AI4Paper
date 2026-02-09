"""
md2json.py
将 data/file_collect/{date}/ 下的 *_limit.md 文件逐个转换为 JSON，
输出到 database/summary_limit/json/{date}/ 目录。

用法:
    python md2json.py                    # 自动使用今天日期
    python md2json.py 2026-02-07         # 指定日期
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

# ---------- 路径配置 ----------
BASE_DIR = Path(__file__).resolve().parent
INPUT_ROOT = BASE_DIR / "data" / "file_collect"
OUTPUT_ROOT = BASE_DIR / "database" / "summary_limit" / "json"


def parse_limit_md(text: str) -> dict:
    """将一篇 *_limit.md 的文本解析为结构化字典。"""
    lines = text.strip().splitlines()
    result: dict = {}

    # ---------- 头部三行 ----------
    if len(lines) >= 1:
        header = lines[0]
        if ":" in header:
            parts = header.split(":", 1)
            result["institution"] = parts[0].strip()
            result["short_title"] = parts[1].strip()
        elif "：" in header:
            parts = header.split("：", 1)
            result["institution"] = parts[0].strip()
            result["short_title"] = parts[1].strip()
        else:
            result["header"] = header.strip()

    if len(lines) >= 2:
        title_line = lines[1]
        m = re.search(r"[标题][：:]\s*(.*)", title_line)
        result["📖标题"] = m.group(1).strip() if m else title_line.strip()

    if len(lines) >= 3:
        source_line = lines[2]
        m = re.search(r"[来源][：:]\s*(.*)", source_line)
        if m:
            parts = [p.strip() for p in m.group(1).split(",")]
            result["🌐来源"] = parts[0] if parts else ""
            result["paper_id"] = parts[1] if len(parts) > 1 else ""
        else:
            result["🌐来源"] = source_line.strip()

    # ---------- 分节解析 ----------
    section_map = {
        "文章简介": "🛎️文章简介",
        "重点思路": "📝重点思路",
        "分析总结": "🔎分析总结",
        "个人观点": "💡个人观点",
    }

    current_section = None
    section_items: dict[str, list[str]] = {v: [] for v in section_map.values()}

    for line in lines[3:]:
        line = line.strip()
        if not line:
            continue

        # 检测分节标题
        matched_section = None
        for zh_name, en_name in section_map.items():
            if zh_name in line:
                matched_section = en_name
                break
        if matched_section:
            current_section = matched_section
            continue

        if current_section is None:
            continue

        # 保留 🔸 emoji
        section_items[current_section].append(line)

    # ---------- 结构化子字段 ----------
    intro = section_items.get("🛎️文章简介", [])
    intro_dict: dict = {}
    for item in intro:
        # 去掉 🔸 后检测子字段名称，但值里保留 🔸
        clean = re.sub(r"^🔸\s*", "", item)
        if clean.startswith("研究问题"):
            intro_dict["🔸研究问题"] = re.sub(r"^研究问题[:：]\s*", "", clean)
        elif clean.startswith("主要贡献"):
            intro_dict["🔸主要贡献"] = re.sub(r"^主要贡献[:：]\s*", "", clean)
        else:
            intro_dict.setdefault("other", []).append(item)
    result["🛎️文章简介"] = intro_dict

    result["📝重点思路"] = section_items.get("📝重点思路", [])
    result["🔎分析总结"] = section_items.get("🔎分析总结", [])

    opinion_items = section_items.get("💡个人观点", [])
    result["💡个人观点"] = "\n".join(opinion_items) if opinion_items else ""

    return result


def convert_folder(target_date: str) -> None:
    """转换指定日期文件夹下的所有 *_limit.md → JSON。"""
    input_dir = INPUT_ROOT / target_date
    output_dir = OUTPUT_ROOT / target_date

    if not input_dir.exists():
        print(f"[错误] 输入目录不存在: {input_dir}")
        sys.exit(1)

    md_files = sorted(input_dir.rglob("*_limit.md"))
    if not md_files:
        print(f"[警告] 未找到 *_limit.md 文件: {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"输入目录 : {input_dir}")
    print(f"输出目录 : {output_dir}")
    print(f"待转换文件: {len(md_files)} 个\n")

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        data = parse_limit_md(text)

        # 用 paper_id 或原文件名作为输出文件名
        stem = md_path.stem  # e.g. "2602.05810_limit"
        json_name = stem.replace("_limit", "") + ".json"
        json_path = output_dir / json_name

        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  [OK] {md_path.name}  ->  {json_name}")

    print(f"\n完成，共转换 {len(md_files)} 个文件。")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = date.today().strftime("%Y-%m-%d")
    convert_folder(target)
