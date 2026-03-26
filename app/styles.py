"""文风加载/保存"""

import json
from typing import Optional

from .config import STYLES_FILE, PRESET_STYLES_FILE


def _load_preset_styles() -> list:
    """加载根目录下的预设文风（只读）"""
    if PRESET_STYLES_FILE.exists():
        data = json.loads(PRESET_STYLES_FILE.read_text(encoding="utf-8"))
        return data.get("styles", [])
    return []


def _load_styles() -> dict:
    """加载文风配置：预设文风 + 用户自定义文风"""
    presets = _load_preset_styles()
    if STYLES_FILE.exists():
        user_data = json.loads(STYLES_FILE.read_text(encoding="utf-8"))
    else:
        user_data = {"styles": [], "default_word_count": 800}
    user_ids = {s["id"] for s in user_data.get("styles", [])}
    merged = [p for p in presets if p["id"] not in user_ids] + user_data.get("styles", [])
    return {"styles": merged, "default_word_count": user_data.get("default_word_count", 800)}


def _get_style_by_id(style_id: str) -> Optional[dict]:
    """根据ID获取文风"""
    if not style_id:
        return None
    data = _load_styles()
    for s in data.get("styles", []):
        if s["id"] == style_id:
            return s
    return None
