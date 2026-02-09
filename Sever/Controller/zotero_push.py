import argparse
import hashlib
import json
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from urllib.parse import urlparse, urlunparse

import requests

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config.config import DATA_ROOT


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def load_api_key() -> str:
    p1 = Path("config") / "zotero_api.txt"
    if p1.exists():
        return p1.read_text(encoding="utf-8", errors="ignore").strip()
    p2 = Path("config") / "zotero.txt"
    if p2.exists():
        txt = p2.read_text(encoding="utf-8", errors="ignore")
        for ln in txt.splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                if k.strip().lower() in ("api_key", "key"):
                    return v.strip().strip('"').strip("'")
    return ""


def load_user_id() -> str:
    p1 = Path("config") / "zotero_user.txt"
    if p1.exists():
        return p1.read_text(encoding="utf-8", errors="ignore").strip()
    p2 = Path("config") / "zotero.txt"
    if p2.exists():
        txt = p2.read_text(encoding="utf-8", errors="ignore")
        for ln in txt.splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                if k.strip().lower() in ("user_id", "userid", "user"):
                    return v.strip().strip('"').strip("'")
    return ""


def today_str() -> str:
    from datetime import datetime
    return datetime.now().date().isoformat()


def normalize_spaces(s: str) -> str:
    return " ".join((s or "").replace("\r", " ").replace("\n", " ").split()).strip()


def firstline_from_summary(summary_dir: Path, stem: str) -> str:
    p = summary_dir / f"{stem}.txt"
    if not p.exists():
        return ""
    lines = [ln.strip() for ln in read_text(p).splitlines()]
    if not lines:
        return ""
    for i, ln in enumerate(lines):
        if (ln.startswith("📖标题") or ln.lower().startswith("title")) and i > 0:
            j = i - 1
            while j >= 0:
                if lines[j]:
                    return normalize_spaces(lines[j])
                j -= 1
            break
    for ln in lines:
        if ln:
            return normalize_spaces(ln)
    return ""


def parse_title_and_abstract(stem: str, summary_dir: Path, md_dir: Path) -> Tuple[str, str]:
    title = stem
    abstract = ""
    sfile = summary_dir / f"{stem}.txt"
    if sfile.exists():
        text = read_text(sfile)
        lines = [ln.strip() for ln in text.splitlines()]
        for ln in lines:
            if ln.startswith("📖标题:"):
                t = ln.split(":", 1)[-1].strip()
                if t:
                    title = t
                break
        abstract = text.strip()
        return normalize_spaces(title) or stem, abstract.strip()
    mfile = resolve_md_path(md_dir, stem)
    if mfile.exists():
        text = read_text(mfile)
        lines = [ln.strip() for ln in text.splitlines()]
        for ln in lines:
            if ln.startswith("📖标题") or ln.lower().startswith("title"):
                t = ln.split(":", 1)[-1].strip() if ":" in ln else ln
                if t:
                    title = t
                break
        abstract = text.strip()
    return normalize_spaces(title) or stem, abstract.strip()


def resolve_md_path(md_dir: Path, stem: str) -> Path:
    direct = md_dir / f"{stem}.md"
    if direct.exists():
        return direct
    nested = md_dir / stem / f"{stem}.md"
    if nested.exists():
        return nested
    return direct


def is_arxiv_id(s: str) -> bool:
    return re.match(r"^\d{4}\.\d{5}(?:v\d+)?$", s) is not None


def infer_arxiv_url(stem: str) -> str:
    if is_arxiv_id(stem):
        base = stem.split("v")[0]
        return f"https://arxiv.org/abs/{base}"
    return ""


def fetch_arxiv_metadata(arxiv_id: str, timeout: int = 20) -> Tuple[str, str]:
    if not is_arxiv_id(arxiv_id):
        return "", ""
    api = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        r = requests.get(api, timeout=timeout, headers={"User-Agent": "arxiv-daily-paper/1.0"})
        if r.status_code != 200 or not r.text:
            return "", ""
        root = ET.fromstring(r.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", ns)
        if entry is None:
            return "", ""
        title = entry.findtext("a:title", default="", namespaces=ns)
        summary = entry.findtext("a:summary", default="", namespaces=ns)
        return normalize_spaces(title), (summary or "").strip()
    except Exception:
        return "", ""


def apply_title_template(tpl: str, *, stem: str, title: str) -> str:
    if not tpl:
        return title
    try:
        return tpl.format(stem=stem, title=title)
    except Exception:
        return title


def load_title_map(path: Path, *, fmt: str = "auto", id_field: str = "stem", title_field: str = "title") -> Dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"title map file not found: {path}")
    ext = path.suffix.lower()
    if fmt == "auto":
        if ext in (".jsonl", ".jsonlines"):
            fmt = "jsonl"
        elif ext == ".json":
            fmt = "json"
        elif ext == ".csv":
            fmt = "csv"
        elif ext == ".tsv":
            fmt = "tsv"
        else:
            fmt = "jsonl"
    mp: Dict[str, str] = {}
    if fmt == "json":
        obj = json.loads(read_text(path) or "{}")
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str):
                    mp[str(k)] = normalize_spaces(v)
                elif isinstance(v, dict):
                    t = v.get(title_field)
                    if isinstance(t, str) and t.strip():
                        mp[str(k)] = normalize_spaces(t)
        return mp
    if fmt == "jsonl":
        for ln in read_text(path).splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:
                continue
            if not isinstance(o, dict):
                continue
            kid = o.get(id_field)
            t = o.get(title_field)
            if isinstance(kid, str) and isinstance(t, str) and t.strip():
                mp[kid] = normalize_spaces(t)
        return mp
    if fmt in ("csv", "tsv"):
        delim = "," if fmt == "csv" else "\t"
        lines = [ln for ln in read_text(path).splitlines() if ln.strip()]
        if not lines:
            return mp
        header = [h.strip() for h in lines[0].split(delim)]
        has_header = (id_field in header) and (title_field in header)
        if has_header:
            idx_id = header.index(id_field)
            idx_t = header.index(title_field)
            for ln in lines[1:]:
                parts = [p.strip() for p in ln.split(delim)]
                if len(parts) <= max(idx_id, idx_t):
                    continue
                kid = parts[idx_id]
                t = parts[idx_t]
                if kid and t:
                    mp[kid] = normalize_spaces(t)
        else:
            for ln in lines:
                parts = [p.strip() for p in ln.split(delim)]
                if len(parts) >= 2 and parts[0] and parts[1]:
                    mp[parts[0]] = normalize_spaces(parts[1])
        return mp
    raise ValueError(f"unsupported title map format: {fmt}")


def resolve_title_and_abstract(
    *,
    stem: str,
    summary_attach_dir: Optional[Path],
    summary_dir: Path,
    md_dir: Path,
    title_mode: str,
    title_map: Optional[Dict[str, str]],
    title_map_fallback: bool,
    arxiv_timeout: int,
) -> Tuple[str, str, str]:
    base_title, base_abs = parse_title_and_abstract(stem, summary_dir, md_dir)
    has_better = normalize_spaces(base_title) and normalize_spaces(base_title) != stem
    if title_mode == "auto":
        return base_title, base_abs, ("summary/md" if has_better else "fallback")
    if title_mode == "file":
        t0 = ""
        if summary_attach_dir:
            t0 = firstline_from_summary(summary_attach_dir, stem)
        if t0:
            return t0, base_abs, "file_firstline"
        if title_map and stem in title_map and title_map[stem]:
            return title_map[stem], base_abs, "map"
        if title_map_fallback:
            return base_title, base_abs, ("summary/md" if has_better else "fallback")
        return stem, base_abs, "fallback"
    if title_mode == "drag":
        if has_better:
            return base_title, base_abs, "summary/md"
        if is_arxiv_id(stem):
            t, s = fetch_arxiv_metadata(stem, timeout=arxiv_timeout)
            if t:
                abs2 = base_abs if base_abs.strip() else s.strip()
                return t, abs2, "arxiv"
        return base_title, base_abs, "fallback"
    return base_title, base_abs, ("summary/md" if has_better else "fallback")


def sha1_short(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:12]


def connector_base_from_saveitems(connector_saveitems_url: str) -> str:
    u = urlparse(connector_saveitems_url)
    return urlunparse((u.scheme, u.netloc, "", "", "", ""))


def http_post_json(url: str, payload: Dict[str, Any], timeout: int = 60) -> requests.Response:
    headers = {
        "Content-Type": "application/json",
        "X-Zotero-Connector-API-Version": "3",
    }
    return requests.post(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        timeout=timeout,
    )


def http_post_stream(
    url: str,
    *,
    body: bytes,
    content_type: str,
    x_metadata: Dict[str, Any],
    timeout: int = 300,
) -> requests.Response:
    headers = {
        "Content-Type": content_type,
        "X-Metadata": json.dumps(x_metadata, ensure_ascii=False),
        "X-Zotero-Connector-API-Version": "3",
        "Content-Length": str(len(body)),
    }
    return requests.post(url, data=body, headers=headers, timeout=timeout)


def connector_get_selected(connector_base: str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    try:
        r = http_post_json(f"{connector_base}/connector/getSelectedCollection", payload={}, timeout=timeout)
        if r.status_code == 200 and r.text:
            return r.json()
    except Exception:
        return None
    return None


@dataclass
class LocalAttachment:
    title: str
    mime: str
    path: Path
    fake_url: str


@dataclass
class FileListItem:
    stem: str
    pdf_path: Path
    md_path: Path
    summary_path: Path
    title: str
    abstract: str


def read_pdf_info_title(subdir: Path) -> str:
    info_path = subdir / "pdf_info.json"
    if not info_path.exists():
        return ""
    try:
        obj = json.loads(read_text(info_path))
    except Exception:
        return ""
    if isinstance(obj, dict):
        title = obj.get("title")
        if isinstance(title, str) and title.strip():
            return normalize_spaces(title)
    return ""


def resolve_title_and_abstract_from_files(title_hint: str, summary_path: Path, md_path: Path, stem: str) -> Tuple[str, str]:
    title = normalize_spaces(title_hint) if title_hint else ""
    abstract = ""
    if summary_path.exists():
        text = read_text(summary_path).strip()
        if not title:
            lines = [ln.strip() for ln in text.splitlines()]
            for ln in lines:
                if ln.startswith("📖标题") or ln.lower().startswith("title"):
                    t = ln.split(":", 1)[-1].strip() if ":" in ln else ln
                    if t:
                        title = normalize_spaces(t)
                    break
        abstract = text
    elif md_path.exists():
        text = read_text(md_path).strip()
        if not title:
            lines = [ln.strip() for ln in text.splitlines()]
            for ln in lines:
                if ln.startswith("📖标题") or ln.lower().startswith("title"):
                    t = ln.split(":", 1)[-1].strip() if ":" in ln else ln
                    if t:
                        title = normalize_spaces(t)
                    break
        abstract = text
    return (title or stem), abstract


def list_file_list_items(file_list_root: Path) -> List[FileListItem]:
    items: List[FileListItem] = []
    if not file_list_root.exists():
        return items
    for subdir in sorted([p for p in file_list_root.iterdir() if p.is_dir()]):
        pdfs = sorted(subdir.glob("*.pdf"))
        if not pdfs:
            continue
        title_hint = read_pdf_info_title(subdir)
        for pdf_path in pdfs:
            stem = pdf_path.stem
            md_path = resolve_md_path(subdir, stem)
            summary_path = subdir / f"{stem}_limit.md"
            if not summary_path.exists():
                summary_path = subdir / f"{stem}_summary.md"
            title, abstract = resolve_title_and_abstract_from_files(title_hint, summary_path, md_path, stem)
            items.append(
                FileListItem(
                    stem=stem,
                    pdf_path=pdf_path.resolve(),
                    md_path=md_path.resolve(),
                    summary_path=summary_path.resolve(),
                    title=title,
                    abstract=abstract,
                )
            )
    return items


def run_mode_a(args: argparse.Namespace) -> int:
    date_str = args.date.strip() or today_str()
    # 使用 file_collect 的输出目录
    if args.file_list_root:
        file_list_root = Path(args.file_list_root)
    else:
        file_list_root = Path(DATA_ROOT) / "file_collect" / date_str
    use_file_list = (not args.no_file_list) and file_list_root.exists()
    if use_file_list:
        items = list_file_list_items(file_list_root)
        if not items:
            print(f"[A] no pdfs under: {file_list_root}")
            return 0
    else:
        pdf_dir = Path(args.pdf_root) / date_str
        md_dir = Path(args.md_root) / date_str
        summary_dir = Path(args.summary_root) / date_str
        summary_attach_dir = Path(args.summary_attach_root) / date_str
        if not pdf_dir.exists():
            print(f"[A] pdf dir not found: {pdf_dir}")
            return 2
        stems = sorted([p.stem for p in pdf_dir.glob("*.pdf")])
        if not stems:
            print(f"[A] no pdfs under: {pdf_dir}")
            return 0
    connector_base = connector_base_from_saveitems(args.connector_url)
    sel = connector_get_selected(connector_base)
    if sel:
        cur_name = sel.get("name")
        lib_name = sel.get("libraryName")
        lib_editable = sel.get("libraryEditable")
        files_editable = sel.get("filesEditable")
        print(f"[A] Zotero save target (current selection): {cur_name} (library={lib_name}, libraryEditable={lib_editable}, filesEditable={files_editable})")
        if not files_editable:
            print("[A][WARN] filesEditable=false: Zotero will refuse /connector/saveAttachment, so you will get items without attachments.")
            print("[A][WARN] Switch to 'My Library' or an editable library/collection that allows file editing, then run again.")
    else:
        print("[A] (info) Could not query /connector/getSelectedCollection; continuing.")
    title_map: Optional[Dict[str, str]] = None
    if args.a_title_mode == "file" and args.title_map_file:
        try:
            title_map = load_title_map(
                Path(args.title_map_file),
                fmt=args.title_map_format,
                id_field=args.title_map_id_field,
                title_field=args.title_map_title_field,
            )
            print(f"[A] loaded title map: {args.title_map_file} (entries={len(title_map)})")
        except Exception as e:
            print(f"[A][ERR] failed to load title map: {e}")
            return 2
    session_id = f"arxiv_daily_{uuid.uuid4().hex}"
    items_payload: List[Dict[str, Any]] = []
    attachments_plan: Dict[str, List[LocalAttachment]] = {}
    if use_file_list:
        for item in items:
            stem = item.stem
            pdf_path = item.pdf_path
            title = item.title
            abstract = item.abstract
            src = "file_list"
            if args.title_template:
                title = apply_title_template(args.title_template, stem=stem, title=title)
            url = infer_arxiv_url(stem)
            item_id = f"item_{sha1_short(stem)}_{sha1_short(title)}"
            items_payload.append(
                {
                    "id": item_id,
                    "itemType": "journalArticle",
                    "title": title,
                    "abstractNote": abstract,
                    "url": url,
                    "language": "zh-CN",
                }
            )
            md_path = item.md_path
            sum_path = item.summary_path
            fake_pdf_url = f"http://local.file/{sha1_short(str(pdf_path))}/{pdf_path.name}"
            fake_md_url = f"http://local.file/{sha1_short(str(md_path))}/{md_path.name}"
            fake_sum_url = f"http://local.file/{sha1_short(str(sum_path))}/{sum_path.name}"
            att_list: List[LocalAttachment] = [
                LocalAttachment(title="PDF", mime="application/pdf", path=pdf_path, fake_url=fake_pdf_url)
            ]
            if md_path.exists():
                att_list.append(LocalAttachment(title="MD", mime="text/markdown", path=md_path, fake_url=fake_md_url))
            if sum_path.exists():
                sum_mime = args.summary_mime or "application/octet-stream"
                att_list.append(LocalAttachment(title="Summary", mime=sum_mime, path=sum_path, fake_url=fake_sum_url))
            attachments_plan[item_id] = att_list
            if args.debug:
                print(f"[A][debug] stem={stem} title_source={src} title={title}")
    else:
        items = []
        for stem in stems:
            pdf_path = (pdf_dir / f"{stem}.pdf").resolve()
            title, abstract, src = resolve_title_and_abstract(
                stem=stem,
                summary_attach_dir=summary_attach_dir,
                summary_dir=summary_dir,
                md_dir=md_dir,
                title_mode=args.a_title_mode,
                title_map=title_map,
                title_map_fallback=args.title_map_fallback,
                arxiv_timeout=args.arxiv_timeout,
            )
            if args.title_template:
                title = apply_title_template(args.title_template, stem=stem, title=title)
            url = infer_arxiv_url(stem)
            item_id = f"item_{sha1_short(stem)}_{sha1_short(title)}"
            items_payload.append(
                {
                    "id": item_id,
                    "itemType": "journalArticle",
                    "title": title,
                    "abstractNote": abstract,
                    "url": url,
                    "language": "zh-CN",
                }
            )
            md_path = resolve_md_path(md_dir, stem).resolve()
            sum_path = (summary_attach_dir / f"{stem}.txt").resolve()
            fake_pdf_url = f"http://local.file/{sha1_short(str(pdf_path))}/{pdf_path.name}"
            fake_md_url = f"http://local.file/{sha1_short(str(md_path))}/{md_path.name}"
            fake_sum_url = f"http://local.file/{sha1_short(str(sum_path))}/{sum_path.name}"
            att_list: List[LocalAttachment] = [
                LocalAttachment(title="PDF", mime="application/pdf", path=pdf_path, fake_url=fake_pdf_url)
            ]
            if md_path.exists():
                att_list.append(LocalAttachment(title="MD", mime="text/markdown", path=md_path, fake_url=fake_md_url))
            if sum_path.exists():
                sum_mime = args.summary_mime or "application/octet-stream"
                att_list.append(LocalAttachment(title="Summary", mime=sum_mime, path=sum_path, fake_url=fake_sum_url))
            attachments_plan[item_id] = att_list
            if args.debug:
                print(f"[A][debug] stem={stem} title_source={src} title={title}")

    r = http_post_json(
        args.connector_url,
        {
            "sessionID": session_id,
            "uri": "http://localhost/",
            "items": items_payload,
        },
        timeout=args.timeout,
    )
    print(f"[A] /connector/saveItems status={r.status_code}")
    if r.text:
        print(f"[A] response: {r.text[:2000]}")
    if r.status_code >= 400:
        print("[A] saveItems failed; no attachments uploaded.")
        return 3
    saveatt_url = f"{connector_base}/connector/saveAttachment"
    ok_items = 0
    ok_atts = 0
    fail_atts = 0
    skip_atts = 0
    processed_items = 0
    total_items = len(items_payload)
    for item in items_payload:
        item_id = item["id"]
        att_list = attachments_plan.get(item_id, [])
        all_ok_for_item = True
        for att in att_list:
            if not att.path.exists():
                print(f"[A][SKIP] missing file: {att.path}")
                skip_atts += 1
                all_ok_for_item = False
                continue
            body = att.path.read_bytes()
            meta = {
                "sessionID": session_id,
                "parentItemID": item_id,
                "title": att.title,
                "url": att.fake_url,
            }
            rr = http_post_stream(
                saveatt_url,
                body=body,
                content_type=att.mime,
                x_metadata=meta,
                timeout=args.attach_timeout,
            )
            if rr.status_code == 201:
                ok_atts += 1
                if args.debug:
                    print(f"[A] {item_id} {att.title}: OK (201) size={len(body)}")
            else:
                fail_atts += 1
                all_ok_for_item = False
                msg = (rr.text or "").strip().replace("\n", " ")
                if args.debug:
                    print(
                        f"[A] {item_id} {att.title}: FAIL ({rr.status_code}) size={len(body)} mime={att.mime} resp={msg[:200]}"
                    )
        if all_ok_for_item:
            ok_items += 1
        processed_items += 1
        progress_msg = (
            f"[A] importing items {processed_items}/{total_items} "
            f"items_ok={ok_items} attachments_ok={ok_atts} "
            f"attachments_fail={fail_atts} attachments_skip={skip_atts}"
        )
        print("\r" + progress_msg, end="", flush=True)
    print()
    print(
        f"[A] done. items={len(items_payload)} items_ok={ok_items} attachments_ok={ok_atts} attachments_fail={fail_atts} attachments_skip={skip_atts}"
    )
    return 0 if fail_atts == 0 else 4


def ensure_collection(base_url: str, user_id: str, api_key: str, name: str) -> str:
    headers = {"Zotero-API-Key": api_key}
    limit = 100
    start = 0
    while True:
        r = requests.get(
            f"{base_url}/users/{user_id}/collections",
            headers=headers,
            params={"limit": limit, "start": start},
            timeout=30,
        )
        if r.status_code != 200:
            break
        arr = r.json()
        for c in arr:
            if c.get("data", {}).get("name", "") == name:
                return c.get("key", "") or c.get("data", {}).get("key", "")
        if len(arr) < limit:
            break
        start += limit
    headers = {"Zotero-API-Key": api_key, "Content-Type": "application/json"}
    body = [{"name": name}]
    r2 = requests.post(f"{base_url}/users/{user_id}/collections", headers=headers, data=json.dumps(body), timeout=30)
    if r2.status_code in (200, 201):
        obj = r2.json()
        if isinstance(obj, list) and obj:
            it = obj[0]
            return it.get("key", "") or it.get("data", {}).get("key", "")
    return ""


def create_item(base_url: str, user_id: str, api_key: str, item: Dict[str, Any]) -> str:
    headers = {"Zotero-API-Key": api_key, "Content-Type": "application/json"}
    r = requests.post(f"{base_url}/users/{user_id}/items", headers=headers, data=json.dumps([item]), timeout=30)
    if r.status_code in (200, 201):
        obj = r.json()
        if isinstance(obj, dict):
            suc = obj.get("success") or {}
            if isinstance(suc, dict) and suc:
                return str(next(iter(suc.values())))
    return ""


def create_attachment_item(base_url: str, user_id: str, api_key: str, attachment: Dict[str, Any]) -> str:
    headers = {"Zotero-API-Key": api_key, "Content-Type": "application/json"}
    r = requests.post(f"{base_url}/users/{user_id}/items", headers=headers, data=json.dumps([attachment]), timeout=30)
    if r.status_code in (200, 201):
        obj = r.json()
        if isinstance(obj, dict):
            suc = obj.get("success") or {}
            if isinstance(suc, dict) and suc:
                return str(next(iter(suc.values())))
    return ""


def _md5_size_mtime(p: Path) -> Tuple[str, int, int]:
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    md5 = h.hexdigest()
    st = p.stat()
    size = int(st.st_size)
    mtime_ms = int(round(st.st_mtime * 1000))
    return md5, size, mtime_ms


def upload_file_to_attachment(base_url: str, user_id: str, api_key: str, attachment_key: str, file_path: Path) -> bool:
    headers = {"Zotero-API-Key": api_key, "Content-Type": "application/x-www-form-urlencoded", "If-None-Match": "*"}
    md5, size, mtime_ms = _md5_size_mtime(file_path)
    data = {"md5": md5, "filename": file_path.name, "filesize": str(size), "mtime": str(mtime_ms)}
    r = requests.post(f"{base_url}/users/{user_id}/items/{attachment_key}/file", headers=headers, data=data, timeout=60)
    if r.status_code != 200:
        msg = r.text.strip().replace("\n", " ")
        print(f"[WebAPI] request upload failed: {r.status_code} {msg[:300]}")
        return False
    js = r.json()
    if isinstance(js, dict) and js.get("exists") == 1:
        return True
    url = js.get("url")
    prefix = js.get("prefix", "")
    suffix = js.get("suffix", "")
    ct = js.get("contentType", "multipart/form-data")
    if not url:
        print("[WebAPI] upload init succeeded but no url returned")
        return False
    with file_path.open("rb") as f:
        payload = prefix.encode("utf-8") + f.read() + suffix.encode("utf-8")
    r2 = requests.post(url, data=payload, headers={"Content-Type": ct}, timeout=300)
    return 200 <= r2.status_code < 300


def run_mode_b(args: argparse.Namespace) -> int:
    api_key = load_api_key()
    user_id = load_user_id()
    if not api_key or not user_id:
        print("[B] missing api_key/user_id. Put them in config/zotero_api.txt and config/zotero_user.txt")
        return 2
    base_url = "https://api.zotero.org"
    date_str = args.date.strip() or today_str()
    # 使用 file_collect 的输出目录
    if args.file_list_root:
        file_list_root = Path(args.file_list_root)
    else:
        file_list_root = Path(DATA_ROOT) / "file_collect" / date_str
    use_file_list = (not args.no_file_list) and file_list_root.exists()
    if use_file_list:
        items = list_file_list_items(file_list_root)
        if not items:
            print(f"[B] no pdfs under: {file_list_root}")
            return 0
    else:
        pdf_dir = Path(args.pdf_root) / date_str
        md_dir = Path(args.md_root) / date_str
        summary_dir = Path(args.summary_root) / date_str
        summary_attach_dir = Path(args.summary_attach_root) / date_str
        if not pdf_dir.exists():
            print(f"[B] pdf dir not found: {pdf_dir}, skip zotero_push")
            return 0
        stems = sorted([p.stem for p in pdf_dir.glob("*.pdf")])
        if not stems:
            print(f"[B] no pdfs under: {pdf_dir}")
            return 0
    col_key = ""
    if args.collection:
        col_key = ensure_collection(base_url, user_id, api_key, args.collection)
    if use_file_list:
        for item in items:
            stem = item.stem
            title = item.title
            abstract = item.abstract
            url = infer_arxiv_url(stem)
            item_payload: Dict[str, Any] = {
                "itemType": "journalArticle",
                "title": title,
                "abstractNote": abstract,
                "url": url,
                "language": "zh-CN",
            }
            if col_key:
                item_payload["collections"] = [col_key]
            parent_key = create_item(base_url, user_id, api_key, item_payload)
            if not parent_key:
                print(f"[B] failed to create parent item for {stem}")
                continue
            pdf_path = item.pdf_path
            md_path = item.md_path
            sum_path = item.summary_path
            if args.b_attachment_mode == "imported":
                att_pdf = {
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "title": "PDF",
                    "contentType": "application/pdf",
                    "parentItem": parent_key,
                }
                pdf_key = create_attachment_item(base_url, user_id, api_key, att_pdf)
                ok_pdf = False
                if pdf_key:
                    ok_pdf = upload_file_to_attachment(base_url, user_id, api_key, pdf_key, pdf_path)
                print(f"[B] {stem} PDF upload: {ok_pdf}")
                ok_md = False
                if md_path.exists():
                    att_md = {
                        "itemType": "attachment",
                        "linkMode": "imported_file",
                        "title": "MD",
                        "contentType": "text/markdown",
                        "parentItem": parent_key,
                    }
                    md_key = create_attachment_item(base_url, user_id, api_key, att_md)
                    if md_key:
                        ok_md = upload_file_to_attachment(base_url, user_id, api_key, md_key, md_path)
                print(f"[B] {stem} MD upload: {ok_md}")
                ok_sum = False
                if sum_path.exists():
                    att_sum = {
                        "itemType": "attachment",
                        "linkMode": "imported_file",
                        "title": "Summary",
                        "contentType": "text/plain",
                        "parentItem": parent_key,
                    }
                    sum_key = create_attachment_item(base_url, user_id, api_key, att_sum)
                    if sum_key:
                        ok_sum = upload_file_to_attachment(base_url, user_id, api_key, sum_key, sum_path)
                print(f"[B] {stem} Summary upload: {ok_sum}")
            else:
                create_attachment_item(
                    base_url,
                    user_id,
                    api_key,
                    {
                        "itemType": "attachment",
                        "linkMode": "linked_file",
                        "title": "PDF",
                        "contentType": "application/pdf",
                        "path": str(pdf_path),
                        "parentItem": parent_key,
                    },
                )
                if md_path.exists():
                    create_attachment_item(
                        base_url,
                        user_id,
                        api_key,
                        {
                            "itemType": "attachment",
                            "linkMode": "linked_file",
                            "title": "MD",
                            "contentType": "text/markdown",
                            "path": str(md_path),
                            "parentItem": parent_key,
                        },
                    )
                if sum_path.exists():
                    create_attachment_item(
                        base_url,
                        user_id,
                        api_key,
                        {
                            "itemType": "attachment",
                            "linkMode": "linked_file",
                            "title": "Summary",
                            "contentType": "text/plain",
                            "path": str(sum_path),
                            "parentItem": parent_key,
                        },
                    )
                print(f"[B] {stem} linked attachments created")
            print(f"[B] created parent item: {parent_key}")
    else:
        for stem in stems:
            title, abstract = parse_title_and_abstract(stem, summary_dir, md_dir)
            url = infer_arxiv_url(stem)
            item: Dict[str, Any] = {
                "itemType": "journalArticle",
                "title": title,
                "abstractNote": abstract,
                "url": url,
                "language": "zh-CN",
            }
            if col_key:
                item["collections"] = [col_key]
            parent_key = create_item(base_url, user_id, api_key, item)
            if not parent_key:
                print(f"[B] failed to create parent item for {stem}")
                continue
            pdf_path = (pdf_dir / f"{stem}.pdf").resolve()
            md_path = resolve_md_path(md_dir, stem).resolve()
            sum_path = (summary_attach_dir / f"{stem}.txt").resolve()
            if args.b_attachment_mode == "imported":
                att_pdf = {
                    "itemType": "attachment",
                    "linkMode": "imported_file",
                    "title": "PDF",
                    "contentType": "application/pdf",
                    "parentItem": parent_key,
                }
                pdf_key = create_attachment_item(base_url, user_id, api_key, att_pdf)
                ok_pdf = False
                if pdf_key:
                    ok_pdf = upload_file_to_attachment(base_url, user_id, api_key, pdf_key, pdf_path)
                print(f"[B] {stem} PDF upload: {ok_pdf}")
                ok_md = False
                if md_path.exists():
                    att_md = {
                        "itemType": "attachment",
                        "linkMode": "imported_file",
                        "title": "MD",
                        "contentType": "text/markdown",
                        "parentItem": parent_key,
                    }
                    md_key = create_attachment_item(base_url, user_id, api_key, att_md)
                    if md_key:
                        ok_md = upload_file_to_attachment(base_url, user_id, api_key, md_key, md_path)
                print(f"[B] {stem} MD upload: {ok_md}")
                ok_sum = False
                if sum_path.exists():
                    att_sum = {
                        "itemType": "attachment",
                        "linkMode": "imported_file",
                        "title": "Summary",
                        "contentType": "text/plain",
                        "parentItem": parent_key,
                    }
                    sum_key = create_attachment_item(base_url, user_id, api_key, att_sum)
                    if sum_key:
                        ok_sum = upload_file_to_attachment(base_url, user_id, api_key, sum_key, sum_path)
                print(f"[B] {stem} Summary upload: {ok_sum}")
            else:
                create_attachment_item(
                    base_url,
                    user_id,
                    api_key,
                    {
                        "itemType": "attachment",
                        "linkMode": "linked_file",
                        "title": "PDF",
                        "contentType": "application/pdf",
                        "path": str(pdf_path),
                        "parentItem": parent_key,
                    },
                )
                if md_path.exists():
                    create_attachment_item(
                        base_url,
                        user_id,
                        api_key,
                        {
                            "itemType": "attachment",
                            "linkMode": "linked_file",
                            "title": "MD",
                            "contentType": "text/markdown",
                            "path": str(md_path),
                            "parentItem": parent_key,
                        },
                    )
                if sum_path.exists():
                    create_attachment_item(
                        base_url,
                        user_id,
                        api_key,
                        {
                            "itemType": "attachment",
                            "linkMode": "linked_file",
                            "title": "Summary",
                            "contentType": "text/plain",
                            "path": str(sum_path),
                            "parentItem": parent_key,
                        },
                    )
                print(f"[B] {stem} linked attachments created")
            print(f"[B] created parent item: {parent_key}")
    return 0


def main() -> None:
    pa = argparse.ArgumentParser("zotero_push")

    pa.add_argument("--mode", choices=["A", "B"], default="A")
    pa.add_argument("--date", default="")

    pa.add_argument("--pdf-root", default=str(Path(DATA_ROOT) / "selectedpaper"))
    pa.add_argument("--md-root", default=str(Path(DATA_ROOT) / "paper_summary" / "single"))
    pa.add_argument("--summary-root", default=str(Path(DATA_ROOT) / "paper_summary" / "single"))
    pa.add_argument("--summary-attach-root", default=str(Path(DATA_ROOT) / "paper_summary" / "single"))

    pa.add_argument("--connector-url", default="http://127.0.0.1:23119/connector/saveItems")
    pa.add_argument("--timeout", type=int, default=60)
    pa.add_argument("--attach-timeout", type=int, default=300)

    pa.add_argument("--a-title-mode", choices=["auto", "drag", "file"], default="drag")
    pa.add_argument("--arxiv-timeout", type=int, default=20)

    pa.add_argument("--title-map-file", default="")
    pa.add_argument("--title-map-format", choices=["auto", "json", "jsonl", "csv", "tsv"], default="auto")
    pa.add_argument("--title-map-id-field", default="stem")
    pa.add_argument("--title-map-title-field", default="title")
    pa.add_argument("--title-map-fallback", action="store_true")

    pa.add_argument("--title-template", default="")

    pa.add_argument("--summary-mime", default="application/octet-stream")

    pa.add_argument("--debug", action="store_true")

    pa.add_argument("--collection", default="论文_导入未处理")
    pa.add_argument("--b-attachment-mode", choices=["imported", "linked"], default="imported")
    pa.add_argument("--file-list-root", default="")
    pa.add_argument("--no-file-list", action="store_true")

    args = pa.parse_args()

    print("============开始导入精选论文到 Zotero==============", flush=True)
    if args.mode == "A":
        code = run_mode_a(args)
    else:
        code = run_mode_b(args)
    print("============结束导入精选论文到 Zotero==============", flush=True)

    raise SystemExit(code)


if __name__ == "__main__":
    main()
