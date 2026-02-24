"""
Inspiration Generation v2 – data service layer.

Manages all idea-related data in the shared SQLite database
(Sever/database/paper_analysis.db), including:

Tables
------
idea_atoms            – Structured extractions from papers (Claim/Method/Setup/Limitation)
idea_atoms_fts        – FTS5 virtual table for full-text search on atoms
idea_questions        – Trigger questions mined from limitations / future work
idea_candidates       – Generated inspiration candidates with scores and revision history
idea_plans            – Executable experiment / landing plans linked to candidates
idea_feedback         – User actions on candidates (favorite / discard / modify / land)
idea_exemplars        – High-quality inspiration patterns mined from feedback
idea_prompt_versions  – Versioned prompts / templates for reproducibility
idea_benchmarks       – Evaluation benchmark question sets
idea_regen_runs       – Periodic regeneration run records

All data is scoped by ``user_id``.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "database", "paper_analysis.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ---------------------------------------------------------------------------
# Schema & init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all idea_* tables if they do not exist."""
    conn = _connect()
    try:
        conn.executescript("""
            -- Idea Atoms: structured extraction units from papers
            CREATE TABLE IF NOT EXISTS idea_atoms (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL DEFAULT 0,
                paper_id    TEXT    NOT NULL,
                date_str    TEXT    NOT NULL DEFAULT '',
                atom_type   TEXT    NOT NULL DEFAULT 'claim',
                content     TEXT    NOT NULL DEFAULT '',
                tags_json   TEXT    NOT NULL DEFAULT '[]',
                evidence_json TEXT  NOT NULL DEFAULT '[]',
                section     TEXT    NOT NULL DEFAULT '',
                source_file TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );

            -- FTS5 virtual table for full-text search on atoms
            CREATE VIRTUAL TABLE IF NOT EXISTS idea_atoms_fts USING fts5(
                content,
                tags,
                section,
                content='idea_atoms',
                content_rowid='id'
            );

            -- Triggers to keep FTS5 in sync with idea_atoms
            CREATE TRIGGER IF NOT EXISTS idea_atoms_ai AFTER INSERT ON idea_atoms BEGIN
                INSERT INTO idea_atoms_fts(rowid, content, tags, section)
                VALUES (new.id, new.content, new.tags_json, new.section);
            END;

            CREATE TRIGGER IF NOT EXISTS idea_atoms_ad AFTER DELETE ON idea_atoms BEGIN
                INSERT INTO idea_atoms_fts(idea_atoms_fts, rowid, content, tags, section)
                VALUES ('delete', old.id, old.content, old.tags_json, old.section);
            END;

            CREATE TRIGGER IF NOT EXISTS idea_atoms_au AFTER UPDATE ON idea_atoms BEGIN
                INSERT INTO idea_atoms_fts(idea_atoms_fts, rowid, content, tags, section)
                VALUES ('delete', old.id, old.content, old.tags_json, old.section);
                INSERT INTO idea_atoms_fts(rowid, content, tags, section)
                VALUES (new.id, new.content, new.tags_json, new.section);
            END;

            -- Trigger questions mined from limitations / future work
            CREATE TABLE IF NOT EXISTS idea_questions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL DEFAULT 0,
                source_atom_ids TEXT    NOT NULL DEFAULT '[]',
                question_text   TEXT    NOT NULL DEFAULT '',
                strategy        TEXT    NOT NULL DEFAULT '',
                context_json    TEXT    NOT NULL DEFAULT '{}',
                created_at      TEXT    NOT NULL
            );

            -- Generated inspiration candidates
            CREATE TABLE IF NOT EXISTS idea_candidates (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id              INTEGER NOT NULL DEFAULT 0,
                question_id          INTEGER DEFAULT NULL,
                title                TEXT    NOT NULL DEFAULT '',
                goal                 TEXT    NOT NULL DEFAULT '',
                mechanism            TEXT    NOT NULL DEFAULT '',
                input_atom_ids       TEXT    NOT NULL DEFAULT '[]',
                evidence_json        TEXT    NOT NULL DEFAULT '[]',
                risks                TEXT    NOT NULL DEFAULT '',
                scores_json          TEXT    NOT NULL DEFAULT '{}',
                status               TEXT    NOT NULL DEFAULT 'draft',
                revision_history_json TEXT   NOT NULL DEFAULT '[]',
                strategy             TEXT    NOT NULL DEFAULT '',
                folder_id            INTEGER DEFAULT NULL,
                tags_json            TEXT    NOT NULL DEFAULT '[]',
                created_at           TEXT    NOT NULL,
                updated_at           TEXT    NOT NULL
            );

            -- Executable plans linked to candidates
            CREATE TABLE IF NOT EXISTS idea_plans (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL DEFAULT 0,
                candidate_id    INTEGER NOT NULL,
                milestones_json TEXT    NOT NULL DEFAULT '[]',
                metrics         TEXT    NOT NULL DEFAULT '',
                datasets        TEXT    NOT NULL DEFAULT '',
                ablation        TEXT    NOT NULL DEFAULT '',
                cost            TEXT    NOT NULL DEFAULT '',
                timeline        TEXT    NOT NULL DEFAULT '',
                full_plan       TEXT    NOT NULL DEFAULT '',
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            );

            -- User feedback on candidates
            CREATE TABLE IF NOT EXISTS idea_feedback (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                candidate_id  INTEGER NOT NULL,
                action        TEXT    NOT NULL DEFAULT 'view',
                context_json  TEXT    NOT NULL DEFAULT '{}',
                created_at    TEXT    NOT NULL
            );

            -- High-quality exemplar patterns
            CREATE TABLE IF NOT EXISTS idea_exemplars (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL DEFAULT 0,
                candidate_id  INTEGER DEFAULT NULL,
                pattern_json  TEXT    NOT NULL DEFAULT '{}',
                score         REAL    NOT NULL DEFAULT 0.0,
                notes         TEXT    NOT NULL DEFAULT '',
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            );

            -- Prompt / template version tracking
            CREATE TABLE IF NOT EXISTS idea_prompt_versions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL DEFAULT 0,
                stage         TEXT    NOT NULL DEFAULT '',
                version       INTEGER NOT NULL DEFAULT 1,
                prompt_text   TEXT    NOT NULL DEFAULT '',
                metrics_json  TEXT    NOT NULL DEFAULT '{}',
                created_at    TEXT    NOT NULL
            );

            -- Evaluation benchmark question sets
            CREATE TABLE IF NOT EXISTS idea_benchmarks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL DEFAULT 0,
                name            TEXT    NOT NULL DEFAULT '',
                question_ids_json TEXT  NOT NULL DEFAULT '[]',
                model_version   TEXT    NOT NULL DEFAULT '',
                results_json    TEXT    NOT NULL DEFAULT '{}',
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            );

            -- Regeneration run records
            CREATE TABLE IF NOT EXISTS idea_regen_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL DEFAULT 0,
                trigger_type    TEXT    NOT NULL DEFAULT 'manual',
                question_ids_json TEXT  NOT NULL DEFAULT '[]',
                model_version   TEXT    NOT NULL DEFAULT '',
                status          TEXT    NOT NULL DEFAULT 'pending',
                results_json    TEXT    NOT NULL DEFAULT '{}',
                started_at      TEXT    NOT NULL,
                finished_at     TEXT
            );

            -- Idea library folders (reuse kb_folders with scope='idea_library')
            -- No separate table needed; we leverage kb_folders with scope='idea_library'
        """)
        conn.commit()
    finally:
        conn.close()


# Run on module import
init_db()


# ---------------------------------------------------------------------------
# Atom CRUD
# ---------------------------------------------------------------------------

def create_atom(
    user_id: int,
    paper_id: str,
    atom_type: str,
    content: str,
    tags: list[str] | None = None,
    evidence: list[dict] | None = None,
    section: str = "",
    date_str: str = "",
    source_file: str = "",
) -> dict:
    """Create a single idea atom. Returns the created row dict."""
    now = _now_iso()
    tags_json = json.dumps(tags or [], ensure_ascii=False)
    evidence_json = json.dumps(evidence or [], ensure_ascii=False)
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO idea_atoms
               (user_id, paper_id, date_str, atom_type, content, tags_json,
                evidence_json, section, source_file, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, paper_id, date_str, atom_type, content, tags_json,
             evidence_json, section, source_file, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_atoms WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _atom_row_to_dict(row)
    finally:
        conn.close()


def create_atoms_batch(user_id: int, atoms: list[dict]) -> int:
    """Batch-insert atoms. Returns count of inserted rows."""
    now = _now_iso()
    conn = _connect()
    try:
        rows = []
        for a in atoms:
            rows.append((
                user_id,
                a.get("paper_id", ""),
                a.get("date_str", ""),
                a.get("atom_type", "claim"),
                a.get("content", ""),
                json.dumps(a.get("tags", []), ensure_ascii=False),
                json.dumps(a.get("evidence", []), ensure_ascii=False),
                a.get("section", ""),
                a.get("source_file", ""),
                now, now,
            ))
        conn.executemany(
            """INSERT INTO idea_atoms
               (user_id, paper_id, date_str, atom_type, content, tags_json,
                evidence_json, section, source_file, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def get_atom(atom_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM idea_atoms WHERE id = ?", (atom_id,)).fetchone()
        return _atom_row_to_dict(row) if row else None
    finally:
        conn.close()



def list_atoms(
    user_id: int = 0,
    paper_id: str | None = None,
    atom_type: str | None = None,
    tag: str | None = None,
    date_str: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """List atoms with optional filters."""
    conn = _connect()
    try:
        clauses = ["1=1"]
        params: list = []
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if paper_id:
            clauses.append("paper_id = ?")
            params.append(paper_id)
        if atom_type:
            clauses.append("atom_type = ?")
            params.append(atom_type)
        if tag:
            clauses.append("tags_json LIKE ?")
            params.append(f"%{tag}%")
        if date_str:
            clauses.append("date_str = ?")
            params.append(date_str)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT * FROM idea_atoms WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [_atom_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def search_atoms_fts(query: str, user_id: int = 0, limit: int = 50) -> list[dict]:
    """Full-text search on atoms using FTS5."""
    conn = _connect()
    try:
        if user_id:
            rows = conn.execute(
                """SELECT a.* FROM idea_atoms a
                   JOIN idea_atoms_fts f ON a.id = f.rowid
                   WHERE idea_atoms_fts MATCH ? AND a.user_id = ?
                   ORDER BY rank LIMIT ?""",
                (query, user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.* FROM idea_atoms a
                   JOIN idea_atoms_fts f ON a.id = f.rowid
                   WHERE idea_atoms_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit),
            ).fetchall()
        return [_atom_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def delete_atoms_for_paper(user_id: int, paper_id: str) -> int:
    """Delete all atoms for a specific paper. Returns count deleted."""
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM idea_atoms WHERE user_id = ? AND paper_id = ?",
            (user_id, paper_id),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def delete_questions_for_date(user_id: int, date_str: str) -> int:
    """Delete all questions created on *date_str* for this user.

    Uses ``created_at LIKE '{date_str}%'`` because idea_questions has no
    explicit date_str column.  Returns count of rows deleted.
    """
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM idea_questions WHERE user_id = ? AND created_at LIKE ?",
            (user_id, f"{date_str}%"),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def delete_candidates_for_date(user_id: int, date_str: str) -> int:
    """Delete all candidates created on *date_str* for this user.

    Uses ``created_at LIKE '{date_str}%'`` because idea_candidates has no
    explicit date_str column.  Returns count of rows deleted.
    """
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM idea_candidates WHERE user_id = ? AND created_at LIKE ?",
            (user_id, f"{date_str}%"),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def count_atoms(user_id: int = 0) -> int:
    conn = _connect()
    try:
        if user_id:
            row = conn.execute("SELECT COUNT(*) as cnt FROM idea_atoms WHERE user_id = ?", (user_id,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) as cnt FROM idea_atoms").fetchone()
        return row["cnt"]
    finally:
        conn.close()


def _atom_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.pop("tags_json", "[]"))
    d["evidence"] = json.loads(d.pop("evidence_json", "[]"))
    return d


# ---------------------------------------------------------------------------
# Question CRUD
# ---------------------------------------------------------------------------

def create_question(
    user_id: int,
    question_text: str,
    source_atom_ids: list[int] | None = None,
    strategy: str = "",
    context: dict | None = None,
) -> dict:
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO idea_questions
               (user_id, source_atom_ids, question_text, strategy, context_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, json.dumps(source_atom_ids or []),
             question_text, strategy, json.dumps(context or {}), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_questions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _question_row_to_dict(row)
    finally:
        conn.close()


def list_questions(user_id: int, limit: int = 100, offset: int = 0) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM idea_questions WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
        return [_question_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_question(question_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM idea_questions WHERE id = ?", (question_id,)).fetchone()
        return _question_row_to_dict(row) if row else None
    finally:
        conn.close()


def _question_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["source_atom_ids"] = json.loads(d.pop("source_atom_ids", "[]"))
    d["context"] = json.loads(d.pop("context_json", "{}"))
    return d


# ---------------------------------------------------------------------------
# Candidate CRUD
# ---------------------------------------------------------------------------

def create_candidate(
    user_id: int,
    title: str,
    goal: str = "",
    mechanism: str = "",
    input_atom_ids: list[int] | None = None,
    evidence: list[dict] | None = None,
    risks: str = "",
    scores: dict | None = None,
    status: str = "draft",
    strategy: str = "",
    question_id: int | None = None,
    tags: list[str] | None = None,
    folder_id: int | None = None,
) -> dict:
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO idea_candidates
               (user_id, question_id, title, goal, mechanism, input_atom_ids,
                evidence_json, risks, scores_json, status, revision_history_json,
                strategy, folder_id, tags_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, ?)""",
            (user_id, question_id, title, goal, mechanism,
             json.dumps(input_atom_ids or []),
             json.dumps(evidence or []),
             risks,
             json.dumps(scores or {}),
             status, strategy, folder_id,
             json.dumps(tags or []),
             now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_candidates WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _candidate_row_to_dict(row)
    finally:
        conn.close()


def get_candidate(candidate_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM idea_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return _candidate_row_to_dict(row) if row else None
    finally:
        conn.close()


def list_candidates(
    user_id: int,
    status: str | None = None,
    folder_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    conn = _connect()
    try:
        clauses = ["user_id = ?"]
        params: list = [user_id]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if folder_id is not None:
            clauses.append("folder_id = ?")
            params.append(folder_id)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"SELECT * FROM idea_candidates WHERE {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [_candidate_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_candidate(
    candidate_id: int,
    user_id: int,
    **kwargs,
) -> dict | None:
    """Update candidate fields. Supports: title, goal, mechanism, risks, scores,
    status, folder_id, tags, revision_history (append)."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM idea_candidates WHERE id = ? AND user_id = ?",
            (candidate_id, user_id),
        ).fetchone()
        if row is None:
            return None

        updates = []
        params = []
        for key in ("title", "goal", "mechanism", "risks", "status", "strategy"):
            if key in kwargs:
                updates.append(f"{key} = ?")
                params.append(kwargs[key])
        if "scores" in kwargs:
            updates.append("scores_json = ?")
            params.append(json.dumps(kwargs["scores"], ensure_ascii=False))
        if "tags" in kwargs:
            updates.append("tags_json = ?")
            params.append(json.dumps(kwargs["tags"], ensure_ascii=False))
        if "folder_id" in kwargs:
            updates.append("folder_id = ?")
            params.append(kwargs["folder_id"])
        if "input_atom_ids" in kwargs:
            updates.append("input_atom_ids = ?")
            params.append(json.dumps(kwargs["input_atom_ids"]))
        if "evidence" in kwargs:
            updates.append("evidence_json = ?")
            params.append(json.dumps(kwargs["evidence"], ensure_ascii=False))
        if "revision_entry" in kwargs:
            # Append a new revision to history
            history = json.loads(row["revision_history_json"])
            history.append(kwargs["revision_entry"])
            updates.append("revision_history_json = ?")
            params.append(json.dumps(history, ensure_ascii=False))

        if not updates:
            return _candidate_row_to_dict(row)

        now = _now_iso()
        updates.append("updated_at = ?")
        params.append(now)
        params.extend([candidate_id, user_id])

        conn.execute(
            f"UPDATE idea_candidates SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
            params,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return _candidate_row_to_dict(row)
    finally:
        conn.close()


def delete_candidate(user_id: int, candidate_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM idea_candidates WHERE id = ? AND user_id = ?",
            (candidate_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_shared_candidates_for_date(
    date_str: str,
    allowed_paper_ids: list[str],
    viewer_user_id: int,
    limit: int = 200,
) -> tuple[list[dict], int]:
    """Return (candidates, total_available) from the admin pipeline (user_id=1) for a
    given date, filtered to only those whose source atoms come from papers the viewer
    is allowed to see.

    Steps
    -----
    1. Find atom IDs in idea_atoms where date_str matches and paper_id is in
       allowed_paper_ids (using any pipeline-owner user, i.e. no user_id filter on atoms).
    2. Collect all candidate IDs where input_atom_ids has at least one of those atom IDs.
    3. Exclude candidates already acted on (collect/discard) by viewer_user_id.
    4. Return up to `limit` candidates from the full filtered set.
    """
    if not allowed_paper_ids:
        return [], 0

    conn = _connect()
    try:
        # Step 1: get atom IDs for the date & allowed papers
        placeholders = ",".join("?" for _ in allowed_paper_ids)
        atom_rows = conn.execute(
            f"SELECT id FROM idea_atoms WHERE date_str = ? AND paper_id IN ({placeholders})",
            [date_str] + list(allowed_paper_ids),
        ).fetchall()
        allowed_atom_ids: set[int] = {r["id"] for r in atom_rows}

        if not allowed_atom_ids:
            return [], 0

        # Step 2: fetch all candidates (not scoped to user_id so admin candidates are visible)
        # and filter in Python for input_atom_ids intersection
        cand_rows = conn.execute(
            "SELECT * FROM idea_candidates ORDER BY updated_at DESC"
        ).fetchall()

        # Step 3: get candidate IDs already acted on by this viewer
        acted_rows = conn.execute(
            "SELECT DISTINCT candidate_id FROM idea_feedback "
            "WHERE user_id = ? AND action IN ('collect', 'discard')",
            (viewer_user_id,),
        ).fetchall()
        acted_ids: set[int] = {r["candidate_id"] for r in acted_rows}

        filtered: list[dict] = []
        for row in cand_rows:
            d = _candidate_row_to_dict(row)
            cid = d["id"]
            if cid in acted_ids:
                continue
            atom_ids_in_candidate = set(d.get("input_atom_ids") or [])
            if atom_ids_in_candidate & allowed_atom_ids:
                filtered.append(d)

        total_available = len(filtered)
        return filtered[:limit], total_available
    finally:
        conn.close()


def count_candidates(user_id: int, status: str | None = None) -> int:
    conn = _connect()
    try:
        if status:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM idea_candidates WHERE user_id = ? AND status = ?",
                (user_id, status),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM idea_candidates WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def _candidate_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["input_atom_ids"] = json.loads(d.pop("input_atom_ids", "[]"))
    d["evidence"] = json.loads(d.pop("evidence_json", "[]"))
    d["scores"] = json.loads(d.pop("scores_json", "{}"))
    d["revision_history"] = json.loads(d.pop("revision_history_json", "[]"))
    d["tags"] = json.loads(d.pop("tags_json", "[]"))
    return d


# ---------------------------------------------------------------------------
# Plan CRUD
# ---------------------------------------------------------------------------

def create_plan(
    user_id: int,
    candidate_id: int,
    milestones: list[dict] | None = None,
    metrics: str = "",
    datasets: str = "",
    ablation: str = "",
    cost: str = "",
    timeline: str = "",
    full_plan: str = "",
) -> dict:
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO idea_plans
               (user_id, candidate_id, milestones_json, metrics, datasets,
                ablation, cost, timeline, full_plan, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, candidate_id, json.dumps(milestones or []),
             metrics, datasets, ablation, cost, timeline, full_plan, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_plans WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _plan_row_to_dict(row)
    finally:
        conn.close()


def get_plan(plan_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM idea_plans WHERE id = ?", (plan_id,)).fetchone()
        return _plan_row_to_dict(row) if row else None
    finally:
        conn.close()


def get_plan_for_candidate(user_id: int, candidate_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM idea_plans WHERE user_id = ? AND candidate_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id, candidate_id),
        ).fetchone()
        return _plan_row_to_dict(row) if row else None
    finally:
        conn.close()


def _plan_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["milestones"] = json.loads(d.pop("milestones_json", "[]"))
    return d


# ---------------------------------------------------------------------------
# Feedback CRUD
# ---------------------------------------------------------------------------

def create_feedback(
    user_id: int,
    candidate_id: int,
    action: str,
    context: dict | None = None,
) -> dict:
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO idea_feedback
               (user_id, candidate_id, action, context_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, candidate_id, action, json.dumps(context or {}), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_feedback WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _feedback_row_to_dict(row)
    finally:
        conn.close()


def list_feedback(user_id: int, candidate_id: int | None = None, limit: int = 100) -> list[dict]:
    conn = _connect()
    try:
        if candidate_id:
            rows = conn.execute(
                "SELECT * FROM idea_feedback WHERE user_id = ? AND candidate_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, candidate_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM idea_feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [_feedback_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def _feedback_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["context"] = json.loads(d.pop("context_json", "{}"))
    return d


# ---------------------------------------------------------------------------
# Exemplar CRUD
# ---------------------------------------------------------------------------

def create_exemplar(
    user_id: int,
    candidate_id: int | None = None,
    pattern: dict | None = None,
    score: float = 0.0,
    notes: str = "",
) -> dict:
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO idea_exemplars
               (user_id, candidate_id, pattern_json, score, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, candidate_id, json.dumps(pattern or {}), score, notes, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_exemplars WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _exemplar_row_to_dict(row)
    finally:
        conn.close()


def list_exemplars(user_id: int, limit: int = 100) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM idea_exemplars WHERE user_id = ? ORDER BY score DESC, created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [_exemplar_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def delete_exemplar(user_id: int, exemplar_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM idea_exemplars WHERE id = ? AND user_id = ?",
            (exemplar_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _exemplar_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["pattern"] = json.loads(d.pop("pattern_json", "{}"))
    return d


# ---------------------------------------------------------------------------
# Prompt Version CRUD
# ---------------------------------------------------------------------------

def create_prompt_version(
    user_id: int,
    stage: str,
    prompt_text: str,
    metrics: dict | None = None,
) -> dict:
    conn = _connect()
    try:
        # Auto-increment version per stage
        row = conn.execute(
            "SELECT MAX(version) as max_v FROM idea_prompt_versions WHERE user_id = ? AND stage = ?",
            (user_id, stage),
        ).fetchone()
        next_v = (row["max_v"] or 0) + 1
        now = _now_iso()
        cur = conn.execute(
            """INSERT INTO idea_prompt_versions
               (user_id, stage, version, prompt_text, metrics_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, stage, next_v, prompt_text, json.dumps(metrics or {}), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_prompt_versions WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _prompt_version_row_to_dict(row)
    finally:
        conn.close()


def list_prompt_versions(user_id: int, stage: str | None = None) -> list[dict]:
    conn = _connect()
    try:
        if stage:
            rows = conn.execute(
                "SELECT * FROM idea_prompt_versions WHERE user_id = ? AND stage = ? ORDER BY version DESC",
                (user_id, stage),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM idea_prompt_versions WHERE user_id = ? ORDER BY stage, version DESC",
                (user_id,),
            ).fetchall()
        return [_prompt_version_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def _prompt_version_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["metrics"] = json.loads(d.pop("metrics_json", "{}"))
    return d


# ---------------------------------------------------------------------------
# Benchmark CRUD
# ---------------------------------------------------------------------------

def create_benchmark(
    user_id: int,
    name: str,
    question_ids: list[int] | None = None,
    model_version: str = "",
) -> dict:
    now = _now_iso()
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO idea_benchmarks
               (user_id, name, question_ids_json, model_version, results_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, '{}', ?, ?)""",
            (user_id, name, json.dumps(question_ids or []), model_version, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_benchmarks WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _benchmark_row_to_dict(row)
    finally:
        conn.close()


def list_benchmarks(user_id: int) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM idea_benchmarks WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_benchmark_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_benchmark_results(user_id: int, benchmark_id: int, results: dict) -> dict | None:
    conn = _connect()
    try:
        now = _now_iso()
        conn.execute(
            "UPDATE idea_benchmarks SET results_json = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (json.dumps(results, ensure_ascii=False), now, benchmark_id, user_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM idea_benchmarks WHERE id = ?", (benchmark_id,)).fetchone()
        return _benchmark_row_to_dict(row) if row else None
    finally:
        conn.close()


def _benchmark_row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["question_ids"] = json.loads(d.pop("question_ids_json", "[]"))
    d["results"] = json.loads(d.pop("results_json", "{}"))
    return d


# ---------------------------------------------------------------------------
# Dashboard / stats helpers
# ---------------------------------------------------------------------------

def get_stats(user_id: int) -> dict:
    """Return summary stats for the idea dashboard."""
    conn = _connect()
    try:
        atom_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM idea_atoms WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]
        question_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM idea_questions WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]
        candidate_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM idea_candidates WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]
        published_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM idea_candidates WHERE user_id = ? AND status = 'published'",
            (user_id,),
        ).fetchone()["cnt"]
        exemplar_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM idea_exemplars WHERE user_id = ?", (user_id,)
        ).fetchone()["cnt"]

        # Recent atoms by type
        type_dist = conn.execute(
            "SELECT atom_type, COUNT(*) as cnt FROM idea_atoms WHERE user_id = ? GROUP BY atom_type",
            (user_id,),
        ).fetchall()

        return {
            "atom_count": atom_count,
            "question_count": question_count,
            "candidate_count": candidate_count,
            "published_count": published_count,
            "exemplar_count": exemplar_count,
            "atom_type_distribution": {r["atom_type"]: r["cnt"] for r in type_dist},
        }
    finally:
        conn.close()
