"""Bot4 Memory Manager: condensed + abstract + big-summarize + compress (per-workspace)"""

import json
from fastapi import APIRouter, Depends
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
from ..workspace import require_workspace

router = APIRouter(
    prefix="/api/w/{workspace}",
    dependencies=[Depends(require_workspace)],
)


async def _stream_with_retry(config, messages, max_retries=2):
    """Stream LLM chunks with automatic retry on transient failure."""
    last_error = None
    for attempt in range(max_retries):
        try:
            async for chunk in stream_llm(config, messages):
                yield chunk
            return
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                messages = messages + [{"role": "user", "content": "Previous attempt failed. Please try again."}]
    raise last_error


# ---------- Condensed version (Bot4 main model) ----------

@router.post("/bot4/summarize")
async def bot4_summarize(workspace: str, req: Bot4SummarizeRequest):
    """Generate condensed version of a chapter."""
    messages = [{"role": "system", "content": BOT4_CONDENSED_SYSTEM}]
    prompt = ""
    if req.previous_summary:
        prompt += f"【前情记忆】\n{req.previous_summary}\n\n"
    if req.outline:
        prompt += f"【本章大纲】\n{req.outline}\n\n"
    prompt += f"【本章正文】\n{req.content}"
    prompt += "\n\n请将上述正文压缩为缩略版原文。"
    messages.append({"role": "user", "content": prompt})

    async def generate():
        try:
            async for chunk in _stream_with_retry(req.config.bot4, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------- Abstract (Bot4 cheap model) ----------

@router.post("/bot4/abstract")
async def bot4_abstract(workspace: str, req: Bot4AbstractRequest):
    """Generate structured abstract from condensed text (falls back to full content)."""
    # Reuse bot4 base_url and api_key, but model may differ
    bot4_cfg = req.config.bot4
    if req.abstract_model:
        abstract_cfg = BotConfig(
            base_url=bot4_cfg.base_url,
            api_key=bot4_cfg.api_key,
            model=req.abstract_model,
            temperature=0.3,
            max_tokens=16384,
        )
    else:
        abstract_cfg = bot4_cfg

    messages = [
        {"role": "system", "content": BOT4_ABSTRACT_SYSTEM},
        {"role": "user", "content": f"请为以下章节内容生成结构化摘要：\n\n{req.condensed or req.content}"},
    ]

    async def generate():
        try:
            async for chunk in _stream_with_retry(abstract_cfg, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------- Big summary ----------

@router.post("/bot4/big-summarize")
async def bot4_big_summarize(workspace: str, req: BigSummarizeRequest):
    """Aggregate multiple chapter summaries into global memory."""
    total = len(req.summaries)
    if total == 0:
        async def _empty():
            yield f"data: {json.dumps({'error': 'summaries is empty'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    parts = []
    for i, s in enumerate(req.summaries):
        ch = s.get("chapter", i + 1)
        # First abstract_count chapters use abstract, remaining condensed_count use condensed
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
            async for chunk in _stream_with_retry(req.config.bot4, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------- Memory compression ----------

@router.post("/compress-summary")
async def compress_summary(workspace: str, req: CompressSummaryRequest):
    messages = [
        {"role": "system", "content": COMPRESS_SYSTEM},
        {"role": "user", "content": (
            f"请将以下多章累积的故事记忆压缩为精简版（控制在{req.max_chars}字以内）：\n\n"
            f"{req.summary}"
        )}
    ]

    async def generate():
        try:
            async for chunk in _stream_with_retry(req.config.bot4, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
