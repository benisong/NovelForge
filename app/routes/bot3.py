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
BOT3_FORMAT_RETRY_LIMIT = 1  # max 1 auto-retry (Bot3 responses are expensive: non-streaming, full parse)

BOT3_FORMAT_ANCHOR = """## Output Format Hard Constraints (system-enforced, cannot be overridden)
- Only FOUR tag blocks allowed: <scores>, <rewrite_plan>, <analysis>, <item> — in that fixed order
- <scores> MUST contain all four: literary / logic / style / ai_feel, format: literary=8.5
- <rewrite_plan> MUST contain 3-6 lines, directly addressed to Bot2 for execution, ordered by priority. No filler.
- Each <item> MUST contain all five fields: dim / severity / location / problem / suggestion
- suggestion MUST be an executable fix. Forbidden: vague filler like "加强描写 / 优化语言 / 增加细节 / 调整节奏"
- If the issue concerns a specific sentence or paragraph, suggestion should prioritize a replacement direction; if possible, give a concrete rewrite example
- NO JSON, markdown lists, or code fences. NO natural-language text outside the four tag blocks.
- Failing review: at least 4 items. Re-review mode exception: in re-review, only output genuinely unresolved or newly discovered issues. Do not repeat old suggestions just to meet a quota. Passing review: at least 2 low items retained as optional improvements.
"""

BOT3_REREVIEW_ANCHOR = """## Re-Review Hard Constraints
- The current draft is Bot2's rewrite based on the previous round's suggestions. You MUST first judge whether the previous suggestions have been resolved.
- Do NOT repeat items for issues that have already been fixed. Do NOT rehash the previous round's vague suggestions just to meet a quota.
- For unresolved issues: you MUST cite new evidence from the current draft, and prefix the problem field with "Previous issue still unresolved: "
- If the previous suggestions were too vague, translate them into more specific, executable rewrite_plan items — do NOT copy them verbatim.
- Newly discovered issues can be raised, but MUST be clearly distinguished from leftover issues from the previous round.
"""

BOT3_STRICT_FORMAT_RETRY = """## CRITICAL: Your previous response failed format parsing. Output again now.

Follow these rules EXACTLY — do not improvise:

1. Output ONLY these four tag blocks IN ORDER: <scores>, <rewrite_plan>, <analysis>, <item>...
2. <scores> MUST contain all four dimensions with numeric values:
   literary=X.X
   logic=X.X
   style=X.X
   ai_feel=X.X
3. <rewrite_plan> MUST contain 3-6 actionable lines. No filler.
4. <analysis> must be 2-3 sentences.
5. Each <item> MUST have all five fields: dim, severity, location, problem, suggestion.
6. Every tag MUST be properly closed. No text outside the four tag blocks.

OUTPUT NOTHING ELSE. NO preamble, NO markdown, NO code fences, NO commentary."""

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
    """Extract content from a balanced or unbalanced tag block.

    The balanced regex would match across other tag boundaries when tags are
    mis-nested (e.g. <scores>...<rewrite_plan>...</rewrite_plan></scores>).
    We validate that matched content doesn't contain other structural tags,
    falling through to the unbalanced path when it does.
    """
    balanced = re.search(fr"<{tag}>\s*(.*?)\s*</{tag}>", result, re.DOTALL | re.IGNORECASE)
    if balanced:
        content = balanced.group(1).strip()
        # Reject matches that swallowed other structural tag blocks
        other_tags = "|".join(t for t in KNOWN_TAGS if t != tag)
        if not other_tags or not re.search(fr"</?({other_tags})\b", content, re.IGNORECASE):
            return content
        # Content contains other tags — mis-nested. Fall through to unbalanced.

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


def _clip_prompt_text(value: str | None, max_chars: int = 6000) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[previous suggestions truncated]"


# Minimum character length for problem/suggestion to be considered substantive.
# Items with content shorter than this are likely noise from truncated or
# garbled LLM output — they carry no actionable information for Bot2.
_MIN_MEANINGFUL_LEN = 8


def _normalize_items(items: list[dict]) -> list[dict]:
    normalized = []
    for item in items:
        problem = _cleanup_text(item.get("problem", ""))
        suggestion = _cleanup_text(item.get("suggestion", ""))
        location = _cleanup_text(item.get("location", ""))

        # Drop items with no content at all
        if not (problem or suggestion or location):
            continue

        # Drop items whose only "content" is a dim+severity pair with no
        # substantive review text. Common artifact of truncated <item> blocks
        # that got cut off after the severity field.
        if len(problem) < _MIN_MEANINGFUL_LEN and len(suggestion) < _MIN_MEANINGFUL_LEN:
            if not location or location == "全文":
                continue

        if not problem and suggestion:
            problem = "This passage needs revision per review feedback"
        if not suggestion and problem:
            suggestion = (
                f"Directly rewrite this passage around "
                f"\"{problem[:_MIN_MEANINGFUL_LEN * 2]}\" — "
                f"provide more specific action, dialogue, or causality."
            )

        dim = _normalize_dim(item.get("dim", "literary"))
        severity = _normalize_severity(item.get("severity", "medium"))

        normalized.append(
            {
                "dim": dim,
                "severity": severity,
                "location": location or "全文",
                "problem": problem or "The expression or progression at this location needs improvement",
                "suggestion": suggestion or "Directly rewrite this passage — avoid vague suggestions.",
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
        # Validate: reject matches that swallowed other structural tag blocks
        other_tags = "|".join(t for t in KNOWN_TAGS if t != tag)
        if not other_tags or not any(
            re.search(fr"</?({other_tags})\b", b, re.IGNORECASE) for b in balanced
        ):
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
            # Only treat 'dim' as an item boundary when its value is a recognized
            # dimension key (literary/logic/style/ai_feel or their Chinese equivalents).
            # This prevents mid-text occurrences like "the dim: atmosphere was..."
            # from falsely splitting items, while still correctly detecting real dim
            # fields like "dim=literary" or "dim=人味".
            if key == "dim" and current:
                normalized_val = _KEY_MAP.get((value or "").strip().lower(), "")
                if normalized_val in DIM_KEYS:
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
                "problem": f"Prioritize this rewrite instruction: {line[:60]}",
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
        lines.append(f"First, bring {' / '.join(failing_dims)} back above the pass threshold — fix hard issues before polishing.")
    else:
        lines.append("Preserve the current draft's strengths — only make targeted local corrections. Do not rewrite the entire chapter from scratch.")

    for index, item in enumerate(_select_priority_items(scores, items), 1):
        location = item.get("location") or "全文"
        suggestion = item.get("suggestion") or item.get("problem") or "Directly rewrite this passage"
        lines.append(
            f"{index}. [{DIM_LABELS.get(item.get('dim', 'literary'), '文学性')}] {location}：{suggestion}"
        )

    if analysis:
        analysis_hint = analysis.strip().splitlines()[0][:80]
        if analysis_hint:
            lines.append(f"Overall assessment: {analysis_hint}")
    if not items:
        lines.append("Re-examine the main problem passages and produce directly executable rewrite plans — do not just keep the scores.")

    return "\n".join(lines[:6]).strip()


def _detect_truncation(result: str) -> bool:
    """Return True if the response appears truncated (incomplete).

    Detection methods:
      A. Tag count mismatch — any tag opened more times than closed. Classic
         max_tokens cutoff mid-tag-block.
      B. Abrupt ending — last ~80 chars have no closing tag for the most recently
         opened tag. Catches cases where all tags are nominally balanced but the
         final block's content was cut off (e.g. <item> has dim/severity but
         suggestion is missing).
      C. Partial closing tag at end — response ends with a fragment like '</ite'
         or '<rewrite_' that was clearly mid-tag.
    """
    text = result or ""

    # A: Tag count mismatch
    for tag in KNOWN_TAGS:
        opens = len(re.findall(fr"<{tag}\b[^>]*>", text, re.IGNORECASE))
        closes = len(re.findall(fr"</{tag}>", text, re.IGNORECASE))
        if opens > closes:
            return True

    # B: Last ~80 chars — is the most recently opened tag properly closed?
    tail = text[-80:]
    # Find the LAST opening tag in the tail
    last_open = re.search(
        fr"<({'|'.join(KNOWN_TAGS)})\b[^>]*>(?!.*</?({'|'.join(KNOWN_TAGS)})\b)",
        tail,
        re.IGNORECASE,
    )
    if last_open:
        tag_name = last_open.group(1)
        # Check if this tag is closed AFTER its position in the tail
        after_open = tail[last_open.end():]
        if f"</{tag_name}>" not in after_open.lower():
            return True

    # C: Partial closing tag at the very end (e.g. '</ite' or '<rewri')
    if re.search(r"</?[a-z_]{2,15}$", text.strip(), re.IGNORECASE):
        return True

    return False


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

    truncated = _detect_truncation(result)

    if len([key for key in DIM_KEYS if key in scores]) >= 4:
        values = [scores.get(key, 0) for key in DIM_KEYS]
        average = round(sum(values) / 4, 1)

        if truncated:
            return {
                "scores": {key: scores.get(key, 0) for key in DIM_KEYS},
                "average": average,
                "passed": False,
                "analysis": "(Bot3 response was truncated mid-stream — result incomplete)",
                "rewrite_brief": (
                    "Bot3 response was truncated within the 16384 token hard limit — "
                    "likely the input is too long or the model generated excessive output. "
                    "Try shortening the chapter content (reduce word count or use Bot4 "
                    "summary to compress prior context first), then click Re-Review to run again."
                ),
                "items": [],
                "retry_hint": True,
                "truncated": True,
            }

        if not items:
            return {
                "scores": {key: scores.get(key, 0) for key in DIM_KEYS},
                "average": average,
                "passed": average >= pass_score,
                "analysis": analysis or "(Review complete, but no itemized suggestions could be extracted)",
                "rewrite_brief": (
                    "Bot3 did not produce parseable itemized suggestions or a rewrite "
                    "plan this round. Expand the raw AI response below to manually "
                    "add suggestions, or click Re-Review to run again."
                ),
                "items": [],
                "retry_hint": True,
            }

        rewrite_brief = _build_rewrite_brief(scores, items, analysis, pass_score, rewrite_plan)
        return {
            "scores": {key: scores.get(key, 0) for key in DIM_KEYS},
            "average": average,
            "passed": average >= pass_score,
            "analysis": analysis or "(Review complete)",
            "rewrite_brief": rewrite_brief,
            "items": items,
        }

    return {
        "scores": {key: 0 for key in DIM_KEYS},
        "average": 0,
        "passed": False,
        "analysis": "Review result parsing failed",
        "rewrite_brief": "Re-run to get a valid review result — prioritize obtaining executable revision suggestions — then pass to Bot2 for rewrite.",
        "items": [
            {
                "dim": "literary",
                "severity": "high",
                "location": "全文",
                "problem": "Unable to parse review result",
                "suggestion": f"Bot3 raw response preview: {result[:300]}",
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
    previous_suggestions = _clip_prompt_text(req.previous_suggestions)
    try:
        review_attempt = max(1, int(req.review_attempt or 1))
    except (TypeError, ValueError):
        review_attempt = 1

    style = _get_effective_style(workspace, req.style_id)
    if style:
        if style.get("instruction"):
            system_parts.append(f"【Default Style Constraint】\n{style['instruction']}")
        system_parts.append(
            f"【Target Style: {style['name']}】\n"
            f"Style description: {style.get('desc', '')}\n"
            f"Reference excerpt:\n---\n{style['example']}\n---\n"
            "In the Style Consistency dimension, focus on judging whether the content "
            "adheres to the above style requirements."
        )

    if previous_suggestions:
        system_parts.append(BOT3_REREVIEW_ANCHOR)

    system_parts.append(BOT3_FORMAT_ANCHOR)
    messages = [{"role": "system", "content": "\n\n".join(system_parts)}]

    cache_breaker = f"[Review request #{uuid.uuid4().hex[:16]}]"
    previous_block = ""
    if previous_suggestions:
        previous_block = (
            f"【Re-Review Context】\n"
            f"This is review round {review_attempt}. The current draft has been rewritten "
            f"by Bot2 based on the previous round's suggestions.\n"
            f"The previous round's revision requirements sent to Bot2:\n{previous_suggestions}\n\n"
            "During re-review, check each previous requirement item by item: resolved issues "
            "should NOT be repeated; unresolved issues MUST cite new evidence from the current "
            "draft and provide more specific replacement direction.\n\n"
        )
    user_content = (
        f"{cache_breaker}\n\n"
        f"【Outline Requirements】\n{req.outline}\n\n"
        f"{previous_block}"
        f"【Content to Review】\n{req.content}\n\n"
        f"Pass threshold: {req.config.pass_score}\n\n"
        "Output strictly in the tag format specified in the system prompt. "
        "The priority is to produce a rewrite_plan that Bot2 can directly execute, "
        "along with itemized, actionable suggestions — do not just output scores."
    )
    messages.append({"role": "user", "content": user_content})

    # Try up to BOT3_FORMAT_RETRY_LIMIT + 1 times (initial + retries)
    last_review = None
    for attempt in range(BOT3_FORMAT_RETRY_LIMIT + 1):
        try:
            result = await call_llm_full(req.config.bot3, messages)
        except Exception as e:
            return {"error": str(e)[:500], "retry_hint": True}

        logger.info("[Bot3] response length %d chars (attempt %d)", len(result), attempt + 1)
        logger.debug("[Bot3 raw preview]\n%s", result[:1000])

        review = _parse_bot3_tags(result, req.config.pass_score)
        review["_raw_preview"] = result[:800]
        last_review = review

        # If parsing succeeded (no retry_hint), we're done
        if not review.get("retry_hint"):
            return review

        # Retry: rebuild with strict format-only system prompt
        if attempt < BOT3_FORMAT_RETRY_LIMIT:
            logger.info("[Bot3] format parse issue detected, retrying with strict prompt")
            messages = [
                {"role": "system", "content": BOT3_STRICT_FORMAT_RETRY},
                {"role": "user", "content": user_content},
            ]

    return last_review
