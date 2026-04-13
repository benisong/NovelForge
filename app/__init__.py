"""NovelForge application entrypoint."""

import pathlib
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

from .routes import bot1, bot2, bot3, bot4, configs, projects

app = FastAPI(title="NovelForge v2.4")

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
        return "mobile.html"
    if forced_view == "desktop":
        return "index.html"

    user_agent = request.headers.get("user-agent", "").lower()
    is_mobile = any(hint in user_agent for hint in MOBILE_UA_HINTS)
    return "mobile.html" if is_mobile else "index.html"


def _render_index(file_name: str) -> HTMLResponse:
    html = pathlib.Path(__file__).parent.parent / "static" / file_name
    return HTMLResponse(html.read_text(encoding="utf-8"))


# Index
@app.get("/")
async def index(request: Request):
    return _render_index(_pick_index_file(request))


@app.get("/mobile")
async def mobile_index():
    return _render_index("mobile.html")


@app.get("/desktop")
async def desktop_index():
    return _render_index("index.html")


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={}, status_code=204)


# Static files
app.mount("/static", StaticFiles(directory=str(pathlib.Path(__file__).parent.parent / "static")), name="static")
