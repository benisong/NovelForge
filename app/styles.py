"""文风加载/保存（per-workspace）"""

import json
from typing import Optional

from .config import PRESET_STYLES_FILE, styles_file


def _load_preset_styles() -> list:
    """加载根目录下的预设文风（只读，所有工作空间共享）"""
    if PRESET_STYLES_FILE.exists():
        data = json.loads(PRESET_STYLES_FILE.read_text(encoding="utf-8"))
        return data.get("styles", [])
    return []


def _load_styles(workspace: str) -> dict:
    """加载某工作空间的文风：预设文风 + 该工作空间自定义文风"""
    presets = _load_preset_styles()
    sf = styles_file(workspace)
    if sf.exists():
        user_data = json.loads(sf.read_text(encoding="utf-8"))
    else:
        user_data = {"styles": [], "default_word_count": 800}
    user_ids = {s["id"] for s in user_data.get("styles", [])}
    merged = [p for p in presets if p["id"] not in user_ids] + user_data.get("styles", [])
    return {"styles": merged, "default_word_count": user_data.get("default_word_count", 800)}


def _get_style_by_id(workspace: str, style_id: str) -> Optional[dict]:
    """根据 ID 获取某工作空间的文风"""
    if not style_id:
        return None
    data = _load_styles(workspace)
    for s in data.get("styles", []):
        if s["id"] == style_id:
            return s
    return None
