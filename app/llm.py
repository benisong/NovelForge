"""LLM 调用封装 (OpenAI兼容API)"""

import json
import httpx

from .config import API_TIMEOUT
from .models import BotConfig


async def stream_llm(config: BotConfig, messages: list[dict]):
    """异步流式调用LLM，不重试，3分钟超时"""
    base_url = config.base_url.rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": True,
    }

    has_content = False
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise Exception(f"API返回HTTP {resp.status_code}: {body.decode()[:300]}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                has_content = True
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
    except httpx.TimeoutException:
        raise Exception("API请求超时(3分钟)，请检查网络后重试")
    except httpx.ConnectError:
        raise Exception("无法连接到API服务器，请检查API地址和网络")
    except httpx.RequestError as e:
        raise Exception(f"网络请求失败: {type(e).__name__}")

    if not has_content:
        raise Exception("API返回空内容，可能是模型无响应或请求被拒绝")


async def call_llm_full(config: BotConfig, messages: list[dict]) -> str:
    """非流式完整调用，不重试，3分钟超时"""
    base_url = config.base_url.rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        raise Exception("API请求超时(3分钟)，请检查网络后重试")
    except httpx.ConnectError:
        raise Exception("无法连接到API服务器，请检查API地址和网络")
    except httpx.RequestError as e:
        raise Exception(f"网络请求失败: {type(e).__name__}")

    if resp.status_code != 200:
        raise Exception(f"API返回HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise Exception(f"API响应格式异常: {str(e)}")

    if not content or not content.strip():
        raise Exception("API返回空内容，可能是模型无响应或请求被拒绝")

    return content
