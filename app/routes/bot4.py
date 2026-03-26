"""Bot4 总结 + 记忆压缩"""

import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..models import Bot4SummarizeRequest, CompressSummaryRequest
from ..prompts import BOT4_SYSTEM, COMPRESS_SYSTEM
from ..llm import stream_llm

router = APIRouter()


@router.post("/api/bot4/summarize")
async def bot4_summarize(req: Bot4SummarizeRequest):
    messages = [{"role": "system", "content": BOT4_SYSTEM}]
    prompt = ""
    if req.previous_summary:
        prompt += f"【之前的故事总结/记忆】\n{req.previous_summary}\n\n"
    if req.outline:
        prompt += f"【本章大纲（作者设计意图）】\n{req.outline}\n\n"
    prompt += f"【本章正文】\n{req.content}"
    prompt += "\n\n请对比大纲与正文进行总结，重点追踪：哪些伏笔已在正文中埋下、哪些大纲设计尚未完全落实，并更新故事记忆。"
    messages.append({"role": "user", "content": prompt})

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot4, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/api/compress-summary")
async def compress_summary(req: CompressSummaryRequest):
    messages = [
        {"role": "system", "content": COMPRESS_SYSTEM},
        {"role": "user", "content": (
            f"请将以下多章累积的故事记忆压缩为精简版（控制在{req.max_chars}字以内）：\n\n"
            f"{req.summary}"
        )}
    ]

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot4, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
