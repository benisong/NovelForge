"""项目 CRUD + 导出（per-workspace）"""

import json
import logging
import re
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import styles_file, workspace_data_dir
from ..models import SaveProjectRequest
from ..styles import _load_styles
from ..workspace import require_workspace

logger = logging.getLogger(__name__)


class SaveChapterRequest(BaseModel):
    project_id: str
    project_name: str
    chapter_num: int
    content: str


router = APIRouter(
    prefix="/api/w/{workspace}",
    dependencies=[Depends(require_workspace)],
)


_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")
_SAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe_id(pid: str) -> str:
    safe = _SAFE_ID_RE.sub("_", pid or "").strip("._")
    if not safe:
        raise HTTPException(400, "无效的项目ID")
    return safe[:128]


def _resolve_within(root: Path, candidate: Path) -> Path:
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        raise HTTPException(400, "非法的路径")
    return resolved


def _project_path(workspace: str, pid: str) -> Path:
    root = workspace_data_dir(workspace)
    safe = _safe_id(pid)
    return _resolve_within(root, root / f"{safe}.json")


def _chapters_dir(workspace: str, pid: str) -> Path:
    root = workspace_data_dir(workspace)
    chapters_root = root / "chapters"
    chapters_root.mkdir(parents=True, exist_ok=True)
    safe = _safe_id(pid)
    return _resolve_within(chapters_root, chapters_root / safe)


def _safe_filename(name: str, fallback: str = "untitled") -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name or "").strip(" .")
    if not cleaned:
        cleaned = fallback
    return cleaned[:128]


@router.get("/projects")
async def list_projects(workspace: str):
    """列出当前工作空间所有已保存的项目"""
    data_root = workspace_data_dir(workspace)
    projects = []
    for f in sorted(data_root.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取项目文件失败 %s/%s: %s", workspace, f.name, e)
            continue
        if not isinstance(data, dict):
            continue
        projects.append(
            {
                "id": data.get("project_id", f.stem),
                "name": data.get("name", f.stem),
                "chapters": len(data.get("chapters", []) or []),
                "updated": data.get("updated", ""),
            }
        )
    return {"projects": projects}


@router.get("/projects/latest")
async def latest_project(workspace: str):
    data_root = workspace_data_dir(workspace)
    latest_id = None
    latest_time = ""
    for f in data_root.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取项目文件失败 %s/%s: %s", workspace, f.name, e)
            continue
        if not isinstance(data, dict):
            continue
        updated = data.get("updated", "")
        if updated > latest_time:
            latest_time = updated
            latest_id = data.get("project_id", f.stem)
    return {"project_id": latest_id}


@router.post("/projects/save")
async def save_project(workspace: str, req: SaveProjectRequest):
    data_root = workspace_data_dir(workspace)
    payload = req.model_dump()
    payload["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path = _project_path(workspace, req.project_id)

    if path.exists():
        backup_dir = data_root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_pid = _safe_id(req.project_id)
        backup_path = backup_dir / f"{safe_pid}_{timestamp}.json"
        try:
            shutil.copy2(path, backup_path)
            all_backups = sorted(
                backup_dir.glob(f"{safe_pid}_*.json"),
                key=lambda p: p.stat().st_mtime,
            )
            if len(all_backups) > 10:
                for old in all_backups[:-10]:
                    try:
                        old.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as e:
                        logger.warning("删除旧备份失败 %s: %s", old.name, e)
        except OSError as e:
            logger.warning("自动备份失败: %s", e)

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path.relative_to(data_root))}


@router.get("/projects/{project_id}")
async def load_project(workspace: str, project_id: str):
    path = _project_path(workspace, project_id)
    if not path.exists():
        raise HTTPException(404, "项目不存在")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(500, "项目文件损坏或无法读取")


@router.post("/projects/save-chapter")
async def save_chapter(workspace: str, req: SaveChapterRequest):
    ch_dir = _chapters_dir(workspace, req.project_id)
    ch_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(req.project_name)
    if req.chapter_num < 0 or req.chapter_num > 100000:
        raise HTTPException(400, "章节序号超出范围")
    filename = f"{safe_name}_正式_第{req.chapter_num}章.txt"
    filepath = _resolve_within(ch_dir, ch_dir / filename)
    filepath.write_text(req.content, encoding="utf-8")
    data_root = workspace_data_dir(workspace)
    return {"ok": True, "filename": filename, "path": str(filepath.relative_to(data_root))}


@router.get("/projects/{project_id}/chapters")
async def list_chapter_files(workspace: str, project_id: str):
    ch_dir = _chapters_dir(workspace, project_id)
    if not ch_dir.exists():
        return {"files": []}
    files = sorted(ch_dir.glob("*.txt"))
    return {"files": [f.name for f in files]}


@router.delete("/projects/{project_id}")
async def delete_project(workspace: str, project_id: str, delete_chapters: bool = False):
    path = _project_path(workspace, project_id)
    if path.exists():
        try:
            path.unlink()
        except OSError as e:
            logger.error("删除项目文件失败 %s: %s", path.name, e)
            raise HTTPException(500, "删除失败")
    if delete_chapters:
        ch_dir = _chapters_dir(workspace, project_id)
        if ch_dir.exists():
            shutil.rmtree(ch_dir, ignore_errors=True)
    return {"ok": True}


@router.post("/projects/{project_id}/export")
async def export_project(workspace: str, project_id: str):
    path = _project_path(workspace, project_id)
    if not path.exists():
        raise HTTPException(404, "项目不存在")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(500, "项目文件损坏或无法读取")
    lines = [f"# {data.get('name', project_id)}\n"]
    for i, ch in enumerate(data.get("chapters", []) or [], 1):
        lines.append(f"\n## 第{i}章\n")
        lines.append(ch.get("content", "") if isinstance(ch, dict) else "")
        lines.append("")
    text = "\n".join(lines)
    return {"text": text, "word_count": len(text)}


# ---------- 文风 ----------

@router.get("/styles")
async def get_styles(workspace: str):
    return _load_styles(workspace)


@router.post("/styles")
async def save_styles(workspace: str, data: dict):
    sf = styles_file(workspace)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@router.get("/styles/{style_id}")
async def get_style(workspace: str, style_id: str):
    from ..styles import _get_style_by_id

    style = _get_style_by_id(workspace, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="文风不存在")
    return style
