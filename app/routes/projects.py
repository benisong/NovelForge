"""项目 CRUD + 导出"""

import json
import re
import time
from fastapi import APIRouter, HTTPException

from ..models import SaveProjectRequest
from ..config import DATA_DIR, STYLES_FILE
from ..styles import _load_styles

router = APIRouter()


def _project_path(pid: str):
    safe = re.sub(r'[^\w\-]', '_', pid)
    return DATA_DIR / f"{safe}.json"


@router.get("/api/projects")
async def list_projects():
    """列出所有已保存的项目"""
    projects = []
    for f in sorted(DATA_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            projects.append({
                "id": data.get("project_id", f.stem),
                "name": data.get("name", f.stem),
                "chapters": len(data.get("chapters", [])),
                "updated": data.get("updated", ""),
            })
        except Exception:
            continue
    return {"projects": projects}


@router.post("/api/projects/save")
async def save_project(req: SaveProjectRequest):
    """保存/更新一个项目"""
    data = req.model_dump()
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path = _project_path(req.project_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path)}


@router.get("/api/projects/{project_id}")
async def load_project(project_id: str):
    """加载一个项目"""
    path = _project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "项目不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """删除一个项目"""
    path = _project_path(project_id)
    if path.exists():
        path.unlink()
    return {"ok": True}


@router.post("/api/projects/{project_id}/export")
async def export_project(project_id: str):
    """导出项目为纯文本"""
    path = _project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "项目不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = [f"# {data.get('name', project_id)}\n"]
    for i, ch in enumerate(data.get("chapters", []), 1):
        lines.append(f"\n## 第{i}章\n")
        lines.append(ch.get("content", ""))
        lines.append("")
    text = "\n".join(lines)
    return {"text": text, "word_count": len(text)}


@router.get("/api/styles")
async def get_styles():
    """获取所有文风列表"""
    return _load_styles()


@router.post("/api/styles")
async def save_styles(data: dict):
    """保存文风配置（含自定义文风）"""
    STYLES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@router.get("/api/styles/{style_id}")
async def get_style(style_id: str):
    """获取单个文风详情"""
    from ..styles import _get_style_by_id
    style = _get_style_by_id(style_id)
    if not style:
        raise HTTPException(status_code=404, detail="文风不存在")
    return style
