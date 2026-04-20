"""NovelForge application entrypoint (multi-workspace)."""

import json
import logging
import os
import pathlib

from fastapi import (
    Body,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routes import bot1, bot2, bot3, bot4, configs, projects
from . import workspace as ws

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="NovelForge v3.0 (multi-workspace)")

# 首次启动若 _admin.json 不存在，用默认 admin/admin 初始化
ws.ensure_admin_initialized()

# --- CORS ---
_cors_origins = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
    )
    return response


# --- 工作空间内部 API（受 require_workspace 保护，路由本身带 /api/w/{workspace} 前缀）---
app.include_router(bot1.router)
app.include_router(bot2.router)
app.include_router(bot3.router)
app.include_router(bot4.router)
app.include_router(configs.router)
app.include_router(projects.router)


STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"
MOBILE_DIR = STATIC_DIR / "m"
if not MOBILE_DIR.exists():
    MOBILE_DIR = STATIC_DIR / "mobile-app" / "dist"
MOBILE_DIR.mkdir(parents=True, exist_ok=True)


MOBILE_UA_HINTS = (
    "iphone", "ipod", "android", "mobile",
    "windows phone", "opera mini", "iemobile",
)


def _is_mobile_ua(request: Request) -> bool:
    forced = request.query_params.get("view", "").strip().lower()
    if forced == "mobile":
        return True
    if forced == "desktop":
        return False
    ua = request.headers.get("user-agent", "").lower()
    return any(h in ua for h in MOBILE_UA_HINTS)


def _read_static(filename: str) -> str:
    return (STATIC_DIR / filename).read_text(encoding="utf-8")


def _inject_workspace(html: str, slug: str) -> str:
    """把 window.WORKSPACE 注入到 <head>。"""
    snippet = f'<script>window.WORKSPACE = "{slug}";</script>'
    if "</head>" in html:
        return html.replace("</head>", snippet + "\n</head>", 1)
    return snippet + html


# ===== 首页：工作空间选择 =====

@app.get("/")
async def index(request: Request):
    # 如果只有 1 个工作空间，自动跳进去（朋友少时更顺手）
    items = ws.list_workspaces_public()
    if len(items) == 1:
        return RedirectResponse(url=f"/w/{items[0]['slug']}/", status_code=302)
    return HTMLResponse(_read_static("picker.html"))


@app.get("/api/workspaces")
async def api_list_workspaces():
    """公开列表，绝不含密码哈希。"""
    return {"workspaces": ws.list_workspaces_public()}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={}, status_code=204)


# ===== 工作空间登录 =====

@app.get("/w/{workspace}/login")
async def login_page(workspace: str, request: Request, error: str = ""):
    if not ws.is_valid_slug(workspace) or not ws.get_workspace(workspace):
        raise HTTPException(404, "工作空间不存在")
    # 已登录则直接进
    raw = request.cookies.get(ws.cookie_name(workspace), "")
    if ws.verify_cookie(workspace, raw):
        return RedirectResponse(url=f"/w/{workspace}/", status_code=302)
    html = _read_static("login.html")
    name = ws.get_workspace(workspace).get("name", workspace)
    locked, secs = ws.is_locked(workspace)
    error_msg = error
    if locked:
        error_msg = f"登录失败次数过多，请 {secs} 秒后再试"
    # workspace slug 已经被 is_valid_slug 校验过（只允许 [a-z0-9-]），
    # 用在 form action 里安全；name 与 error 是任意字符串，必须经 json.dumps 注入到 script
    html = (
        html.replace("{{WORKSPACE_SLUG}}", workspace)
            .replace("{{WORKSPACE_NAME_JSON}}", json.dumps(name))
            .replace("{{WORKSPACE_SLUG_JSON}}", json.dumps(workspace))
            .replace("{{ERROR_JSON}}", json.dumps(error_msg or ""))
    )
    return HTMLResponse(html)


@app.post("/w/{workspace}/login")
async def login_submit(workspace: str, password: str = Form("")):
    if not ws.is_valid_slug(workspace) or not ws.get_workspace(workspace):
        raise HTTPException(404, "工作空间不存在")
    locked, secs = ws.is_locked(workspace)
    if locked:
        return RedirectResponse(
            url=f"/w/{workspace}/login?error=锁定中（{secs}秒）",
            status_code=303,
        )
    if not ws.verify_password(workspace, password):
        return RedirectResponse(
            url=f"/w/{workspace}/login?error=密码错误",
            status_code=303,
        )
    cookie_val = ws.issue_cookie(workspace)
    resp = RedirectResponse(url=f"/w/{workspace}/", status_code=303)
    # path="/" 是必要的：API 路径 /api/w/<slug>/* 不在 /w/<slug>/ 之下，
    # 必须让 cookie 在所有路径都被携带；不同工作空间通过 cookie name(ws_<slug>) 区分，
    # 不会互相串扰。
    resp.set_cookie(
        ws.cookie_name(workspace),
        cookie_val,
        max_age=ws.COOKIE_MAX_AGE,
        httponly=True,
        samesite=ws.COOKIE_SAMESITE,
        secure=False,  # 部署时 Nginx 终止 TLS；直连 HTTPS 时改为 True
        path="/",
    )
    return resp


@app.get("/w/{workspace}/logout")
async def logout(workspace: str):
    resp = RedirectResponse(url="/", status_code=302)
    resp.delete_cookie(ws.cookie_name(workspace), path="/")
    return resp


# ===== 工作空间主界面 =====

def _workspace_or_redirect(workspace: str, request: Request):
    """返回 (slug, redirect_response_or_None)。redirect 不为 None 时直接返回它。"""
    if not ws.is_valid_slug(workspace) or not ws.get_workspace(workspace):
        raise HTTPException(404, "工作空间不存在")
    raw = request.cookies.get(ws.cookie_name(workspace), "")
    if not ws.verify_cookie(workspace, raw):
        return workspace, RedirectResponse(url=f"/w/{workspace}/login", status_code=302)
    ws.touch_last_active(workspace)
    return workspace, None


@app.get("/w/{workspace}/")
async def workspace_index(workspace: str, request: Request):
    slug, redirect = _workspace_or_redirect(workspace, request)
    if redirect is not None:
        return redirect
    if _is_mobile_ua(request):
        return RedirectResponse(url=f"/m/w/{slug}/", status_code=302)
    html = _inject_workspace(_read_static("index.html"), slug)
    return HTMLResponse(html)


@app.get("/m/w/{workspace}/")
async def mobile_workspace_index(workspace: str, request: Request):
    slug, redirect = _workspace_or_redirect(workspace, request)
    if redirect is not None:
        return redirect
    # 移动端 SPA 入口（dist/index.html），同样注入 window.WORKSPACE
    mobile_index = MOBILE_DIR / "index.html"
    if not mobile_index.exists():
        return HTMLResponse("<h1>移动端构建产物不存在</h1>", status_code=503)
    html = _inject_workspace(mobile_index.read_text(encoding="utf-8"), slug)
    return HTMLResponse(html)


# ===== 管理员入口（密码登录 + 30 天 cookie 会话）=====

def _require_admin(request: Request) -> None:
    """受保护 API 依赖：校验 admin cookie；不通过 403。"""
    raw = request.cookies.get(ws.ADMIN_COOKIE_NAME, "")
    if not ws.verify_admin_cookie(raw):
        raise HTTPException(status_code=403, detail="未登录管理员")


@app.get("/admin")
async def admin_page(request: Request):
    """有有效 cookie → 渲染管理页；否则跳转登录页。"""
    raw = request.cookies.get(ws.ADMIN_COOKIE_NAME, "")
    if not ws.verify_admin_cookie(raw):
        return RedirectResponse(url="/admin/login", status_code=302)
    return HTMLResponse(_read_static("admin.html"))


@app.get("/admin/login")
async def admin_login_page(request: Request, error: str = ""):
    """展示密码输入页；已登录则直接进管理。"""
    raw = request.cookies.get(ws.ADMIN_COOKIE_NAME, "")
    if ws.verify_admin_cookie(raw):
        return RedirectResponse(url="/admin", status_code=302)
    html = _read_static("admin_login.html").replace("{{ERROR_JSON}}", json.dumps(error or ""))
    return HTMLResponse(html)


@app.post("/admin/login")
async def admin_login_submit(
    username: str = Form(""),
    password: str = Form(""),
):
    if not ws.verify_admin_login(username, password):
        return RedirectResponse(url="/admin/login?error=用户名或密码错误", status_code=303)
    cookie_val = ws.issue_admin_cookie()
    resp = RedirectResponse(url="/admin", status_code=303)
    resp.set_cookie(
        ws.ADMIN_COOKIE_NAME,
        cookie_val,
        max_age=ws.ADMIN_COOKIE_MAX_AGE,
        httponly=True,
        samesite=ws.COOKIE_SAMESITE,
        secure=False,  # 部署时 Nginx/CF 终止 TLS；直连 HTTPS 可改 True
        path="/",
    )
    return resp


@app.get("/admin/logout")
async def admin_logout():
    resp = RedirectResponse(url="/admin/login", status_code=302)
    resp.delete_cookie(ws.ADMIN_COOKIE_NAME, path="/")
    return resp


# ---- admin API（全部靠 cookie 校验）----

@app.get("/api/admin/me")
async def admin_me(_: None = Depends(_require_admin)):
    """当前登录的管理员账户名（用于管理页显示）。"""
    return {"username": ws.get_admin_username()}


@app.post("/api/admin/password")
async def admin_change_self_password(payload: dict = Body(...), _: None = Depends(_require_admin)):
    """管理员自助改密码。需要提供当前密码 + 新密码。"""
    current = payload.get("current") or ""
    new = payload.get("new") or ""
    try:
        ws.update_admin_password(current, new)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/admin/workspaces")
async def admin_list(_: None = Depends(_require_admin)):
    return {"workspaces": ws.list_workspaces_admin()}


@app.post("/api/admin/workspaces")
async def admin_create(payload: dict = Body(...), _: None = Depends(_require_admin)):
    slug = (payload.get("slug") or "").strip().lower()
    name = (payload.get("name") or slug).strip()
    password = payload.get("password") or ""
    try:
        return ws.create_workspace(slug, name, password)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/workspaces/{slug}/password")
async def admin_change_password(slug: str, payload: dict = Body(...), _: None = Depends(_require_admin)):
    password = payload.get("password") or ""
    try:
        ws.update_password(slug, password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/admin/workspaces/{slug}/rename")
async def admin_rename(slug: str, payload: dict = Body(...), _: None = Depends(_require_admin)):
    name = (payload.get("name") or "").strip()
    try:
        ws.rename_workspace(slug, name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/admin/workspaces/{slug}")
async def admin_delete(slug: str, _: None = Depends(_require_admin)):
    try:
        ws.delete_workspace(slug)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ===== 静态资源 =====

# /static/* 是公开静态资源（CSS/JS/图片）
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# /m/static/* 也复用同一个目录（移动端 SPA 内的 css/js）
app.mount("/m/static", StaticFiles(directory=str(MOBILE_DIR)), name="mobile_static")
