"""Bot2 创作/重写"""

import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..models import Bot2WriteRequest, Bot2RewriteRequest
from ..prompts import BOT2_SYSTEM
from ..styles import _get_style_by_id
from ..llm import stream_llm

router = APIRouter()


def _build_bot2_system(style_id: str = "", word_count: int = 800,
                       tips: str = "", prev_ending: str = "",
                       bot2_context: str = "") -> str:
    """根据文风、字数、历史经验、上章结尾、上下文构建Bot2系统提示词

    按注意力分布排列：
    [开头-高注意力] 角色设定 + 大总结/condensed上下文
    [中间-低注意力] 文风、历史经验、上章结尾等辅助信息
    [末尾-高注意力] 字数要求（user message里会放大纲）
    """
    base = BOT2_SYSTEM

    # 开头：大总结 + condensed 上下文（高注意力位置）
    if bot2_context and bot2_context.strip():
        base += f"\n\n{bot2_context.strip()}"

    # 中间：文风、历史经验、上章结尾
    style = _get_style_by_id(style_id)
    if style:
        base += f"\n\n【文风要求：{style['name']}】\n{style.get('desc', '')}\n\n以下是该文风的参考示例片段，请深度学习其语言风格、叙事节奏、遣词造句的特点，并在创作中自然运用（不要生搬硬套，要融会贯通）：\n\n---\n{style['example']}\n---"

    if tips and tips.strip():
        base += f"\n\n【历史审核经验（请注意避免以下问题）】\n{tips.strip()}"

    if prev_ending and prev_ending.strip():
        base += f"\n\n【上一章结尾片段（请保持文风衔接和叙事连贯）】\n---\n{prev_ending.strip()}\n---"

    # 末尾：字数要求
    word_part = f"\n\n【字数要求】\n本章内容目标字数约{word_count}字（中文）。请合理控制篇幅，既不要过于简略也不要无意义地灌水凑字数。"
    base += word_part

    return base


@router.post("/api/bot2/write")
async def bot2_write(req: Bot2WriteRequest):
    system_prompt = _build_bot2_system(req.style_id, req.word_count, req.tips, req.prev_ending, req.bot2_context)
    messages = [{"role": "system", "content": system_prompt}]
    # 末尾放大纲（高注意力位置）
    outline_parts = []
    if req.outline:
        outline_parts.append(f"【总大纲】\n{req.outline}")
    if req.chapter_outline:
        outline_parts.append(f"【本章详细大纲】\n{req.chapter_outline}")
    prompt = "\n\n".join(outline_parts) if outline_parts else f"【本章大纲】\n{req.outline}"
    messages.append({"role": "user", "content": prompt})

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot2, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/bot2/rewrite")
async def bot2_rewrite(req: Bot2RewriteRequest):
    system_prompt = _build_bot2_system(req.style_id, req.word_count, req.tips, req.prev_ending, req.bot2_context)
    messages = [{"role": "system", "content": system_prompt}]
    # 组装大纲部分
    outline_text = ""
    if req.outline:
        outline_text += f"【总大纲】\n{req.outline}\n\n"
    if req.chapter_outline:
        outline_text += f"【本章详细大纲】\n{req.chapter_outline}\n\n"
    if not outline_text:
        outline_text = f"【本章大纲】\n{req.outline}\n\n"
    prompt = f"""{outline_text}【当前小说正文】
{req.content}

【审核反馈和修改建议】
{req.suggestions}

请参考大纲方向，严格按照审核建议对正文进行针对性修改。保留原文的优点和整体结构，只改进建议中指出的具体问题。直接输出修改后的完整小说正文，目标字数约{req.word_count}字。"""
    messages.append({"role": "user", "content": prompt})

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot2, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
