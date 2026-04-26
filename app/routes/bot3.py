"""Bot3 review routes and prompt management (per-workspace)."""

from __future__ import annotations

import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends

from ..config import bot3_prompts_file
from ..llm import call_llm_full
from ..models import Bot3ReviewRequest
from ..prompts import BOT3_SYSTEM
from ..styles import _get_effective_style
from ..workspace import require_workspace

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/w/{workspace}",
    dependencies=[Depends(require_workspace)],
)

DIM_KEYS = ("literary", "logic", "style", "ai_feel")
DIM_LABELS = {
    "literary": "文学性",
    "logic": "逻辑性",
    "style": "风格一致性",
    "ai_feel": "人味",
}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
KNOWN_TAGS = ("scores", "rewrite_plan", "analysis", "item", "items")

BOT3_FORMAT_ANCHOR = """## 输出格式硬约束（系统强制，不可覆盖）
- 只允许输出 <scores>、<rewrite_plan>、<analysis>、<item> 四种标签块，顺序固定
- <scores> 必须包含 literary / logic / style / ai_feel 四项，格式如 literary=8.5
- <rewrite_plan> 必须写 3-6 行，直接写给 Bot2 执行，按优先级排序，禁止空话
- 每条 <item> 必须包含 dim / severity / location / problem / suggestion 五个字段
- suggestion 必须是可执行改法；禁止只写“加强描写 / 优化语言 / 增加细节 / 调整节奏”这类空泛建议
- 如问题涉及某一句或某一段的具体表达，suggestion 优先给出替换方向，必要时直接给一句示范改写
- 禁止输出 JSON、markdown 列表或代码围栏；禁止在标签外输出任何自然语言
- 未通过审核时至少输出 4 条 item；通过审核时至少保留 2 条 low item 作为可选优化
"""

_KEY_MAP = {
    "文学性": "literary",
    "literary": "literary",
    "逻辑性": "logic",
    "logic": "logic",
    "风格一致性": "style",
    "风格": "style",
    "style": "style",
    "人味": "ai_feel",
    "人味感": "ai_feel",
    "ai_feel": "ai_feel",
    "维度": "dim",
    "dim": "dim",
    "严重程度": "severity",
    "severity": "severity",
    "位置": "location",
    "location": "location",
    "问题": "problem",
    "problem": "problem",
    "建议": "suggestion",
    "suggestion": "suggestion",
    "修改建议": "suggestion",
}


def _load_bot3_prompts(workspace: str) -> list[dict]:
    path = bot3_prompts_file(workspace)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            pass
    return []


def _save_bot3_prompts(workspace: str, prompts: list[dict]) -> None:
    path = bot3_prompts_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_kv_line(line: str) -> tuple[str | None, str | None]:
    text = line.strip().lstrip("-").lstrip("*").strip()
    if not text:
        return None, None

    for sep in ("=", ":", "："):
        if sep in text:
            raw_key, raw_value = text.split(sep, 1)
            key = _KEY_MAP.get(raw_key.strip().lower(), raw_key.strip().lower())
            value = raw_value.strip()
            return key, value
    return None, None


def _extract_tag_block(result: str, tag: str) -> str:
    balanced = re.search(fr"<{tag}>\s*(.*?)\s*</{tag}>", result, re.DOTALL | re.IGNORECASE)
    if balanced:
        return balanced.group(1).strip()

    next_tags = "|".join(KNOWN_TAGS)
    unbalanced = re.search(
        fr"<{tag}>\s*(.*?)(?=<(?:{next_tags})\b|$)",
        result,
        re.DOTALL | re.IGNORECASE,
    )
    return unbalanced.group(1).strip() if unbalanced else ""


def _normalize_dim(value: str) -> str:
    normalized = _KEY_MAP.get(str(value or "").strip().lower(), str(value or "").strip().lower())
    return normalized if normalized in DIM_KEYS else "literary"


def _normalize_severity(value: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in SEVERITY_ORDER else "medium"


def _cleanup_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_items(items: list[dict]) -> list[dict]:
    normalized = []
    for item in items:
        problem = _cleanup_text(item.get("problem", ""))
        suggestion = _cleanup_text(item.get("suggestion", ""))
        location = _cleanup_text(item.get("location", ""))
        if not (problem or suggestion or location):
            continue

        if not problem and suggestion:
            problem = "该处需要按审核意见重写"
        if not suggestion and problem:
            suggestion = f"围绕“{problem}”直接重写这一处，给出更具体的动作、对白或因果。"

        normalized.append(
            {
                "dim": _normalize_dim(item.get("dim", "literary")),
                "severity": _normalize_severity(item.get("severity", "medium")),
                "location": location or "全文",
                "problem": problem or "该处表达或推进存在问题",
                "suggestion": suggestion or "请直接重写这一处，避免空泛表述。",
            }
        )
    return normalized


def _parse_scores_block(block: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    for line in block.splitlines():
        key, value = _parse_kv_line(line)
        if key in DIM_KEYS and value:
            matched = re.match(r"(\d+(?:\.\d+)?)", value)
            if matched:
                scores[key] = float(matched.group(1))
    return scores


def _extract_all_tag_blocks(result: str, tag: str) -> list[str]:
    open_count = len(re.findall(fr"<{tag}\b[^>]*>", result, re.IGNORECASE))
    if open_count == 0:
        return []

    balanced = [
        matched.group(1).strip()
        for matched in re.finditer(fr"<{tag}>\s*(.*?)\s*</{tag}>", result, re.DOTALL | re.IGNORECASE)
    ]
    balanced = [block for block in balanced if block]
    if balanced and len(balanced) >= open_count:
        return balanced

    next_tags = "|".join(KNOWN_TAGS)
    blocks: list[str] = []
    for matched in re.finditer(
        fr"<{tag}>\s*(.*?)(?=</?(?:{next_tags})\b|$)",
        result,
        re.DOTALL | re.IGNORECASE,
    ):
        block = matched.group(1).strip()
        block = re.sub(fr"</{tag}>\s*$", "", block, flags=re.IGNORECASE).strip()
        if block:
            blocks.append(block)
    return blocks or balanced


_FIELD_KEYS_RE = (
    r"(?:dim|severity|location|problem|suggestion|"
    r"维度|严重程度|位置|问题|建议|修改建议)"
)


def _parse_item_dicts_from_block(block: str) -> list[dict]:
    if not block:
        return []

    # Strip any nested structural tags (e.g. inner <item> when block came from <items>)
    cleaned = re.sub(
        fr"</?(?:{'|'.join(KNOWN_TAGS)})\b[^>]*>",
        "",
        block.strip(),
        flags=re.IGNORECASE,
    )

    prepared = re.sub(
        fr"[\s；;,，、]+(?={_FIELD_KEYS_RE}\s*[:=：])",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )

    items: list[dict] = []
    current: dict[str, str] = {}
    current_key: str | None = None

    for raw_line in prepared.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        key, value = _parse_kv_line(line)
        if key:
            if key == "dim" and current:
                items.append(current)
                current = {}
            if value:
                current[key] = value
            current_key = key
        elif current_key:
            existing = current.get(current_key, "")
            current[current_key] = f"{existing} {line}".strip() if existing else line

    if current:
        items.append(current)

    return items


def _parse_item_blocks(result: str) -> list[dict]:
    raw_items: list[dict] = []
    seen: set[tuple] = set()
    for tag in ("item", "items"):
        for block in _extract_all_tag_blocks(result, tag):
            for item in _parse_item_dicts_from_block(block):
                fingerprint = (
                    str(item.get("dim", "")).strip().lower(),
                    str(item.get("severity", "")).strip().lower(),
                    _cleanup_text(item.get("location", ""))[:40],
                    _cleanup_text(item.get("problem", ""))[:40],
                )
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                raw_items.append(item)
    return _normalize_items(raw_items)


def _parse_json_fallback(result: str) -> tuple[dict[str, float], str, str, list[dict]]:
    json_str = result
    if "```json" in result:
        json_str = result.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in result:
        json_str = result.split("```", 1)[1].split("```", 1)[0]
    else:
        first = result.find("{")
        last = result.rfind("}")
        if first != -1 and last > first:
            json_str = result[first:last + 1]

    parsed = json.loads(json_str.strip())
    raw_scores = parsed.get("scores", {}) if isinstance(parsed, dict) else {}
    scores: dict[str, float] = {}
    if isinstance(raw_scores, dict):
        for raw_key, raw_value in raw_scores.items():
            key = _normalize_dim(raw_key)
            try:
                scores[key] = float(raw_value)
            except (TypeError, ValueError):
                continue

    rewrite_plan = parsed.get("rewrite_plan") or parsed.get("rewrite_brief") or ""
    if isinstance(rewrite_plan, list):
        rewrite_plan = "\n".join(str(item).strip() for item in rewrite_plan if str(item).strip())
    analysis = str(parsed.get("analysis", "") or "")

    raw_items = parsed.get("items", [])
    items: list[dict] = []
    if isinstance(raw_items, list):
        items = _normalize_items([item for item in raw_items if isinstance(item, dict)])
    elif parsed.get("suggestions"):
        items = _normalize_items(
            [
                {
                    "dim": "literary",
                    "severity": "medium",
                    "location": "全文",
                    "problem": "综合修改建议",
                    "suggestion": str(parsed.get("suggestions")),
                }
            ]
        )

    return scores, str(rewrite_plan).strip(), analysis.strip(), items


def _regex_score_fallback(result: str, scores: dict[str, float]) -> dict[str, float]:
    patterns = {
        "literary": r"(?:literary|文学性)\s*[=:：]\s*(\d+(?:\.\d+)?)",
        "logic": r"(?:logic|逻辑性)\s*[=:：]\s*(\d+(?:\.\d+)?)",
        "style": r"(?:style|风格一致性|风格)\s*[=:：]\s*(\d+(?:\.\d+)?)",
        "ai_feel": r"(?:ai_feel|人味|人味感)\s*[=:：]\s*(\d+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        if key in scores:
            continue
        matched = re.search(pattern, result, re.IGNORECASE)
        if matched:
            scores[key] = float(matched.group(1))
    return scores


def _fallback_analysis(result: str) -> str:
    cleaned = re.sub(
        r"</?(?:scores|rewrite_plan|analysis|item|items)\b[^>]*>",
        "\n",
        result,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?im)^\s*(literary|logic|style|ai_feel|dim|severity|location|problem|suggestion|"
        r"文学性|逻辑性|风格一致性|风格|人味|维度|严重程度|位置|问题|建议|修改建议)\s*[:=：].*$",
        "",
        cleaned,
    )
    lines = [line.strip(" -•*\t") for line in cleaned.splitlines()]
    lines = [line for line in lines if line and len(line) > 6]
    return lines[0][:200] if lines else ""


def _rewrite_plan_lines(rewrite_plan: str) -> list[str]:
    if not rewrite_plan:
        return []

    prepared = rewrite_plan.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in prepared:
        prepared = re.sub(r"(?<=[。；;])\s+", "\n", prepared)

    lines = []
    for raw_line in prepared.splitlines():
        line = raw_line.strip()
        line = re.sub(r"^[\-\*\d\.\)\(、\s]+", "", line)
        line = _cleanup_text(line)
        if line:
            lines.append(line)
    return lines[:6]


def _infer_dim_from_text(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("逻辑", "因果", "动机", "设定", "前后")):
        return "logic"
    if any(token in lowered for token in ("风格", "语气", "文风", "口吻", "一致")):
        return "style"
    if any(token in lowered for token in ("ai", "人味", "陈词", "欧化", "翻译腔", "比喻", "对仗")):
        return "ai_feel"
    return "literary"


def _items_from_rewrite_plan(rewrite_plan: str) -> list[dict]:
    lines = _rewrite_plan_lines(rewrite_plan)
    if not lines:
        return []

    synthetic_items = []
    for index, line in enumerate(lines):
        severity = "high" if index < 2 else "medium" if index < 4 else "low"
        synthetic_items.append(
            {
                "dim": _infer_dim_from_text(line),
                "severity": severity,
                "location": "全文",
                "problem": f"需要优先处理这项重写指令：{line[:60]}",
                "suggestion": line,
            }
        )
    return _normalize_items(synthetic_items)


def _select_priority_items(scores: dict[str, float], items: list[dict], limit: int = 4) -> list[dict]:
    dim_rank = {
        key: index
        for index, key in enumerate(
            sorted(DIM_KEYS, key=lambda dim: (scores.get(dim, 10), DIM_KEYS.index(dim)))
        )
    }
    return sorted(
        items,
        key=lambda item: (
            SEVERITY_ORDER.get(item.get("severity", "medium"), 1),
            dim_rank.get(item.get("dim", "literary"), 99),
        ),
    )[:limit]


def _build_rewrite_brief(
    scores: dict[str, float],
    items: list[dict],
    analysis: str,
    pass_score: float,
    existing: str = "",
) -> str:
    existing = existing.strip()
    if existing and len(existing) >= 24:
        return existing

    failing_dims = [DIM_LABELS[key] for key in DIM_KEYS if scores.get(key, 0) < pass_score]
    lines: list[str] = []
    if failing_dims:
        lines.append(f"先把{'、'.join(failing_dims)}拉回及格线，优先处理硬伤，再做润色。")
    else:
        lines.append("保留当前成稿的优点，只做针对性的局部修正，不要整章推倒重来。")

    for index, item in enumerate(_select_priority_items(scores, items), 1):
        location = item.get("location") or "全文"
        suggestion = item.get("suggestion") or item.get("problem") or "请直接重写这一处"
        lines.append(
            f"{index}. [{DIM_LABELS.get(item.get('dim', 'literary'), '文学性')}] {location}：{suggestion}"
        )

    if analysis:
        analysis_hint = analysis.strip().splitlines()[0][:80]
        if analysis_hint:
            lines.append(f"整体把握：{analysis_hint}")

    if not items:
        lines.append("请重新审视主要问题段落，补出可直接执行的重写方案，而不是只保留分数。")

    return "\n".join(lines[:6]).strip()


def _parse_bot3_tags(result: str, pass_score: float) -> dict:
    scores = _parse_scores_block(_extract_tag_block(result, "scores"))
    rewrite_plan = _extract_tag_block(result, "rewrite_plan")
    analysis = _extract_tag_block(result, "analysis")
    items = _parse_item_blocks(result)

    if len([key for key in DIM_KEYS if key in scores]) < 4:
        try:
            json_scores, json_rewrite, json_analysis, json_items = _parse_json_fallback(result)
            scores.update(json_scores)
            if not rewrite_plan:
                rewrite_plan = json_rewrite
            if not analysis:
                analysis = json_analysis
            if not items:
                items = json_items
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
            pass

    if len([key for key in DIM_KEYS if key in scores]) < 4:
        scores = _regex_score_fallback(result, scores)

    if not analysis:
        analysis = _fallback_analysis(result)

    if not items and rewrite_plan:
        items = _items_from_rewrite_plan(rewrite_plan)

    if len([key for key in DIM_KEYS if key in scores]) >= 4:
        values = [scores.get(key, 0) for key in DIM_KEYS]
        average = round(sum(values) / 4, 1)

        if not items:
            return {
                "scores": {key: scores.get(key, 0) for key in DIM_KEYS},
                "average": average,
                "passed": average >= pass_score,
                "analysis": analysis or "（审核完成，但未提取到逐条修改建议）",
                "rewrite_brief": (
                    "Bot3 这次没有给出可解析的逐条建议或重写计划。"
                    "请展开下方“AI 原始回复”人工补建议，或点“再次审核”重新跑一次。"
                ),
                "items": [],
                "retry_hint": True,
            }

        rewrite_brief = _build_rewrite_brief(scores, items, analysis, pass_score, rewrite_plan)
        return {
            "scores": {key: scores.get(key, 0) for key in DIM_KEYS},
            "average": average,
            "passed": average >= pass_score,
            "analysis": analysis or "（审核完成）",
            "rewrite_brief": rewrite_brief,
            "items": items,
        }

    return {
        "scores": {key: 0 for key in DIM_KEYS},
        "average": 0,
        "passed": False,
        "analysis": "审核结果解析失败",
        "rewrite_brief": "先重新获取一版有效审核结果，重点补出可执行的修改建议，再交给 Bot2 重写。",
        "items": [
            {
                "dim": "literary",
                "severity": "high",
                "location": "全文",
                "problem": "无法解析审核结果",
                "suggestion": f"Bot3 原始回复预览：{result[:300]}",
            }
        ],
        "retry_hint": True,
    }


@router.get("/bot3-prompts")
async def get_bot3_prompts(workspace: str):
    return {"prompts": _load_bot3_prompts(workspace), "default_prompt": BOT3_SYSTEM}


@router.post("/bot3-prompts")
async def save_bot3_prompts(workspace: str, data: dict):
    _save_bot3_prompts(workspace, data.get("prompts", []))
    return {"ok": True}


@router.post("/bot3/review")
async def bot3_review(workspace: str, req: Bot3ReviewRequest):
    base_prompt = req.custom_prompt.strip() if req.custom_prompt and req.custom_prompt.strip() else BOT3_SYSTEM
    system_parts = [base_prompt]

    style = _get_effective_style(workspace, req.style_id)
    if style:
        if style.get("instruction"):
            system_parts.append(f"【默认文风约束】\n{style['instruction']}")
        system_parts.append(
            f"【目标文风：{style['name']}】\n"
            f"风格描述：{style.get('desc', '')}\n"
            f"参考示例片段：\n---\n{style['example']}\n---\n"
            "请在“风格一致性”维度重点判断内容是否贴合上述文风要求。"
        )

    system_parts.append(BOT3_FORMAT_ANCHOR)
    messages = [{"role": "system", "content": "\n\n".join(system_parts)}]

    cache_breaker = f"[审核请求 #{uuid.uuid4().hex[:16]}]"
    user_content = (
        f"{cache_breaker}\n\n"
        f"【大纲要求】\n{req.outline}\n\n"
        f"【待审核的小说内容】\n{req.content}\n\n"
        f"及格分数线：{req.config.pass_score}分\n\n"
        "请严格按系统提示中的标签格式输出。重点是给出能直接交给 Bot2 执行的 rewrite_plan，"
        "以及逐条、可落地的 suggestion；不要只给分数。"
    )
    messages.append({"role": "user", "content": user_content})

    try:
        result = await call_llm_full(req.config.bot3, messages)
    except Exception as e:
        return {"error": str(e)[:500], "retry_hint": True}

    logger.info("[Bot3] response length %d chars", len(result))
    logger.debug("[Bot3 raw preview]\n%s", result[:1000])

    review = _parse_bot3_tags(result, req.config.pass_score)
    review["_raw_preview"] = result[:800]
    return review
