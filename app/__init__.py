"""NovelForge application entrypoint."""

import logging
import os
import pathlib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routes import bot1, bot2, bot3, bot4, configs, projects

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(title="NovelForge v2.4")

# --- CORS ---
# 默认同源，不开放跨域；如需允许其他前端域名，用逗号分隔 CORS_ORIGINS 即可
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


# --- 安全响应头 ---
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    # 仅在 HTTPS 下生效；反代负责 TLS 终止
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
    )
    return response


# Routers
app.include_router(bot1.router)
app.include_router(bot2.router)
app.include_router(bot3.router)
app.include_router(bot4.router)
app.include_router(configs.router)
app.include_router(projects.router)

MOBILE_UA_HINTS = (
    "iphone",
    "ipod",
    "android",
    "mobile",
    "windows phone",
    "opera mini",
    "iemobile",
)


def _pick_index_file(request: Request) -> str:
    forced_view = request.query_params.get("view", "").strip().lower()
    if forced_view == "mobile":
        return "redirect"
    if forced_view == "desktop":
        return "index.html"

    user_agent = request.headers.get("user-agent", "").lower()
    is_mobile = any(hint in user_agent for hint in MOBILE_UA_HINTS)
    return "redirect" if is_mobile else "index.html"


def _render_index(file_name: str) -> HTMLResponse:
    html = pathlib.Path(__file__).parent.parent / "static" / file_name
    return HTMLResponse(html.read_text(encoding="utf-8"))


@app.get("/")
async def index(request: Request):
    decision = _pick_index_file(request)
    if decision == "redirect":
        return RedirectResponse(url="/m/")
    return _render_index(decision)


@app.get("/mobile")
async def mobile_index():
    return RedirectResponse(url="/m/")


@app.get("/desktop")
async def desktop_index():
    return _render_index("index.html")


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={}, status_code=204)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# Static files
static_dir = pathlib.Path(__file__).parent.parent / "static"
app.mount(
    "/static",
    StaticFiles(directory=str(static_dir)),
    name="static",
)

mobile_dir = static_dir / "m"
if not mobile_dir.exists():
    mobile_dir = static_dir / "mobile-app" / "dist"

mobile_dir.mkdir(parents=True, exist_ok=True)
app.mount("/m", StaticFiles(directory=str(mobile_dir), html=True), name="mobile")
