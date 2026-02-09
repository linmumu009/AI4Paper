from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from openai import OpenAI

import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config.config import (
    qwen_api_key,
    summary_base_url,
    summary_model,
    summary_base_url_2,
    summary_gptgod_apikey,
    summary_model_2,
    summary_base_url_3,
    summary_apikey_3,
    summary_model_3,
    summary_max_tokens,
    summary_temperature,
    summary_input_hard_limit,
    summary_input_safety_margin,
    summary_concurrency,
    system_prompt,
    DATA_ROOT,
    SLLM,
)


def approx_input_tokens(text: str) -> int:
    if not text:
        return 0
    return len(text.encode("utf-8", errors="ignore"))


def crop_to_input_tokens(text: str, limit_tokens: int) -> str:
    budget = int(limit_tokens)
    if budget <= 0:
        return ""
    b = text.encode("utf-8", errors="ignore")
    if len(b) <= budget:
        return text
    return b[:budget].decode("utf-8", errors="ignore")


def list_md_files(root: Path) -> List[Path]:
    return sorted(root.rglob("*.md"))


def today_str() -> str:
    return datetime.now().date().isoformat()


def write_gather(single_dir: Path, gather_dir: Path, date_str: str) -> Path:
    files = list_md_files(single_dir)
    gather_dir.mkdir(parents=True, exist_ok=True)
    gather_path = gather_dir / f"{date_str}.txt"
    with gather_path.open("w", encoding="utf-8") as f:
        first = True
        for p in files:
            text = p.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            if not first:
                f.write("\n")
            first = False
            f.write("#" * 100 + "\n")
            f.write(f"{p.name}\n")
            f.write("#" * 100 + "\n")
            f.write(text)
            f.write("\n")
    return gather_path


def make_client() -> OpenAI:
    # 根据 SLLM 选择不同的大模型服务与密钥
    if SLLM == 2:
        key = (summary_gptgod_apikey or "").strip()
        if not key:
            raise SystemExit("summary_gptgod_apikey missing in config.config")
        base = (summary_base_url_2 or "").strip()
        if not base:
            raise SystemExit("summary_base_url_2 missing in config.config")
    elif SLLM == 3:
        key = (summary_apikey_3 or "").strip()
        if not key:
            raise SystemExit("summary_apikey_3 missing in config.config")
        base = (summary_base_url_3 or "").strip()
        if not base:
            raise SystemExit("summary_base_url_3 missing in config.config")
    else:
        key = (qwen_api_key or "").strip()
        if not key:
            raise SystemExit("qwen_api_key missing in config.config")
        base = (summary_base_url or "").strip()
        if not base:
            raise SystemExit("summary_base_url missing in config.config")
    return OpenAI(api_key=key, base_url=base)


def summarize_one(client: OpenAI, md_path: Path) -> Tuple[Path, str]:
    md_text = md_path.read_text(encoding="utf-8", errors="ignore")
    if not md_text.strip():
        return md_path, ""
    sys_prompt = system_prompt
    user_content = md_text
    hard_limit = int(summary_input_hard_limit)
    safety_margin = int(summary_input_safety_margin)
    limit_total = hard_limit - safety_margin
    sys_tokens = approx_input_tokens(sys_prompt)
    user_budget = max(1, limit_total - sys_tokens)
    user_content = crop_to_input_tokens(user_content, user_budget)
    kwargs = {}
    if summary_temperature is not None:
        kwargs["temperature"] = float(summary_temperature)
    if summary_max_tokens is not None:
        kwargs["max_tokens"] = int(summary_max_tokens)
    # 根据 SLLM 选择对应的模型名称
    if SLLM == 2:
        model_name = summary_model_2
    elif SLLM == 3:
        model_name = summary_model_3
    else:
        model_name = summary_model

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_content},
        ],
        stream=False,
        **kwargs,
    )
    content = resp.choices[0].message.content if resp.choices else ""
    if not content:
        return md_path, ""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("🌐来源"):
            arxiv_id = md_path.stem
            lines[i] = f"🌐来源：arXiv,{arxiv_id}"
            break
    content = normalize_summary_format("\n".join(lines))
    return md_path, content


def normalize_summary_format(text: str) -> str:
    if not text.strip():
        return text

    lines = text.splitlines()
    section_headers = ("🛎️", "📝", "🔎", "💡")

    def is_section_header(line: str) -> bool:
        s = line.strip()
        return any(s.startswith(h) for h in section_headers)

    # Ensure the first line uses "笔记标题："
    first_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_idx = idx
            break
    if first_idx is None:
        return text

    first = lines[first_idx].strip()
    if first.startswith("笔记标题"):
        rest = first[len("笔记标题"):].lstrip()
        if rest.startswith(":") or rest.startswith("："):
            rest = rest[1:].lstrip()
        lines[first_idx] = f"笔记标题：{rest}".rstrip()
    elif first.startswith("标题"):
        rest = first[len("标题"):].lstrip()
        if rest.startswith(":") or rest.startswith("："):
            rest = rest[1:].lstrip()
        lines[first_idx] = f"笔记标题：{rest}".rstrip()
    elif is_section_header(first) or first.startswith("🔸"):
        lines.insert(first_idx, "笔记标题：")
    else:
        lines[first_idx] = f"笔记标题：{first}".rstrip()

    # Insert a blank line before each section header
    out: List[str] = []
    for line in lines:
        s = line.strip()
        if is_section_header(s):
            if out and out[-1].strip():
                out.append("")
        out.append(line.rstrip())

    return "\n".join(out).rstrip() + "\n"


def run() -> None:
    ap = argparse.ArgumentParser("paper_summary")
    ap.add_argument("--input-dir", default=str(Path(DATA_ROOT) / "selectedpaper_to_mineru"))
    ap.add_argument("--out-root", default=str(Path(DATA_ROOT) / "paper_summary"))
    ap.add_argument("--date", default="")
    ap.add_argument("--concurrency", type=int, default=summary_concurrency)
    args = ap.parse_args()

    in_root = Path(args.input_dir)
    if not in_root.exists():
        print(f"[SUMMARY] input dir not found: {in_root}, skip paper_summary", flush=True)
        return

    if args.date:
        in_dir = in_root / args.date
        if not in_dir.exists():
            print(f"[SUMMARY] input dir not found: {in_dir}, skip paper_summary", flush=True)
            return
        date_str = args.date
    else:
        today = today_str()
        candidate = in_root / today
        if candidate.is_dir():
            in_dir = candidate
            date_str = today
        else:
            subdirs = []
            for d in in_root.iterdir():
                if d.is_dir():
                    name = d.name
                    if len(name) == 10 and name[4] == "-" and name[7] == "-":
                        subdirs.append(d)
            if subdirs:
                subdirs.sort(key=lambda p: p.name)
                in_dir = subdirs[-1]
                date_str = in_dir.name
            else:
                in_dir = in_root
                date_str = today

    files = list_md_files(in_dir)
    if not files:
        print(f"[SUMMARY] no md files in {in_dir}, skip paper_summary", flush=True)
        return
    print("============开始生成精选论文中文摘要==============", flush=True)

    out_root = Path(args.out_root)
    single_dir = out_root / "single" / date_str
    gather_dir = out_root / "gather" / date_str
    single_dir.mkdir(parents=True, exist_ok=True)

    to_run: List[Path] = []
    for p in files:
        out_path = single_dir / f"{p.stem}.md"
        if out_path.exists():
            continue
        to_run.append(p)

    total = len(to_run)
    if total == 0:
        gather_path = write_gather(single_dir, gather_dir, date_str)
        print(f"[SUMMARY] all files already summarized, single_dir={single_dir}", flush=True)
        print(f"[SUMMARY] gather_path={gather_path}", flush=True)
        return

    client = make_client()
    workers = max(1, int(args.concurrency or 0))
    print(f"[SUMMARY] input_dir={in_dir} total={total} concurrency={workers}", flush=True)

    start = time.monotonic()
    done = 0
    empty = 0

    def task(md_path: Path) -> Tuple[Path, str]:
        path, content = summarize_one(client, md_path)
        if not content.strip():
            return path, ""
        out_path = single_dir / f"{path.stem}.md"
        out_path.write_text(content, encoding="utf-8")
        return path, content

    with ThreadPoolExecutor(max_workers=workers) as ex:
        future_map = {ex.submit(task, p): p for p in to_run}
        for fut in as_completed(future_map):
            src = future_map[fut]
            try:
                _, content = fut.result()
                if not content.strip():
                    empty += 1
            except Exception as e:
                print(f"\r[SUMMARY] error on {src.name}: {e!r}", end="", flush=True)
            done += 1
            elapsed = time.monotonic() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"\r[SUMMARY] progress done={done}/{total} empty={empty} rate={rate:.2f}/s", end="", flush=True)

    print()
    gather_path = write_gather(single_dir, gather_dir, date_str)
    print(f"[SUMMARY] single_dir={single_dir}", flush=True)
    print(f"[SUMMARY] gather_path={gather_path}", flush=True)
    print("============结束生成精选论文中文摘要==============", flush=True)


if __name__ == "__main__":
    run()
