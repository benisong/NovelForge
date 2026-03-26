"""Bot4 总结系统：小总结（缩略+摘要）+ 大总结 + 记忆压缩"""

import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..models import (
    Bot4SummarizeRequest, Bot4AbstractRequest,
    BigSummarizeRequest, CompressSummaryRequest, BotConfig,
)
from ..prompts import (
    BOT4_CONDENSED_SYSTEM, BOT4_ABSTRACT_SYSTEM,
    BOT4_BIG_SUMMARY_SYSTEM, COMPRESS_SYSTEM,
)
from ..llm import stream_llm

router = APIRouter()


# ---------- 小总结：缩略版原文（Bot4主模型）----------

@router.post("/api/bot4/summarize")
async def bot4_summarize(req: Bot4SummarizeRequest):
    """生成缩略版原文"""
    messages = [{"role": "system", "content": BOT4_CONDENSED_SYSTEM}]
    prompt = ""
    if req.outline:
        prompt += f"【本章大纲】\n{req.outline}\n\n"
    prompt += f"【本章正文】\n{req.content}"
    prompt += "\n\n请将上述正文压缩为缩略版原文。"
    messages.append({"role": "user", "content": prompt})

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot4, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------- 小总结：摘要（Bot4廉价模型）----------

@router.post("/api/bot4/abstract")
async def bot4_abstract(req: Bot4AbstractRequest):
    """从缩略版原文生成结构化摘要"""
    # 复用bot4的base_url和api_key，但model可能不同
    bot4_cfg = req.config.bot4
    if req.abstract_model:
        abstract_cfg = BotConfig(
            base_url=bot4_cfg.base_url,
            api_key=bot4_cfg.api_key,
            model=req.abstract_model,
            temperature=0.3,
            max_tokens=2048,
        )
    else:
        abstract_cfg = bot4_cfg

    messages = [
        {"role": "system", "content": BOT4_ABSTRACT_SYSTEM},
        {"role": "user", "content": f"请为以下章节内容生成结构化摘要：\n\n{req.condensed}"},
    ]

    async def generate():
        try:
            async for chunk in stream_llm(abstract_cfg, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------- 大总结 ----------

@router.post("/api/bot4/big-summarize")
async def bot4_big_summarize(req: BigSummarizeRequest):
    """汇总多个小总结为全局记忆"""
    parts = []
    total = len(req.summaries)
    for i, s in enumerate(req.summaries):
        ch = s.get("chapter", i + 1)
        # 前 abstract_count 章用摘要，后 condensed_count 章用缩略原文
        if i < req.abstract_count:
            content = s.get("abstract", s.get("condensed", ""))
            label = "摘要"
        else:
            content = s.get("condensed", s.get("abstract", ""))
            label = "缩略原文"
        parts.append(f"--- 第{ch}章 ({label}) ---\n{content}")

    combined = "\n\n".join(parts)
    messages = [
        {"role": "system", "content": BOT4_BIG_SUMMARY_SYSTEM},
        {"role": "user", "content": (
            f"以下是第{req.summaries[0].get('chapter',1)}章到"
            f"第{req.summaries[-1].get('chapter',total)}章的分段总结，"
            f"请整合为一份全局记忆：\n\n{combined}"
        )},
    ]

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot4, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------- 记忆压缩（保留）----------

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
