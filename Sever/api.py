"""
FastAPI server for ArxivPaper4.
Provides REST API endpoints for the Vue frontend to consume paper data.

Usage:
    uvicorn api:app --reload --port 8000
    (run from the Sever/ directory)
"""

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fastapi.responses import StreamingResponse

from services import auth_service
from services import data_service
from services import kb_service
from services import compare_service
from services import user_settings_service
from services import config_service

app = FastAPI(
    title="ArxivPaper4 API",
    description="Backend API for ArxivPaper4 paper digest system",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    """应用启动时加载配置。"""
    config_service.load_config()

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

# Mount PDF.js viewer static files
_PDFJS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "pdfjs")
if os.path.isdir(_PDFJS_DIR):
    app.mount("/static/pdfjs", StaticFiles(directory=_PDFJS_DIR, html=True), name="pdfjs")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

class AuthCredentialBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)

class UpdateUserTierBody(BaseModel):
    tier: str = Field(..., pattern="^(free|pro|pro_plus)$")

class UpdateUserRoleBody(BaseModel):
    role: str = Field(..., pattern="^(user|admin|superadmin)$")

class RunPipelineBody(BaseModel):
    pipeline: str = Field(default="default")
    date: Optional[str] = None
    sllm: Optional[int] = None
    zo: Optional[str] = Field(default="F", pattern="^[TF]$")

class ScheduleConfigBody(BaseModel):
    enabled: bool
    hour: int = Field(default=6, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    pipeline: str = Field(default="daily")
    sllm: Optional[int] = None
    zo: Optional[str] = Field(default="F", pattern="^[TF]$")


def _set_session_cookie(resp: Response, session_id: str) -> None:
    resp.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=False,  # local dev over HTTP
        max_age=auth_service.SESSION_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )


def _clear_session_cookie(resp: Response) -> None:
    resp.delete_cookie(key=auth_service.SESSION_COOKIE_NAME, path="/")


def _get_optional_user(request: Request) -> Optional[dict]:
    session_id = request.cookies.get(auth_service.SESSION_COOKIE_NAME, "")
    return auth_service.get_user_by_session(session_id)


def _tier_quota_limit(user: Optional[dict]) -> Optional[int]:
    if not user:
        return 3
    tier = user.get("tier", "free")
    if tier == "pro":
        return 15
    if tier == "pro_plus":
        return None
    return 3


def _tier_label(user: Optional[dict]) -> str:
    if not user:
        return "anonymous"
    return user.get("tier", "free")


@app.post("/api/auth/register", summary="Register")
def api_auth_register(body: AuthCredentialBody):
    """Create a user account."""
    user = auth_service.register_user(body.username, body.password)
    return {"ok": True, "user": user}


@app.post("/api/auth/login", summary="Login")
def api_auth_login(body: AuthCredentialBody, request: Request, response: Response):
    """Login and set session cookie."""
    user = auth_service.verify_credentials(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    session = auth_service.create_session(
        user_id=user["id"],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session["session_id"])
    return {"ok": True, "user": user}


@app.post("/api/auth/logout", summary="Logout")
def api_auth_logout(request: Request, response: Response):
    """Logout and clear session cookie."""
    session_id = request.cookies.get(auth_service.SESSION_COOKIE_NAME, "")
    auth_service.delete_session(session_id)
    _clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me", summary="Current user")
def api_auth_me(request: Request):
    """Return current authenticated user if session exists."""
    session_id = request.cookies.get(auth_service.SESSION_COOKIE_NAME, "")
    user = auth_service.get_user_by_session(session_id)
    return {"authenticated": user is not None, "user": user}


# ---------------------------------------------------------------------------
# User Settings
# ---------------------------------------------------------------------------

class UserSettingsBody(BaseModel):
    settings: dict


@app.get("/api/user/settings/{feature}", summary="Get user settings for a feature")
def api_get_user_settings(feature: str, _user=Depends(auth_service.require_user)):
    """Return merged settings (user overrides + defaults) for the given feature."""
    settings = user_settings_service.get_settings(_user["id"], feature)
    defaults = user_settings_service.get_defaults(feature)
    return {"ok": True, "feature": feature, "settings": settings, "defaults": defaults}


@app.put("/api/user/settings/{feature}", summary="Save user settings for a feature")
def api_save_user_settings(feature: str, body: UserSettingsBody, _user=Depends(auth_service.require_user)):
    """Upsert user settings for the given feature."""
    merged = user_settings_service.save_settings(_user["id"], feature, body.settings)
    defaults = user_settings_service.get_defaults(feature)
    return {"ok": True, "feature": feature, "settings": merged, "defaults": defaults}


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

@app.get("/api/admin/users", summary="Admin list users")
def api_admin_list_users(_admin=Depends(auth_service.require_admin_user)):
    """List all registered users for admin management."""
    return {"users": auth_service.list_users()}


@app.patch("/api/admin/users/{user_id}/tier", summary="Admin update user tier")
def api_admin_update_user_tier(
    user_id: int,
    body: UpdateUserTierBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """Update a user's subscription tier."""
    user = auth_service.update_user_tier(user_id, body.tier)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True, "user": user}


@app.patch("/api/admin/users/{user_id}/role", summary="Superadmin update user role")
def api_admin_update_user_role(
    user_id: int,
    body: UpdateUserRoleBody,
    admin=Depends(auth_service.require_superadmin_user),
):
    """Update a user's role. Only superadmin can do this."""
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    user = auth_service.update_user_role(user_id, body.role)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True, "user": user}


# ---------------------------------------------------------------------------
# Pipeline Execution & Scheduling
# ---------------------------------------------------------------------------

_SEVER_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_PY_PATH = os.path.join(_SEVER_DIR, "app.py")
_SCHEDULE_CONFIG_PATH = os.path.join(_SEVER_DIR, "database", "schedule_config.json")

# In-memory pipeline run state
_pipeline_state: dict = {
    "running": False,
    "current_step": None,
    "logs": [],
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "params": {},
    "process": None,
}
_pipeline_lock = threading.Lock()

# Scheduler state
_scheduler_state: dict = {
    "enabled": False,
    "hour": 6,
    "minute": 0,
    "pipeline": "daily",
    "sllm": None,
    "zo": "F",
    "last_run_date": None,
}
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop_event = threading.Event()


def _load_schedule_config() -> dict:
    """Load schedule config from disk."""
    if os.path.isfile(_SCHEDULE_CONFIG_PATH):
        try:
            with open(_SCHEDULE_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_schedule_config(cfg: dict) -> None:
    """Save schedule config to disk."""
    os.makedirs(os.path.dirname(_SCHEDULE_CONFIG_PATH), exist_ok=True)
    with open(_SCHEDULE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _run_pipeline_thread(pipeline: str, date_str: str, sllm: Optional[int], zo: str):
    """Execute pipeline in a background thread, capturing output line by line."""
    global _pipeline_state
    cmd = [sys.executable, "-u", _APP_PY_PATH, pipeline, "--date", date_str, "--Zo", zo]
    if sllm is not None:
        cmd.extend(["--SLLM", str(sllm)])

    env = {**os.environ, "RUN_DATE": date_str}
    if sllm is not None:
        env["SLLM"] = str(sllm)

    with _pipeline_lock:
        _pipeline_state["running"] = True
        _pipeline_state["current_step"] = "启动中..."
        _pipeline_state["logs"] = [f"[{datetime.now().strftime('%H:%M:%S')}] 启动 Pipeline: {pipeline}  日期: {date_str}"]
        _pipeline_state["started_at"] = datetime.now(timezone.utc).isoformat()
        _pipeline_state["finished_at"] = None
        _pipeline_state["exit_code"] = None
        _pipeline_state["params"] = {"pipeline": pipeline, "date": date_str, "sllm": sllm, "zo": zo}

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=_SEVER_DIR,
            env=env,
        )
        with _pipeline_lock:
            _pipeline_state["process"] = proc

        for line in proc.stdout:
            line = line.rstrip("\n")
            with _pipeline_lock:
                _pipeline_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {line}")
                # Keep last 500 lines
                if len(_pipeline_state["logs"]) > 500:
                    _pipeline_state["logs"] = _pipeline_state["logs"][-500:]
                # Detect current step from output
                if line.startswith("RUN step:"):
                    _pipeline_state["current_step"] = line.replace("RUN step:", "").strip()
                elif line.startswith("SKIP step:"):
                    _pipeline_state["current_step"] = f"跳过: {line.replace('SKIP step:', '').strip()}"

        proc.wait()
        exit_code = proc.returncode
    except Exception as exc:
        exit_code = -1
        with _pipeline_lock:
            _pipeline_state["logs"].append(f"[ERROR] {exc}")
    finally:
        with _pipeline_lock:
            _pipeline_state["running"] = False
            _pipeline_state["finished_at"] = datetime.now(timezone.utc).isoformat()
            _pipeline_state["exit_code"] = exit_code
            _pipeline_state["current_step"] = "已完成" if exit_code == 0 else f"异常退出 (code={exit_code})"
            _pipeline_state["process"] = None


def _scheduler_loop():
    """Background thread that triggers daily pipeline runs."""
    while not _scheduler_stop_event.is_set():
        now = datetime.now()
        cfg = _scheduler_state
        if (
            cfg.get("enabled")
            and now.hour == cfg.get("hour", 6)
            and now.minute == cfg.get("minute", 0)
            and cfg.get("last_run_date") != now.date().isoformat()
        ):
            # Time to run!
            with _pipeline_lock:
                if _pipeline_state["running"]:
                    # Already running, skip
                    pass
                else:
                    date_str = now.date().isoformat()
                    cfg["last_run_date"] = date_str
                    t = threading.Thread(
                        target=_run_pipeline_thread,
                        args=(cfg.get("pipeline", "daily"), date_str, cfg.get("sllm"), cfg.get("zo", "F")),
                        daemon=True,
                    )
                    t.start()
        # Sleep 30 seconds before checking again
        _scheduler_stop_event.wait(30)


def _start_scheduler():
    """Start the scheduler background thread if not already running."""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    _scheduler_stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()


# Load saved schedule on startup
_saved_schedule = _load_schedule_config()
if _saved_schedule:
    _scheduler_state.update(_saved_schedule)
    if _scheduler_state.get("enabled"):
        _start_scheduler()


@app.post("/api/admin/pipeline/run", summary="Manually run pipeline")
def api_admin_run_pipeline(
    body: RunPipelineBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """Manually trigger a pipeline run. Can be called even when auto-schedule is active."""
    with _pipeline_lock:
        if _pipeline_state["running"]:
            raise HTTPException(status_code=409, detail="Pipeline 正在运行中，请等待完成")

    date_str = body.date or datetime.now().date().isoformat()
    t = threading.Thread(
        target=_run_pipeline_thread,
        args=(body.pipeline, date_str, body.sllm, body.zo or "F"),
        daemon=True,
    )
    t.start()
    return {"ok": True, "message": f"Pipeline '{body.pipeline}' 已启动，日期: {date_str}"}


@app.get("/api/admin/pipeline/status", summary="Get pipeline run status")
def api_admin_pipeline_run_status(
    _admin=Depends(auth_service.require_admin_user),
):
    """Get current pipeline execution status and logs."""
    with _pipeline_lock:
        return {
            "running": _pipeline_state["running"],
            "current_step": _pipeline_state["current_step"],
            "logs": list(_pipeline_state["logs"]),
            "started_at": _pipeline_state["started_at"],
            "finished_at": _pipeline_state["finished_at"],
            "exit_code": _pipeline_state["exit_code"],
            "params": _pipeline_state["params"],
        }


@app.post("/api/admin/pipeline/stop", summary="Stop running pipeline")
def api_admin_stop_pipeline(
    _admin=Depends(auth_service.require_admin_user),
):
    """Attempt to stop a running pipeline."""
    with _pipeline_lock:
        proc = _pipeline_state.get("process")
        if proc is not None and _pipeline_state["running"]:
            try:
                proc.terminate()
            except Exception:
                pass
            return {"ok": True, "message": "已发送终止信号"}
    raise HTTPException(status_code=400, detail="当前没有正在运行的 Pipeline")


@app.get("/api/admin/schedule", summary="Get schedule config")
def api_admin_get_schedule(
    _admin=Depends(auth_service.require_admin_user),
):
    """Get current auto-schedule configuration."""
    return {
        "enabled": _scheduler_state.get("enabled", False),
        "hour": _scheduler_state.get("hour", 6),
        "minute": _scheduler_state.get("minute", 0),
        "pipeline": _scheduler_state.get("pipeline", "daily"),
        "sllm": _scheduler_state.get("sllm"),
        "zo": _scheduler_state.get("zo", "F"),
        "last_run_date": _scheduler_state.get("last_run_date"),
    }


@app.post("/api/admin/schedule", summary="Update schedule config")
def api_admin_update_schedule(
    body: ScheduleConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """Update auto-schedule configuration."""
    _scheduler_state["enabled"] = body.enabled
    _scheduler_state["hour"] = body.hour
    _scheduler_state["minute"] = body.minute
    _scheduler_state["pipeline"] = body.pipeline
    _scheduler_state["sllm"] = body.sllm
    _scheduler_state["zo"] = body.zo or "F"

    # Persist to disk
    _save_schedule_config({
        "enabled": body.enabled,
        "hour": body.hour,
        "minute": body.minute,
        "pipeline": body.pipeline,
        "sllm": body.sllm,
        "zo": body.zo or "F",
    })

    if body.enabled:
        _start_scheduler()

    return {"ok": True, "schedule": {
        "enabled": body.enabled,
        "hour": body.hour,
        "minute": body.minute,
        "pipeline": body.pipeline,
        "sllm": body.sllm,
        "zo": body.zo or "F",
    }}


# ---------------------------------------------------------------------------
# System Config Management
# ---------------------------------------------------------------------------

class SystemConfigBody(BaseModel):
    config: dict = Field(..., description="配置项字典")


@app.get("/api/admin/config", summary="Get system configuration")
def api_admin_get_config(
    _admin=Depends(auth_service.require_admin_user),
):
    """获取所有系统配置项（按分组组织）。"""
    try:
        result = config_service.get_config_with_groups()
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@app.post("/api/admin/config", summary="Update system configuration")
def api_admin_update_config(
    body: SystemConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """更新系统配置项。"""
    try:
        updated = config_service.update_config(body.config)
        return {"ok": True, "config": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@app.post("/api/admin/config/reset", summary="Reset system configuration to defaults")
def api_admin_reset_config(
    _admin=Depends(auth_service.require_admin_user),
):
    """重置所有配置为默认值。"""
    try:
        config_service.reset_config()
        return {"ok": True, "message": "配置已重置为默认值"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置配置失败: {str(e)}")


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
    user: Optional[dict] = Depends(_get_optional_user),
):
    """Get all papers for a given date, with optional search and filter."""
    papers = data_service.get_papers_by_date(date, search=search, institution=institution)
    total_available = len(papers)
    quota_limit = _tier_quota_limit(user)
    if quota_limit is not None:
        papers = papers[:quota_limit]
    return {
        "date": date,
        "count": len(papers),
        "papers": papers,
        "total_available": total_available,
        "quota_limit": quota_limit,
        "tier": _tier_label(user),
    }


@app.get("/api/papers/{paper_id}", summary="Get paper detail")
def api_paper_detail(paper_id: str):
    """Get full detail for a single paper including summary and structured analysis."""
    detail = data_service.get_paper_detail(paper_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not found")
    return detail


@app.get("/api/digest/{date}", summary="Daily digest")
def api_daily_digest(
    date: str,
    user: Optional[dict] = Depends(_get_optional_user),
):
    """Get daily digest: paper count, institution distribution, all papers."""
    digest = data_service.get_daily_digest(date)
    papers = digest.get("papers", [])

    # Filter out papers already in KB or dismissed by the current user
    kb_ids: set[str] = set()
    dismissed_ids: set[str] = set()
    if user:
        kb_ids = kb_service.get_kb_paper_ids(user["id"])
        dismissed_ids = kb_service.get_dismissed_paper_ids(user["id"])
    exclude_ids = kb_ids | dismissed_ids
    if exclude_ids:
        papers = [p for p in papers if p.get("paper_id") not in exclude_ids]

    total_available = len(papers)
    quota_limit = _tier_quota_limit(user)
    if quota_limit is not None:
        digest["papers"] = papers[:quota_limit]
    else:
        digest["papers"] = papers
    digest["total_available"] = total_available
    digest["total_papers"] = len(digest["papers"])
    digest["quota_limit"] = quota_limit
    digest["tier"] = _tier_label(user)
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
    scope: str = "kb"

class RenameFolderBody(BaseModel):
    name: str
    scope: str = "kb"

class AddPaperBody(BaseModel):
    paper_id: str
    paper_data: dict
    folder_id: Optional[int] = None
    scope: str = "kb"

class MoveFolderBody(BaseModel):
    target_parent_id: Optional[int] = None
    scope: str = "kb"

class MovePapersBody(BaseModel):
    paper_ids: list[str]
    target_folder_id: Optional[int] = None
    scope: str = "kb"


@app.get("/api/kb/tree", summary="Get knowledge base tree")
def api_kb_tree(scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    """Return full knowledge base tree: folders (nested) + root-level papers."""
    return kb_service.get_tree(_user["id"], scope=scope)


@app.post("/api/kb/folders", summary="Create folder")
def api_kb_create_folder(body: CreateFolderBody, _user=Depends(auth_service.require_user)):
    """Create a new folder in the knowledge base."""
    folder = kb_service.create_folder(_user["id"], body.name, body.parent_id, scope=body.scope)
    return folder


@app.patch("/api/kb/folders/{folder_id}", summary="Rename folder")
def api_kb_rename_folder(folder_id: int, body: RenameFolderBody, _user=Depends(auth_service.require_user)):
    """Rename an existing folder."""
    folder = kb_service.rename_folder(_user["id"], folder_id, body.name, scope=body.scope)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@app.patch("/api/kb/folders/{folder_id}/move", summary="Move folder")
def api_kb_move_folder(folder_id: int, body: MoveFolderBody, _user=Depends(auth_service.require_user)):
    """Move a folder to a new parent (or root)."""
    folder = kb_service.move_folder(_user["id"], folder_id, body.target_parent_id, scope=body.scope)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@app.delete("/api/kb/folders/{folder_id}", summary="Delete folder")
def api_kb_delete_folder(folder_id: int, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    """Delete a folder. Its contents are moved to the parent folder (or root)."""
    ok = kb_service.delete_folder(_user["id"], folder_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


@app.post("/api/kb/papers", summary="Add paper to KB")
def api_kb_add_paper(body: AddPaperBody, _user=Depends(auth_service.require_user)):
    """Add (or update) a paper in the knowledge base. Also auto-attaches the PDF from file_collect."""
    paper = kb_service.add_paper(_user["id"], body.paper_id, body.paper_data, body.folder_id, scope=body.scope)
    # Auto-attach PDF from file_collect (runs in background, non-blocking)
    try:
        kb_service.auto_attach_pdf(_user["id"], body.paper_id, scope=body.scope)
    except Exception:
        pass  # Don't fail the whole request if PDF copy fails
    return paper


@app.delete("/api/kb/papers/{paper_id}", summary="Remove paper from KB")
def api_kb_remove_paper(paper_id: str, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    """Remove a paper from the knowledge base."""
    ok = kb_service.remove_paper(_user["id"], paper_id, scope=scope)
    if not ok:
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    return {"ok": True}


@app.patch("/api/kb/papers/move", summary="Batch move papers")
def api_kb_move_papers(body: MovePapersBody, _user=Depends(auth_service.require_user)):
    """Move one or more papers to a target folder (or root)."""
    count = kb_service.move_papers(_user["id"], body.paper_ids, body.target_folder_id, scope=body.scope)
    return {"ok": True, "moved": count}


# ---------------------------------------------------------------------------
# Note / File Endpoints
# ---------------------------------------------------------------------------

class CreateNoteBody(BaseModel):
    title: str = "未命名笔记"
    content: str = ""
    scope: str = "kb"

class UpdateNoteBody(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class AddLinkBody(BaseModel):
    title: str
    url: str
    scope: str = "kb"


@app.get("/api/kb/papers/{paper_id}/notes", summary="List notes for a paper")
def api_kb_list_notes(paper_id: str, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    """Return all notes / files attached to a paper."""
    notes = kb_service.list_notes(_user["id"], paper_id, scope=scope)
    return {"paper_id": paper_id, "notes": notes}


@app.post("/api/kb/papers/{paper_id}/notes", summary="Create markdown note")
def api_kb_create_note(paper_id: str, body: CreateNoteBody, _user=Depends(auth_service.require_user)):
    """Create a new markdown note attached to a paper."""
    if not kb_service.is_paper_in_kb(_user["id"], paper_id, scope=body.scope):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    note = kb_service.create_note(_user["id"], paper_id, body.title, body.content, scope=body.scope)
    return note


@app.get("/api/kb/notes/{note_id}", summary="Get note detail")
def api_kb_get_note(note_id: int, _user=Depends(auth_service.require_user)):
    """Get a single note including its content."""
    note = kb_service.get_note(_user["id"], note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.patch("/api/kb/notes/{note_id}", summary="Update note")
def api_kb_update_note(note_id: int, body: UpdateNoteBody, _user=Depends(auth_service.require_user)):
    """Update a note's title and/or content."""
    note = kb_service.update_note(_user["id"], note_id, body.title, body.content)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.delete("/api/kb/notes/{note_id}", summary="Delete note")
def api_kb_delete_note(note_id: int, _user=Depends(auth_service.require_user)):
    """Delete a note or file attachment."""
    ok = kb_service.delete_note(_user["id"], note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


@app.post("/api/kb/papers/{paper_id}/notes/upload", summary="Upload file")
async def api_kb_upload_file(
    paper_id: str,
    scope: str = Query("kb"),
    file: UploadFile = File(...),
    _user=Depends(auth_service.require_user),
):
    """Upload a file and attach it to a paper."""
    if not kb_service.is_paper_in_kb(_user["id"], paper_id, scope=scope):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    file_bytes = await file.read()
    mime = file.content_type or "application/octet-stream"
    note = kb_service.add_note_file(_user["id"], paper_id, file.filename or "upload", file_bytes, mime, scope=scope)
    return note


@app.post("/api/kb/papers/{paper_id}/notes/link", summary="Add link")
def api_kb_add_link(paper_id: str, body: AddLinkBody, _user=Depends(auth_service.require_user)):
    """Add an external link note to a paper."""
    if not kb_service.is_paper_in_kb(_user["id"], paper_id, scope=body.scope):
        raise HTTPException(status_code=404, detail="Paper not in knowledge base")
    note = kb_service.add_note_link(_user["id"], paper_id, body.title, body.url, scope=body.scope)
    return note


# ---------------------------------------------------------------------------
# Dismiss paper (not interested)
# ---------------------------------------------------------------------------

class ComparePapersBody(BaseModel):
    paper_ids: list[str] = Field(..., min_length=2, max_length=5)
    scope: str = "kb"


@app.post("/api/kb/compare", summary="Compare papers via LLM (SSE)")
def api_kb_compare(body: ComparePapersBody, _user=Depends(auth_service.require_user)):
    """Stream a comparative analysis of 2-5 KB papers using an LLM."""
    return StreamingResponse(
        compare_service.stream_compare(_user["id"], body.paper_ids, body.scope),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class DismissPaperBody(BaseModel):
    paper_id: str


@app.post("/api/kb/dismiss", summary="Dismiss paper")
def api_kb_dismiss_paper(body: DismissPaperBody, user=Depends(auth_service.require_user)):
    """Record that the current user is not interested in a paper."""
    kb_service.dismiss_paper(user["id"], body.paper_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Paper rename
# ---------------------------------------------------------------------------

class RenamePaperBody(BaseModel):
    title: str
    scope: str = "kb"


@app.patch("/api/kb/papers/{paper_id}/rename", summary="Rename paper")
def api_kb_rename_paper(paper_id: str, body: RenamePaperBody, _user=Depends(auth_service.require_user)):
    """Rename a paper's display title (short_title)."""
    result = kb_service.rename_paper(_user["id"], paper_id, body.title, scope=body.scope)
    if result is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return result


# ---------------------------------------------------------------------------
# Compare Results Endpoints
# ---------------------------------------------------------------------------

class SaveCompareResultBody(BaseModel):
    title: str
    markdown: str
    paper_ids: list[str]
    folder_id: Optional[int] = None


class RenameCompareResultBody(BaseModel):
    title: str


class MoveCompareResultBody(BaseModel):
    target_folder_id: Optional[int] = None


@app.get("/api/kb/compare-results/tree", summary="Get compare results tree")
def api_kb_compare_results_tree(_user=Depends(auth_service.require_user)):
    """Return the full compare results tree: folders + results."""
    return kb_service.get_compare_results_tree(_user["id"])


@app.post("/api/kb/compare-results", summary="Save compare result")
def api_kb_save_compare_result(body: SaveCompareResultBody, _user=Depends(auth_service.require_user)):
    """Save a compare analysis result to the compare library."""
    result = kb_service.add_compare_result(
        _user["id"], body.title, body.markdown, body.paper_ids, body.folder_id,
    )
    return result


@app.get("/api/kb/compare-results/{result_id}", summary="Get compare result")
def api_kb_get_compare_result(result_id: int, _user=Depends(auth_service.require_user)):
    """Get a single compare result including markdown."""
    result = kb_service.get_compare_result(_user["id"], result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Compare result not found")
    return result


@app.patch("/api/kb/compare-results/{result_id}", summary="Rename compare result")
def api_kb_rename_compare_result(result_id: int, body: RenameCompareResultBody, _user=Depends(auth_service.require_user)):
    """Rename a compare result."""
    result = kb_service.rename_compare_result(_user["id"], result_id, body.title)
    if result is None:
        raise HTTPException(status_code=404, detail="Compare result not found")
    return result


@app.patch("/api/kb/compare-results/{result_id}/move", summary="Move compare result")
def api_kb_move_compare_result(result_id: int, body: MoveCompareResultBody, _user=Depends(auth_service.require_user)):
    """Move a compare result to a folder (or root)."""
    result = kb_service.move_compare_result(_user["id"], result_id, body.target_folder_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Compare result not found")
    return result


@app.delete("/api/kb/compare-results/{result_id}", summary="Delete compare result")
def api_kb_delete_compare_result(result_id: int, _user=Depends(auth_service.require_user)):
    """Delete a compare result."""
    ok = kb_service.delete_compare_result(_user["id"], result_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Compare result not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Annotation Endpoints (PDF highlights / notes)
# ---------------------------------------------------------------------------

class CreateAnnotationBody(BaseModel):
    page: int
    type: str = "highlight"
    content: str = ""
    color: str = "#FFFF00"
    position_data: str = ""
    scope: str = "kb"

class UpdateAnnotationBody(BaseModel):
    content: Optional[str] = None
    color: Optional[str] = None


@app.get("/api/kb/papers/{paper_id}/annotations", summary="List annotations")
def api_kb_list_annotations(paper_id: str, scope: str = Query("kb"), _user=Depends(auth_service.require_user)):
    """Return all annotations for a paper's PDF."""
    annotations = kb_service.list_annotations(_user["id"], paper_id, scope=scope)
    return {"paper_id": paper_id, "annotations": annotations}


@app.post("/api/kb/papers/{paper_id}/annotations", summary="Create annotation")
def api_kb_create_annotation(
    paper_id: str, body: CreateAnnotationBody, _user=Depends(auth_service.require_user)
):
    """Create a new annotation on a paper's PDF."""
    annotation = kb_service.create_annotation(
        _user["id"], paper_id, body.page, body.type, body.content, body.color, body.position_data,
        scope=body.scope,
    )
    return annotation


@app.patch("/api/kb/annotations/{annotation_id}", summary="Update annotation")
def api_kb_update_annotation(
    annotation_id: int, body: UpdateAnnotationBody, _user=Depends(auth_service.require_user)
):
    """Update an annotation."""
    annotation = kb_service.update_annotation(_user["id"], annotation_id, body.content, body.color)
    if annotation is None:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return annotation


@app.delete("/api/kb/annotations/{annotation_id}", summary="Delete annotation")
def api_kb_delete_annotation(annotation_id: int, _user=Depends(auth_service.require_user)):
    """Delete an annotation."""
    ok = kb_service.delete_annotation(_user["id"], annotation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"ok": True}
