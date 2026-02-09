from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# 假设你的配置文件路径是正确的，如果报错请调整
# sys.path.append(os.path.dirname(os.path.dirname(__file__)))
# from config.config import DATA_ROOT  # noqa: E402

# 为了方便你在本地直接运行测试，我先模拟一个 DATA_ROOT，
# 实际使用时请取消上面的注释，删掉下面这一行
DATA_ROOT = "./data" 


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def today_str() -> str:
    return datetime.now().date().isoformat()


def load_paper_assets(date_str: str) -> List[Dict[str, Any]]:
    """从 data/paper_assets/{date_str}.jsonl 加载全部论文记录。"""
    # 兼容处理：如果没有传日期，尝试读取当前目录下的测试文件，或者构建路径
    if not date_str:
        date_str = today_str()
        
    assets_path = Path(DATA_ROOT) / "paper_assets" / f"{date_str}.jsonl"
    
    # 如果文件不存在，为了演示方便，我这里加一个 mock 数据判定
    # 实际部署时请删掉这个 if not exists 的逻辑，保留 return [] 即可
    if not assets_path.exists():
        print(f"[PAPER_ASSETS_VIS] 文件不存在: {assets_path} (请确保有数据文件)", flush=True)
        return []

    records: List[Dict[str, Any]] = []
    with assets_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _safe_print(text: str) -> None:
    """在 Windows 终端安全输出含 Unicode 的字符串。"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding), flush=True)


def get_db_path() -> Path:
    """返回 SQLite 数据库文件路径，自动创建父目录。"""
    db_dir = Path(DATA_ROOT).parent / "database"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "paper_analysis.db"


# ---------------------------------------------------------------------------
# 可视化函数 1 —— 实验结果提取 (现有功能)
# ---------------------------------------------------------------------------

def parse_results_table(paper_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 blocks.results.bullets 提取结构化实验数据"""
    paper_id = paper_json.get("paper_id", "")
    title = paper_json.get("title", "")
    blocks = paper_json.get("blocks", {})
    if not isinstance(blocks, dict): return []
    
    results_block = blocks.get("results", {})
    bullets = results_block.get("bullets", [])
    if not isinstance(bullets, list): return []

    rows: List[Dict[str, Any]] = []

    for bullet in bullets:
        if not isinstance(bullet, str): continue

        # 模式 1: "Task：Metric = Score (±Delta)"
        m = re.search(r"(.*?)[：:](.*?)[=≈]\s*([\d\.]+%?)\s*\(([\+\-↑↓][\d\.]+%?)", bullet)
        if m:
            rows.append({
                "Paper_ID": paper_id,
                "Title": title,
                "Task": m.group(1).strip(),
                "Metric": m.group(2).strip(),
                "Score": m.group(3).strip(),
                "Improvement": m.group(4).strip(),
            })
            continue

        # 模式 2: "Task：Metric = ±Score"
        m = re.search(r"(.*?)[：:](.*?)[=≈]\s*([\+\-↑↓][\d\.]+%?(?:\s*(?:pts|points|分))?)", bullet)
        if m:
            rows.append({
                "Paper_ID": paper_id,
                "Title": title,
                "Task": m.group(1).strip(),
                "Metric": m.group(2).strip(),
                "Score": m.group(3).strip(),
                "Improvement": m.group(3).strip(),
            })
            continue

    return rows


def visualize_results(papers: List[Dict[str, Any]]) -> pd.DataFrame:
    """生成实验结果 DataFrame"""
    if not papers: return pd.DataFrame()
    all_rows = []
    for paper in papers:
        all_rows.extend(parse_results_table(paper))
    return pd.DataFrame(all_rows)


# ---------------------------------------------------------------------------
# 可视化函数 2 —— 方法论提取 (新增功能)
# ---------------------------------------------------------------------------

def parse_method_row(paper_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 blocks.method.bullets 中解析 【Key】：Value 结构。
    返回一行字典，Key 为 'Paper_ID', 'Title' 以及提取到的方法标签。
    """
    paper_id = paper_json.get("paper_id", "")
    title = paper_json.get("title", "")
    
    # 基础行数据
    row = {"Paper_ID": paper_id, "Title": title}
    
    blocks = paper_json.get("blocks", {})
    if not isinstance(blocks, dict): return row
    
    method_block = blocks.get("method", {})
    bullets = method_block.get("bullets", [])
    if not isinstance(bullets, list): return row

    # 正则：匹配 【Key】：Value 或 【Key】: Value
    # 忽略前导空格
    pattern = re.compile(r"^\s*【(.*?)】[：:]\s*(.*)$")

    for bullet in bullets:
        if not isinstance(bullet, str): continue
        match = pattern.match(bullet)
        if match:
            key = match.group(1).strip()
            val = match.group(2).strip()
            # 将提取到的 Key 直接放入 row 中
            row[key] = val
        else:
            # 如果没有按格式写，也可以选择放入 "备注" 字段
            pass
            
    return row


def visualize_methods(papers: List[Dict[str, Any]]) -> pd.DataFrame:
    """生成方法论对比 DataFrame"""
    if not papers: return pd.DataFrame()
    
    all_rows = []
    for paper in papers:
        all_rows.append(parse_method_row(paper))
    
    df = pd.DataFrame(all_rows)
    
    # --- 列排序美化 ---
    # 我们希望某些重要的列排在前面，而不是按字母顺序乱排
    priority_cols = ["Paper_ID", "Title", "是否训练", "输入", "架构", "关键机制", "创新点"]
    
    # 找出 DataFrame 中实际存在的列
    existing_cols = df.columns.tolist()
    
    # 1. 先放 Priority 中存在的列
    final_cols = [c for c in priority_cols if c in existing_cols]
    
    # 2. 再放剩下的列
    final_cols += [c for c in existing_cols if c not in final_cols]
    
    # --- 归一化 "是否训练" 列 ---
    if "是否训练" in df.columns:
        def _normalize_training(val: Any) -> str:
            if not isinstance(val, str) or not val.strip():
                return str(val)
            s = val.strip()
            if s.startswith("是") or s.lower().startswith("yes"):
                return "YES"
            if s.startswith("否") or s.lower().startswith("no"):
                return "NO"
            return s
        df["是否训练"] = df["是否训练"].apply(_normalize_training)

    return df[final_cols]


# ---------------------------------------------------------------------------
# SQLite 持久化
# ---------------------------------------------------------------------------

def init_db(conn: sqlite3.Connection) -> None:
    """创建 3 张表（如不存在）。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            paper_id   TEXT    NOT NULL,
            title      TEXT,
            url        TEXT,
            year       INTEGER,
            date       TEXT    NOT NULL,
            blocks_json TEXT,
            PRIMARY KEY (paper_id, date)
        );

        CREATE TABLE IF NOT EXISTS results (
            paper_id    TEXT NOT NULL,
            title       TEXT,
            task        TEXT,
            metric      TEXT,
            score       TEXT,
            improvement TEXT,
            date        TEXT NOT NULL,
            PRIMARY KEY (paper_id, task, metric, date)
        );

        CREATE TABLE IF NOT EXISTS methods (
            paper_id      TEXT NOT NULL,
            title         TEXT,
            is_training   TEXT,
            input         TEXT,
            architecture  TEXT,
            key_mechanism TEXT,
            innovation    TEXT,
            date          TEXT NOT NULL,
            PRIMARY KEY (paper_id, date)
        );
    """)


# 方法论 DataFrame 中文列名 → DB 英文列名 的映射
_METHOD_COL_MAP: Dict[str, str] = {
    "Paper_ID":  "paper_id",
    "Title":     "title",
    "是否训练":   "is_training",
    "输入":      "input",
    "架构":      "architecture",
    "关键机制":   "key_mechanism",
    "创新点":    "innovation",
}


def save_to_db(
    date_str: str,
    papers: List[Dict[str, Any]],
    df_results: pd.DataFrame,
    df_methods: pd.DataFrame,
) -> None:
    """将原始论文数据与分析结果写入 SQLite（同日期覆盖模式）。"""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        cur = conn.cursor()

        # ---------- 1. 清除该日期旧数据 ----------
        for table in ("papers", "results", "methods"):
            cur.execute(f"DELETE FROM {table} WHERE date = ?", (date_str,))

        # ---------- 2. 写入 papers 基表 ----------
        for p in papers:
            cur.execute(
                "INSERT INTO papers (paper_id, title, url, year, date, blocks_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    p.get("paper_id", ""),
                    p.get("title", ""),
                    p.get("url", ""),
                    p.get("year"),
                    date_str,
                    json.dumps(p.get("blocks", {}), ensure_ascii=False),
                ),
            )

        # ---------- 3. 写入 results 表 ----------
        if not df_results.empty:
            for _, row in df_results.iterrows():
                cur.execute(
                    "INSERT INTO results "
                    "(paper_id, title, task, metric, score, improvement, date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        row.get("Paper_ID", ""),
                        row.get("Title", ""),
                        row.get("Task", ""),
                        row.get("Metric", ""),
                        row.get("Score", ""),
                        row.get("Improvement", ""),
                        date_str,
                    ),
                )

        # ---------- 4. 写入 methods 表 ----------
        if not df_methods.empty:
            for _, row in df_methods.iterrows():
                cur.execute(
                    "INSERT INTO methods "
                    "(paper_id, title, is_training, input, architecture, "
                    "key_mechanism, innovation, date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row.get("Paper_ID", ""),
                        row.get("Title", ""),
                        row.get("是否训练", ""),
                        row.get("输入", ""),
                        row.get("架构", ""),
                        row.get("关键机制", ""),
                        row.get("创新点", ""),
                        date_str,
                    ),
                )

        conn.commit()
        _safe_print(
            f"[PAPER_ASSETS_ANALYSIS] Saved to {db_path} "
            f"({len(papers)} papers, {len(df_results)} results, "
            f"{len(df_methods)} methods)"
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def run() -> None:
    ap = argparse.ArgumentParser("paper_assets_analysis")
    ap.add_argument("--date", default="", help="日期字符串，如 2026-02-07；默认为今天")
    args = ap.parse_args()

    date_str = args.date.strip() if args.date else ""
    if not date_str:
        env_date = os.environ.get("RUN_DATE", "").strip()
        date_str = env_date if env_date else today_str()

    _safe_print(f"[PAPER_ASSETS_VIS] 日期={date_str}")
    
    # 1. 加载数据 (只读取一次)
    papers = load_paper_assets(date_str)
    if not papers:
        _safe_print("[PAPER_ASSETS_VIS] 未找到任何论文数据。")
        return

    # 2. 展示实验结果表 (原有功能)
    df_results = visualize_results(papers)
    if df_results.empty:
        _safe_print("[PAPER_ASSETS_VIS] 未提取到实验结果数据")
    else:
        _safe_print("\n" + "="*50)
        _safe_print(" >>> 🏆 实验结果排行榜 (Results Leaderboard)")
        _safe_print("="*50)
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 200)
        pd.set_option("display.max_colwidth", 40)
        _safe_print(df_results.to_string(index=False))

    # 3. 展示方法论表 (新增功能)
    df_methods = visualize_methods(papers)
    if df_methods.empty:
        _safe_print("[PAPER_ASSETS_VIS] 未提取到方法论数据")
    else:
        _safe_print("\n" + "="*50)
        _safe_print(" >>> 🛠️ 技术流派兵器谱 (Methodology Specs)")
        _safe_print("="*50)
        # 调整显示宽度，因为 Method 里的文字通常比较长
        pd.set_option("display.max_colwidth", 30) 
        _safe_print(df_methods.to_string(index=False))
        
    # 4. 持久化到 SQLite
    save_to_db(date_str, papers, df_results, df_methods)

    _safe_print(f"\n[Summary] 共加载 {len(papers)} 篇论文。")


if __name__ == "__main__":
    run()