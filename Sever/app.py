import os
import sys
import subprocess
from datetime import datetime

ROOT = os.path.dirname(__file__)
DATA_ROOT = "data"

# Per-step output path (file or dir) that indicates "done" for a given date.
# If the path exists, the step is skipped on re-run.
STEP_OUTPUT_PATHS = {
    "arxiv_search": lambda d: os.path.join(ROOT, DATA_ROOT, "arxivList", "md", f"{d}.md"),
    "paperList_remove_duplications": lambda d: os.path.join(ROOT, DATA_ROOT, "paperList_remove_duplications", f"{d}.json"),
    "llm_select_theme": lambda d: os.path.join(ROOT, DATA_ROOT, "llm_select_theme", f"{d}.json"),
    "paper_theme_filter": lambda d: os.path.join(ROOT, DATA_ROOT, "paper_theme_filter", f"{d}.json"),
    "pdf_download": lambda d: os.path.join(ROOT, DATA_ROOT, "raw_pdf", d, "_manifest.json"),
    "pdf_split": lambda d: os.path.join(ROOT, DATA_ROOT, "preview_pdf", d, "_manifest.json"),
    "pdfsplite_to_minerU": lambda d: os.path.join(ROOT, DATA_ROOT, "preview_pdf_to_mineru", d, "_manifest.json"),
    "pdf_info": lambda d: os.path.join(ROOT, DATA_ROOT, "pdf_info", f"{d}.json"),
    "instutions_filter": lambda d: os.path.join(ROOT, DATA_ROOT, "instutions_filter", d, f"{d}.json"),
    "selectpaper": lambda d: os.path.join(ROOT, DATA_ROOT, "selectedpaper", d, "_manifest.json"),
    "selectedpaper_to_mineru": lambda d: os.path.join(ROOT, DATA_ROOT, "selectedpaper_to_mineru", d, "_manifest.json"),
    "paper_summary": lambda d: os.path.join(ROOT, DATA_ROOT, "paper_summary", "single", d),
    "summary_limit": lambda d: os.path.join(ROOT, DATA_ROOT, "summary_limit", "single", d),
    "select_image": lambda d: os.path.join(ROOT, DATA_ROOT, "select_image", d, f"select_image_{d}.json"),
    "file_collect": lambda d: os.path.join(ROOT, DATA_ROOT, "file_collect", d),
    "paper_assets": lambda d: os.path.join(ROOT, DATA_ROOT, "paper_assets", f"{d}.jsonl"),
    # zotero_push has no local dated output; no entry so it is never skipped by output check
}

STEPS = {
    "arxiv_search": [sys.executable, "-u", os.path.join(ROOT, "Controller", "arxiv_search04.py")],
    "paperList_remove_duplications": [sys.executable, "-u", os.path.join(ROOT, "Controller", "paperList_remove_duplications.py")],
    "llm_select_theme": [sys.executable, "-u", os.path.join(ROOT, "Controller", "llm_select_theme.py")],
    "paper_theme_filter": [sys.executable, "-u", os.path.join(ROOT, "Controller", "paper_theme_filter.py")],
    "pdf_download": [sys.executable, "-u", os.path.join(ROOT, "Controller", "pdf_download.py")],
    "pdf_split": [sys.executable, "-u", os.path.join(ROOT, "Controller", "pdf_split.py")],
    "pdfsplite_to_minerU": [sys.executable, "-u", os.path.join(ROOT, "Controller", "pdfsplite_to_minerU.py")],
    "pdf_info": [sys.executable, "-u", os.path.join(ROOT, "Controller", "pdf_info.py")],
    "instutions_filter": [sys.executable, "-u", os.path.join(ROOT, "Controller", "instutions_filter.py")],
    "selectpaper": [sys.executable, "-u", os.path.join(ROOT, "Controller", "selectpaper.py")],
    "selectedpaper_to_mineru": [sys.executable, "-u", os.path.join(ROOT, "Controller", "selectedpaper_to_mineru.py")],
    "paper_summary": [sys.executable, "-u", os.path.join(ROOT, "Controller", "paper_summary.py")],
    "summary_limit": [sys.executable, "-u", os.path.join(ROOT, "Controller", "summary_limit.py")],
    "select_image": [sys.executable, "-u", os.path.join(ROOT, "Controller", "select_image.py")],
    "file_collect": [sys.executable, "-u", os.path.join(ROOT, "Controller", "file_collect.py")],
    "paper_assets": [sys.executable, "-u", os.path.join(ROOT, "Controller", "paper_assets.py")],
    "zotero_push": [sys.executable, "-u", os.path.join(ROOT, "Controller", "zotero_push.py")],
}


PIPELINES = {
    "default": [
        "arxiv_search",
        "paperList_remove_duplications",
        "llm_select_theme",
        "paper_theme_filter",
        "pdf_download",
        "pdf_split",
        "pdfsplite_to_minerU",
        "pdf_info",
        "instutions_filter",
        "selectpaper",
        "selectedpaper_to_mineru",
        "paper_summary",
        "summary_limit",
        "select_image",
        "file_collect",
        "paper_assets",
        "zotero_push",
    ],
    "daily": [
        "arxiv_search",
        "paperList_remove_duplications",
        "llm_select_theme",
        "paper_theme_filter",
        "pdf_download",
        "pdf_split",
        "pdfsplite_to_minerU",
        "pdf_info",
        "instutions_filter",
        "selectpaper",
        "selectedpaper_to_mineru",
        "paper_summary",
        "summary_limit",
        "select_image",
        "file_collect",
        "paper_assets",
        "zotero_push",
    ],
}


def step_output_exists(step: str, date_str: str) -> bool:
    if step not in STEP_OUTPUT_PATHS:
        return False
    path = STEP_OUTPUT_PATHS[step](date_str)
    if os.path.isfile(path):
        return True
    if os.path.isdir(path):
        return True
    return False


def run_step(name, extra_args=None, env=None):
    if name not in STEPS:
        raise SystemExit(f"Unknown step: {name}")
    cmd = STEPS[name] + (extra_args or [])
    r = subprocess.run(cmd, check=True, env=env)
    return r.returncode


def detect_selected_count():
    data_root = os.path.join(ROOT, "data", "arxivList", "md")
    if not os.path.isdir(data_root):
        return None
    files = [os.path.join(data_root, f) for f in os.listdir(data_root) if f.endswith(".md")]
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    latest = files[0]
    try:
        with open(latest, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("- Selected"):
                    # line format: - Selected: **N**
                    parts = line.split("**")
                    if len(parts) >= 2:
                        try:
                            return int(parts[1])
                        except ValueError:
                            return None
    except OSError:
        return None
    return None


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    pipeline = "default"
    extra = []
    if argv:
        pipeline = argv[0]
        extra = list(argv[1:])
    # Parse --date and --SLLM from extra so RUN_DATE / SLLM 都能传给各个 step
    run_date = os.environ.get("RUN_DATE") or datetime.now().date().isoformat()
    # --date
    if "--date" in extra:
        idx = extra.index("--date")
        if idx + 1 < len(extra):
            run_date = extra[idx + 1]
            extra = extra[:idx] + extra[idx + 2:]
    # --SLLM（1/2/3，控制摘要生成/精简所用的大模型）
    sllm_value = os.environ.get("SLLM")
    if "--SLLM" in extra:
        idx = extra.index("--SLLM")
        if idx + 1 < len(extra):
            raw = extra[idx + 1]
            try:
                iv = int(raw)
            except ValueError:
                iv = None
            if iv in (1, 2, 3):
                sllm_value = str(iv)
        # 从传给首个 step 的参数中移除 --SLLM 及其值，避免下游脚本 argparse 报错
        extra = extra[:idx] + extra[idx + 2:]
    # --user-id（可选，传给 paper_summary / summary_limit 以使用用户自定义配置）
    user_id_value = os.environ.get("PIPELINE_USER_ID")
    if "--user-id" in extra:
        idx = extra.index("--user-id")
        if idx + 1 < len(extra):
            user_id_value = extra[idx + 1]
        extra = extra[:idx] + extra[idx + 2:]
    # --Zo（T/F，控制是否执行最后一步 Zotero 导入；默认 F = 关闭）
    zo_value = os.environ.get("ZO", "F")
    if "--Zo" in extra:
        idx = extra.index("--Zo")
        if idx + 1 < len(extra):
            raw = (extra[idx + 1] or "").strip().upper()
            if raw in ("T", "F"):
                zo_value = raw
        # 同样从首个 step 的参数中移除 --Zo 及其值，避免下游脚本 argparse 报错
        extra = extra[:idx] + extra[idx + 2:]
    zo_value = (zo_value or "F").strip().upper()
    if zo_value not in ("T", "F"):
        zo_value = "F"
    env = {**os.environ, "RUN_DATE": run_date, "PYTHONIOENCODING": "utf-8"}
    if sllm_value is not None:
        env["SLLM"] = sllm_value
    if user_id_value is not None:
        env["PIPELINE_USER_ID"] = str(user_id_value)
    steps = PIPELINES.get(pipeline)
    if not steps:
        raise SystemExit(f"Unknown pipeline: {pipeline}")
    # 根据 Zo 开关决定是否保留最后一步 zotero_push（默认不执行）
    if zo_value != "T":
        steps = [s for s in steps if s != "zotero_push"]
    else:
        steps = list(steps)
    print(
        f"START pipeline '{pipeline}' with {len(steps)} step(s) RUN_DATE={run_date} Zo={zo_value}",
        flush=True,
    )
    # Steps that accept --user-id for per-user config overrides
    _USER_ID_STEPS = {"llm_select_theme", "pdf_info", "paper_assets", "paper_summary", "summary_limit"}

    for i, step in enumerate(steps):
        if i == 0:
            step_args = list(extra)
        else:
            step_args = []
        # Forward --user-id to supported steps
        if user_id_value and step in _USER_ID_STEPS:
            step_args.extend(["--user-id", str(user_id_value)])
        if step_output_exists(step, run_date):
            print(f"SKIP step: {step} (output exists for {run_date})", flush=True)
            continue
        print(f"RUN step: {step}", flush=True)
        run_step(step, step_args, env=env)
        if step == "arxiv_search":
            selected = detect_selected_count()
            if selected == 0:
                print("[PIPELINE] No papers selected in current window; stop after arxiv_search.", flush=True)
                return


if __name__ == "__main__":
    main()
