"""
Knowledge Base service layer.

Manages folders and saved papers in a local SQLite database
(Sever/database/paper_analysis.db).

Tables
------
kb_folders  – hierarchical folder tree (self-referencing parent_id)
kb_papers   – papers saved into the KB, each optionally placed in a folder
kb_notes    – notes / files / links attached to a paper
"""

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")

_KB_FILES_DIR = os.path.join(_BASE_DIR, "data", "kb_files")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they do not exist yet."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kb_folders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                parent_id  INTEGER DEFAULT NULL
                           REFERENCES kb_folders(id) ON DELETE SET NULL,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kb_papers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id   TEXT    NOT NULL UNIQUE,
                folder_id  INTEGER DEFAULT NULL
                           REFERENCES kb_folders(id) ON DELETE SET NULL,
                paper_data TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kb_notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id   TEXT    NOT NULL,
                type       TEXT    NOT NULL DEFAULT 'markdown',
                title      TEXT    NOT NULL,
                content    TEXT,
                file_path  TEXT,
                file_url   TEXT,
                file_size  INTEGER,
                mime_type  TEXT,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL,
                FOREIGN KEY (paper_id) REFERENCES kb_papers(paper_id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# Run on module import so tables are ready
init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------------------------------------------------------------------------
# Folder CRUD
# ---------------------------------------------------------------------------

def create_folder(name: str, parent_id: Optional[int] = None) -> dict:
    """Create a new folder. Returns the created folder dict."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_folders (name, parent_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, parent_id, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_folders WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def rename_folder(folder_id: int, name: str) -> Optional[dict]:
    """Rename a folder. Returns updated folder or None if not found."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE kb_folders SET name = ?, updated_at = ? WHERE id = ?",
            (name, now, folder_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def move_folder(folder_id: int, target_parent_id: Optional[int]) -> Optional[dict]:
    """
    Move a folder under a new parent (or to root when target_parent_id is None).
    Returns the updated folder dict, or None if not found.
    Prevents moving a folder into itself or its own descendant.
    """
    now = _now_iso()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM kb_folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            return None

        # Prevent moving into itself
        if target_parent_id == folder_id:
            return _row_to_dict(row)

        # Prevent moving into a descendant
        if target_parent_id is not None:
            ancestor = target_parent_id
            while ancestor is not None:
                if ancestor == folder_id:
                    return _row_to_dict(row)  # would create a cycle, abort
                r = conn.execute("SELECT parent_id FROM kb_folders WHERE id = ?", (ancestor,)).fetchone()
                ancestor = r["parent_id"] if r else None

        conn.execute(
            "UPDATE kb_folders SET parent_id = ?, updated_at = ? WHERE id = ?",
            (target_parent_id, now, folder_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_folders WHERE id = ?", (folder_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def delete_folder(folder_id: int) -> bool:
    """
    Delete a folder.  Its child folders and papers are re-parented to
    the deleted folder's parent (or root if the folder was top-level).
    Returns True if a row was actually deleted.
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT parent_id FROM kb_folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            return False
        parent_id = row["parent_id"]  # may be None (root)

        # Re-parent child folders
        conn.execute(
            "UPDATE kb_folders SET parent_id = ? WHERE parent_id = ?",
            (parent_id, folder_id),
        )
        # Re-parent papers
        conn.execute(
            "UPDATE kb_papers SET folder_id = ? WHERE folder_id = ?",
            (parent_id, folder_id),
        )
        conn.execute("DELETE FROM kb_folders WHERE id = ?", (folder_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Paper CRUD
# ---------------------------------------------------------------------------

def add_paper(paper_id: str, paper_data: dict, folder_id: Optional[int] = None) -> dict:
    """
    Add a paper to the knowledge base.  If the paper already exists, update
    its folder and data instead.  Returns the paper row dict.
    """
    now = _now_iso()
    data_json = json.dumps(paper_data, ensure_ascii=False)
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT id FROM kb_papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE kb_papers SET folder_id = ?, paper_data = ? WHERE paper_id = ?",
                (folder_id, data_json, paper_id),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM kb_papers WHERE paper_id = ?", (paper_id,)).fetchone()
        else:
            cur = conn.execute(
                "INSERT INTO kb_papers (paper_id, folder_id, paper_data, created_at) VALUES (?, ?, ?, ?)",
                (paper_id, folder_id, data_json, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM kb_papers WHERE id = ?", (cur.lastrowid,)).fetchone()
        result = _row_to_dict(row)
        result["paper_data"] = json.loads(result["paper_data"])
        return result
    finally:
        conn.close()


def remove_paper(paper_id: str) -> bool:
    """Remove a paper from the knowledge base. Returns True if deleted."""
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM kb_papers WHERE paper_id = ?", (paper_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def move_papers(paper_ids: list[str], target_folder_id: Optional[int]) -> int:
    """
    Move one or more papers to a target folder (or root when target_folder_id
    is None).  Returns the number of rows updated.
    """
    if not paper_ids:
        return 0
    conn = _connect()
    try:
        placeholders = ",".join("?" for _ in paper_ids)
        cur = conn.execute(
            f"UPDATE kb_papers SET folder_id = ? WHERE paper_id IN ({placeholders})",
            [target_folder_id, *paper_ids],
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tree query
# ---------------------------------------------------------------------------

def get_tree() -> dict:
    """
    Return the full knowledge-base tree:
    {
      "folders": [ ... nested ... ],
      "papers": [ ... root-level papers ... ]
    }
    Each paper dict includes a ``note_count`` field.
    """
    conn = _connect()
    try:
        folder_rows = conn.execute("SELECT * FROM kb_folders ORDER BY created_at").fetchall()
        paper_rows = conn.execute("SELECT * FROM kb_papers ORDER BY created_at DESC").fetchall()
        note_count_rows = conn.execute(
            "SELECT paper_id, COUNT(*) as cnt FROM kb_notes GROUP BY paper_id"
        ).fetchall()
    finally:
        conn.close()

    note_counts: dict[str, int] = {r["paper_id"]: r["cnt"] for r in note_count_rows}

    # Build folder lookup
    folders_by_id: dict[int, dict] = {}
    for row in folder_rows:
        d = _row_to_dict(row)
        d["children"] = []
        d["papers"] = []
        folders_by_id[d["id"]] = d

    # Attach papers to their folders (or collect root papers)
    root_papers: list[dict] = []
    for row in paper_rows:
        p = _row_to_dict(row)
        p["paper_data"] = json.loads(p["paper_data"])
        p["note_count"] = note_counts.get(p["paper_id"], 0)
        fid = p["folder_id"]
        if fid and fid in folders_by_id:
            folders_by_id[fid]["papers"].append(p)
        else:
            root_papers.append(p)

    # Build tree from flat list
    root_folders: list[dict] = []
    for fid, folder in folders_by_id.items():
        pid = folder["parent_id"]
        if pid and pid in folders_by_id:
            folders_by_id[pid]["children"].append(folder)
        else:
            root_folders.append(folder)

    return {"folders": root_folders, "papers": root_papers}


def is_paper_in_kb(paper_id: str) -> bool:
    """Check whether a paper is already saved in the KB."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM kb_papers WHERE paper_id = ? LIMIT 1", (paper_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Note / File CRUD
# ---------------------------------------------------------------------------

def list_notes(paper_id: str) -> list[dict]:
    """Return all notes / files attached to a paper (lightweight, no content)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, paper_id, type, title, file_path, file_url, file_size, mime_type, created_at, updated_at "
            "FROM kb_notes WHERE paper_id = ? ORDER BY created_at",
            (paper_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_note(note_id: int) -> Optional[dict]:
    """Return a single note including its content."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def create_note(paper_id: str, title: str, content: str = "") -> dict:
    """Create a new markdown note attached to a paper."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_notes (paper_id, type, title, content, created_at, updated_at) "
            "VALUES (?, 'markdown', ?, ?, ?, ?)",
            (paper_id, title, content, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_note(note_id: int, title: Optional[str] = None, content: Optional[str] = None) -> Optional[dict]:
    """Update the title and/or content of a note. Returns updated row or None."""
    now = _now_iso()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            return None
        new_title = title if title is not None else row["title"]
        new_content = content if content is not None else row["content"]
        conn.execute(
            "UPDATE kb_notes SET title = ?, content = ?, updated_at = ? WHERE id = ?",
            (new_title, new_content, now, note_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (note_id,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def delete_note(note_id: int) -> bool:
    """Delete a note/file. If it's an uploaded file, also remove from disk."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            return False
        # Remove physical file if present
        if row["file_path"]:
            abs_path = os.path.join(_KB_FILES_DIR, row["file_path"])
            if os.path.isfile(abs_path):
                os.remove(abs_path)
        conn.execute("DELETE FROM kb_notes WHERE id = ?", (note_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def add_note_file(
    paper_id: str,
    filename: str,
    file_bytes: bytes,
    mime_type: str,
) -> dict:
    """
    Save an uploaded file to disk and create a 'file' note entry.
    Files are stored under  data/kb_files/{paper_id}/{filename}.
    """
    paper_dir = os.path.join(_KB_FILES_DIR, paper_id)
    os.makedirs(paper_dir, exist_ok=True)

    # Avoid overwriting: if filename exists, add a numeric suffix
    base, ext = os.path.splitext(filename)
    dest = os.path.join(paper_dir, filename)
    counter = 1
    while os.path.exists(dest):
        filename = f"{base}_{counter}{ext}"
        dest = os.path.join(paper_dir, filename)
        counter += 1

    with open(dest, "wb") as f:
        f.write(file_bytes)

    rel_path = f"{paper_id}/{filename}"
    file_size = len(file_bytes)
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_notes (paper_id, type, title, file_path, file_size, mime_type, created_at, updated_at) "
            "VALUES (?, 'file', ?, ?, ?, ?, ?, ?)",
            (paper_id, filename, rel_path, file_size, mime_type, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def add_note_link(paper_id: str, title: str, url: str) -> dict:
    """Create a 'link' note entry pointing to an external URL."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_notes (paper_id, type, title, file_url, created_at, updated_at) "
            "VALUES (?, 'link', ?, ?, ?, ?)",
            (paper_id, title, url, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_note_counts_by_paper() -> dict[str, int]:
    """Return a mapping of paper_id -> note count for all papers that have notes."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT paper_id, COUNT(*) as cnt FROM kb_notes GROUP BY paper_id"
        ).fetchall()
        return {r["paper_id"]: r["cnt"] for r in rows}
    finally:
        conn.close()
