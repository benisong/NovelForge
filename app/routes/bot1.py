"""Bot1 对话 + 模型获取（per-workspace）"""

import re
import json
from typing import Literal
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse

from ..models import Bot1ChatRequest, OutlineChatRequest, FetchModelsRequest
from ..prompts import BOT1_SYSTEM
from ..llm import stream_llm
from ..workspace import require_workspace

router = APIRouter(
    prefix="/api/w/{workspace}",
    dependencies=[Depends(require_workspace)],
)

REQUIRED_OUTLINE_TAGS = ("outline", "chapter_outline")
REQUIRED_OUTLINE_ONLY_TAGS = ("outline",)
BOT1_FORMAT_RETRY_LIMIT = 2
PLACEHOLDER_OUTLINE_TEXTS = {
    "同上",
    "略",
    "保持不变",
    "完整总大纲",
    "完整当前章节大纲",
    "完整章节大纲",
    "待补充",
    "暂无",
    "无",
    "...",
}
SHORT_PLACEHOLDER_MARKERS = (
    "同上",
    "保持不变",
    "完整总大纲",
    "完整当前章节大纲",
    "完整章节大纲",
    "待补充",
)
SHRINK_ALLOWED_KEYWORDS = (
    "精简",
    "压缩",
    "简化",
    "缩短",
    "重开",
    "重新开始",
    "从头",
    "推翻",
    "清空",
    "删除",
    "重写大纲",
    "重新规划",
)

BOT1_STRICT_FORMAT_RETRY = """## Bot1 Format Retry Instruction (HIGHEST PRIORITY)

Your previous response failed programmatic validation. Output a new complete response now.

Strictly follow the 3-part order:
1. PART 1: Chat with the user — affirm ideas, point out issues, or give suggestions. NO tags.
2. PART 2: <outline>...</outline> — complete book-level outline.
3. PART 3: <chapter_outline>...</chapter_outline> — complete chapter-level outline.

Tag requirements:
- Only ONE pair of <outline>...</outline> and ONE pair of <chapter_outline>...</chapter_outline>
- Output Part 1 chat first, then <outline>, then <chapter_outline>
- Both tags must be properly closed; tag names must match exactly
- Inside tags: write COMPLETE, usable outline text. No placeholders like "同上", "略", "保持不变", or any variant
- If the outline needs no changes, copy the current outline VERBATIM — no summarizing, no omitting details
- NO JSON, code fences, markdown tables; do not explain format errors
- Before output, silently self-check tag completeness — do NOT write out the check

If your previous response had usable content, absorb it. If tags were missing, rebuild from the current outlines, summary memory, and latest user input."""

BOT1_OUTLINE_STRICT_FORMAT_RETRY = """## Bot1 Outline Format Retry Instruction (HIGHEST PRIORITY)

Your previous response failed programmatic validation. Output a new complete response now.

Strictly follow the 2-part order:
1. PART 1: Chat with the user — discuss the official outline direction, clarify structure, or give revision advice. NO tags.
2. PART 2: <outline>...</outline> — complete official-outline draft.

Tag requirements:
- Output exactly ONE pair of <outline>...</outline>
- Output Part 1 chat first, then <outline>
- <outline> must be properly closed; tag name must match exactly
- Inside <outline>: write COMPLETE, usable official-outline text. No placeholders like "同上", "略", "保持不变", or any variant
- If the outline needs no changes, copy the current outline VERBATIM — no summarizing, no omitting details
- Do NOT output <chapter_outline> in this mode
- NO JSON, code fences, markdown tables; do not explain format errors
- Before output, silently self-check tag completeness — do NOT write out the check

If your previous response had usable content, absorb it. If the tag was missing, rebuild from the current outline, summary memory, and latest user input."""

BOT1_OUTLINE_MINIMAL_RETRY = """## Bot1 Outline Fallback Instruction (FINAL SAFETY NET, HIGHEST PRIORITY)

Now output ONLY two parts. Do not explain format errors. Do not add commentary.

PART 1: One-sentence reply to the user — affirm ideas, point out structural issues, or ask a concise follow-up.

<outline>
Complete official-outline draft. If no changes needed, copy the current full outline VERBATIM.
</outline>

Do not output <chapter_outline>. Tag name must match exactly. The tag must be properly closed. No placeholders inside the tag."""


def _build_bot1_system(req: Bot1ChatRequest, mode: Literal["chapter", "outline"] = "chapter") -> str:
    """Assemble Bot1 context in a fixed order, with a generous soft cap for attention quality.

    Bot1 only deals with outlines and summaries — not full novel text — so the context
    is naturally bounded (~5K-15K chars for typical projects). A soft cap at 20000 chars
    keeps attention focused on the most relevant content without truncating normal projects.
    """
    MAX_SYSTEM_CHARS = 20000
    intro_parts = [BOT1_SYSTEM]

    if mode == "outline":
        intro_parts.append(
            "## Active Mode\n"
            "You are currently in official-outline design/revision mode, not ordinary chapter planning.\n"
            "- Focus Part 1 on discussing the book-level direction, premise, worldbuilding, character arcs, and structural adjustments.\n"
            "- In <outline>, output the current best complete OFFICIAL outline draft.\n"
            "- In <chapter_outline>, output a minimal placeholder chapter-planning note only if no concrete chapter plan exists yet; do not invent detailed chapter beats just to satisfy ordinary planning habits.\n"
            "- Do not let chapter-planning details dominate the response when the user is clearly revising the official outline."
        )

    parts = intro_parts

    if req.current_outline and req.current_outline.strip():
        parts.append(f"【Current Full Outline】\n{req.current_outline.strip()}")

    if req.chapter_outline and req.chapter_outline.strip():
        parts.append(f"【Current Chapter Outline】\n{req.chapter_outline.strip()}")

    if req.context and req.context.strip():
        parts.append(req.context.strip())

    combined = "\n\n".join(parts)
    if len(combined) <= MAX_SYSTEM_CHARS:
        return combined

    # Only triggers for pathological cases. Strategy: keep BOT1_SYSTEM intact,
    # trim the oldest/furthest context first (summaries → full outline tail → full outline head)
    base = BOT1_SYSTEM
    remaining = MAX_SYSTEM_CHARS - len(base)

    chapter_outline = (req.chapter_outline or "").strip()
    full_outline = (req.current_outline or "").strip()
    context = (req.context or "").strip()

    # Priority 1: chapter outline (what user is working on NOW) — keep as much as possible
    if chapter_outline:
        if len(chapter_outline) <= remaining:
            chapter_block = f"【Current Chapter Outline】\n{chapter_outline}"
            remaining -= len(chapter_block) + 2
        else:
            chapter_block = f"【Current Chapter Outline】\n{chapter_outline[:remaining]}"
            remaining = 0
    else:
        chapter_block = ""

    # Priority 2: full outline — keep beginning + recent chapters, drop middle
    if full_outline and remaining > 500:
        if len(full_outline) <= remaining:
            full_block = f"【Current Full Outline】\n{full_outline}"
            remaining -= len(full_block) + 2
        else:
            keep_start = int(remaining * 0.3)
            keep_end = remaining - keep_start
            full_block = (
                f"【Current Full Outline — truncated for attention, recent chapters preserved】\n"
                f"{full_outline[:keep_start]}\n\n...\n\n{full_outline[-keep_end:]}"
            )
            remaining = 0
    else:
        full_block = ""

    # Priority 3: summaries — keep most recent (end), drop oldest
    if context and remaining > 300:
        if len(context) <= remaining:
            context_block = context
        else:
            context_block = (
                f"[Older summaries trimmed for attention focus]\n"
                f"{context[-remaining:]}"
            )
    else:
        context_block = ""

    return "\n\n".join(b for b in [base, full_block, chapter_block, context_block] if b)


def _last_assistant_message(messages: list[dict]) -> dict | None:
    """Extract the last assistant reply from chat history."""
    for message in reversed(messages or []):
        if not isinstance(message, dict):
            continue
        if message.get("role") == "assistant":
            content = str(message.get("content", "")).strip()
            if content:
                return {"role": "assistant", "content": content}
    return None


def _last_user_messages(messages: list[dict], count: int = 2) -> list[dict]:
    """Extract the last N user messages from chat history, most recent last."""
    result = []
    for message in reversed(messages or []):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        content = str(message.get("content", "")).strip()
        if content:
            result.insert(0, {"role": "user", "content": content})
            if len(result) >= count:
                break
    return result


def _extract_chat_only(assistant_content: str) -> str:
    """Extract only the chat part (Part 1) from an assistant reply, dropping outline tags.

    Returns empty string if no chat part found (e.g. format was completely broken).
    The chat part is everything before the first <outline> tag.
    """
    raw = assistant_content or ""
    lowered = raw.lower()
    outline_start = lowered.find("<outline>")
    if outline_start >= 0:
        chat = raw[:outline_start].strip()
        return chat
    # No <outline> tag — the response was probably malformed. Return a short excerpt.
    return raw[:300]


def _latest_user_message(messages: list[dict]) -> dict | None:
    """Keep only the latest user input for Bot1."""
    for message in reversed(messages or []):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        content = str(message.get("content", "")).strip()
        if content:
            return {"role": "user", "content": content}
    return None


def _extract_tag_blocks(text: str, tag: str) -> list[str]:
    pattern = rf"<{tag}>\s*([\s\S]*?)\s*</{tag}>"
    return [match.strip() for match in re.findall(pattern, text or "", flags=re.IGNORECASE)]


def _looks_like_placeholder(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text or "").strip()
    if not normalized:
        return True
    if normalized in PLACEHOLDER_OUTLINE_TEXTS:
        return True
    if normalized.strip("#：:") in PLACEHOLDER_OUTLINE_TEXTS:
        return True
    if len(normalized) < 80 and any(item in normalized for item in SHORT_PLACEHOLDER_MARKERS):
        return True
    return False


def _allows_outline_shrink(req: Bot1ChatRequest) -> bool:
    latest_user = _latest_user_message(req.messages)
    content = latest_user["content"] if latest_user else ""
    return any(keyword in content for keyword in SHRINK_ALLOWED_KEYWORDS)


def _validate_outline_block(
    *,
    tag: str,
    content: str,
    existing: str,
    shrink_allowed: bool,
) -> list[str]:
    issues: list[str] = []
    if _looks_like_placeholder(content):
        issues.append(f"<{tag}> 标签块内容不可用")
        return issues

    existing = (existing or "").strip()
    if existing and not shrink_allowed:
        existing_len = len(existing)
        content_len = len(content.strip())
        if existing_len >= 240 and content_len < max(120, int(existing_len * 0.45)):
            issues.append(f"<{tag}> 比当前已保存大纲明显变短，疑似丢失内容")
    return issues


def _validate_bot1_response(text: str, req: Bot1ChatRequest, mode: Literal["chapter", "outline"] = "chapter") -> list[str]:
    issues: list[str] = []
    raw = text or ""
    lowered = raw.lower()
    shrink_allowed = _allows_outline_shrink(req)

    outline_start = lowered.find("<outline>")
    outline_end = lowered.find("</outline>")
    chat_part = raw[:outline_start].strip() if outline_start >= 0 else ""
    if not chat_part:
        issues.append("缺少第一部分用户聊天正文")

    required_tags = REQUIRED_OUTLINE_ONLY_TAGS if mode == "outline" else REQUIRED_OUTLINE_TAGS

    for tag in required_tags:
        blocks = _extract_tag_blocks(raw, tag)
        if not blocks:
            issues.append(f"缺少 <{tag}>...</{tag}> 标签块")
            continue
        if len(blocks) > 1:
            issues.append(f"<{tag}> 标签块重复")
        existing = req.current_outline if tag == "outline" else req.chapter_outline
        issues.extend(
            _validate_outline_block(
                tag=tag,
                content=blocks[0],
                existing=existing or "",
                shrink_allowed=shrink_allowed,
            )
        )

    if mode == "outline":
        chapter_blocks = _extract_tag_blocks(raw, "chapter_outline")
        if chapter_blocks:
            issues.append("总纲模式不得输出 <chapter_outline>")
        if outline_end >= 0:
            trailing = raw[outline_end + len("</outline>") :].strip()
            if trailing:
                issues.append("总纲模式下 <outline> 后不得有额外文字")
        return issues

    chapter_start = lowered.find("<chapter_outline>")
    chapter_end = lowered.find("</chapter_outline>")

    if outline_start >= 0 and chapter_start >= 0 and outline_start > chapter_start:
        issues.append("<outline> 必须出现在 <chapter_outline> 之前")
    if chapter_start >= 0 and outline_start >= 0:
        between = raw[outline_start:chapter_start]
        if "</outline>" not in between.lower():
            issues.append("<outline> 必须完整闭合后再输出 <chapter_outline>")
    if outline_end >= 0 and chapter_start >= 0 and outline_end < chapter_start:
        between_parts = raw[outline_end + len("</outline>") : chapter_start].strip()
        if between_parts:
            issues.append("第二部分和第三部分之间不得有额外文字")
    if chapter_end >= 0:
        trailing = raw[chapter_end + len("</chapter_outline>") :].strip()
        if trailing:
            issues.append("第三部分章节大纲后不得有额外文字")

    return issues


def _build_retry_messages(
    messages: list[dict],
    bad_response: str,
    issues: list[str],
    req: Bot1ChatRequest,
    *,
    tag_only: bool = False,
    mode: Literal["chapter", "outline"] = "chapter",
) -> list[dict]:
    """Build a compact retry prompt that preserves the previous round's content.

    Key insight: users typically only tweak what was generated in the last round.
    The content/ideas are usually good — only the format needs fixing. So we:
      - Keep a condensed version of the failed response as an assistant message
        (so the model can reference its own good ideas)
      - Use a clean, short system prompt (retry instruction + current outline state)
      - Only ask the model to fix format, not rethink everything
    """
    strict_instruction = (
        BOT1_OUTLINE_MINIMAL_RETRY if tag_only else BOT1_OUTLINE_STRICT_FORMAT_RETRY
    ) if mode == "outline" else (
        BOT1_MINIMAL_THREE_PART_RETRY if tag_only else BOT1_STRICT_FORMAT_RETRY
    )
    issue_text = "；".join(issues) if issues else "tag format incomplete"

    # Build a clean system prompt: format instructions + current outline state
    system_parts = [strict_instruction]

    full_outline = (req.current_outline or "").strip()
    chapter_outline = (req.chapter_outline or "").strip()

    if full_outline:
        if len(full_outline) > 3000:
            full_outline = full_outline[:1500] + "\n\n...\n\n" + full_outline[-1500:]
        system_parts.append(f"【Current Full Outline】\n{full_outline}")

    if chapter_outline:
        if len(chapter_outline) > 2000:
            chapter_outline = chapter_outline[:2000]
        system_parts.append(f"【Current Chapter Outline】\n{chapter_outline}")

    system_msg = {"role": "system", "content": "\n\n".join(system_parts)}

    # Build retry messages: include the previous response content for continuity
    retry_messages = [system_msg]

    # Preserve the failed response's content — model can reference its own good ideas
    # and only needs to fix the format. Truncate to save context budget.
    if bad_response and not tag_only:
        previous = bad_response.strip()
        if len(previous) > 2500:
            # Keep start (chat part + outline structure) and end (chapter outline tail)
            previous = previous[:1500] + "\n\n... [middle section truncated] ...\n\n" + previous[-1000:]
        retry_messages.append({
            "role": "assistant",
            "content": (
                f"The following was my previous attempt. The CONTENT and ideas are valid — "
                f"only the FORMAT needs correction. Use this as a content reference:\n\n{previous}"
            ),
        })

    retry_user_content = (
        f"Last response failed format validation: {issue_text}.\n"
        "Please fix ONLY the format issues listed above and output again.\n"
        "PRESERVE all the good content and ideas — do not rethink or rewrite from scratch."
    )
    retry_messages.append({"role": "user", "content": retry_user_content})
    return retry_messages


def _sse_json(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_bot1_with_format_guard(
    messages: list[dict],
    req: Bot1ChatRequest,
    *,
    mode: Literal["chapter", "outline"] = "chapter",
):
    active_messages = messages
    last_issues: list[str] = []

    for attempt in range(BOT1_FORMAT_RETRY_LIMIT + 1):
        chunks: list[str] = []
        async for chunk in stream_llm(req.config.bot1, active_messages):
            chunks.append(chunk)
            yield _sse_json({"content": chunk})

        response = "".join(chunks)
        issues = _validate_bot1_response(response, req, mode=mode)
        if not issues:
            return

        last_issues = issues
        if attempt < BOT1_FORMAT_RETRY_LIMIT:
            yield _sse_json(
                {
                    "reset": True,
                    "reason": "Bot1 format validation failed — auto-retrying with stricter instructions",
                }
            )
            active_messages = _build_retry_messages(
                messages,
                response,
                issues,
                req,
                tag_only=attempt == BOT1_FORMAT_RETRY_LIMIT - 1,
                mode=mode,
            )

    raise Exception("Bot1 retries exhausted — still failed format validation: " + "；".join(last_issues))


@router.post("/models")
async def fetch_models(workspace: str, req: FetchModelsRequest):
    """获取可用模型列表"""
    base_url = req.base_url.rstrip("/")
    url = f"{base_url}/models"
    headers = {"Authorization": f"Bearer {req.api_key}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        return JSONResponse(status_code=500, content={"error": "请求超时，请检查API地址"})
    except httpx.ConnectError:
        return JSONResponse(status_code=500, content={"error": "无法连接到API服务器，请检查地址"})
    except httpx.RequestError as e:
        return JSONResponse(status_code=500, content={"error": f"网络请求失败: {str(e)[:200]}"})

    if resp.status_code != 200:
        return JSONResponse(status_code=500, content={"error": f"API返回HTTP {resp.status_code}"})

    try:
        raw = resp.text
        if not raw or not raw.strip():
            return JSONResponse(status_code=500, content={"error": "API返回空内容"})
        data = json.loads(raw)
        models = sorted([m["id"] for m in data.get("data", [])])
        return {"models": models}
    except json.JSONDecodeError:
        return JSONResponse(status_code=500, content={"error": f"返回的不是有效JSON: {resp.text[:200]}"})


def _build_bot1_messages(req: Bot1ChatRequest, mode: Literal["chapter", "outline"] = "chapter") -> list[dict]:
    # Message order: system -> previous assistant chat -> previous user -> latest user
    # This lets the AI see the conversation flow: what was asked, how it replied, what's asked now.
    # The outline state in the system prompt reflects what the previous round should have updated.
    system_msg = {"role": "system", "content": _build_bot1_system(req, mode=mode)}
    messages = [system_msg]

    last_assistant = _last_assistant_message(req.messages)
    if last_assistant:
        chat_only = _extract_chat_only(last_assistant["content"])
        if chat_only:
            if len(chat_only) > 800:
                chat_only = chat_only[:800]
            messages.append({"role": "assistant", "content": chat_only})

    recent_users = _last_user_messages(req.messages, count=2)
    messages.extend(recent_users)
    return messages


@router.post("/bot1/chat")
async def bot1_chat(workspace: str, req: Bot1ChatRequest):
    messages = _build_bot1_messages(req, mode="chapter")

    async def generate():
        try:
            async for event in _stream_bot1_with_format_guard(messages, req, mode="chapter"):
                yield event
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/bot1/outline-chat")
async def bot1_outline_chat(workspace: str, req: OutlineChatRequest):
    outline_req = Bot1ChatRequest(
        messages=req.messages,
        config=req.config,
        current_outline=req.current_outline,
        chapter_outline="",
        context=req.context,
    )

    messages = _build_bot1_messages(outline_req, mode="outline")

    async def generate():
        try:
            async for event in _stream_bot1_with_format_guard(messages, outline_req, mode="outline"):
                yield event
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
