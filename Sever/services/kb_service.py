"""
Knowledge Base service layer.

Manages folders and saved papers in a local SQLite database
(Sever/database/paper_analysis.db).

**All KB data is scoped to a specific user (user_id) AND scope.**  Every table
carries ``user_id`` and ``scope`` columns and every query filters by both,
ensuring strict data isolation between users and between different KB contexts
(e.g. 'kb' for the discovery page, 'inspiration' for the inspiration page).

Tables
------
kb_folders           – hierarchical folder tree (self-referencing parent_id)
kb_papers            – papers saved into the KB, each optionally placed in a folder
kb_notes             – notes / files / links attached to a paper
kb_dismissed_papers  – per-user record of papers the user is not interested in
kb_annotations       – PDF highlight / annotation storage
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

_FILE_COLLECT_DIR = os.path.join(_BASE_DIR, "data", "file_collect")

_DEFAULT_SCOPE = "kb"


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema & migration
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they do not exist yet (new-style with user_id)."""
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kb_folders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL DEFAULT 0,
                scope      TEXT    NOT NULL DEFAULT 'kb',
                name       TEXT    NOT NULL,
                parent_id  INTEGER DEFAULT NULL
                           REFERENCES kb_folders(id) ON DELETE SET NULL,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kb_papers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL DEFAULT 0,
                scope      TEXT    NOT NULL DEFAULT 'kb',
                paper_id   TEXT    NOT NULL,
                folder_id  INTEGER DEFAULT NULL,
                paper_data TEXT    NOT NULL,
                created_at TEXT    NOT NULL,
                UNIQUE(user_id, paper_id, scope)
            );

            CREATE TABLE IF NOT EXISTS kb_notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL DEFAULT 0,
                scope      TEXT    NOT NULL DEFAULT 'kb',
                paper_id   TEXT    NOT NULL,
                type       TEXT    NOT NULL DEFAULT 'markdown',
                title      TEXT    NOT NULL,
                content    TEXT,
                file_path  TEXT,
                file_url   TEXT,
                file_size  INTEGER,
                mime_type  TEXT,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kb_dismissed_papers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                paper_id   TEXT    NOT NULL,
                created_at TEXT    NOT NULL,
                UNIQUE(user_id, paper_id)
            );

            CREATE TABLE IF NOT EXISTS kb_annotations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL DEFAULT 0,
                scope         TEXT    NOT NULL DEFAULT 'kb',
                paper_id      TEXT    NOT NULL,
                page          INTEGER NOT NULL,
                type          TEXT    NOT NULL DEFAULT 'highlight',
                content       TEXT,
                color         TEXT    DEFAULT '#FFFF00',
                position_data TEXT,
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kb_compare_results (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                title      TEXT    NOT NULL,
                markdown   TEXT    NOT NULL DEFAULT '',
                paper_ids  TEXT    NOT NULL DEFAULT '[]',
                folder_id  INTEGER DEFAULT NULL,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            );
            """
        )
        conn.commit()

        # Migrate legacy tables that lack user_id
        _migrate_add_user_id(conn)
        # Migrate tables that lack scope column
        _migrate_add_scope(conn)
    finally:
        conn.close()


def _migrate_add_user_id(conn: sqlite3.Connection) -> None:
    """
    One-time migration: add ``user_id`` to legacy tables that were created
    without it.  Existing rows receive ``user_id = 0``.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(kb_folders)").fetchall()}
    if "user_id" in cols:
        return  # Already migrated

    # Disable FK checks while we rebuild tables
    conn.execute("PRAGMA foreign_keys=OFF")

    # 1) kb_folders – simple ALTER
    conn.execute("ALTER TABLE kb_folders ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")

    # 2) kb_papers – need to recreate because UNIQUE constraint changes
    #    (old: paper_id UNIQUE  →  new: UNIQUE(user_id, paper_id))
    conn.execute("""
        CREATE TABLE kb_papers_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL DEFAULT 0,
            paper_id   TEXT    NOT NULL,
            folder_id  INTEGER DEFAULT NULL,
            paper_data TEXT    NOT NULL,
            created_at TEXT    NOT NULL,
            UNIQUE(user_id, paper_id)
        )
    """)
    conn.execute("""
        INSERT INTO kb_papers_new (id, user_id, paper_id, folder_id, paper_data, created_at)
        SELECT id, 0, paper_id, folder_id, paper_data, created_at FROM kb_papers
    """)
    conn.execute("DROP TABLE kb_papers")
    conn.execute("ALTER TABLE kb_papers_new RENAME TO kb_papers")

    # 3) kb_notes – recreate to drop old FK (paper_id is no longer unique)
    conn.execute("""
        CREATE TABLE kb_notes_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL DEFAULT 0,
            paper_id   TEXT    NOT NULL,
            type       TEXT    NOT NULL DEFAULT 'markdown',
            title      TEXT    NOT NULL,
            content    TEXT,
            file_path  TEXT,
            file_url   TEXT,
            file_size  INTEGER,
            mime_type  TEXT,
            created_at TEXT    NOT NULL,
            updated_at TEXT    NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO kb_notes_new (id, user_id, paper_id, type, title, content,
                                  file_path, file_url, file_size, mime_type,
                                  created_at, updated_at)
        SELECT id, 0, paper_id, type, title, content,
               file_path, file_url, file_size, mime_type,
               created_at, updated_at
        FROM kb_notes
    """)
    conn.execute("DROP TABLE kb_notes")
    conn.execute("ALTER TABLE kb_notes_new RENAME TO kb_notes")

    # 4) kb_annotations – simple ALTER
    conn.execute("ALTER TABLE kb_annotations ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")

    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()


def _migrate_add_scope(conn: sqlite3.Connection) -> None:
    """
    One-time migration: add ``scope`` column to tables that lack it.
    Existing rows receive ``scope = 'kb'``.
    Also rebuilds kb_papers to update the UNIQUE constraint to include scope.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(kb_folders)").fetchall()}
    if "scope" in cols:
        return  # Already migrated

    conn.execute("PRAGMA foreign_keys=OFF")

    # 1) kb_folders – simple ALTER
    conn.execute("ALTER TABLE kb_folders ADD COLUMN scope TEXT NOT NULL DEFAULT 'kb'")

    # 2) kb_papers – recreate to update UNIQUE(user_id, paper_id) → UNIQUE(user_id, paper_id, scope)
    conn.execute("""
        CREATE TABLE kb_papers_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL DEFAULT 0,
            scope      TEXT    NOT NULL DEFAULT 'kb',
            paper_id   TEXT    NOT NULL,
            folder_id  INTEGER DEFAULT NULL,
            paper_data TEXT    NOT NULL,
            created_at TEXT    NOT NULL,
            UNIQUE(user_id, paper_id, scope)
        )
    """)
    conn.execute("""
        INSERT INTO kb_papers_new (id, user_id, scope, paper_id, folder_id, paper_data, created_at)
        SELECT id, user_id, 'kb', paper_id, folder_id, paper_data, created_at FROM kb_papers
    """)
    conn.execute("DROP TABLE kb_papers")
    conn.execute("ALTER TABLE kb_papers_new RENAME TO kb_papers")

    # 3) kb_notes – simple ALTER
    conn.execute("ALTER TABLE kb_notes ADD COLUMN scope TEXT NOT NULL DEFAULT 'kb'")

    # 4) kb_annotations – simple ALTER
    conn.execute("ALTER TABLE kb_annotations ADD COLUMN scope TEXT NOT NULL DEFAULT 'kb'")

    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()


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

def create_folder(user_id: int, name: str, parent_id: Optional[int] = None, scope: str = _DEFAULT_SCOPE) -> dict:
    """Create a new folder. Returns the created folder dict."""
    now = _now_iso()
    conn = _connect()
    try:
        # Verify parent belongs to the same user and scope (if specified)
        if parent_id is not None:
            owner = conn.execute(
                "SELECT user_id, scope FROM kb_folders WHERE id = ?", (parent_id,)
            ).fetchone()
            if owner is None or owner["user_id"] != user_id or owner["scope"] != scope:
                parent_id = None  # Fall back to root

        cur = conn.execute(
            "INSERT INTO kb_folders (user_id, scope, name, parent_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, scope, name, parent_id, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_folders WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def rename_folder(user_id: int, folder_id: int, name: str, scope: str = _DEFAULT_SCOPE) -> Optional[dict]:
    """Rename a folder. Returns updated folder or None if not found."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE kb_folders SET name = ?, updated_at = ? WHERE id = ? AND user_id = ? AND scope = ?",
            (name, now, folder_id, user_id, scope),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM kb_folders WHERE id = ? AND user_id = ? AND scope = ?", (folder_id, user_id, scope)
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def move_folder(user_id: int, folder_id: int, target_parent_id: Optional[int], scope: str = _DEFAULT_SCOPE) -> Optional[dict]:
    """
    Move a folder under a new parent (or to root when target_parent_id is None).
    Returns the updated folder dict, or None if not found.
    Prevents moving a folder into itself or its own descendant.
    """
    now = _now_iso()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM kb_folders WHERE id = ? AND user_id = ? AND scope = ?", (folder_id, user_id, scope)
        ).fetchone()
        if row is None:
            return None

        # Prevent moving into itself
        if target_parent_id == folder_id:
            return _row_to_dict(row)

        # Verify target parent belongs to the same user and scope
        if target_parent_id is not None:
            target_owner = conn.execute(
                "SELECT user_id, scope FROM kb_folders WHERE id = ?", (target_parent_id,)
            ).fetchone()
            if target_owner is None or target_owner["user_id"] != user_id or target_owner["scope"] != scope:
                return _row_to_dict(row)  # invalid target, abort

        # Prevent moving into a descendant
        if target_parent_id is not None:
            ancestor = target_parent_id
            while ancestor is not None:
                if ancestor == folder_id:
                    return _row_to_dict(row)  # would create a cycle, abort
                r = conn.execute("SELECT parent_id FROM kb_folders WHERE id = ?", (ancestor,)).fetchone()
                ancestor = r["parent_id"] if r else None

        conn.execute(
            "UPDATE kb_folders SET parent_id = ?, updated_at = ? WHERE id = ? AND user_id = ? AND scope = ?",
            (target_parent_id, now, folder_id, user_id, scope),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM kb_folders WHERE id = ? AND user_id = ? AND scope = ?", (folder_id, user_id, scope)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def delete_folder(user_id: int, folder_id: int, scope: str = _DEFAULT_SCOPE) -> bool:
    """
    Delete a folder.  Its child folders and papers are re-parented to
    the deleted folder's parent (or root if the folder was top-level).
    Returns True if a row was actually deleted.
    """
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT parent_id FROM kb_folders WHERE id = ? AND user_id = ? AND scope = ?",
            (folder_id, user_id, scope),
        ).fetchone()
        if row is None:
            return False
        parent_id = row["parent_id"]  # may be None (root)

        # Re-parent child folders (only this user's, same scope)
        conn.execute(
            "UPDATE kb_folders SET parent_id = ? WHERE parent_id = ? AND user_id = ? AND scope = ?",
            (parent_id, folder_id, user_id, scope),
        )
        # Re-parent papers (only this user's, same scope)
        conn.execute(
            "UPDATE kb_papers SET folder_id = ? WHERE folder_id = ? AND user_id = ? AND scope = ?",
            (parent_id, folder_id, user_id, scope),
        )
        conn.execute(
            "DELETE FROM kb_folders WHERE id = ? AND user_id = ? AND scope = ?",
            (folder_id, user_id, scope),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Paper CRUD
# ---------------------------------------------------------------------------

def add_paper(user_id: int, paper_id: str, paper_data: dict, folder_id: Optional[int] = None, scope: str = _DEFAULT_SCOPE) -> dict:
    """
    Add a paper to the user's knowledge base.  If the paper already exists
    for this user in the given scope, update its folder and data instead.
    Returns the paper row dict.
    """
    now = _now_iso()
    data_json = json.dumps(paper_data, ensure_ascii=False)
    conn = _connect()
    try:
        # Verify folder belongs to the same user and scope (if specified)
        if folder_id is not None:
            owner = conn.execute(
                "SELECT user_id, scope FROM kb_folders WHERE id = ?", (folder_id,)
            ).fetchone()
            if owner is None or owner["user_id"] != user_id or owner["scope"] != scope:
                folder_id = None

        existing = conn.execute(
            "SELECT id FROM kb_papers WHERE user_id = ? AND paper_id = ? AND scope = ?",
            (user_id, paper_id, scope),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE kb_papers SET folder_id = ?, paper_data = ? WHERE user_id = ? AND paper_id = ? AND scope = ?",
                (folder_id, data_json, user_id, paper_id, scope),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM kb_papers WHERE user_id = ? AND paper_id = ? AND scope = ?",
                (user_id, paper_id, scope),
            ).fetchone()
        else:
            cur = conn.execute(
                "INSERT INTO kb_papers (user_id, scope, paper_id, folder_id, paper_data, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, scope, paper_id, folder_id, data_json, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM kb_papers WHERE id = ?", (cur.lastrowid,)).fetchone()
        result = _row_to_dict(row)
        result["paper_data"] = json.loads(result["paper_data"])
        return result
    finally:
        conn.close()


def remove_paper(user_id: int, paper_id: str, scope: str = _DEFAULT_SCOPE) -> bool:
    """Remove a paper from the user's knowledge base. Also removes associated
    notes (and their files) and annotations. Returns True if deleted."""
    conn = _connect()
    try:
        # Delete associated note files from disk
        note_rows = conn.execute(
            "SELECT * FROM kb_notes WHERE user_id = ? AND paper_id = ? AND scope = ?",
            (user_id, paper_id, scope),
        ).fetchall()
        for note in note_rows:
            if note["file_path"]:
                abs_path = os.path.join(_KB_FILES_DIR, note["file_path"])
                if os.path.isfile(abs_path):
                    try:
                        os.remove(abs_path)
                    except OSError:
                        pass

        # Delete notes
        conn.execute(
            "DELETE FROM kb_notes WHERE user_id = ? AND paper_id = ? AND scope = ?",
            (user_id, paper_id, scope),
        )
        # Delete annotations
        conn.execute(
            "DELETE FROM kb_annotations WHERE user_id = ? AND paper_id = ? AND scope = ?",
            (user_id, paper_id, scope),
        )
        # Delete the paper
        cur = conn.execute(
            "DELETE FROM kb_papers WHERE user_id = ? AND paper_id = ? AND scope = ?",
            (user_id, paper_id, scope),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def move_papers(user_id: int, paper_ids: list[str], target_folder_id: Optional[int], scope: str = _DEFAULT_SCOPE) -> int:
    """
    Move one or more papers to a target folder (or root when target_folder_id
    is None).  Returns the number of rows updated.
    """
    if not paper_ids:
        return 0
    conn = _connect()
    try:
        # Verify target folder belongs to user and same scope
        if target_folder_id is not None:
            owner = conn.execute(
                "SELECT user_id, scope FROM kb_folders WHERE id = ?", (target_folder_id,)
            ).fetchone()
            if owner is None or owner["user_id"] != user_id or owner["scope"] != scope:
                target_folder_id = None

        placeholders = ",".join("?" for _ in paper_ids)
        cur = conn.execute(
            f"UPDATE kb_papers SET folder_id = ? WHERE user_id = ? AND scope = ? AND paper_id IN ({placeholders})",
            [target_folder_id, user_id, scope, *paper_ids],
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tree query
# ---------------------------------------------------------------------------

def get_tree(user_id: int, scope: str = _DEFAULT_SCOPE) -> dict:
    """
    Return the full knowledge-base tree for a specific user and scope:
    {
      "folders": [ ... nested ... ],
      "papers": [ ... root-level papers ... ]
    }
    Each paper dict includes a ``note_count`` field.
    """
    conn = _connect()
    try:
        folder_rows = conn.execute(
            "SELECT * FROM kb_folders WHERE user_id = ? AND scope = ? ORDER BY created_at",
            (user_id, scope),
        ).fetchall()
        paper_rows = conn.execute(
            "SELECT * FROM kb_papers WHERE user_id = ? AND scope = ? ORDER BY created_at DESC",
            (user_id, scope),
        ).fetchall()
        note_count_rows = conn.execute(
            "SELECT paper_id, COUNT(*) as cnt FROM kb_notes WHERE user_id = ? AND scope = ? GROUP BY paper_id",
            (user_id, scope),
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


def get_paper_data(user_id: int, paper_id: str, scope: str = _DEFAULT_SCOPE) -> dict | None:
    """Return the parsed paper_data dict for a single KB paper, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT paper_data FROM kb_papers WHERE user_id = ? AND paper_id = ? AND scope = ? LIMIT 1",
            (user_id, paper_id, scope),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["paper_data"])
    finally:
        conn.close()


def is_paper_in_kb(user_id: int, paper_id: str, scope: str = _DEFAULT_SCOPE) -> bool:
    """Check whether a paper is already saved in the user's KB (in the given scope)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM kb_papers WHERE user_id = ? AND paper_id = ? AND scope = ? LIMIT 1",
            (user_id, paper_id, scope),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Note / File CRUD
# ---------------------------------------------------------------------------

def list_notes(user_id: int, paper_id: str, scope: str = _DEFAULT_SCOPE) -> list[dict]:
    """Return all notes / files attached to a paper (lightweight, no content)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, user_id, paper_id, type, title, file_path, file_url, file_size, mime_type, created_at, updated_at "
            "FROM kb_notes WHERE user_id = ? AND paper_id = ? AND scope = ? ORDER BY created_at",
            (user_id, paper_id, scope),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_note(user_id: int, note_id: int) -> Optional[dict]:
    """Return a single note including its content (only if it belongs to the user).
    Note: scope is not needed here since note_id is globally unique."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM kb_notes WHERE id = ? AND user_id = ?",
            (note_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def create_note(user_id: int, paper_id: str, title: str, content: str = "", scope: str = _DEFAULT_SCOPE) -> dict:
    """Create a new markdown note attached to a paper."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_notes (user_id, scope, paper_id, type, title, content, created_at, updated_at) "
            "VALUES (?, ?, ?, 'markdown', ?, ?, ?, ?)",
            (user_id, scope, paper_id, title, content, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_note(user_id: int, note_id: int, title: Optional[str] = None, content: Optional[str] = None) -> Optional[dict]:
    """Update the title and/or content of a note. Returns updated row or None.
    Note: scope is not needed here since note_id is globally unique."""
    now = _now_iso()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM kb_notes WHERE id = ? AND user_id = ?",
            (note_id, user_id),
        ).fetchone()
        if row is None:
            return None
        new_title = title if title is not None else row["title"]
        new_content = content if content is not None else row["content"]
        conn.execute(
            "UPDATE kb_notes SET title = ?, content = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (new_title, new_content, now, note_id, user_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM kb_notes WHERE id = ? AND user_id = ?",
            (note_id, user_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def delete_note(user_id: int, note_id: int) -> bool:
    """Delete a note/file. If it's an uploaded file, also remove from disk.
    Note: scope is not needed here since note_id is globally unique."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM kb_notes WHERE id = ? AND user_id = ?",
            (note_id, user_id),
        ).fetchone()
        if row is None:
            return False
        # Remove physical file if present
        if row["file_path"]:
            abs_path = os.path.join(_KB_FILES_DIR, row["file_path"])
            if os.path.isfile(abs_path):
                try:
                    os.remove(abs_path)
                except OSError:
                    pass
        conn.execute(
            "DELETE FROM kb_notes WHERE id = ? AND user_id = ?",
            (note_id, user_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def add_note_file(
    user_id: int,
    paper_id: str,
    filename: str,
    file_bytes: bytes,
    mime_type: str,
    scope: str = _DEFAULT_SCOPE,
) -> dict:
    """
    Save an uploaded file to disk and create a 'file' note entry.
    Files are stored under  data/kb_files/{user_id}/{paper_id}/{filename}.
    """
    paper_dir = os.path.join(_KB_FILES_DIR, str(user_id), paper_id)
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

    rel_path = f"{user_id}/{paper_id}/{filename}"
    file_size = len(file_bytes)
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_notes (user_id, scope, paper_id, type, title, file_path, file_size, mime_type, created_at, updated_at) "
            "VALUES (?, ?, ?, 'file', ?, ?, ?, ?, ?, ?)",
            (user_id, scope, paper_id, filename, rel_path, file_size, mime_type, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def add_note_link(user_id: int, paper_id: str, title: str, url: str, scope: str = _DEFAULT_SCOPE) -> dict:
    """Create a 'link' note entry pointing to an external URL."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_notes (user_id, scope, paper_id, type, title, file_url, created_at, updated_at) "
            "VALUES (?, ?, ?, 'link', ?, ?, ?, ?)",
            (user_id, scope, paper_id, title, url, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_note_counts_by_paper(user_id: int, scope: str = _DEFAULT_SCOPE) -> dict[str, int]:
    """Return a mapping of paper_id -> note count for the user's papers that have notes."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT paper_id, COUNT(*) as cnt FROM kb_notes WHERE user_id = ? AND scope = ? GROUP BY paper_id",
            (user_id, scope),
        ).fetchall()
        return {r["paper_id"]: r["cnt"] for r in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dismissed papers (per-user) — scope-independent
# ---------------------------------------------------------------------------

def dismiss_paper(user_id: int, paper_id: str) -> bool:
    """Record that a user is not interested in a paper. Returns True on success."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO kb_dismissed_papers (user_id, paper_id, created_at) "
            "VALUES (?, ?, ?)",
            (user_id, paper_id, now),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_dismissed_paper_ids(user_id: int) -> set[str]:
    """Return the set of paper_ids that the user has dismissed."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT paper_id FROM kb_dismissed_papers WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r["paper_id"] for r in rows}
    finally:
        conn.close()


def get_kb_paper_ids(user_id: int, scope: str = _DEFAULT_SCOPE) -> set[str]:
    """Return the set of all paper_ids currently in the user's knowledge base."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT paper_id FROM kb_papers WHERE user_id = ? AND scope = ?",
            (user_id, scope),
        ).fetchall()
        return {r["paper_id"] for r in rows}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Auto-attach PDF from file_collect
# ---------------------------------------------------------------------------

def _find_pdf_in_file_collect(paper_id: str) -> Optional[str]:
    """
    Search all date directories under data/file_collect/ for
    {date}/{paper_id}/{paper_id}.pdf.  Returns the absolute path if found.
    """
    if not os.path.isdir(_FILE_COLLECT_DIR):
        return None
    for date_dir in os.listdir(_FILE_COLLECT_DIR):
        pdf_path = os.path.join(_FILE_COLLECT_DIR, date_dir, paper_id, f"{paper_id}.pdf")
        if os.path.isfile(pdf_path):
            return pdf_path
    return None


def auto_attach_pdf(user_id: int, paper_id: str, scope: str = _DEFAULT_SCOPE) -> Optional[dict]:
    """
    Find the paper's PDF in file_collect and copy it to kb_files/{user_id}/{paper_id}/.
    Also creates a kb_notes entry of type 'file' so it appears in the sidebar.
    Returns the created note dict, or None if no PDF was found.
    Skips if the PDF is already attached (same filename exists in kb_notes).
    """
    # Check if there's already a PDF note for this paper from this user in the same scope
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT 1 FROM kb_notes WHERE user_id = ? AND paper_id = ? AND scope = ? AND type = 'file' "
            "AND title LIKE '%.pdf' LIMIT 1",
            (user_id, paper_id, scope),
        ).fetchone()
    finally:
        conn.close()

    if existing:
        return None  # PDF already attached

    source_pdf = _find_pdf_in_file_collect(paper_id)
    if source_pdf is None:
        return None

    # Copy PDF to kb_files/{user_id}/{paper_id}/
    paper_dir = os.path.join(_KB_FILES_DIR, str(user_id), paper_id)
    os.makedirs(paper_dir, exist_ok=True)
    filename = f"{paper_id}.pdf"
    dest = os.path.join(paper_dir, filename)
    if not os.path.isfile(dest):
        shutil.copy2(source_pdf, dest)

    # Create kb_notes entry
    rel_path = f"{user_id}/{paper_id}/{filename}"
    file_size = os.path.getsize(dest)
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_notes (user_id, scope, paper_id, type, title, file_path, file_size, mime_type, created_at, updated_at) "
            "VALUES (?, ?, ?, 'file', ?, ?, ?, 'application/pdf', ?, ?)",
            (user_id, scope, paper_id, filename, rel_path, file_size, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Annotation CRUD (PDF highlights / notes)
# ---------------------------------------------------------------------------

def list_annotations(user_id: int, paper_id: str, scope: str = _DEFAULT_SCOPE) -> list[dict]:
    """Return all annotations for a paper, ordered by page then creation time."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM kb_annotations WHERE user_id = ? AND paper_id = ? AND scope = ? ORDER BY page, created_at",
            (user_id, paper_id, scope),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def create_annotation(
    user_id: int,
    paper_id: str,
    page: int,
    type: str = "highlight",
    content: str = "",
    color: str = "#FFFF00",
    position_data: str = "",
    scope: str = _DEFAULT_SCOPE,
) -> dict:
    """Create a new annotation on a specific page of a paper's PDF."""
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO kb_annotations (user_id, scope, paper_id, page, type, content, color, position_data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, scope, paper_id, page, type, content, color, position_data, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_annotations WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_annotation(
    user_id: int,
    annotation_id: int,
    content: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[dict]:
    """Update an annotation's content and/or color.
    Note: scope is not needed here since annotation_id is globally unique."""
    now = _now_iso()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM kb_annotations WHERE id = ? AND user_id = ?",
            (annotation_id, user_id),
        ).fetchone()
        if row is None:
            return None
        new_content = content if content is not None else row["content"]
        new_color = color if color is not None else row["color"]
        conn.execute(
            "UPDATE kb_annotations SET content = ?, color = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (new_content, new_color, now, annotation_id, user_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM kb_annotations WHERE id = ? AND user_id = ?",
            (annotation_id, user_id),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def delete_annotation(user_id: int, annotation_id: int) -> bool:
    """Delete an annotation. Returns True if deleted.
    Note: scope is not needed here since annotation_id is globally unique."""
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM kb_annotations WHERE id = ? AND user_id = ?",
            (annotation_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Paper rename
# ---------------------------------------------------------------------------

def rename_paper(user_id: int, paper_id: str, new_title: str, scope: str = _DEFAULT_SCOPE) -> Optional[dict]:
    """Rename a paper's display title (short_title inside paper_data JSON).
    Returns the updated paper dict or None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM kb_papers WHERE user_id = ? AND paper_id = ? AND scope = ?",
            (user_id, paper_id, scope),
        ).fetchone()
        if row is None:
            return None
        paper_data = json.loads(row["paper_data"])
        paper_data["short_title"] = new_title
        data_json = json.dumps(paper_data, ensure_ascii=False)
        conn.execute(
            "UPDATE kb_papers SET paper_data = ? WHERE user_id = ? AND paper_id = ? AND scope = ?",
            (data_json, user_id, paper_id, scope),
        )
        conn.commit()
        result = _row_to_dict(row)
        result["paper_data"] = paper_data
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Compare Results CRUD
# ---------------------------------------------------------------------------

_COMPARE_RESULTS_SCOPE = "compare_results"


def add_compare_result(
    user_id: int,
    title: str,
    markdown: str,
    paper_ids: list[str],
    folder_id: Optional[int] = None,
) -> dict:
    """Save a compare result. Returns the created row dict."""
    now = _now_iso()
    paper_ids_json = json.dumps(paper_ids, ensure_ascii=False)
    conn = _connect()
    try:
        # Verify folder belongs to user (compare_results uses its own folders in scope='compare_results')
        if folder_id is not None:
            owner = conn.execute(
                "SELECT user_id, scope FROM kb_folders WHERE id = ?", (folder_id,)
            ).fetchone()
            if owner is None or owner["user_id"] != user_id or owner["scope"] != _COMPARE_RESULTS_SCOPE:
                folder_id = None

        cur = conn.execute(
            "INSERT INTO kb_compare_results (user_id, title, markdown, paper_ids, folder_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, title, markdown, paper_ids_json, folder_id, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM kb_compare_results WHERE id = ?", (cur.lastrowid,)).fetchone()
        result = _row_to_dict(row)
        result["paper_ids"] = json.loads(result["paper_ids"])
        return result
    finally:
        conn.close()


def get_compare_result(user_id: int, result_id: int) -> Optional[dict]:
    """Return a single compare result including markdown, or None."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM kb_compare_results WHERE id = ? AND user_id = ?",
            (result_id, user_id),
        ).fetchone()
        if row is None:
            return None
        result = _row_to_dict(row)
        result["paper_ids"] = json.loads(result["paper_ids"])
        return result
    finally:
        conn.close()


def rename_compare_result(user_id: int, result_id: int, title: str) -> Optional[dict]:
    """Rename a compare result. Returns updated row or None."""
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE kb_compare_results SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (title, now, result_id, user_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM kb_compare_results WHERE id = ? AND user_id = ?",
            (result_id, user_id),
        ).fetchone()
        if row is None:
            return None
        result = _row_to_dict(row)
        result["paper_ids"] = json.loads(result["paper_ids"])
        return result
    finally:
        conn.close()


def delete_compare_result(user_id: int, result_id: int) -> bool:
    """Delete a compare result. Returns True if deleted."""
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM kb_compare_results WHERE id = ? AND user_id = ?",
            (result_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_compare_results_tree(user_id: int) -> dict:
    """
    Return the compare results tree for a user:
    {
      "folders": [ ... nested ... ],
      "results": [ ... root-level compare results ... ]
    }
    Folders use scope='compare_results'.
    """
    scope = _COMPARE_RESULTS_SCOPE
    conn = _connect()
    try:
        folder_rows = conn.execute(
            "SELECT * FROM kb_folders WHERE user_id = ? AND scope = ? ORDER BY created_at",
            (user_id, scope),
        ).fetchall()
        result_rows = conn.execute(
            "SELECT id, user_id, title, paper_ids, folder_id, created_at, updated_at "
            "FROM kb_compare_results WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    # Build folder lookup
    folders_by_id: dict[int, dict] = {}
    for row in folder_rows:
        d = _row_to_dict(row)
        d["children"] = []
        d["results"] = []
        folders_by_id[d["id"]] = d

    # Attach results to folders or root
    root_results: list[dict] = []
    for row in result_rows:
        r = _row_to_dict(row)
        r["paper_ids"] = json.loads(r["paper_ids"])
        fid = r["folder_id"]
        if fid and fid in folders_by_id:
            folders_by_id[fid]["results"].append(r)
        else:
            root_results.append(r)

    # Build tree
    root_folders: list[dict] = []
    for fid, folder in folders_by_id.items():
        pid = folder["parent_id"]
        if pid and pid in folders_by_id:
            folders_by_id[pid]["children"].append(folder)
        else:
            root_folders.append(folder)

    return {"folders": root_folders, "results": root_results}


def move_compare_result(user_id: int, result_id: int, target_folder_id: Optional[int]) -> Optional[dict]:
    """Move a compare result to a folder (or root). Returns updated row or None."""
    conn = _connect()
    try:
        # Verify target folder
        if target_folder_id is not None:
            owner = conn.execute(
                "SELECT user_id, scope FROM kb_folders WHERE id = ?", (target_folder_id,)
            ).fetchone()
            if owner is None or owner["user_id"] != user_id or owner["scope"] != _COMPARE_RESULTS_SCOPE:
                target_folder_id = None

        conn.execute(
            "UPDATE kb_compare_results SET folder_id = ? WHERE id = ? AND user_id = ?",
            (target_folder_id, result_id, user_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM kb_compare_results WHERE id = ? AND user_id = ?",
            (result_id, user_id),
        ).fetchone()
        if row is None:
            return None
        result = _row_to_dict(row)
        result["paper_ids"] = json.loads(result["paper_ids"])
        return result
    finally:
        conn.close()
