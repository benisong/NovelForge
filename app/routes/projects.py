"""项目 CRUD + 导出"""

import json
import logging
import re
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models import SaveProjectRequest
from ..config import DATA_DIR, STYLES_FILE
from ..styles import _load_styles

logger = logging.getLogger(__name__)


class SaveChapterRequest(BaseModel):
    project_id: str
    project_name: str
    chapter_num: int
    content: str


router = APIRouter()


_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_\-]")
_SAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_DATA_ROOT = DATA_DIR.resolve()
_CHAPTERS_ROOT = (_DATA_ROOT / "chapters").resolve()


def _safe_id(pid: str) -> str:
    """把 project_id 规范化成只包含字母数字下划线和连字符。"""
    safe = _SAFE_ID_RE.sub("_", pid or "").strip("._")
    if not safe:
        raise HTTPException(400, "无效的项目ID")
    return safe[:128]


def _resolve_within(root: Path, candidate: Path) -> Path:
    """确保 candidate 在 root 目录内，防止路径穿越。"""
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        raise HTTPException(400, "非法的路径")
    return resolved


def _project_path(pid: str) -> Path:
    safe = _safe_id(pid)
    return _resolve_within(_DATA_ROOT, _DATA_ROOT / f"{safe}.json")


def _chapters_dir(project_id: str) -> Path:
    safe = _safe_id(project_id)
    _CHAPTERS_ROOT.mkdir(parents=True, exist_ok=True)
    return _resolve_within(_CHAPTERS_ROOT, _CHAPTERS_ROOT / safe)


def _safe_filename(name: str, fallback: str = "untitled") -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name or "").strip(" .")
    if not cleaned:
        cleaned = fallback
    return cleaned[:128]


@router.get("/api/projects")
async def list_projects():
    """列出所有已保存的项目"""
    projects = []
    for f in sorted(DATA_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取项目文件失败 %s: %s", f.name, e)
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


@router.get("/api/projects/latest")
async def latest_project():
    """获取最近更新的项目ID"""
    latest_id = None
    latest_time = ""
    for f in DATA_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("读取项目文件失败 %s: %s", f.name, e)
            continue
        if not isinstance(data, dict):
            continue
        updated = data.get("updated", "")
        if updated > latest_time:
            latest_time = updated
            latest_id = data.get("project_id", f.stem)
    return {"project_id": latest_id}


@router.post("/api/projects/save")
async def save_project(req: SaveProjectRequest):
    """保存/更新一个项目，带防丢失备份机制"""
    data = req.model_dump()
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path = _project_path(req.project_id)

    # ==== 自动备份机制 ====
    if path.exists():
        backup_dir = DATA_DIR / "backups"
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
                for old_backup in all_backups[:-10]:
                    try:
                        old_backup.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as e:
                        logger.warning("删除旧备份失败 %s: %s", old_backup.name, e)
        except OSError as e:
            logger.warning("自动备份失败: %s", e)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path.relative_to(_DATA_ROOT))}


@router.get("/api/projects/{project_id}")
async def load_project(project_id: str):
    """加载一个项目"""
    path = _project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "项目不存在")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(500, "项目文件损坏或无法读取")
    return data


@router.post("/api/projects/save-chapter")
async def save_chapter(req: SaveChapterRequest):
    """保存正式章节文件"""
    ch_dir = _chapters_dir(req.project_id)
    ch_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(req.project_name)
    if req.chapter_num < 0 or req.chapter_num > 100000:
        raise HTTPException(400, "章节序号超出范围")
    filename = f"{safe_name}_正式_第{req.chapter_num}章.txt"
    filepath = _resolve_within(ch_dir, ch_dir / filename)
    filepath.write_text(req.content, encoding="utf-8")
    return {"ok": True, "filename": filename, "path": str(filepath.relative_to(_DATA_ROOT))}


@router.get("/api/projects/{project_id}/chapters")
async def list_chapter_files(project_id: str):
    """列出项目的正式章节文件"""
    ch_dir = _chapters_dir(project_id)
    if not ch_dir.exists():
        return {"files": []}
    files = sorted(ch_dir.glob("*.txt"))
    return {"files": [f.name for f in files]}


@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, delete_chapters: bool = False):
    """删除一个项目，可选删除章节文件"""
    path = _project_path(project_id)
    if path.exists():
        try:
            path.unlink()
        except OSError as e:
            logger.error("删除项目文件失败 %s: %s", path.name, e)
            raise HTTPException(500, "删除失败")
    if delete_chapters:
        ch_dir = _chapters_dir(project_id)
        if ch_dir.exists():
            shutil.rmtree(ch_dir, ignore_errors=True)
    return {"ok": True}


@router.post("/api/projects/{project_id}/export")
async def export_project(project_id: str):
    """导出项目为纯文本"""
    path = _project_path(project_id)
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


@router.get("/api/styles")
async def get_styles():
    """获取所有文风列表"""
    return _load_styles()


@router.post("/api/styles")
async def save_styles(data: dict):
    """保存文风配置（含自定义文风）"""
    STYLES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True}


@router.get("/api/styles/{style_id}")
async def get_style(style_id: str):
    """获取单个文风详情"""
    from ..styles import _get_style_by_id

    style = _get_style_by_id(style_id)
    if not style:
        raise HTTPException(status_code=404, detail="文风不存在")
    return style
