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

BOT1_STRICT_FORMAT_RETRY = """## Bot1 输出格式重试指令（最高优先级）

你上一次回复没有通过程序校验。现在重新输出一版完整回复。

必须严格满足：
1. 只允许出现一组 <outline>...</outline> 和一组 <chapter_outline>...</chapter_outline>
2. 先输出 <outline>，再输出 <chapter_outline>
3. 两个标签都必须闭合，标签名必须完全一致
4. 标签内必须是完整可用的大纲，不得写“同上”“略”“保持不变”
5. 不要使用 JSON、代码围栏、markdown 表格，不要解释格式错误
6. 输出前自行复查标签完整性，复查过程不要写出来

若上一次回复中已有可用设定，可以吸收；若标签缺失，请根据当前总大纲、当前章节大纲、摘要记忆和用户最新输入补齐。"""

BOT1_TAG_ONLY_RETRY = """## Bot1 标签补救指令（最终兜底，最高优先级）

现在不要再输出解释、寒暄、分析正文。
只返回两个完整标签块：

<outline>
完整总大纲
</outline>

<chapter_outline>
完整当前章节大纲
</chapter_outline>

标签外不得写任何文字。标签名必须完全一致，且两个标签都必须闭合。"""


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


def _validate_bot1_response(text: str) -> list[str]:
    issues: list[str] = []
    raw = text or ""

    for tag in REQUIRED_OUTLINE_TAGS:
        blocks = _extract_tag_blocks(raw, tag)
        if not blocks:
            issues.append(f"缺少 <{tag}>...</{tag}> 标签块")
            continue
        if len(blocks) > 1:
            issues.append(f"<{tag}> 标签块重复")
        if not blocks[0].strip():
            issues.append(f"<{tag}> 标签块内容为空")
        if blocks[0].strip() in {"同上", "略", "保持不变"}:
            issues.append(f"<{tag}> 标签块内容不可用")

    outline_start = raw.lower().find("<outline>")
    chapter_start = raw.lower().find("<chapter_outline>")
    if outline_start >= 0 and chapter_start >= 0 and outline_start > chapter_start:
        issues.append("<outline> 必须出现在 <chapter_outline> 之前")

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
    strict_instruction = BOT1_TAG_ONLY_RETRY if tag_only else BOT1_STRICT_FORMAT_RETRY
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
            "只返回 <outline>...</outline> 与 <chapter_outline>...</chapter_outline> 两个标签块。"
        )
    else:
        retry_user_content = (
            f"上一版未通过格式校验：{issue_text}。\n"
            "请重新生成完整 Bot1 回复，必须包含可解析、闭合且内容完整的 "
            "<outline>...</outline> 与 <chapter_outline>...</chapter_outline>。"
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
        issues = _validate_bot1_response(response)
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
