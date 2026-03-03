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

from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse

from services import auth_service
from services import sms_service
from services import data_service
from services import kb_service
from services import compare_service
from services import user_settings_service
from services import config_service
from services import llm_config_service
from services import prompt_config_service
from services import config_mapper
from services import user_presets_service
from services import idea_service
from services import idea_pipeline_service

app = FastAPI(
    title="ArxivPaper4 API",
    description="Backend API for ArxivPaper4 paper digest system",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event():
    """应用启动时加载配置并初始化数据库表，并确保关键数据目录存在。"""
    config_service.load_config()
    llm_config_service.init_db()
    prompt_config_service.init_db()
    seeded_prompts = prompt_config_service.seed_default_idea_prompts()
    if seeded_prompts:
        print(f"[STARTUP] 已写入 {seeded_prompts} 条灵感生成默认提示词到数据库")
    seeded_llm = llm_config_service.seed_default_idea_llm_configs()
    if seeded_llm:
        print(f"[STARTUP] 已写入 {seeded_llm} 条灵感生成默认模型配置到数据库")
    auth_service.init_auth_db()

    # 确保 data/file_collect 目录存在（若不存在说明服务器端尚未运行流水线）
    _sever_dir = os.path.dirname(os.path.abspath(__file__))
    _fc_dir = os.path.join(_sever_dir, "data", "file_collect")
    if not os.path.isdir(_fc_dir):
        print(
            f"[WARN] data/file_collect 目录不存在: {_fc_dir}\n"
            "       服务器端尚未运行流水线，日期下拉框和推荐卡片将为空。\n"
            "       请将本地的 Sever/data/file_collect/ 目录上传到服务器，\n"
            "       或在服务器上运行一次流水线以生成数据。",
            flush=True,
        )

# ---------------------------------------------------------------------------
# CORS 配置
# 开发模式：固定允许 localhost 各端口
# 生产模式：通过环境变量 CORS_ORIGINS 追加服务器域名（逗号分隔）
# 示例：export CORS_ORIGINS="http://your-server.com,https://your-server.com"
# ---------------------------------------------------------------------------
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://localhost:5174",   # Mobile dev server
    "http://127.0.0.1:5174",  # Mobile dev server
    "http://localhost:1420",   # Tauri desktop dev server
    "http://127.0.0.1:1420",  # Tauri desktop dev server
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # Tauri desktop app origins (WebView2 on Windows uses tauri:// or https://tauri.localhost)
    "tauri://localhost",
    "https://tauri.localhost",
]
_extra_origins_env = os.environ.get("CORS_ORIGINS", "")
_extra_origins = [o.strip() for o in _extra_origins_env.split(",") if o.strip()]
_allowed_origins = list(dict.fromkeys(_default_origins + _extra_origins))  # 去重保序

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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


# Mount exe_release directory for installer downloads
_EXE_RELEASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "exe_release")
_EXE_RELEASE_DIR = os.path.normpath(_EXE_RELEASE_DIR)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/download/latest-installer")
async def download_latest_installer():
    """返回 exe_release 文件夹中最新的安装包文件（按修改时间排序）。"""
    if not os.path.isdir(_EXE_RELEASE_DIR):
        raise HTTPException(status_code=404, detail="安装包目录不存在")
    exes = [
        f for f in os.listdir(_EXE_RELEASE_DIR)
        if f.lower().endswith((".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".AppImage"))
    ]
    if not exes:
        raise HTTPException(status_code=404, detail="未找到安装包文件")
    exes.sort(key=lambda f: os.path.getmtime(os.path.join(_EXE_RELEASE_DIR, f)), reverse=True)
    latest = exes[0]
    file_path = os.path.join(_EXE_RELEASE_DIR, latest)
    return FileResponse(
        path=file_path,
        filename=latest,
        media_type="application/octet-stream",
    )

class AuthCredentialBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)

class AuthRegisterBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    phone: str = Field(..., description="中国大陆手机号，注册时必填")
    sms_code: str = Field(..., min_length=4, max_length=8, description="短信验证码")

class SmsSendBody(BaseModel):
    phone: str = Field(..., description="中国大陆手机号")

class SmsLoginBody(BaseModel):
    phone: str = Field(..., description="中国大陆手机号")
    code: str = Field(..., min_length=4, max_length=8, description="短信验证码")

class UpdateProfileBody(BaseModel):
    nickname: Optional[str] = Field(None, max_length=64, description="昵称")
    username: Optional[str] = Field(None, min_length=3, max_length=32, description="用户名")

class SetPasswordBody(BaseModel):
    password: str = Field(..., min_length=8, max_length=128, description="新密码")

class ChangePasswordBody(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128, description="旧密码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码")

class UpdateUserTierBody(BaseModel):
    tier: str = Field(..., pattern="^(free|pro|pro_plus)$")

class UpdateUserRoleBody(BaseModel):
    role: str = Field(..., pattern="^(user|admin|superadmin)$")

class RunPipelineBody(BaseModel):
    pipeline: str = Field(default="default")
    date: Optional[str] = None
    sllm: Optional[int] = None
    zo: Optional[str] = Field(default="F", pattern="^[TF]$")
    user_id: Optional[int] = Field(default=None, description="User ID for per-user config overrides (paper_recommend)")
    force: bool = Field(default=False, description="强制重新执行：删除已有输出，忽略幂等检查")
    # Arxiv 检索参数（透传给第一步 arxiv_search04.py）
    days: Optional[int] = Field(default=None, ge=1, le=30, description="时间窗口天数（--days），默认 1 天")
    categories: Optional[str] = Field(default=None, description="arXiv 分类列表，逗号分隔，如 cs.AI,cs.LG")
    extra_query: Optional[str] = Field(default=None, description="附加关键词/高级表达式（--query）")
    max_papers: Optional[int] = Field(default=None, ge=1, le=5000, description="最多获取论文数（--max-papers）")
    anchor_tz: Optional[str] = Field(default=None, description="锚定时区（--anchor-tz），如 Asia/Shanghai")

class ScheduleConfigBody(BaseModel):
    enabled: bool
    hour: int = Field(default=6, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    pipeline: str = Field(default="daily")
    sllm: Optional[int] = None
    zo: Optional[str] = Field(default="F", pattern="^[TF]$")
    user_id: Optional[int] = Field(default=None, description="灵感管线使用的用户ID")


# ---------------------------------------------------------------------------
# Cookie 安全配置
# 生产 HTTPS 环境：export COOKIE_SECURE=true
# 开发 HTTP 环境：不设置或 export COOKIE_SECURE=false（默认）
# ---------------------------------------------------------------------------
_COOKIE_SECURE_RAW = os.environ.get("COOKIE_SECURE", "false").strip().lower()
_COOKIE_SAMESITE_RAW = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower()
_COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN", "").strip() or None

_VALID_SAMESITE = {"lax", "strict", "none"}
if _COOKIE_SAMESITE_RAW not in _VALID_SAMESITE:
    print(
        f"[WARN] Invalid COOKIE_SAMESITE={_COOKIE_SAMESITE_RAW!r}; fallback to 'lax'. "
        "Allowed values: lax / strict / none",
        flush=True,
    )
    _COOKIE_SAMESITE_RAW = "lax"


def _is_request_https(request: Optional[Request]) -> bool:
    if request is None:
        return False
    # Prefer proxy header when the app is behind reverse proxy (Nginx/Caddy/Traefik).
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto:
        return proto == "https"
    return request.url.scheme == "https"


def _cookie_secure_flag(request: Optional[Request]) -> bool:
    if _COOKIE_SECURE_RAW in ("auto",):
        secure = _is_request_https(request)
    else:
        secure = _COOKIE_SECURE_RAW in ("1", "true", "yes")
    # Modern browsers reject SameSite=None cookies when Secure=false.
    if _COOKIE_SAMESITE_RAW == "none" and not secure:
        print(
            "[WARN] COOKIE_SAMESITE=none requires Secure cookie; force secure=True for session cookie.",
            flush=True,
        )
        secure = True
    return secure


def _set_session_cookie(resp: Response, session_id: str, request: Optional[Request] = None) -> None:
    secure = _cookie_secure_flag(request)
    resp.set_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite=_COOKIE_SAMESITE_RAW,
        secure=secure,
        max_age=auth_service.SESSION_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
        domain=_COOKIE_DOMAIN,
    )


def _clear_session_cookie(resp: Response, request: Optional[Request] = None) -> None:
    secure = _cookie_secure_flag(request)
    resp.delete_cookie(
        key=auth_service.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=_COOKIE_SAMESITE_RAW,
        secure=secure,
        domain=_COOKIE_DOMAIN,
    )


def _get_optional_user(request: Request) -> Optional[dict]:
    session_id = auth_service._extract_session_id(request)
    return auth_service.get_user_by_session(session_id)


def _tier_quota_limit(user: Optional[dict]) -> Optional[int]:
    if not user:
        return 3
    # admin / superadmin 角色自动享有无限配额
    role = user.get("role", "user")
    if role in ("admin", "superadmin"):
        return None
    tier = user.get("tier", "free")
    if tier == "pro":
        return 15
    if tier == "pro_plus":
        return None
    return 3


def _tier_label(user: Optional[dict]) -> str:
    if not user:
        return "anonymous"
    # admin / superadmin 角色在前端也展示为 pro_plus（不受限）
    role = user.get("role", "user")
    if role in ("admin", "superadmin"):
        return "pro_plus"
    return user.get("tier", "free")


@app.post("/api/auth/sms/send", summary="Send SMS verify code")
def api_auth_sms_send(body: SmsSendBody):
    """发送短信验证码到指定手机号。"""
    result = sms_service.send_verify_code(body.phone)
    if not result["success"]:
        raise HTTPException(
            status_code=429 if result.get("wait_seconds", 0) > 0 else 400,
            detail=result["message"],
        )
    return {"ok": True, "message": result["message"]}


@app.post("/api/auth/login/sms", summary="Login by phone + SMS code (auto-register if new)")
def api_auth_login_sms(body: SmsLoginBody, request: Request, response: Response):
    """使用手机号和短信验证码登录。若手机号尚未注册则自动创建账号。"""
    verify = sms_service.check_verify_code(body.phone, body.code)
    if not verify["success"]:
        raise HTTPException(status_code=401, detail=verify["message"])
    user = auth_service.login_by_phone(body.phone)
    is_new_user = False
    if user is None:
        user = auth_service.auto_register_by_phone(body.phone)
        is_new_user = True
    session = auth_service.create_session(
        user_id=user["id"],
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, session["session_id"], request=request)
    return {"ok": True, "user": user, "is_new_user": is_new_user, "session_id": session["session_id"]}


@app.post("/api/auth/register", summary="Register")
def api_auth_register(body: AuthRegisterBody):
    """注册账号（需手机号短信验证）。"""
    verify = sms_service.check_verify_code(body.phone, body.sms_code)
    if not verify["success"]:
        raise HTTPException(status_code=400, detail=f"手机验证失败：{verify['message']}")
    user = auth_service.register_user(body.username, body.password, phone=body.phone)
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
    _set_session_cookie(response, session["session_id"], request=request)
    return {"ok": True, "user": user, "session_id": session["session_id"]}


@app.post("/api/auth/logout", summary="Logout")
def api_auth_logout(request: Request, response: Response):
    """Logout and clear session cookie."""
    session_id = auth_service._extract_session_id(request)
    auth_service.delete_session(session_id)
    _clear_session_cookie(response, request=request)
    return {"ok": True}


@app.get("/api/auth/me", summary="Current user")
def api_auth_me(request: Request):
    """Return current authenticated user if session exists."""
    session_id = auth_service._extract_session_id(request)
    user = auth_service.get_user_by_session(session_id)
    return {"authenticated": user is not None, "user": user}


@app.get("/api/auth/check-username", summary="Check username availability")
def api_auth_check_username(
    username: str = Query(..., min_length=1, max_length=32, description="要检查的用户名"),
    exclude_user_id: Optional[int] = Query(None, description="排除的用户 ID（当前用户自身）"),
):
    """检查用户名是否可用（不需要登录）。"""
    result = auth_service.check_username_available(username, exclude_user_id=exclude_user_id)
    return result


@app.get("/api/auth/profile", summary="Get current user profile")
def api_auth_get_profile(_user=Depends(auth_service.require_user)):
    """返回当前登录用户的完整资料（含 nickname、has_password 等）。"""
    profile = auth_service.get_user_profile(_user["id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"ok": True, "user": profile}


@app.put("/api/auth/profile", summary="Update current user profile")
def api_auth_update_profile(body: UpdateProfileBody, _user=Depends(auth_service.require_user)):
    """更新当前用户的昵称和/或用户名。"""
    if body.nickname is None and body.username is None:
        raise HTTPException(status_code=400, detail="请提供至少一个需要更新的字段")
    updated = auth_service.update_user_profile(
        _user["id"],
        nickname=body.nickname,
        username=body.username,
    )
    return {"ok": True, "user": updated}


@app.post("/api/auth/profile/set-password", summary="Set password for phone-only account")
def api_auth_set_password(body: SetPasswordBody, _user=Depends(auth_service.require_user)):
    """为手机号账号首次设置密码。"""
    updated = auth_service.set_user_password(_user["id"], body.password)
    return {"ok": True, "user": updated}


@app.post("/api/auth/profile/change-password", summary="Change password")
def api_auth_change_password(body: ChangePasswordBody, _user=Depends(auth_service.require_user)):
    """修改密码（需提供旧密码）。"""
    updated = auth_service.change_user_password(_user["id"], body.old_password, body.new_password)
    return {"ok": True, "user": updated}


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
# User LLM Presets
# ---------------------------------------------------------------------------

class UserLlmPresetBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    input_hard_limit: Optional[int] = None
    input_safety_margin: Optional[int] = None


@app.get("/api/user/llm-presets", summary="List user LLM presets")
def api_user_list_llm_presets(_user=Depends(auth_service.require_user)):
    presets = user_presets_service.list_llm_presets(_user["id"])
    return {"ok": True, "presets": presets}


@app.post("/api/user/llm-presets", summary="Create LLM preset")
def api_user_create_llm_preset(body: UserLlmPresetBody, _user=Depends(auth_service.require_user)):
    preset = user_presets_service.create_llm_preset(_user["id"], body.dict())
    return {"ok": True, "preset": preset}


@app.put("/api/user/llm-presets/{preset_id}", summary="Update LLM preset")
def api_user_update_llm_preset(preset_id: int, body: UserLlmPresetBody, _user=Depends(auth_service.require_user)):
    preset = user_presets_service.update_llm_preset(_user["id"], preset_id, body.dict())
    if preset is None:
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"ok": True, "preset": preset}


@app.delete("/api/user/llm-presets/{preset_id}", summary="Delete LLM preset")
def api_user_delete_llm_preset(preset_id: int, _user=Depends(auth_service.require_user)):
    ok = user_presets_service.delete_llm_preset(_user["id"], preset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# User Prompt Presets
# ---------------------------------------------------------------------------

class UserPromptPresetBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    prompt_content: str = ""


@app.get("/api/user/prompt-presets", summary="List user prompt presets")
def api_user_list_prompt_presets(_user=Depends(auth_service.require_user)):
    presets = user_presets_service.list_prompt_presets(_user["id"])
    return {"ok": True, "presets": presets}


@app.post("/api/user/prompt-presets", summary="Create prompt preset")
def api_user_create_prompt_preset(body: UserPromptPresetBody, _user=Depends(auth_service.require_user)):
    preset = user_presets_service.create_prompt_preset(_user["id"], body.dict())
    return {"ok": True, "preset": preset}


@app.put("/api/user/prompt-presets/{preset_id}", summary="Update prompt preset")
def api_user_update_prompt_preset(preset_id: int, body: UserPromptPresetBody, _user=Depends(auth_service.require_user)):
    preset = user_presets_service.update_prompt_preset(_user["id"], preset_id, body.dict())
    if preset is None:
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"ok": True, "preset": preset}


@app.delete("/api/user/prompt-presets/{preset_id}", summary="Delete prompt preset")
def api_user_delete_prompt_preset(preset_id: int, _user=Depends(auth_service.require_user)):
    ok = user_presets_service.delete_prompt_preset(_user["id"], preset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="预设不存在")
    return {"ok": True}


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
# Persistent runtime state (shared across multiple uvicorn workers via disk)
_RUNTIME_STATE_PATH = os.path.join(_SEVER_DIR, "database", "pipeline_runtime_state.json")
_ADMIN_LOG_DIR = os.path.join(_SEVER_DIR, "logs", "admin_pipeline")

# In-memory pipeline run state (worker-local cache)
_pipeline_state: dict = {
    "running": False,
    "current_step": None,
    "logs": [],
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "params": {},
    "process": None,
    "run_id": None,
    "log_file": None,
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
    "user_id": None,
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


# ---------------------------------------------------------------------------
# Persistent runtime state helpers (cross-worker support)
# ---------------------------------------------------------------------------

def _load_runtime_state() -> dict:
    """Read pipeline runtime state from disk (shared across all uvicorn workers)."""
    if os.path.isfile(_RUNTIME_STATE_PATH):
        try:
            with open(_RUNTIME_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_runtime_state(state: dict) -> None:
    """Atomically persist pipeline runtime state to disk."""
    os.makedirs(os.path.dirname(_RUNTIME_STATE_PATH), exist_ok=True)
    tmp = _RUNTIME_STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, _RUNTIME_STATE_PATH)


def _get_log_tail(log_file: str, n: int = 300) -> list:
    """Return the last *n* lines from an admin pipeline log file."""
    if not log_file or not os.path.isfile(log_file):
        return []
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [ln.rstrip("\n") for ln in lines[-n:]]
    except OSError:
        return []


def _run_pipeline_thread(
    pipeline: str,
    date_str: str,
    sllm: Optional[int],
    zo: str,
    user_id: Optional[int] = None,
    force: bool = False,
    days: Optional[int] = None,
    categories: Optional[str] = None,
    extra_query: Optional[str] = None,
    max_papers: Optional[int] = None,
    anchor_tz: Optional[str] = None,
):
    """Execute pipeline in a background thread, capturing output line by line.
    Logs are written to a per-run file so they remain visible across multiple
    uvicorn workers and survive page refreshes / server restarts."""
    global _pipeline_state
    cmd = [sys.executable, "-u", _APP_PY_PATH, pipeline, "--date", date_str, "--Zo", zo]
    if force:
        cmd.append("--force")
    if sllm is not None:
        cmd.extend(["--SLLM", str(sllm)])
    if user_id is not None:
        cmd.extend(["--user-id", str(user_id)])
    # Arxiv 检索参数（透传给第一步 arxiv_search04.py）
    if days is not None:
        cmd.extend(["--days", str(days)])
    if categories:
        cmd.extend(["--categories", categories])
    if extra_query:
        cmd.extend(["--query", extra_query])
    if max_papers is not None:
        cmd.extend(["--max-papers", str(max_papers)])
    if anchor_tz:
        cmd.extend(["--anchor-tz", anchor_tz])

    env = {**os.environ, "RUN_DATE": date_str, "PYTHONIOENCODING": "utf-8"}
    if sllm is not None:
        env["SLLM"] = str(sllm)
    if user_id is not None:
        env["PIPELINE_USER_ID"] = str(user_id)

    # Generate run_id and prepare log file (cross-worker shared via filesystem)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(_ADMIN_LOG_DIR, exist_ok=True)
    log_file = os.path.join(_ADMIN_LOG_DIR, f"{run_id}.log")

    params = {
        "pipeline": pipeline,
        "date": date_str,
        "sllm": sllm,
        "zo": zo,
        "user_id": user_id,
        "days": days,
        "categories": categories,
        "extra_query": extra_query,
        "max_papers": max_papers,
        "anchor_tz": anchor_tz,
    }
    started_at = datetime.now(timezone.utc).isoformat()
    init_log_line = f"[{datetime.now().strftime('%H:%M:%S')}] 启动 Pipeline: {pipeline}  日期: {date_str}"

    with _pipeline_lock:
        _pipeline_state["running"] = True
        _pipeline_state["current_step"] = "启动中..."
        _pipeline_state["logs"] = [init_log_line]
        _pipeline_state["started_at"] = started_at
        _pipeline_state["finished_at"] = None
        _pipeline_state["exit_code"] = None
        _pipeline_state["params"] = params
        _pipeline_state["run_id"] = run_id
        _pipeline_state["log_file"] = log_file

    # Write initial state to disk (makes this run visible to all workers immediately)
    _save_runtime_state({
        "running": True,
        "current_step": "启动中...",
        "started_at": started_at,
        "finished_at": None,
        "exit_code": None,
        "params": params,
        "run_id": run_id,
        "log_file": log_file,
    })

    exit_code = -1
    log_fh = None
    try:
        log_fh = open(log_file, "w", encoding="utf-8", buffering=1)  # line-buffered
        log_fh.write(init_log_line + "\n")

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

        # Persist PID to disk immediately so other workers (e.g. after --reload)
        # can still locate and kill the subprocess even if this worker dies.
        try:
            _save_runtime_state({
                "running": True,
                "pid": proc.pid,
                "current_step": "启动中...",
                "started_at": started_at,
                "finished_at": None,
                "exit_code": None,
                "params": params,
                "run_id": run_id,
                "log_file": log_file,
            })
        except OSError:
            pass

        def _is_progress_line(s: str) -> bool:
            """Return True if s looks like an in-place progress update."""
            return " progress done=" in s or "[PROGRESS] " in s

        current_step = "启动中..."
        for line in proc.stdout:
            line = line.rstrip("\n")
            log_line = f"[{datetime.now().strftime('%H:%M:%S')}] {line}"

            # Detect step changes (used for both memory and disk state updates)
            step_changed = False
            if line.startswith("RUN step:"):
                current_step = line.replace("RUN step:", "").strip()
                step_changed = True
            elif line.startswith("SKIP step:"):
                current_step = f"跳过: {line.replace('SKIP step:', '').strip()}"
                step_changed = True

            # Update in-memory state
            with _pipeline_lock:
                if (
                    _is_progress_line(line)
                    and _pipeline_state["logs"]
                    and _is_progress_line(_pipeline_state["logs"][-1])
                ):
                    _pipeline_state["logs"][-1] = log_line
                else:
                    _pipeline_state["logs"].append(log_line)
                # Keep last 500 lines in memory
                if len(_pipeline_state["logs"]) > 500:
                    _pipeline_state["logs"] = _pipeline_state["logs"][-500:]
                _pipeline_state["current_step"] = current_step

            # Always append to log file (all workers read from here)
            if log_fh:
                log_fh.write(log_line + "\n")

            # On step change, update disk state so other workers see progress
            if step_changed:
                try:
                    _save_runtime_state({
                        "running": True,
                        "pid": proc.pid,
                        "current_step": current_step,
                        "started_at": started_at,
                        "finished_at": None,
                        "exit_code": None,
                        "params": params,
                        "run_id": run_id,
                        "log_file": log_file,
                    })
                except OSError:
                    pass

        proc.wait()
        exit_code = proc.returncode
    except Exception as exc:
        exit_code = -1
        err_line = f"[{datetime.now().strftime('%H:%M:%S')}] [ERROR] {exc}"
        with _pipeline_lock:
            _pipeline_state["logs"].append(err_line)
        if log_fh:
            try:
                log_fh.write(err_line + "\n")
            except OSError:
                pass
    finally:
        if log_fh:
            try:
                log_fh.close()
            except OSError:
                pass
        finished_at = datetime.now(timezone.utc).isoformat()
        final_step = "已完成" if exit_code == 0 else f"异常退出 (code={exit_code})"
        with _pipeline_lock:
            _pipeline_state["running"] = False
            _pipeline_state["finished_at"] = finished_at
            _pipeline_state["exit_code"] = exit_code
            _pipeline_state["current_step"] = final_step
            _pipeline_state["process"] = None
        # Persist final state to disk so all workers see the completed run
        try:
            _save_runtime_state({
                "running": False,
                "current_step": final_step,
                "started_at": started_at,
                "finished_at": finished_at,
                "exit_code": exit_code,
                "params": params,
                "run_id": run_id,
                "log_file": log_file,
            })
        except OSError:
            pass


def _scheduler_loop():
    """Background thread that triggers daily pipeline runs.

    Re-reads schedule config from disk on every cycle so that:
    - Config changes made by any worker are picked up immediately.
    - last_run_date is always taken from the single authoritative disk copy,
      preventing multiple workers from double-firing on the same day.
    """
    while not _scheduler_stop_event.is_set():
        now = datetime.now()
        # Always re-read from disk so all workers share the same view
        disk_cfg = _load_schedule_config()
        # Merge with in-memory (disk wins for last_run_date and enabled flag)
        cfg = {**_scheduler_state, **disk_cfg}
        today = now.date().isoformat()
        if (
            cfg.get("enabled")
            and now.hour == cfg.get("hour", 6)
            and now.minute == cfg.get("minute", 0)
            and cfg.get("last_run_date") != today
        ):
            # Persist last_run_date to disk FIRST before starting the thread.
            # This is the cross-worker lock: whichever worker writes first wins;
            # the others will read today's date and skip.
            new_cfg = {k: v for k, v in cfg.items() if k != "last_run_date"}
            new_cfg["last_run_date"] = today
            try:
                _save_schedule_config(new_cfg)
            except OSError:
                pass
            _scheduler_state["last_run_date"] = today

            # Double-check that pipeline isn't already running (disk + memory)
            disk_rt = _load_runtime_state()
            if not disk_rt.get("running") and not _pipeline_state["running"]:
                t = threading.Thread(
                    target=_run_pipeline_thread,
                    args=(cfg.get("pipeline", "daily"), today, cfg.get("sllm"), cfg.get("zo", "F")),
                    kwargs={"user_id": cfg.get("user_id")},
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
    # Check disk state first (catches runs started by other workers)
    disk_state = _load_runtime_state()
    if disk_state.get("running") or _pipeline_state["running"]:
        raise HTTPException(status_code=409, detail="Pipeline 正在运行中，请等待完成")

    date_str = body.date or datetime.now().date().isoformat()
    # Use user_id from body, or fall back to the calling admin's ID
    pipeline_user_id = body.user_id if body.user_id is not None else _admin.get("id")
    t = threading.Thread(
        target=_run_pipeline_thread,
        kwargs={
            "pipeline": body.pipeline,
            "date_str": date_str,
            "sllm": body.sllm,
            "zo": body.zo or "F",
            "user_id": pipeline_user_id,
            "force": body.force,
            "days": body.days,
            "categories": body.categories,
            "extra_query": body.extra_query,
            "max_papers": body.max_papers,
            "anchor_tz": body.anchor_tz,
        },
        daemon=True,
    )
    t.start()
    force_hint = "（强制模式）" if body.force else ""
    return {"ok": True, "message": f"Pipeline '{body.pipeline}' 已启动{force_hint}，日期: {date_str}"}


@app.get("/api/admin/pipeline/status", summary="Get pipeline run status")
def api_admin_pipeline_run_status(
    _admin=Depends(auth_service.require_admin_user),
):
    """Get current pipeline execution status and logs.
    Reads from persistent disk state so the result is consistent across all
    uvicorn workers and survives page refreshes / server restarts."""
    disk_state = _load_runtime_state()
    if disk_state:
        log_file = disk_state.get("log_file")
        logs = _get_log_tail(log_file, n=300)
        return {
            "running": disk_state.get("running", False),
            "current_step": disk_state.get("current_step"),
            "logs": logs,
            "started_at": disk_state.get("started_at"),
            "finished_at": disk_state.get("finished_at"),
            "exit_code": disk_state.get("exit_code"),
            "params": disk_state.get("params", {}),
            "run_id": disk_state.get("run_id"),
        }
    # Fallback: in-memory state (very first run before any disk state exists)
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
    """Attempt to stop a running pipeline (entire process tree).

    Handles two scenarios:
    1. Normal case: this worker holds the process reference in _pipeline_state.
    2. After --reload: old worker died, process is orphaned; PID is read from disk state.
    """
    pid: Optional[int] = None
    proc_ref = None

    # --- Try in-memory state first ---
    with _pipeline_lock:
        proc_ref = _pipeline_state.get("process")
        if proc_ref is not None and _pipeline_state["running"]:
            pid = proc_ref.pid

    # --- Fallback: read PID from disk state (survives worker reloads) ---
    if pid is None:
        disk_state = _load_runtime_state()
        if disk_state.get("running") and disk_state.get("pid"):
            pid = int(disk_state["pid"])

    if pid is None:
        raise HTTPException(status_code=400, detail="当前没有正在运行的 Pipeline")

    # Kill OUTSIDE the lock to avoid deadlock with the pipeline thread's lock acquisitions.
    # On Windows: taskkill /F /T kills the entire process tree (app.py + all child step scripts).
    # On Unix: kill the process group so all children are terminated together.
    killed = False
    if sys.platform == "win32":
        try:
            result = subprocess.call(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            killed = (result == 0)
        except Exception:
            pass
    else:
        import signal as _signal
        try:
            os.killpg(os.getpgid(pid), _signal.SIGTERM)
            killed = True
        except Exception:
            pass

    if not killed:
        # Fallback: terminate only the direct process
        if proc_ref is not None:
            try:
                proc_ref.kill()
                killed = True
            except Exception:
                pass

    # --- Update disk state so the UI immediately shows "stopped" ---
    # This is especially important when the pipeline thread (old worker) is already dead
    # and can no longer write the final state itself.
    try:
        disk_state = _load_runtime_state()
        if disk_state.get("running"):
            finished_at = datetime.now(timezone.utc).isoformat()
            _save_runtime_state({
                **disk_state,
                "running": False,
                "pid": None,
                "current_step": "已手动终止",
                "finished_at": finished_at,
                "exit_code": -9,
            })
    except OSError:
        pass

    # Also update in-memory state for this worker
    with _pipeline_lock:
        _pipeline_state["running"] = False
        _pipeline_state["process"] = None
        _pipeline_state["current_step"] = "已手动终止"
        _pipeline_state["exit_code"] = -9

    return {"ok": True, "message": "已发送终止信号（进程树已强制结束）"}


@app.get("/api/admin/schedule", summary="Get schedule config")
def api_admin_get_schedule(
    _admin=Depends(auth_service.require_admin_user),
):
    """Get current auto-schedule configuration.
    Merges in-memory state with disk so last_run_date is always up-to-date
    regardless of which worker last updated it."""
    disk_cfg = _load_schedule_config()
    cfg = {**_scheduler_state, **disk_cfg}
    return {
        "enabled": cfg.get("enabled", False),
        "hour": cfg.get("hour", 6),
        "minute": cfg.get("minute", 0),
        "pipeline": cfg.get("pipeline", "daily"),
        "sllm": cfg.get("sllm"),
        "zo": cfg.get("zo", "F"),
        "user_id": cfg.get("user_id"),
        "last_run_date": cfg.get("last_run_date"),
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
    _scheduler_state["user_id"] = body.user_id

    # Persist to disk (preserve last_run_date so it survives a save/restart)
    disk_cfg = _load_schedule_config()
    _save_schedule_config({
        "enabled": body.enabled,
        "hour": body.hour,
        "minute": body.minute,
        "pipeline": body.pipeline,
        "sllm": body.sllm,
        "zo": body.zo or "F",
        "user_id": body.user_id,
        "last_run_date": disk_cfg.get("last_run_date") or _scheduler_state.get("last_run_date"),
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
        "user_id": body.user_id,
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


# ---------------------------------------------------------------------------
# LLM Config Management
# ---------------------------------------------------------------------------

class LlmConfigBody(BaseModel):
    name: str = Field(..., description="配置名称")
    remark: Optional[str] = Field(None, description="备注")
    base_url: str = Field(..., description="API基础地址")
    api_key: str = Field(..., description="API密钥")
    model: str = Field(..., description="模型名称")
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    concurrency: Optional[int] = None
    input_hard_limit: Optional[int] = None
    input_safety_margin: Optional[int] = None
    endpoint: Optional[str] = None
    completion_window: Optional[str] = None
    out_root: Optional[str] = None
    jsonl_root: Optional[str] = None


class ApplyLlmConfigBody(BaseModel):
    usage_prefix: str = Field(..., description="使用前缀（如 theme_select, org, summary 等）")


@app.get("/api/admin/llm-configs", summary="Get all LLM configs")
def api_admin_list_llm_configs(
    _admin=Depends(auth_service.require_admin_user),
):
    """获取所有模型配置列表。"""
    try:
        configs = llm_config_service.list_configs()
        return {"ok": True, "configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置列表失败: {str(e)}")


@app.get("/api/admin/llm-configs/{config_id}", summary="Get LLM config by ID")
def api_admin_get_llm_config(
    config_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    """获取单个模型配置。"""
    try:
        config = llm_config_service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
        return {"ok": True, "config": config}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@app.post("/api/admin/llm-configs", summary="Create LLM config")
def api_admin_create_llm_config(
    body: LlmConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """创建新的模型配置。"""
    try:
        config = llm_config_service.create_config(body.dict())
        return {"ok": True, "config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建配置失败: {str(e)}")


@app.put("/api/admin/llm-configs/{config_id}", summary="Update LLM config")
def api_admin_update_llm_config(
    config_id: int,
    body: LlmConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """更新模型配置。"""
    try:
        config = llm_config_service.update_config(config_id, body.dict(exclude_unset=True))
        if not config:
            raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
        return {"ok": True, "config": config}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@app.delete("/api/admin/llm-configs/{config_id}", summary="Delete LLM config")
def api_admin_delete_llm_config(
    config_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    """删除模型配置。"""
    try:
        success = llm_config_service.delete_config(config_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"模型配置 {config_id} 不存在")
        return {"ok": True, "message": "配置已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除配置失败: {str(e)}")


@app.post("/api/admin/llm-configs/{config_id}/apply", summary="Apply LLM config to config.py")
def api_admin_apply_llm_config(
    config_id: int,
    body: ApplyLlmConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """应用模型配置到config.py（根据usage_prefix前缀映射）。"""
    try:
        updated = config_mapper.apply_llm_config(config_id, body.usage_prefix)
        return {"ok": True, "message": f"配置已应用到 {body.usage_prefix} 前缀", "config": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"应用配置失败: {str(e)}")


# ---------------------------------------------------------------------------
# Prompt Config Management
# ---------------------------------------------------------------------------

class PromptConfigBody(BaseModel):
    name: str = Field(..., description="配置名称")
    remark: Optional[str] = Field(None, description="备注")
    prompt_content: str = Field(..., description="提示词内容")


class ApplyPromptConfigBody(BaseModel):
    variable_name: str = Field(..., description="目标变量名（如 theme_select_system_prompt, system_prompt 等）")


class BatchApplyLlmItem(BaseModel):
    config_id: int = Field(..., description="模型配置ID")
    prefix: str = Field(..., description="使用前缀")


class BatchApplyPromptItem(BaseModel):
    config_id: int = Field(..., description="提示词配置ID")
    variable: str = Field(..., description="目标变量名")


class BatchApplyConfigBody(BaseModel):
    llm_applies: list[BatchApplyLlmItem] = Field(default_factory=list, description="模型配置应用列表")
    prompt_applies: list[BatchApplyPromptItem] = Field(default_factory=list, description="提示词配置应用列表")


@app.get("/api/admin/prompt-configs", summary="Get all prompt configs")
def api_admin_list_prompt_configs(
    _admin=Depends(auth_service.require_admin_user),
):
    """获取所有提示词配置列表。"""
    try:
        configs = prompt_config_service.list_configs()
        return {"ok": True, "configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置列表失败: {str(e)}")


@app.get("/api/admin/prompt-configs/{config_id}", summary="Get prompt config by ID")
def api_admin_get_prompt_config(
    config_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    """获取单个提示词配置。"""
    try:
        config = prompt_config_service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"提示词配置 {config_id} 不存在")
        return {"ok": True, "config": config}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@app.post("/api/admin/prompt-configs", summary="Create prompt config")
def api_admin_create_prompt_config(
    body: PromptConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """创建新的提示词配置。"""
    try:
        config = prompt_config_service.create_config(body.dict())
        return {"ok": True, "config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建配置失败: {str(e)}")


@app.put("/api/admin/prompt-configs/{config_id}", summary="Update prompt config")
def api_admin_update_prompt_config(
    config_id: int,
    body: PromptConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """更新提示词配置。"""
    try:
        config = prompt_config_service.update_config(config_id, body.dict(exclude_unset=True))
        if not config:
            raise HTTPException(status_code=404, detail=f"提示词配置 {config_id} 不存在")
        return {"ok": True, "config": config}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@app.delete("/api/admin/prompt-configs/{config_id}", summary="Delete prompt config")
def api_admin_delete_prompt_config(
    config_id: int,
    _admin=Depends(auth_service.require_admin_user),
):
    """删除提示词配置。"""
    try:
        success = prompt_config_service.delete_config(config_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"提示词配置 {config_id} 不存在")
        return {"ok": True, "message": "配置已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除配置失败: {str(e)}")


@app.post("/api/admin/prompt-configs/{config_id}/apply", summary="Apply prompt config to config.py")
def api_admin_apply_prompt_config(
    config_id: int,
    body: ApplyPromptConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """应用提示词配置到config.py（根据variable_name映射）。"""
    try:
        updated = config_mapper.apply_prompt_config(config_id, body.variable_name)
        return {"ok": True, "message": f"配置已应用到变量 {body.variable_name}", "config": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"应用配置失败: {str(e)}")


@app.post("/api/admin/config/batch-apply", summary="Batch apply LLM and prompt configs")
def api_admin_batch_apply_configs(
    body: BatchApplyConfigBody,
    _admin=Depends(auth_service.require_admin_user),
):
    """批量应用模型配置和提示词配置，仅触发一次文件写入。"""
    try:
        result = config_mapper.batch_apply(
            llm_applies=[item.model_dump() for item in body.llm_applies],
            prompt_applies=[item.model_dump() for item in body.prompt_applies],
        )
        return {
            "ok": True,
            "message": f"批量应用完成，共更新 {result['applied_count']} 项配置",
            "applied_count": result["applied_count"],
            "errors": result["errors"],
            "config": result["config"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量应用失败: {str(e)}")


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


# ---------------------------------------------------------------------------
# Inspiration Generation v2 (灵感生成 v2)
# ---------------------------------------------------------------------------

# -- Pydantic bodies -------------------------------------------------------

class ExtractAtomsBody(BaseModel):
    paper_id: str
    date_str: str = ""

class GenerateQuestionsBody(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)

class GenerateCandidatesBody(BaseModel):
    question_id: Optional[int] = None
    custom_question: str = ""
    strategies: Optional[list[str]] = None

class CreateCandidateBody(BaseModel):
    title: str
    goal: str = ""
    mechanism: str = ""
    risks: str = ""
    strategy: str = ""
    question_id: Optional[int] = None
    tags: Optional[list[str]] = None
    folder_id: Optional[int] = None

class UpdateCandidateBody(BaseModel):
    title: Optional[str] = None
    goal: Optional[str] = None
    mechanism: Optional[str] = None
    risks: Optional[str] = None
    scores: Optional[dict] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    folder_id: Optional[int] = None
    strategy: Optional[str] = None

class ReviewCandidateBody(BaseModel):
    candidate_id: int

class ReviseCandidateBody(BaseModel):
    candidate_id: int
    review_feedback: str = ""

class GeneratePlanBody(BaseModel):
    candidate_id: int

class SavePlanBody(BaseModel):
    candidate_id: int
    milestones: Optional[list[dict]] = None
    metrics: str = ""
    datasets: str = ""
    ablation: str = ""
    cost: str = ""
    timeline: str = ""
    full_plan: str = ""

class FeedbackBody(BaseModel):
    candidate_id: int
    # Accept either `action` (canonical) or `event_type` (legacy frontend field)
    action: Optional[str] = Field(None, description="collect|discard|modify|implement|rate")
    event_type: Optional[str] = None
    context: Optional[dict] = None

    @property
    def resolved_action(self) -> str:
        return self.action or self.event_type or "view"

class CreateExemplarBody(BaseModel):
    candidate_id: int
    pattern: Optional[dict] = None
    score: float = 0.0
    notes: str = ""

class CreateBenchmarkBody(BaseModel):
    name: str
    question_ids: Optional[list[int]] = None
    model_version: str = ""

class EvalReplayBody(BaseModel):
    question_ids: list[int]

class CreatePromptVersionBody(BaseModel):
    stage: str
    prompt_text: str
    metrics: Optional[dict] = None

class CreateIdeaFolderBody(BaseModel):
    name: str
    parent_id: Optional[int] = None

class MoveIdeaCandidatesBody(BaseModel):
    candidate_ids: list[int]
    target_folder_id: Optional[int] = None


# -- Dashboard & stats -----------------------------------------------------

@app.get("/api/idea/stats", summary="Idea dashboard stats")
def api_idea_stats(_user=Depends(auth_service.require_user)):
    """Return summary statistics for the inspiration dashboard."""
    return {"ok": True, **idea_service.get_stats(_user["id"])}


# -- Atom endpoints ---------------------------------------------------------

@app.get("/api/idea/atoms", summary="List idea atoms")
def api_idea_list_atoms(
    paper_id: Optional[str] = None,
    atom_type: Optional[str] = None,
    tag: Optional[str] = None,
    date_str: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _user=Depends(auth_service.require_user),
):
    """List or search idea atoms."""
    if query:
        try:
            atoms = idea_service.search_atoms_fts(query, user_id=_user["id"], limit=limit)
        except Exception:
            atoms = idea_service.list_atoms(user_id=_user["id"], limit=limit, offset=offset)
    else:
        atoms = idea_service.list_atoms(
            user_id=_user["id"], paper_id=paper_id, atom_type=atom_type,
            tag=tag, date_str=date_str, limit=limit, offset=offset,
        )
    return {"ok": True, "atoms": atoms, "count": len(atoms)}


@app.get("/api/idea/atoms/{atom_id}", summary="Get idea atom")
def api_idea_get_atom(atom_id: int, _user=Depends(auth_service.require_user)):
    atom = idea_service.get_atom(atom_id)
    if not atom:
        raise HTTPException(status_code=404, detail="Atom not found")
    return {"ok": True, "atom": atom}


@app.post("/api/idea/atoms/extract", summary="Extract atoms from a paper")
def api_idea_extract_atoms(body: ExtractAtomsBody, _user=Depends(auth_service.require_user)):
    """Run LLM extraction on a paper to produce idea atoms."""
    result = idea_pipeline_service.extract_atoms_for_paper(
        _user["id"], body.paper_id, body.date_str,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"ok": True, **result}


@app.delete("/api/idea/atoms/paper/{paper_id}", summary="Delete atoms for a paper")
def api_idea_delete_atoms_for_paper(paper_id: str, _user=Depends(auth_service.require_user)):
    count = idea_service.delete_atoms_for_paper(_user["id"], paper_id)
    return {"ok": True, "deleted": count}


# -- Question endpoints -----------------------------------------------------

@app.get("/api/idea/questions", summary="List generated questions")
def api_idea_list_questions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user=Depends(auth_service.require_user),
):
    questions = idea_service.list_questions(_user["id"], limit=limit, offset=offset)
    return {"ok": True, "questions": questions, "count": len(questions)}


@app.post("/api/idea/questions/generate", summary="Generate research questions from atoms")
def api_idea_generate_questions(body: GenerateQuestionsBody, _user=Depends(auth_service.require_user)):
    result = idea_pipeline_service.generate_questions(_user["id"], limit=body.limit)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"ok": True, **result}


# -- Idea Digest (permission-filtered, date-scoped) -------------------------

@app.get("/api/idea/digest/{date}", summary="Idea digest for a date (permission-filtered)")
def api_idea_digest(
    date: str,
    _user=Depends(auth_service.require_user),
):
    """Return inspiration candidates for *date* filtered by the requesting user's
    paper-quota tier.  Only ideas whose source atoms come from papers the user
    is allowed to see (same quota logic as /api/digest/{date}) are returned.

    Response shape mirrors /api/digest/{date}:
      { ok, candidates, total_available, quota_limit, tier }
    """
    # 1. Get the ordered paper list for this date (same as digest endpoint)
    digest = data_service.get_daily_digest(date)
    all_papers = digest.get("papers", [])

    # 2. Apply the user's quota to determine which papers are visible
    quota_limit = _tier_quota_limit(_user)
    if quota_limit is not None:
        visible_papers = all_papers[:quota_limit]
    else:
        visible_papers = all_papers
    allowed_paper_ids = [p["paper_id"] for p in visible_papers if p.get("paper_id")]

    # 3. Fetch shared candidates derived from those papers, excluding already-seen
    candidates, total_available = idea_service.list_shared_candidates_for_date(
        date_str=date,
        allowed_paper_ids=allowed_paper_ids,
        viewer_user_id=_user["id"],
    )

    return {
        "ok": True,
        "candidates": candidates,
        "total_available": total_available,
        "quota_limit": quota_limit,
        "tier": _tier_label(_user),
    }


# -- Candidate endpoints ----------------------------------------------------

@app.get("/api/idea/candidates", summary="List inspiration candidates")
def api_idea_list_candidates(
    status: Optional[str] = None,
    folder_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user=Depends(auth_service.require_user),
):
    candidates = idea_service.list_candidates(
        _user["id"], status=status, folder_id=folder_id, limit=limit, offset=offset,
    )
    return {"ok": True, "candidates": candidates, "count": len(candidates)}


@app.get("/api/idea/candidates/{candidate_id}", summary="Get candidate detail")
def api_idea_get_candidate(candidate_id: int, _user=Depends(auth_service.require_user)):
    c = idea_service.get_candidate(candidate_id)
    if not c or c.get("user_id") != _user["id"]:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "candidate": c}


@app.post("/api/idea/candidates", summary="Create candidate manually")
def api_idea_create_candidate(body: CreateCandidateBody, _user=Depends(auth_service.require_user)):
    c = idea_service.create_candidate(
        user_id=_user["id"],
        title=body.title,
        goal=body.goal,
        mechanism=body.mechanism,
        risks=body.risks,
        strategy=body.strategy,
        question_id=body.question_id,
        tags=body.tags,
        folder_id=body.folder_id,
    )
    return {"ok": True, "candidate": c}


@app.patch("/api/idea/candidates/{candidate_id}", summary="Update candidate")
def api_idea_update_candidate(candidate_id: int, body: UpdateCandidateBody, _user=Depends(auth_service.require_user)):
    updates = body.dict(exclude_unset=True)
    c = idea_service.update_candidate(candidate_id, _user["id"], **updates)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True, "candidate": c}


@app.delete("/api/idea/candidates/{candidate_id}", summary="Delete candidate")
def api_idea_delete_candidate(candidate_id: int, _user=Depends(auth_service.require_user)):
    ok = idea_service.delete_candidate(_user["id"], candidate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {"ok": True}


class ManualReviewBody(BaseModel):
    action: str  # approve | reject | revise
    feedback: Optional[str] = None
    scores: Optional[dict] = None


@app.post("/api/idea/candidates/{candidate_id}/review", summary="Submit manual review for a candidate")
def api_idea_manual_review(candidate_id: int, body: ManualReviewBody, _user=Depends(auth_service.require_user)):
    """Submit a manual review with action, optional feedback and scores.

    - action=approve → status becomes 'approved'
    - action=reject  → status becomes 'archived'
    - action=revise  → status becomes 'review'
    The review is appended to revision_history and scores are updated if provided.
    """
    from datetime import datetime, timezone

    c = idea_service.get_candidate(candidate_id)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")

    status_map = {"approve": "approved", "reject": "archived", "revise": "review"}
    new_status = status_map.get(body.action, "review")

    revision_entry = {
        "type": "manual_review",
        "action": body.action,
        "verdict": body.action,
        "feedback": body.feedback or "",
        "scores": body.scores or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    update_kwargs: dict = {
        "status": new_status,
        "revision_entry": revision_entry,
    }
    if body.scores:
        update_kwargs["scores"] = body.scores

    updated = idea_service.update_candidate(candidate_id, _user["id"], **update_kwargs)
    if not updated:
        raise HTTPException(status_code=404, detail="Candidate not found or permission denied")
    return {"ok": True, "message": "评审已提交", "candidate": updated}


@app.post("/api/idea/candidates/generate", summary="Generate candidates (SSE stream)")
def api_idea_generate_candidates(body: GenerateCandidatesBody, _user=Depends(auth_service.require_user)):
    """Stream inspiration candidate generation using LLM."""
    return StreamingResponse(
        idea_pipeline_service.stream_generate_candidates(
            _user["id"],
            question_id=body.question_id,
            custom_question=body.custom_question,
            strategies=body.strategies,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- Review & Revise endpoints (SSE) ----------------------------------------

@app.post("/api/idea/review", summary="Review candidate (SSE stream)")
def api_idea_review_candidate(body: ReviewCandidateBody, _user=Depends(auth_service.require_user)):
    """Stream multi-critic review for a candidate."""
    return StreamingResponse(
        idea_pipeline_service.stream_review_candidate(_user["id"], body.candidate_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/idea/revise", summary="Revise candidate (SSE stream)")
def api_idea_revise_candidate(body: ReviseCandidateBody, _user=Depends(auth_service.require_user)):
    """Stream auto-revision based on review feedback."""
    return StreamingResponse(
        idea_pipeline_service.stream_revise_candidate(
            _user["id"], body.candidate_id, body.review_feedback,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- Plan endpoints ---------------------------------------------------------

@app.post("/api/idea/plans/generate", summary="Generate execution plan (SSE stream)")
def api_idea_generate_plan(body: GeneratePlanBody, _user=Depends(auth_service.require_user)):
    """Stream plan generation for a candidate."""
    return StreamingResponse(
        idea_pipeline_service.stream_generate_plan(_user["id"], body.candidate_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/idea/plans", summary="Save execution plan")
def api_idea_save_plan(body: SavePlanBody, _user=Depends(auth_service.require_user)):
    plan = idea_service.create_plan(
        user_id=_user["id"],
        candidate_id=body.candidate_id,
        milestones=body.milestones,
        metrics=body.metrics,
        datasets=body.datasets,
        ablation=body.ablation,
        cost=body.cost,
        timeline=body.timeline,
        full_plan=body.full_plan,
    )
    return {"ok": True, "plan": plan}


@app.get("/api/idea/plans/{candidate_id}", summary="Get plan for candidate")
def api_idea_get_plan(candidate_id: int, _user=Depends(auth_service.require_user)):
    plan = idea_service.get_plan_for_candidate(_user["id"], candidate_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True, "plan": plan}


# -- Feedback endpoints -----------------------------------------------------

@app.post("/api/idea/feedback", summary="Record user feedback")
def api_idea_feedback(body: FeedbackBody, _user=Depends(auth_service.require_user)):
    fb = idea_service.create_feedback(
        user_id=_user["id"],
        candidate_id=body.candidate_id,
        action=body.resolved_action,
        context=body.context,
    )
    return {"ok": True, "feedback": fb}


@app.get("/api/idea/feedback", summary="List feedback events")
def api_idea_list_feedback(
    candidate_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    _user=Depends(auth_service.require_user),
):
    events = idea_service.list_feedback(_user["id"], candidate_id=candidate_id, limit=limit)
    return {"ok": True, "events": events, "count": len(events)}


# -- Exemplar endpoints -----------------------------------------------------

@app.get("/api/idea/exemplars", summary="List exemplars")
def api_idea_list_exemplars(
    limit: int = Query(100, ge=1, le=500),
    _user=Depends(auth_service.require_user),
):
    exemplars = idea_service.list_exemplars(_user["id"], limit=limit)
    return {"ok": True, "exemplars": exemplars}


@app.post("/api/idea/exemplars", summary="Create exemplar")
def api_idea_create_exemplar(body: CreateExemplarBody, _user=Depends(auth_service.require_user)):
    ex = idea_service.create_exemplar(
        user_id=_user["id"],
        candidate_id=body.candidate_id,
        pattern=body.pattern,
        score=body.score,
        notes=body.notes,
    )
    return {"ok": True, "exemplar": ex}


@app.delete("/api/idea/exemplars/{exemplar_id}", summary="Delete exemplar")
def api_idea_delete_exemplar(exemplar_id: int, _user=Depends(auth_service.require_user)):
    ok = idea_service.delete_exemplar(_user["id"], exemplar_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Exemplar not found")
    return {"ok": True}


# -- Prompt version endpoints -----------------------------------------------

@app.get("/api/idea/prompt-versions", summary="List prompt versions")
def api_idea_list_prompt_versions(
    stage: Optional[str] = None,
    _user=Depends(auth_service.require_user),
):
    versions = idea_service.list_prompt_versions(_user["id"], stage=stage)
    return {"ok": True, "versions": versions}


@app.post("/api/idea/prompt-versions", summary="Create prompt version")
def api_idea_create_prompt_version(body: CreatePromptVersionBody, _user=Depends(auth_service.require_user)):
    v = idea_service.create_prompt_version(
        user_id=_user["id"],
        stage=body.stage,
        prompt_text=body.prompt_text,
        metrics=body.metrics,
    )
    return {"ok": True, "version": v}


# -- Benchmark & Eval replay -----------------------------------------------

@app.get("/api/idea/benchmarks", summary="List benchmarks")
def api_idea_list_benchmarks(_user=Depends(auth_service.require_user)):
    benchmarks = idea_service.list_benchmarks(_user["id"])
    return {"ok": True, "benchmarks": benchmarks}


@app.post("/api/idea/benchmarks", summary="Create benchmark")
def api_idea_create_benchmark(body: CreateBenchmarkBody, _user=Depends(auth_service.require_user)):
    bm = idea_service.create_benchmark(
        user_id=_user["id"],
        name=body.name,
        question_ids=body.question_ids,
        model_version=body.model_version,
    )
    return {"ok": True, "benchmark": bm}


@app.post("/api/idea/eval-replay", summary="Eval replay (SSE stream)")
def api_idea_eval_replay(body: EvalReplayBody, _user=Depends(auth_service.require_user)):
    """Re-generate on a question set for comparison (SSE stream)."""
    return StreamingResponse(
        idea_pipeline_service.stream_eval_replay(_user["id"], body.question_ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- Idea library folders (reuse KB folder pattern with scope='idea_library') --

@app.get("/api/idea/library/tree", summary="Get idea library tree")
def api_idea_library_tree(_user=Depends(auth_service.require_user)):
    """Return the full idea library tree (folders + candidates)."""
    folders = kb_service.get_tree(_user["id"], scope="idea_library")
    candidates = idea_service.list_candidates(_user["id"], limit=500)
    return {"ok": True, "folders": folders, "candidates": candidates}


@app.post("/api/idea/library/folders", summary="Create idea library folder")
def api_idea_library_create_folder(body: CreateIdeaFolderBody, _user=Depends(auth_service.require_user)):
    folder = kb_service.create_folder(_user["id"], body.name, body.parent_id, scope="idea_library")
    return folder


@app.patch("/api/idea/candidates/move", summary="Move candidates to folder")
def api_idea_move_candidates(body: MoveIdeaCandidatesBody, _user=Depends(auth_service.require_user)):
    count = 0
    for cid in body.candidate_ids:
        result = idea_service.update_candidate(cid, _user["id"], folder_id=body.target_folder_id)
        if result:
            count += 1
    return {"ok": True, "moved": count}


# ---------------------------------------------------------------------------
# SPA 前端托管（生产环境）
# 将 Vue 编译产物直接由 FastAPI 托管，彻底解决跨域 Cookie 问题。
# 使用前先构建前端：cd View && npm run build
# ---------------------------------------------------------------------------
_SEVER_ROOT = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIST = os.path.normpath(os.path.join(_SEVER_ROOT, "..", "View", "dist"))

# ---------------------------------------------------------------------------
# 移动端 SPA 托管（/m/ 路径）
# 使用前先构建移动端：cd Mobile && npm run build
# ---------------------------------------------------------------------------
_MOBILE_DIST = os.path.normpath(os.path.join(_SEVER_ROOT, "..", "Mobile", "dist"))

if os.path.isdir(_MOBILE_DIST):
    _mobile_assets = os.path.join(_MOBILE_DIST, "assets")
    if os.path.isdir(_mobile_assets):
        app.mount("/m/assets", StaticFiles(directory=_mobile_assets), name="mobile-assets")

    @app.get("/m/{full_path:path}", include_in_schema=False)
    async def serve_mobile_spa(full_path: str):
        """移动端 SPA 兜底路由，挂载在 /m/ 路径下。"""
        if full_path:
            file_path = os.path.join(_MOBILE_DIST, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
        return FileResponse(os.path.join(_MOBILE_DIST, "index.html"))


import re as _re
_TABLET_UA_RE = _re.compile(r"iPad|Tablet|PlayBook|Silk", _re.I)
_PHONE_UA_RE = _re.compile(r"Android|iPhone|iPod|Mobile|webOS|Windows Phone", _re.I)

if os.path.isdir(_FRONTEND_DIST):
    # 托管 Vite 编译产物中的 /assets/ 目录（JS/CSS 文件）
    _dist_assets = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(_dist_assets):
        app.mount("/assets", StaticFiles(directory=_dist_assets), name="vue-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(request: Request, full_path: str):
        """
        兜底路由：
        1. 检测移动设备 User-Agent，自动重定向到 /m/ 移动端
        2. 优先返回 dist/ 中的真实静态文件
        3. 否则返回 index.html 交给 Vue Router 处理（SPA 路由）
        """
        # 移动设备自动重定向到移动端 SPA
        if os.path.isdir(_MOBILE_DIST):
            ua = request.headers.get("user-agent", "")
            ua_lower = ua.lower()
            is_tablet = bool(_TABLET_UA_RE.search(ua) or ("android" in ua_lower and "mobile" not in ua_lower))
            is_phone = bool((not is_tablet) and _PHONE_UA_RE.search(ua))
            if is_phone:
                target = f"/m/{full_path}" if full_path else "/m/"
                qs = str(request.url.query)
                if qs:
                    target += f"?{qs}"
                return RedirectResponse(url=target, status_code=302)

        if full_path:
            file_path = os.path.join(_FRONTEND_DIST, full_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))
