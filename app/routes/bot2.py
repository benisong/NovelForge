"""Bot2 创作/重写（per-workspace）"""

import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..models import Bot2WriteRequest, Bot2RewriteRequest
from ..prompts import BOT2_SYSTEM
from ..styles import _get_style_by_id
from ..llm import stream_llm
from ..workspace import require_workspace

router = APIRouter(
    prefix="/api/w/{workspace}",
    dependencies=[Depends(require_workspace)],
)


def _build_bot2_system(workspace: str, style_id: str = "", word_count: int = 800,
                       tips: str = "", prev_ending: str = "",
                       bot2_context: str = "") -> str:
    """构建 Bot2 系统提示词

    注意力优先的拼接顺序——越"创作当下需要记住"的越靠后：

      1. BOT2_SYSTEM      角色设定（开头锚定身份）
      2. bot2_context     全局记忆+近期章节缩略（提供前情背景）
      3. style + example  文风定调与参考
      4. tips             累积避坑经验
      5. prev_ending      上一章结尾（衔接用，创作每一句都要记得，放靠后）
      6. word_count       字数约束（最末尾，user 消息之前的最后一眼）
    """
    parts = [BOT2_SYSTEM]

    if bot2_context and bot2_context.strip():
        parts.append(bot2_context.strip())

    style = _get_style_by_id(workspace, style_id)
    if style:
        parts.append(
            f"【文风要求：{style['name']}】\n{style.get('desc', '')}\n\n"
            f"以下是该文风的参考示例片段，请深度学习其语言风格、叙事节奏、遣词造句的特点，"
            f"并在创作中自然运用（不要生搬硬套，要融会贯通）：\n\n"
            f"---\n{style['example']}\n---"
        )

    if tips and tips.strip():
        parts.append(
            f"【历史审核经验（请注意避免以下问题）】\n{tips.strip()}"
        )

    if prev_ending and prev_ending.strip():
        parts.append(
            f"【上一章结尾片段（请保持文风衔接和叙事连贯）】\n"
            f"---\n{prev_ending.strip()}\n---"
        )

    parts.append(
        f"【字数要求】\n本章内容目标字数约{word_count}字（中文）。"
        f"请合理控制篇幅，既不要过于简略也不要无意义地灌水凑字数。"
    )

    return "\n\n".join(parts)


def _build_outline_block(outline: str, chapter_outline: str) -> str:
    """组装大纲块。总大纲相对稳定放前，章节大纲每章变放后。"""
    parts = []
    if outline:
        parts.append(f"【总大纲】\n{outline}")
    if chapter_outline:
        parts.append(f"【本章详细大纲】\n{chapter_outline}")
    if not parts:
        parts.append(f"【本章大纲】\n{outline}")
    return "\n\n".join(parts)


@router.post("/bot2/write")
async def bot2_write(workspace: str, req: Bot2WriteRequest):
    system_prompt = _build_bot2_system(
        workspace, req.style_id, req.word_count, req.tips, req.prev_ending, req.bot2_context
    )
    # user：总大纲 → 本章详细大纲（把创作当下最关键的章节大纲放末尾高注意力位）
    user_prompt = _build_outline_block(req.outline, req.chapter_outline)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot2, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/bot2/rewrite")
async def bot2_rewrite(workspace: str, req: Bot2RewriteRequest):
    system_prompt = _build_bot2_system(
        workspace, req.style_id, req.word_count, req.tips, req.prev_ending, req.bot2_context
    )
    # user：按 稳定→可变→重要指令 排列
    #   大纲（本章内稳定）→ 当前正文（每轮变）→ 审核建议（每轮变、最重要）→ 执行指令（末尾）
    outline_text = _build_outline_block(req.outline, req.chapter_outline)
    user_prompt = (
        f"{outline_text}\n\n"
        f"【当前小说正文】\n{req.content}\n\n"
        f"【审核反馈和修改建议】\n{req.suggestions}\n\n"
        f"请参考大纲方向，严格按照上述审核建议对当前正文进行针对性修改。"
        f"保留原文的优点和整体结构，只改进建议中指出的具体问题。"
        f"直接输出修改后的完整小说正文，目标字数约{req.word_count}字。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot2, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
