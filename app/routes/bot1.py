"""Bot1 对话 + 模型获取（per-workspace）"""

import re
import json
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse, JSONResponse

from ..models import Bot1ChatRequest, FetchModelsRequest
from ..prompts import BOT1_SYSTEM
from ..llm import stream_llm
from ..workspace import require_workspace

router = APIRouter(
    prefix="/api/w/{workspace}",
    dependencies=[Depends(require_workspace)],
)

REQUIRED_OUTLINE_TAGS = ("outline", "chapter_outline")
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

BOT1_STRICT_FORMAT_RETRY = """## Bot1 输出格式重试指令（最高优先级）

你上一次回复没有通过程序校验。现在重新输出一版完整回复。

必须严格满足三部分顺序：
1. 第一部分：和用户聊天，肯定想法、指出误区或给出建议。不要加标签。
2. 第二部分：<outline>...</outline>，完整全文大纲（总）。
3. 第三部分：<chapter_outline>...</chapter_outline>，完整章节大纲。

标签要求：
- 只允许出现一组 <outline>...</outline> 和一组 <chapter_outline>...</chapter_outline>
- 先输出第一部分聊天，再输出 <outline>，最后输出 <chapter_outline>
- 两个标签都必须闭合，标签名必须完全一致
- 标签内必须是完整可用的大纲，不得写“同上”“略”“保持不变”或占位话
- 如果大纲不需要改，就完整照抄当前已有大纲，不得概括、删减或丢失设定
- 不要使用 JSON、代码围栏、markdown 表格，不要解释格式错误
- 输出前自行复查标签完整性，复查过程不要写出来

若上一次回复中已有可用设定，可以吸收；若标签缺失，请根据当前总大纲、当前章节大纲、摘要记忆和用户最新输入补齐。"""

BOT1_MINIMAL_THREE_PART_RETRY = """## Bot1 三段式补救指令（最终兜底，最高优先级）

现在只返回三部分，不要输出解释格式错误的话。

第一部分：一句话回复用户，肯定想法、指出误区或给出建议。

<outline>
完整全文大纲（总）；若无需修改，完整照抄当前总大纲
</outline>

<chapter_outline>
完整章节大纲；若无需修改，完整照抄当前章节大纲
</chapter_outline>

标签名必须完全一致，两个标签都必须闭合，标签内不得写占位话。"""


def _build_bot1_system(req: Bot1ChatRequest) -> str:
    """Assemble Bot1 context in a fixed order."""
    parts = [BOT1_SYSTEM]

    if req.current_outline and req.current_outline.strip():
        parts.append(f"【当前总大纲】\n{req.current_outline.strip()}")

    if req.chapter_outline and req.chapter_outline.strip():
        parts.append(f"【当前章节大纲】\n{req.chapter_outline.strip()}")

    if req.context and req.context.strip():
        parts.append(req.context.strip())

    return "\n\n".join(parts)


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


def _validate_bot1_response(text: str, req: Bot1ChatRequest) -> list[str]:
    issues: list[str] = []
    raw = text or ""
    lowered = raw.lower()
    shrink_allowed = _allows_outline_shrink(req)

    outline_start = lowered.find("<outline>")
    chapter_start = lowered.find("<chapter_outline>")
    outline_end = lowered.find("</outline>")
    chapter_end = lowered.find("</chapter_outline>")
    chat_part = raw[:outline_start].strip() if outline_start >= 0 else ""
    if not chat_part:
        issues.append("缺少第一部分用户聊天正文")

    for tag in REQUIRED_OUTLINE_TAGS:
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
    *,
    tag_only: bool = False,
) -> list[dict]:
    issue_text = "；".join(issues) if issues else "标签格式不完整"
    previous = (bad_response or "").strip()
    if len(previous) > 6000:
        previous = previous[:6000] + "\n\n[前一次无效回复已截断]"

    retry_messages = [dict(messages[0])]
    strict_instruction = BOT1_MINIMAL_THREE_PART_RETRY if tag_only else BOT1_STRICT_FORMAT_RETRY
    retry_messages[0]["content"] = f"{retry_messages[0]['content']}\n\n{strict_instruction}"

    if len(messages) > 1:
        retry_messages.append(messages[1])

    if previous:
        retry_messages.append(
            {
                "role": "assistant",
                "content": f"以下是未通过格式校验的上一版草稿，仅供修复参考：\n\n{previous}",
            }
        )

    if tag_only:
        retry_user_content = (
            f"上一版未通过格式校验：{issue_text}。\n"
            "请只返回三部分：第一部分一句话回复用户；第二部分 <outline>...</outline>；"
            "第三部分 <chapter_outline>...</chapter_outline>。"
        )
    else:
        retry_user_content = (
            f"上一版未通过格式校验：{issue_text}。\n"
            "请重新生成完整 Bot1 回复，必须按三部分输出：用户聊天、全文大纲、章节大纲；"
            "两个大纲标签必须可解析、闭合且内容完整。"
        )

    retry_messages.append(
        {
            "role": "user",
            "content": retry_user_content,
        }
    )
    return retry_messages


def _sse_json(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_bot1_with_format_guard(messages: list[dict], req: Bot1ChatRequest):
    active_messages = messages
    last_issues: list[str] = []

    for attempt in range(BOT1_FORMAT_RETRY_LIMIT + 1):
        chunks: list[str] = []
        async for chunk in stream_llm(req.config.bot1, active_messages):
            chunks.append(chunk)
            yield _sse_json({"content": chunk})

        response = "".join(chunks)
        issues = _validate_bot1_response(response, req)
        if not issues:
            return

        last_issues = issues
        if attempt < BOT1_FORMAT_RETRY_LIMIT:
            yield _sse_json(
                {
                    "reset": True,
                    "reason": "Bot1 标签格式不完整，正在自动用更严格格式重试",
                }
            )
            active_messages = _build_retry_messages(
                messages,
                response,
                issues,
                tag_only=attempt == BOT1_FORMAT_RETRY_LIMIT - 1,
            )

    raise Exception("Bot1 未按标签格式返回，已自动重试仍失败：" + "；".join(last_issues))


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


@router.post("/bot1/chat")
async def bot1_chat(workspace: str, req: Bot1ChatRequest):
    # Fixed order:
    # system -> current total outline -> current chapter outline -> summaries -> latest user input
    system_msg = {"role": "system", "content": _build_bot1_system(req)}
    messages = [system_msg]
    latest_user = _latest_user_message(req.messages)
    if latest_user:
        messages.append(latest_user)

    async def generate():
        try:
            async for event in _stream_bot1_with_format_guard(messages, req):
                yield event
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
