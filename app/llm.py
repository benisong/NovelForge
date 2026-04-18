"""LLM 调用封装 (OpenAI兼容API)"""

import json
import logging

import httpx

from .config import API_TIMEOUT
from .models import BotConfig

logger = logging.getLogger(__name__)


def _upstream_error_message(status_code: int, body: str) -> str:
    """对上游返回生成面向用户的错误信息，同时把详情写入日志。"""
    logger.warning("上游 API 错误 HTTP %s: %s", status_code, body[:500])
    if status_code == 401:
        return "API 鉴权失败（HTTP 401），请检查 API Key"
    if status_code == 403:
        return "API 拒绝访问（HTTP 403），请检查密钥权限"
    if status_code == 404:
        return "API 路径不存在（HTTP 404），请检查 base_url 与 model"
    if status_code == 429:
        return "API 请求过于频繁（HTTP 429），稍后重试"
    if 500 <= status_code < 600:
        return f"上游服务不可用（HTTP {status_code}），请稍后重试"
    return f"API 返回错误 HTTP {status_code}"


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
                    body = (await resp.aread()).decode(errors="replace")
                    raise Exception(_upstream_error_message(resp.status_code, body))
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
        logger.warning("网络请求失败: %s", e)
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
        logger.warning("网络请求失败: %s", e)
        raise Exception(f"网络请求失败: {type(e).__name__}")

    if resp.status_code != 200:
        raise Exception(_upstream_error_message(resp.status_code, resp.text))

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.warning("API 响应格式异常: %s", e)
        raise Exception("API 响应格式异常")

    if not content or not content.strip():
        raise Exception("API返回空内容，可能是模型无响应或请求被拒绝")

    return content
