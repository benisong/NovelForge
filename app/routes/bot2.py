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
                       bot2_context: str = "", rewrite_packet: dict | None = None,
                       is_rewrite: bool = False) -> str:
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

    if is_rewrite:
        packet = rewrite_packet or {}
        rewrite_mode = str(packet.get("rewrite_mode") or "system").strip() or "system"
        instruction_priority = str(packet.get("instruction_priority") or "system_only").strip() or "system_only"
        freedom_policy = str(packet.get("freedom_policy") or "medium").strip() or "medium"
        user_instruction = str(packet.get("user_review_instruction") or "").strip()
        system_review_brief = str(packet.get("system_review_brief") or "").strip()

        parts.append(
            "【Rewrite Mode】\n"
            + {
                "system": "This revision is driven by the system review only.",
                "hybrid": "This revision is user-led, with system review used only as supporting brief.",
                "custom": "This revision is fully user-directed. Execute the user's rewrite goal directly.",
                "full_rewrite": "This revision is a full chapter rewrite driven by the system brief.",
                "full_rewrite_hybrid": "This revision is a user-led full chapter rewrite, with system review used only as supporting brief.",
            }.get(rewrite_mode, "This revision is driven by the current rewrite packet.")
        )

        parts.append(
            "【Freedom Policy】\n"
            + {
                "high": "High freedom: you may reorganize local scene execution, enrich transitions, and expand details as needed, but stay faithful to the chapter goal.",
                "medium": "Medium freedom: you may restructure local passages and repair pacing / logic, but do not rewrite the whole chapter or change the chapter objective.",
                "low": "Low freedom: only change targeted problem locations, keep all healthy passages as stable as possible, and do not add new scenes or broad restructuring.",
                "bypass": "Bypass default freedom constraints: execute the explicit user rewrite goal first, but still remain faithful to chapter intent, continuity, and confirmed story direction.",
            }.get(freedom_policy, "Follow the provided freedom policy conservatively.")
        )

        parts.append(
            "【Instruction Priority】\n"
            + (
                "User instructions are highest priority. If user instructions conflict with system review, follow the user instruction and treat system review only as supplemental reference."
                if instruction_priority == "user_over_system"
                else "Follow system review guidance as the controlling rewrite instruction."
            )
        )

        if user_instruction:
            parts.append(f"【User Self-Review Instruction】\n{user_instruction}")
        if system_review_brief:
            parts.append(f"【System Review Brief】\n{system_review_brief}")

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


def _build_rewrite_user_prompt(req: Bot2RewriteRequest) -> str:
    """Build mode-aware rewrite prompt for Bot2."""
    packet = req.rewrite_packet or {}
    rewrite_mode = str(packet.get("rewrite_mode") or "system").strip() or "system"
    freedom_policy = str(packet.get("freedom_policy") or "medium").strip() or "medium"
    user_instruction = str(packet.get("user_review_instruction") or "").strip()
    system_review_brief = str(packet.get("system_review_brief") or "").strip()
    instruction_priority = str(packet.get("instruction_priority") or "system_only").strip() or "system_only"

    outline_text = _build_outline_block(req.outline, req.chapter_outline)
    sections = [
        outline_text,
        f"【Current Draft】\n{req.content}",
    ]

    if rewrite_mode == "custom":
        if user_instruction:
            sections.append(f"【User Rewrite Goal】\n{user_instruction}")
        sections.append(
            "【Execution Contract】\n"
            "This is a user-directed rewrite. Use the user's instruction as the direct task.\n"
            "You may rewrite any part that is necessary to fulfill that goal.\n"
            "Do not import or obey system review items that are not included in the current task packet.\n"
            "Preserve confirmed story direction, continuity, and chapter intent unless the user explicitly asks to change them.\n"
            "Output the complete revised novel text directly."
        )
        return "\n\n".join(sections)

    if rewrite_mode == "full_rewrite":
        if system_review_brief:
            sections.append(f"【Rewrite Brief】\n{system_review_brief}")
        elif req.suggestions.strip():
            sections.append(f"【Rewrite Brief】\n{req.suggestions.strip()}")
        sections.append(
            "【Execution Contract】\n"
            "This is a full chapter rewrite driven by the current system brief.\n"
            "Do not preserve the old draft sentence-by-sentence. Rebuild the whole chapter around the current chapter objective.\n"
            "You may redesign scene execution, transitions, pacing, and detail distribution as needed.\n"
            "Stay faithful to continuity, chapter intent, and confirmed story direction.\n"
            "Output the complete rewritten novel text directly."
        )
        return "\n\n".join(sections)

    if rewrite_mode == "full_rewrite_hybrid":
        if system_review_brief:
            sections.append(f"【Rewrite Brief】\n{system_review_brief}")
        elif req.suggestions.strip():
            sections.append(f"【Rewrite Brief】\n{req.suggestions.strip()}")
        if user_instruction:
            sections.append(f"【User Rewrite Goal (Highest Priority)】\n{user_instruction}")
        sections.append(
            "【Execution Contract】\n"
            "This is a user-led full chapter rewrite.\n"
            "User instructions are highest priority; system review is only a supporting brief.\n"
            "Do not preserve the old draft sentence-by-sentence. Rebuild the chapter according to the user's goal and the current chapter objective.\n"
            "You may redesign scene execution, pacing, and structure as needed, while preserving continuity and confirmed story direction.\n"
            "Output the complete rewritten novel text directly."
        )
        return "\n\n".join(sections)

    if system_review_brief:
        sections.append(f"【Rewrite Brief】\n{system_review_brief}")
    elif req.suggestions.strip():
        sections.append(f"【Rewrite Brief】\n{req.suggestions.strip()}")

    if rewrite_mode == "hybrid" and user_instruction:
        sections.append(f"【User Rewrite Goal (Highest Priority)】\n{user_instruction}")

    if rewrite_mode == "system":
        sections.append(
            "【Execution Contract】\n"
            "This is a targeted revision driven by the system review.\n"
            "Locate the flagged problem passages and revise only those locations.\n"
            "Keep healthy passages as stable as possible. Do not rewrite the whole chapter.\n"
            "Each flagged issue must receive a visible fix, not just synonym swapping.\n"
            "Before outputting, verify that all flagged issues were addressed.\n"
            "Output the complete revised novel text directly."
        )
    else:
        freedom_line = {
            "high": "Because current freedom is high, you may reorganize local execution, transitions, and detail density when needed.",
            "medium": "Because current freedom is medium, you may adjust local pacing and structure, but keep the chapter objective stable.",
            "low": "Because current freedom is low, prefer narrow, localized fixes unless broader adjustment is clearly required by the user goal.",
            "bypass": "Execute the user goal directly while remaining faithful to continuity and chapter intent.",
        }.get(freedom_policy, "Follow the provided freedom policy conservatively.")
        priority_line = (
            "User instructions are highest priority; system review is only a supporting brief."
            if instruction_priority == "user_over_system"
            else "Follow the current rewrite brief as the controlling instruction."
        )
        sections.append(
            "【Execution Contract】\n"
            "This rewrite is user-led with optional system support.\n"
            f"{priority_line}\n"
            f"{freedom_line}\n"
            "You may revise beyond a single sentence when needed, but do not drift away from the chapter's confirmed direction.\n"
            "System review should be compressed into guidance, not copied as a checklist.\n"
            "Output the complete revised novel text directly."
        )

    return "\n\n".join(sections)


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
        workspace, req.style_id, req.word_count, req.tips, req.prev_ending, req.bot2_context,
        req.rewrite_packet, True
    )
    user_prompt = _build_rewrite_user_prompt(req)
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
