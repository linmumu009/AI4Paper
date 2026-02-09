"""
FastAPI server for ArxivPaper4.
Provides REST API endpoints for the Vue frontend to consume paper data.

Usage:
    uvicorn api:app --reload --port 8000
    (run from the Sever/ directory)
"""

import os
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services import data_service
from services import kb_service

app = FastAPI(
    title="ArxivPaper4 API",
    description="Backend API for ArxivPaper4 paper digest system",
    version="1.0.0",
)

# CORS — allow Vue dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the data directory for static file access (PDFs, images, etc.)
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
if os.path.isdir(_DATA_DIR):
    app.mount("/static/data", StaticFiles(directory=_DATA_DIR), name="data")

# Ensure kb_files directory exists and mount it for uploaded file access
_KB_FILES_DIR = os.path.join(_DATA_DIR, "kb_files")
os.makedirs(_KB_FILES_DIR, exist_ok=True)
app.mount("/static/kb_files", StaticFiles(directory=_KB_FILES_DIR), name="kb_files")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/dates", summary="List available dates")
def api_list_dates():
    """Return all dates that have paper summary data available."""
    dates = data_service.list_dates()
    return {"dates": dates}


@app.get("/api/papers", summary="List papers for a date")
def api_list_papers(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    search: str = Query(None, description="Search in title / paper_id / institution"),
    institution: str = Query(None, description="Filter by institution name"),
):
    """Get all papers for a given date, with optional search and filter."""
    papers = data_service.get_papers_by_date(date, search=search, institution=institution)
    return {"date": date, "count": len(papers), "papers": papers}


@app.get("/api/papers/{paper_id}", summary="Get paper detail")
def api_paper_detail(paper_id: str):
    """Get full detail for a single paper including summary and structured analysis."""
    detail = data_service.get_paper_detail(paper_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    return detail


@app.get("/api/digest/{date}", summary="Daily digest")
def api_daily_digest(date: str):
    """Get daily digest: paper count, institution distribution, all papers."""
    digest = data_service.get_daily_digest(date)
    return digest


@app.get("/api/pipeline/status", summary="Pipeline status")
def api_pipeline_status(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
):
    """Check which pipeline steps have completed for a given date."""
    status = data_service.get_pipeline_status(date)
    return {"date": date, "steps": status}


# ---------------------------------------------------------------------------
# Knowledge Base Endpoints
# ---------------------------------------------------------------------------

class CreateFolderBody(BaseModel):
    name: str
    parent_id: Optional[int] = None

class RenameFolderBody(BaseModel):
    name: str

class AddPaperBody(BaseModel):
    paper_id: str
    paper_data: dict
    folder_id: Optional[int] = None

class MoveFolderBody(BaseModel):
    target_parent_id: Optional[int] = None

class MovePapersBody(BaseModel):
    paper_ids: list[str]
    target_folder_id: Optional[int] = None


@app.get("/api/kb/tree", summary="Get knowledge base tree")
def api_kb_tree():
    """Return full knowledge base tree: folders (nested) + root-level papers."""
    return kb_service.get_tree()


@app.post("/api/kb/folders", summary="Create folder")
def api_kb_create_folder(body: CreateFolderBody):
    """Create a new folder in the knowledge base."""
    folder = kb_service.create_folder(body.name, body.parent_id)
    return folder


@app.patch("/api/kb/folders/{folder_id}", summary="Rename folder")
def api_kb_rename_folder(folder_id: int, body: RenameFolderBody):
    """Rename an existing folder."""
    folder = kb_service.rename_folder(folder_id, body.name)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@app.patch("/api/kb/folders/{folder_id}/move", summary="Move folder")
def api_kb_move_folder(folder_id: int, body: MoveFolderBody):
    """Move a folder to a new parent (or root)."""
    folder = kb_service.move_folder(folder_id, body.target_parent_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@app.delete("/api/kb/folders/{folder_id}", summary="Delete folder")
def api_kb_delete_folder(folder_id: int):
    """Delete a folder. Its contents are moved to the parent folder (or root)."""
    ok = kb_service.delete_folder(folder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


@app.post("/api/kb/papers", summary="Add paper to KB")
def api_kb_add_paper(body: AddPaperBody):
    """Add (or update) a paper in the knowledge base."""
    paper = kb_service.add_paper(body.paper_id, body.paper_data, body.folder_id)
    return paper


@app.delete("/api/kb/papers/{paper_id}", summary="Remove paper from KB")
def api_kb_remove_paper(paper_id: str):
    """Remove a paper from the knowledge base."""
    ok = kb_service.remove_paper(paper_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    return {"ok": True}


@app.patch("/api/kb/papers/move", summary="Batch move papers")
def api_kb_move_papers(body: MovePapersBody):
    """Move one or more papers to a target folder (or root)."""
    count = kb_service.move_papers(body.paper_ids, body.target_folder_id)
    return {"ok": True, "moved": count}


# ---------------------------------------------------------------------------
# Note / File Endpoints
# ---------------------------------------------------------------------------

class CreateNoteBody(BaseModel):
    title: str = "未命名笔记"
    content: str = ""

class UpdateNoteBody(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class AddLinkBody(BaseModel):
    title: str
    url: str


@app.get("/api/kb/papers/{paper_id}/notes", summary="List notes for a paper")
def api_kb_list_notes(paper_id: str):
    """Return all notes / files attached to a paper."""
    notes = kb_service.list_notes(paper_id)
    return {"paper_id": paper_id, "notes": notes}


@app.post("/api/kb/papers/{paper_id}/notes", summary="Create markdown note")
def api_kb_create_note(paper_id: str, body: CreateNoteBody):
    """Create a new markdown note attached to a paper."""
    if not kb_service.is_paper_in_kb(paper_id):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    note = kb_service.create_note(paper_id, body.title, body.content)
    return note


@app.get("/api/kb/notes/{note_id}", summary="Get note detail")
def api_kb_get_note(note_id: int):
    """Get a single note including its content."""
    note = kb_service.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.patch("/api/kb/notes/{note_id}", summary="Update note")
def api_kb_update_note(note_id: int, body: UpdateNoteBody):
    """Update a note's title and/or content."""
    note = kb_service.update_note(note_id, body.title, body.content)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.delete("/api/kb/notes/{note_id}", summary="Delete note")
def api_kb_delete_note(note_id: int):
    """Delete a note or file attachment."""
    ok = kb_service.delete_note(note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


@app.post("/api/kb/papers/{paper_id}/notes/upload", summary="Upload file")
async def api_kb_upload_file(paper_id: str, file: UploadFile = File(...)):
    """Upload a file and attach it to a paper."""
    if not kb_service.is_paper_in_kb(paper_id):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    file_bytes = await file.read()
    mime = file.content_type or "application/octet-stream"
    note = kb_service.add_note_file(paper_id, file.filename or "upload", file_bytes, mime)
    return note


@app.post("/api/kb/papers/{paper_id}/notes/link", summary="Add link")
def api_kb_add_link(paper_id: str, body: AddLinkBody):
    """Add an external link note to a paper."""
    if not kb_service.is_paper_in_kb(paper_id):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    note = kb_service.add_note_link(paper_id, body.title, body.url)
    return note
