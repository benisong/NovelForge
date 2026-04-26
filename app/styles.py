"""Style loading helpers (per-workspace)."""

import json
from typing import Optional

from .config import PRESET_STYLES_FILE, styles_file

DEFAULT_WORD_COUNT = 800
DEFAULT_STYLE_ID = "preset-anti-europeanized-zh"

ANTI_EUROPEANIZED_STYLE = {
    "id": DEFAULT_STYLE_ID,
    "name": "ANTI-EUROPEANIZED CHINESE",
    "desc": "Block Europeanized Chinese, translationese, and English-thinking leakage; keep Chinese prose concise and native.",
    "instruction": """Write native, concise Simplified Chinese prose. Avoid Europeanized Chinese, translationese, and English-thinking leakage. Follow “微言大义”: maximum meaning, minimum words.

Rule 1 and Rule 8 are highest priority. After each paragraph, silently self-check and rewrite before output if needed. Do not reveal the self-check.

Cut unnecessary “一 + 量词 + 名词”.
Fuse “形容词 + 的 + 名词” when a tighter compound exists.
Examples:
一阵寒冷的风 -> 寒风
一种奇怪的感觉 -> 心里莫名发毛

Omit repeated subjects across linked actions.
Drop unnecessary possessives such as “他的 / 她的 / 它的”.
Example:
他站起身，拿了外套，走出门外。

Do not pile up “的 / 地”.
If a modifier before “地” is too long, split the clause or merge it into the verb.
Example:
她的眼中的泪水缓缓地流下了她的脸颊 -> 泪水淌下脸颊

Replace empty verbs like 进行 / 做出 / 给予 with real verbs.
Example:
进行了观察 -> 打量了他

Do not stack adjectives before a noun. Split into clauses instead.
Example:
一个美丽的、优雅的、身材高挑的年轻女人 -> 那女人年轻、高挑、从容

Avoid existential templates like “有一个 / 有一只 …… 在 ……”.
Prefer: location + verb + 着 + entity.
Example:
有一个女孩站在那里 -> 那边站着个姑娘

Delete details that fail any of these:
1. plot
2. perception
3. POV
One action, one verb. Do not over-choreograph.

Strictly avoid binary-contrast phrasing when the result can be stated directly:
不是A，而是B
并非A，而是B
与其说A，不如说B
虽然A，但是B
A，然后B
Keep Half B, cut Half A.
Examples:
不是一下子到位，而是慢慢推 -> 缓缓下推
不是愤怒，而是失望 -> 脸上怒色散尽，只剩灰败
并非不想动，只是身体发沉 -> 浑身发沉，动弹不得

Before using similes like 像 / 仿佛 / 好似 / ……一样 / 似的, delete them first and check whether the image still works. If it does, keep the sentence without the simile.
Example:
像被电击了一样 -> 猛地一弓

Default bias:
有“一”删“一”，有“的”去“的”，能直说就直说。Think like a native Chinese writer, not a translator.""",
    "example": """走廊尽头的灯管坏了半截，明灭不定。储物柜的铁门被人撞上，回声沿水磨石地面滚了老远。

Reese 拐过墙角，连帽衫的帽子耷在后脑勺，步子不快不慢。走到尽头时他余光瞥见安格斯靠在墙上，帽檐压着眉毛，下巴埋进领口，闭着眼，站着就睡过去了。

他脚步顿了半拍，伸手拽了拽安格斯帽子抽绳，帽檐翻到额头上。安格斯眼皮掀开一条缝，瞳孔对焦了好几秒。

"回天才班睡去。堵路。"

安格斯没动，嘴唇蠕动，含混不清嘟囔了什么。身子从墙上推起来，歪歪斜斜朝走廊另一头拖过去。经过 Reese 身边时肩膀蹭了下胸口，又继续走。

Reese 盯着那个背影拐过转角。帽子歪着，步子不直，左脚和右脚的落点差着半寸。

他把手插回口袋。拳头攥了又松。

远处有人摔了书，铁皮柜的回声在走廊里弹了两遍。日光灯管终于不闪了，白光稳下来。""",
    "preset": True,
}


def _style_ids(styles: list[dict]) -> set[str]:
    return {str(item.get("id", "")).strip() for item in styles if item.get("id")}


def _find_style(styles: list[dict], style_id: str) -> Optional[dict]:
    if not style_id:
        return None
    for item in styles:
        if item.get("id") == style_id:
            return item
    return None


def _resolve_default_style_id(styles: list[dict], candidate: str = "") -> str:
    ids = _style_ids(styles)
    if candidate and candidate in ids:
        return candidate
    if DEFAULT_STYLE_ID in ids:
        return DEFAULT_STYLE_ID
    return next(iter(ids), "")


def _load_preset_styles() -> list:
    """Load built-in preset styles shared by all workspaces."""
    styles = []
    if PRESET_STYLES_FILE.exists():
        data = json.loads(PRESET_STYLES_FILE.read_text(encoding="utf-8"))
        styles = data.get("styles", [])

    if not any(item.get("id") == DEFAULT_STYLE_ID for item in styles):
        styles.append(ANTI_EUROPEANIZED_STYLE)
    return styles


def _load_styles(workspace: str) -> dict:
    """Load preset + workspace custom styles."""
    presets = _load_preset_styles()
    sf = styles_file(workspace)

    user_data: dict | list = {}
    if sf.exists():
        try:
            user_data = json.loads(sf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            user_data = {}

    if isinstance(user_data, list):
        user_data = {"styles": user_data}
    if not isinstance(user_data, dict):
        user_data = {}

    user_styles = user_data.get("styles", [])
    user_ids = _style_ids(user_styles)
    merged = [item for item in presets if item.get("id") not in user_ids] + user_styles
    default_style_id = _resolve_default_style_id(
        merged,
        str(user_data.get("default_style_id", "")).strip(),
    )

    return {
        "styles": merged,
        "default_word_count": user_data.get("default_word_count", DEFAULT_WORD_COUNT),
        "default_style_id": default_style_id,
    }


def _get_style_by_id(workspace: str, style_id: str) -> Optional[dict]:
    """Look up a style by ID within one workspace."""
    data = _load_styles(workspace)
    return _find_style(data.get("styles", []), style_id)


def _get_effective_style(workspace: str, style_id: str = "") -> Optional[dict]:
    """Return the explicit style, or fall back to the workspace default style."""
    data = _load_styles(workspace)
    styles = data.get("styles", [])
    style = _find_style(styles, style_id)
    if style:
        return style
    return _find_style(styles, data.get("default_style_id", ""))
