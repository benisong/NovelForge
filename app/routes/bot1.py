"""Bot1 对话 + 模型获取"""

import json
import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from ..models import Bot1ChatRequest, FetchModelsRequest
from ..prompts import BOT1_SYSTEM
from ..llm import stream_llm

router = APIRouter()


@router.post("/api/models")
async def fetch_models(req: FetchModelsRequest):
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


@router.post("/api/bot1/chat")
async def bot1_chat(req: Bot1ChatRequest):
    # 按注意力分布组装：开头放大总结+摘要（高注意力），末尾是用户消息（高注意力）
    system_content = BOT1_SYSTEM
    if req.context:
        system_content = f"{BOT1_SYSTEM}\n\n{req.context}"
    system_msg = {"role": "system", "content": system_content}
    messages = [system_msg] + req.messages

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot1, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
