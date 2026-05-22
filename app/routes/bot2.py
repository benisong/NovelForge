"""Bot2 writing + rewriting routes (per-workspace)."""

import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..models import Bot2WriteRequest, Bot2RewriteRequest
from ..prompts import BOT2_SYSTEM
from ..styles import _get_effective_style
from ..llm import stream_llm
from ..workspace import require_workspace

router = APIRouter(
    prefix="/api/w/{workspace}",
    dependencies=[Depends(require_workspace)],
)


def _build_bot2_system(workspace: str, style_id: str = "", word_count: int = 800,
                       tips: str = "", prev_ending: str = "",
                       bot2_context: str = "") -> str:
    """Build Bot2 system prompt with attention-priority ordering.

    Items the model needs MOST while writing go LAST (recency bias in attention):
      1. BOT2_SYSTEM      — role + anti-slop rules (anchors identity at start)
      2. bot2_context     — global memory + recent chapter summaries (background)
      3. style + example  — style reference and tone calibration
      4. tips             — accumulated review feedback to avoid
      5. prev_ending      — last chapter's ending (continuity anchor, keep close)
      6. word_count       — target length (last thing the model sees before writing)
    """
    parts = [BOT2_SYSTEM]

    if bot2_context and bot2_context.strip():
        parts.append(bot2_context.strip())

    style = _get_effective_style(workspace, style_id)
    if style:
        style_parts = [f"【Style Requirement: {style['name']}】"]
        if style.get("desc"):
            style_parts.append(style["desc"])
        if style.get("instruction"):
            style_parts.append(f"The following rules MUST be prioritized:\n{style['instruction']}")
        if style.get("example"):
            style_parts.append(
                "Below is a reference excerpt for this style. Internalize its language, "
                "narrative rhythm, and syntactic density — absorb naturally, do NOT copy verbatim:\n\n"
                f"---\n{style['example']}\n---"
            )
        parts.append("\n\n".join(style_parts))

    if tips and tips.strip():
        parts.append(
            f"【Accumulated Review Feedback (avoid these issues)】\n{tips.strip()}"
        )

    if prev_ending and prev_ending.strip():
        parts.append(
            f"【Previous Chapter Ending (maintain style and narrative continuity)】\n"
            f"---\n{prev_ending.strip()}\n---"
        )

    parts.append(
        f"【Word Count】\nTarget approximately {word_count} Chinese characters. "
        f"Control length appropriately — neither too sparse nor padded with filler."
    )

    return "\n\n".join(parts)


def _build_outline_block(outline: str, chapter_outline: str) -> str:
    """Build the outline section for the user prompt.

    Full outline (stable) goes first; chapter outline (changes per chapter) goes last
    for recency attention bias.
    """
    parts = []
    if outline:
        parts.append(f"【Full Outline】\n{outline}")
    if chapter_outline:
        parts.append(f"【Chapter Detailed Outline】\n{chapter_outline}")
    if not parts:
        parts.append(f"【Chapter Outline】\n{outline}")
    return "\n\n".join(parts)


@router.post("/bot2/write")
async def bot2_write(workspace: str, req: Bot2WriteRequest):
    system_prompt = _build_bot2_system(
        workspace, req.style_id, req.word_count, req.tips, req.prev_ending, req.bot2_context
    )
    # User prompt: full outline → chapter outline (most critical goes last for attention bias)
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
    # User prompt ordering: stable → variable → most-important-instruction
    #   outline (stable within chapter) → draft (changes per round) → feedback (changes per round, critical) → execution instruction (last)
    outline_text = _build_outline_block(req.outline, req.chapter_outline)
    user_prompt = (
        f"{outline_text}\n\n"
        f"【Current Draft】\n{req.content}\n\n"
        f"【Review Feedback & Targeted Fixes Needed】\n{req.suggestions}\n\n"
        f"IMPORTANT: This is a TARGETED revision, not a full rewrite.\n\n"
        f"Rules:\n"
        f"1. For each issue in the feedback, locate the specific sentence or paragraph "
        f"and rewrite ONLY that part. If the feedback says \"第3段, problem: X\", "
        f"fix ONLY paragraph 3 — leave paragraphs 1, 2, 4, 5 untouched.\n"
        f"2. Keep ALL text that was not flagged by the feedback EXACTLY as-is. "
        f"Do not \"improve\" or rephrase passages that already passed review.\n"
        f"3. If the feedback contains [User Supplemental Suggestions (HIGHEST PRIORITY)], "
        f"those take precedence over Bot3 suggestions when there is a conflict.\n"
        f"4. Internally make a checklist: which locations need changes? Apply only "
        f"those changes. Do NOT output the checklist.\n"
        f"5. Every fix must be a VISIBLE change at the flagged location: rewrite, "
        f"delete, reorder, or expand the targeted passage. Do NOT just swap synonyms.\n"
        f"6. Before outputting, verify: all flagged locations have been addressed. "
        f"All un-flagged text remains unchanged. User suggestions prioritized.\n\n"
        f"The ideal output is 90%+ identical to the input draft — only the "
        f"problem areas should differ.\n\n"
        f"Output the complete revised novel text directly. Target ~{req.word_count} Chinese characters."
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
