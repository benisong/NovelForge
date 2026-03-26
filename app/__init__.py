"""小说创作助手 - 四Bot协作系统 v2.4"""

import pathlib
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

from .routes import bot1, bot2, bot3, bot4, configs, projects

app = FastAPI(title="小说创作助手 v2.4")

# 注册路由
app.include_router(bot1.router)
app.include_router(bot2.router)
app.include_router(bot3.router)
app.include_router(bot4.router)
app.include_router(configs.router)
app.include_router(projects.router)


# 首页
@app.get("/")
async def index():
    html = pathlib.Path(__file__).parent.parent / "static" / "index.html"
    return HTMLResponse(html.read_text(encoding="utf-8"))


@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={}, status_code=204)


# 静态文件
app.mount("/static", StaticFiles(directory=str(pathlib.Path(__file__).parent.parent / "static")), name="static")
