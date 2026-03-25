"""
小说创作助手 - 四Bot协作系统 v2.4
Backend: FastAPI + httpx (OpenAI兼容API)
改进: 数据持久化(JSON文件), 跨Bot信息增强, 记忆压缩, Docker部署支持
"""

import json
import re
import asyncio
import os
import time
import shutil
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
import httpx

app = FastAPI(title="小说创作助手 v2.4")

API_TIMEOUT = 180.0  # 3分钟超时

# ============================================================
# 持久化目录
# ============================================================
DATA_DIR = Path(os.environ.get("NOVEL_DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

STYLES_FILE = DATA_DIR / "writing_styles.json"
PRESET_STYLES_FILE = Path(__file__).parent / "preset_styles.json"

def _load_preset_styles() -> list:
    """加载根目录下的预设文风（只读）"""
    if PRESET_STYLES_FILE.exists():
        data = json.loads(PRESET_STYLES_FILE.read_text(encoding="utf-8"))
        return data.get("styles", [])
    return []

def _load_styles() -> dict:
    """加载文风配置：预设文风 + 用户自定义文风"""
    presets = _load_preset_styles()
    if STYLES_FILE.exists():
        user_data = json.loads(STYLES_FILE.read_text(encoding="utf-8"))
    else:
        user_data = {"styles": [], "default_word_count": 800}
    # 预设在前，用户自定义在后，去重（用户同ID覆盖预设）
    user_ids = {s["id"] for s in user_data.get("styles", [])}
    merged = [p for p in presets if p["id"] not in user_ids] + user_data.get("styles", [])
    return {"styles": merged, "default_word_count": user_data.get("default_word_count", 800)}

def _get_style_by_id(style_id: str) -> Optional[dict]:
    """根据ID获取文风"""
    if not style_id:
        return None
    data = _load_styles()
    for s in data.get("styles", []):
        if s["id"] == style_id:
            return s
    return None

# ============================================================
# 数据模型
# ============================================================

class BotConfig(BaseModel):
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096

class ProjectConfig(BaseModel):
    bot1: BotConfig
    bot2: BotConfig
    bot3: BotConfig
    bot4: BotConfig
    pass_score: float = 8.0
    max_retries: int = 3

class FetchModelsRequest(BaseModel):
    base_url: str
    api_key: str

class Bot1ChatRequest(BaseModel):
    messages: list[dict]
    config: ProjectConfig
    context: Optional[str] = ""

class Bot2WriteRequest(BaseModel):
    outline: str
    config: ProjectConfig
    style_id: Optional[str] = ""       # 文风ID
    word_count: Optional[int] = 800    # 目标字数
    tips: Optional[str] = ""           # 改进4: 历史审核经验
    prev_ending: Optional[str] = ""    # 改进5: 上一章结尾片段

class Bot2RewriteRequest(BaseModel):
    outline: str              # 大纲（保留，供Bot2参考方向）
    content: str              # 当前小说正文（Bot3传回的）
    suggestions: str          # Bot3的修改建议
    config: ProjectConfig
    style_id: Optional[str] = ""
    word_count: Optional[int] = 800
    tips: Optional[str] = ""
    prev_ending: Optional[str] = ""

class Bot3ReviewRequest(BaseModel):
    content: str
    outline: str
    config: ProjectConfig
    style_id: Optional[str] = ""       # 改进1: 文风信息供审核参考
    custom_prompt: Optional[str] = ""  # 用户自定义审核提示词（覆盖默认BOT3_SYSTEM）

class Bot4SummarizeRequest(BaseModel):
    content: str
    config: ProjectConfig
    previous_summary: Optional[str] = ""
    outline: Optional[str] = ""        # 改进2: 大纲辅助伏笔追踪

class CompressSummaryRequest(BaseModel):
    """改进6: 超长记忆二次压缩"""
    summary: str
    config: ProjectConfig
    max_chars: Optional[int] = 800

# ============================================================
# Bot提示词
# ============================================================

BOT1_SYSTEM = """你是一位资深的小说策划编辑（Bot1 - 大纲策划师）。

你的工作方式：
1. 与用户进行多轮对话，深入了解他们的创作意图、风格偏好、人物设定和故事方向
2. 在每次回复中，你既要正常回应用户的问题和想法，又要根据当前讨论生成或更新大纲
3. 你可以主动提问来补充细节，也可以给出建设性建议

**关键规则：你的每次回复都必须包含一个用 <outline> 和 </outline> 标签包裹的完整大纲。**

大纲内容应包含（根据讨论进度逐步丰富）：
- 章节主题和核心冲突
- 场景描述（时间、地点、氛围）
- 人物出场和互动关系
- 情节推进节点（起承转合）
- 情感基调和节奏控制
- 悬念或伏笔设置

回复格式示例：
---
你的分析和回应正文...（可以讨论、提问、建议）

<outline>
# 第X章 章节标题

## 核心冲突
...

## 场景设计
...

## 人物安排
...

## 情节节点
1. 开场：...
2. 发展：...
3. 转折：...
4. 高潮：...
5. 收尾/悬念：...

## 情感基调
...
</outline>
---

大纲会随着对话不断完善，每次都输出最新的完整版本。"""

BOT2_SYSTEM = """你是一位才华横溢的小说作家（Bot2 - 内容创作师）。你的职责是：
1. 根据提供的大纲，创作高质量的小说内容
2. 注重以下方面：
   - 生动的场景描写和氛围营造
   - 立体的人物刻画和对话
   - 流畅的情节推进
   - 恰当的叙事节奏
   - 细腻的情感表达
   - 独特的文学风格
3. 确保内容与大纲方向一致，同时发挥创作自由度

请直接输出小说正文内容，不要添加额外说明。"""

BOT3_SYSTEM = """你是一位严格而专业的文学评审（Bot3 - 质量审核师）。你的职责是从多个维度对小说内容进行深度审核。

## 审核维度（每项1-10分）

1. 文学性(literary)：语言是否优美流畅，修辞手法是否恰当，文学表现力如何，叙事技巧是否成熟
2. 逻辑性(logic)：情节发展是否合理，因果关系是否自洽，有无逻辑漏洞或前后矛盾
3. 风格一致性(style)：是否与大纲/上下文的风格基调一致，人物语言是否符合角色设定，叙事视角是否统一
4. 人味(ai_feel)：内容读起来是否自然真实，像真人写的。分数越高越好，表示AI痕迹越少。扣分项：模板化开头结尾、过于工整的排比对仗、不自然的情感升华、堆砌辞藻、过度完美缺乏瑕疵感

## 输出格式（严格按标签输出，不要添加任何其他内容）

<scores>
literary=分数
logic=分数
style=分数
ai_feel=分数
</scores>

<analysis>综合评价，2-3句话概括</analysis>

<item>
dim=维度key
severity=high或medium或low
location=问题位置
problem=问题描述
suggestion=修改建议
</item>

<item>
dim=维度key
severity=high或medium或low
location=问题位置
problem=问题描述
suggestion=修改建议
</item>

（可以有多个item标签，每个代表一条建议）

## severity说明
- high: 必须修改
- medium: 建议修改
- low: 可选修改

## 注意
- 至少给出3条item建议，未通过时应给出5条以上
- 即使审核通过，也应指出可以进一步改进的地方（severity为low）
- 严格只输出上述标签格式，不要输出JSON，不要添加其他说明文字"""

BOT4_SYSTEM = """你是一位经验丰富的小说编辑（Bot4 - 记忆管理师）。你的职责是：
1. 对通过审核的章节内容进行精炼总结
2. 提取并记录以下关键信息：
   - **情节摘要**：本章主要发生了什么
   - **人物状态**：各角色的当前状态、情感变化、关系变化
   - **世界观更新**：新出现的设定、地点、物品等
   - **伏笔追踪**：已埋下的伏笔和已回收的伏笔
   - **时间线**：故事时间的推进情况
3. 这份总结将作为后续章节创作的上下文记忆，确保小说的连贯性

请以结构化的格式输出总结内容。"""

# ============================================================
# OpenAI兼容API调用 - 不自动重试，失败直接报错
# ============================================================

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

# ============================================================
# API端点
# ============================================================

@app.post("/api/models")
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


# ---------- Bot1: 多轮对话 ----------

@app.post("/api/bot1/chat")
async def bot1_chat(req: Bot1ChatRequest):
    system_msg = {"role": "system", "content": BOT1_SYSTEM}
    if req.context:
        system_msg["content"] += f"\n\n【之前章节的故事记忆】\n{req.context}"
    messages = [system_msg] + req.messages

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot1, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------- 文风配置 API ----------

@app.get("/api/styles")
async def get_styles():
    """获取所有文风列表"""
    return _load_styles()

@app.post("/api/styles")
async def save_styles(data: dict):
    """保存文风配置（含自定义文风）"""
    STYLES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}

@app.get("/api/styles/{style_id}")
async def get_style(style_id: str):
    """获取单个文风详情"""
    style = _get_style_by_id(style_id)
    if not style:
        raise HTTPException(status_code=404, detail="文风不存在")
    return style


# ---------- Bot3 自定义提示词 API ----------

BOT3_PROMPTS_FILE = DATA_DIR / "bot3_prompts.json"

def _load_bot3_prompts() -> list[dict]:
    if BOT3_PROMPTS_FILE.exists():
        try:
            return json.loads(BOT3_PROMPTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_bot3_prompts(prompts: list[dict]):
    BOT3_PROMPTS_FILE.write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")

@app.get("/api/bot3-prompts")
async def get_bot3_prompts():
    """获取所有Bot3自定义提示词 + 默认提示词"""
    return {"prompts": _load_bot3_prompts(), "default_prompt": BOT3_SYSTEM}

@app.post("/api/bot3-prompts")
async def save_bot3_prompts(data: dict):
    """保存Bot3自定义提示词列表"""
    _save_bot3_prompts(data.get("prompts", []))
    return {"ok": True}


# ---------- Bot2: 创作 ----------

def _build_bot2_system(style_id: str = "", word_count: int = 800,
                       tips: str = "", prev_ending: str = "") -> str:
    """根据文风、字数、历史经验、上章结尾构建Bot2系统提示词"""
    base = BOT2_SYSTEM

    # 字数要求
    word_part = f"\n\n【字数要求】\n本章内容目标字数约{word_count}字（中文）。请合理控制篇幅，既不要过于简略也不要无意义地灌水凑字数。"
    base += word_part

    # 文风示例
    style = _get_style_by_id(style_id)
    if style:
        base += f"\n\n【文风要求：{style['name']}】\n{style.get('desc', '')}\n\n以下是该文风的参考示例片段，请深度学习其语言风格、叙事节奏、遣词造句的特点，并在创作中自然运用（不要生搬硬套，要融会贯通）：\n\n---\n{style['example']}\n---"

    # 改进4: 历史审核经验（错题本）
    if tips and tips.strip():
        base += f"\n\n【历史审核经验（请注意避免以下问题）】\n{tips.strip()}"

    # 改进5: 上一章结尾片段（保持文风衔接）
    if prev_ending and prev_ending.strip():
        base += f"\n\n【上一章结尾片段（请保持文风衔接和叙事连贯）】\n---\n{prev_ending.strip()}\n---"

    return base

@app.post("/api/bot2/write")
async def bot2_write(req: Bot2WriteRequest):
    system_prompt = _build_bot2_system(req.style_id, req.word_count, req.tips, req.prev_ending)
    messages = [{"role": "system", "content": system_prompt}]
    prompt = f"【本章大纲】\n{req.outline}"
    messages.append({"role": "user", "content": prompt})

    async def generate():
        try:
            async for chunk in stream_llm(req.config.bot2, messages):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)[:500]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/bot2/rewrite")
async def bot2_rewrite(req: Bot2RewriteRequest):
    system_prompt = _build_bot2_system(req.style_id, req.word_count, req.tips, req.prev_ending)
    messages = [{"role": "system", "content": system_prompt}]
    # 优化：重写时发大纲+原文+修改建议，不发上下文/历史，减少token和注意力分散
    prompt = f"""【本章大纲】
{req.outline}

【当前小说正文】
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


# ---------- Bot3: 审核 ----------

@app.post("/api/bot3/review")
async def bot3_review(req: Bot3ReviewRequest):
    # 如果用户设置了自定义审核提示词，使用自定义的，否则使用默认
    system_prompt = req.custom_prompt.strip() if req.custom_prompt and req.custom_prompt.strip() else BOT3_SYSTEM
    messages = [{"role": "system", "content": system_prompt}]
    # 改进1: 将文风信息注入Bot3审核提示词
    style_hint = ""
    style = _get_style_by_id(req.style_id) if req.style_id else None
    if style:
        style_hint = (
            f"\n\n【目标文风：{style['name']}】\n"
            f"风格描述：{style.get('desc', '')}\n"
            f"参考示例片段：\n---\n{style['example']}\n---\n"
            f"请在「风格一致性」维度重点评判内容是否贴合上述文风要求。\n"
        )
    import time, random
    # 添加时间戳和随机数，防止API缓存导致重复审核结果相同
    cache_breaker = f"[审核请求 #{int(time.time())}-{random.randint(1000,9999)}]"
    messages.append({"role": "user", "content": (
        f"{cache_breaker}\n"
        f"【大纲要求】\n{req.outline}\n\n"
        f"【待审核的小说内容】\n{req.content}\n\n"
        f"及格分数线：{req.config.pass_score}分"
        f"{style_hint}\n\n请进行评审。"
    )})

    try:
        result = await call_llm_full(req.config.bot3, messages)
    except Exception as e:
        return {"error": str(e)[:500], "retry_hint": True}

    import logging
    logging.info(f"[Bot3 原始回复] ({len(result)}字):\n{result[:1000]}")

    review = _parse_bot3_tags(result, req.config.pass_score)
    # 始终附带原始回复片段，前端可用于调试
    review["_raw_preview"] = result[:800]
    return review


def _parse_bot3_tags(result: str, pass_score: float) -> dict:
    """从标签格式解析Bot3审核结果，含JSON兼容降级"""
    import re

    # 中文key到英文key的映射
    _KEY_MAP = {
        "文学性": "literary", "literary": "literary",
        "逻辑性": "logic", "logic": "logic",
        "风格一致性": "style", "风格": "style", "style": "style",
        "人味": "ai_feel", "ai_feel": "ai_feel", "人味感": "ai_feel",
        "维度": "dim", "dim": "dim",
        "严重程度": "severity", "severity": "severity",
        "位置": "location", "location": "location",
        "问题": "problem", "problem": "problem",
        "建议": "suggestion", "suggestion": "suggestion",
        "修改建议": "suggestion",
    }
    dim_keys = ["literary", "logic", "style", "ai_feel"]

    def _parse_kv_line(line: str) -> tuple:
        """解析一行kv，支持 = : ： 分隔符"""
        line = line.strip().lstrip('-').lstrip('*').strip()
        if not line:
            return None, None
        # 尝试 = : ： 三种分隔符
        for sep in ['=', ':', '：']:
            if sep in line:
                k, v = line.split(sep, 1)
                k = k.strip().lower()
                v = v.strip()
                # 映射中文key
                mapped = _KEY_MAP.get(k, k)
                return mapped, v
        return None, None

    scores = {}
    analysis = ""
    items = []

    # ---- 1. 尝试标签格式 ----
    scores_m = re.search(r'<scores>(.*?)</scores>', result, re.DOTALL)
    if scores_m:
        for line in scores_m.group(1).strip().splitlines():
            k, v = _parse_kv_line(line)
            if k and k in dim_keys:
                # 提取数字部分（AI可能写 "8分" 或 "8/10"）
                num_m = re.match(r'(\d+(?:\.\d+)?)', v)
                if num_m:
                    scores[k] = float(num_m.group(1))

    analysis_m = re.search(r'<analysis>(.*?)</analysis>', result, re.DOTALL)
    if analysis_m:
        analysis = analysis_m.group(1).strip()

    for item_m in re.finditer(r'<item>(.*?)</item>', result, re.DOTALL):
        item = {}
        for line in item_m.group(1).strip().splitlines():
            k, v = _parse_kv_line(line)
            if k and v:
                item[k] = v
        if item.get('dim') or item.get('suggestion') or item.get('problem'):
            items.append({
                "dim": item.get("dim", "literary"),
                "severity": item.get("severity", "medium"),
                "location": item.get("location", ""),
                "problem": item.get("problem", ""),
                "suggestion": item.get("suggestion", ""),
            })

    # ---- 2. 标签未提取到分数时，降级尝试JSON ----
    if len([k for k in dim_keys if k in scores]) < 4:
        json_str = result
        try:
            if "```json" in result:
                json_str = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                json_str = result.split("```")[1].split("```")[0]
            else:
                fb = result.find("{")
                lb = result.rfind("}")
                if fb != -1 and lb > fb:
                    json_str = result[fb:lb + 1]
            parsed = json.loads(json_str.strip())
            if isinstance(parsed.get("scores"), dict):
                raw_scores = parsed["scores"]
                for rk, rv in raw_scores.items():
                    mapped = _KEY_MAP.get(rk.strip().lower(), rk.strip().lower())
                    if mapped in dim_keys:
                        scores[mapped] = float(rv) if not isinstance(rv, (int, float)) else rv
            if parsed.get("analysis"):
                analysis = str(parsed["analysis"])
            if isinstance(parsed.get("items"), list):
                for it in parsed["items"]:
                    if isinstance(it, dict):
                        items.append({
                            "dim": _KEY_MAP.get(str(it.get("dim", "literary")).lower(), it.get("dim", "literary")),
                            "severity": it.get("severity", "medium"),
                            "location": it.get("location", ""),
                            "problem": it.get("problem", ""),
                            "suggestion": it.get("suggestion", ""),
                        })
            elif parsed.get("suggestions"):
                items = [{"dim": "literary", "severity": "medium", "location": "全文",
                          "problem": "综合建议", "suggestion": str(parsed["suggestions"])}]
        except (json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError):
            pass

    # ---- 3. 最后手段：正则逐个提取分数（支持中英文key和多种分隔符）----
    if len([k for k in dim_keys if k in scores]) < 4:
        _regex_patterns = {
            "literary": r'(?:literary|文学性)\s*[=:：]\s*(\d+(?:\.\d+)?)',
            "logic": r'(?:logic|逻辑性)\s*[=:：]\s*(\d+(?:\.\d+)?)',
            "style": r'(?:style|风格一致性|风格)\s*[=:：]\s*(\d+(?:\.\d+)?)',
            "ai_feel": r'(?:ai_feel|人味|人味感)\s*[=:：]\s*(\d+(?:\.\d+)?)',
        }
        for key, pattern in _regex_patterns.items():
            if key not in scores:
                m = re.search(pattern, result, re.IGNORECASE)
                if m:
                    scores[key] = float(m.group(1))

    # ---- 4. 如果 analysis 仍为空，尝试从非标签文本提取 ----
    if not analysis:
        # 去掉所有标签内容，剩下的可能是综合评价
        cleaned = re.sub(r'<\w+>.*?</\w+>', '', result, flags=re.DOTALL).strip()
        lines = [l.strip() for l in cleaned.splitlines() if l.strip() and len(l.strip()) > 10]
        if lines:
            analysis = lines[0][:200]

    # ---- 5. 构建最终结果 ----
    if len([k for k in dim_keys if k in scores]) >= 4:
        vals = [scores.get(k, 0) for k in dim_keys]
        real_avg = round(sum(vals) / 4, 1)
        if not items:
            items = [{"dim": "literary", "severity": "low", "location": "全文",
                      "problem": "未提取到逐条建议", "suggestion": "请点击重新审计获取详细建议"}]
        return {
            "scores": {k: scores.get(k, 0) for k in dim_keys},
            "average": real_avg,
            "passed": real_avg >= pass_score,
            "analysis": analysis or "（审核完成）",
            "items": items,
        }

    # 完全解析失败
    return {
        "scores": {"literary": 0, "logic": 0, "style": 0, "ai_feel": 0},
        "average": 0, "passed": False,
        "analysis": "审核结果解析失败",
        "items": [{"dim": "literary", "severity": "high", "location": "全文",
                    "problem": "无法解析审核结果", "suggestion": f"原始回复：{result[:500]}"}],
        "retry_hint": True,
    }


# ---------- Bot4: 总结 ----------

@app.post("/api/bot4/summarize")
async def bot4_summarize(req: Bot4SummarizeRequest):
    messages = [{"role": "system", "content": BOT4_SYSTEM}]
    prompt = ""
    if req.previous_summary:
        prompt += f"【之前的故事总结/记忆】\n{req.previous_summary}\n\n"
    # 改进2: 传入大纲辅助伏笔追踪
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

# ============================================================
# 持久化 API - Bot配置（API密钥/地址/模型）
# ============================================================

CONFIG_FILE = DATA_DIR / "_bot_configs.json"

class BotConfigEntry(BaseModel):
    """单个配置条目（一组Bot1-4的配置）"""
    id: str
    name: str
    bot1: dict  # {base_url, api_key, model}
    bot2: dict
    bot3: dict
    bot4: dict
    pass_score: float = 8.0
    max_retries: int = 3

class SaveConfigRequest(BaseModel):
    configs: list[dict]

def _read_configs() -> list[dict]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _write_configs(configs: list[dict]):
    CONFIG_FILE.write_text(json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")

@app.get("/api/configs")
async def get_configs():
    """获取所有已保存的Bot配置"""
    return {"configs": _read_configs()}

@app.post("/api/configs")
async def save_configs(req: SaveConfigRequest):
    """保存全部Bot配置列表"""
    _write_configs(req.configs)
    return {"ok": True}

@app.delete("/api/configs/{config_id}")
async def delete_config(config_id: str):
    """删除某个配置"""
    configs = _read_configs()
    configs = [c for c in configs if c.get("id") != config_id]
    _write_configs(configs)
    return {"ok": True}

# ============================================================
# 持久化 API - 项目/章节/对话 的 增删改查
# ============================================================

class SaveProjectRequest(BaseModel):
    project_id: str
    name: str
    chapters: list[dict]        # [{outline, content, summary}]
    chat_history: list[dict]    # [{role, content}]
    current_outline: str = ""
    current_summary: str = ""
    current_content: str = ""
    reviews: list[dict] = []    # [{review, attempt, time}]
    logs: list[dict] = []       # [{bot, msg, time}]
    pipeline_state: Optional[dict] = None  # 中断的Pipeline状态，用于恢复
    active_tab: str = ""        # 当前激活的Tab页
    accumulated_tips: list[str] = []  # 改进4: 累积的审核经验

def _project_path(pid: str) -> Path:
    safe = re.sub(r'[^\w\-]', '_', pid)
    return DATA_DIR / f"{safe}.json"

@app.get("/api/projects")
async def list_projects():
    """列出所有已保存的项目"""
    projects = []
    for f in sorted(DATA_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            projects.append({
                "id": data.get("project_id", f.stem),
                "name": data.get("name", f.stem),
                "chapters": len(data.get("chapters", [])),
                "updated": data.get("updated", ""),
            })
        except Exception:
            continue
    return {"projects": projects}

@app.post("/api/projects/save")
async def save_project(req: SaveProjectRequest):
    """保存/更新一个项目"""
    data = req.model_dump()
    data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path = _project_path(req.project_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(path)}

@app.get("/api/projects/{project_id}")
async def load_project(project_id: str):
    """加载一个项目"""
    path = _project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "项目不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """删除一个项目"""
    path = _project_path(project_id)
    if path.exists():
        path.unlink()
    return {"ok": True}

@app.post("/api/projects/{project_id}/export")
async def export_project(project_id: str):
    """导出项目为纯文本（所有章节合并）"""
    path = _project_path(project_id)
    if not path.exists():
        raise HTTPException(404, "项目不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = [f"# {data.get('name', project_id)}\n"]
    for i, ch in enumerate(data.get("chapters", []), 1):
        lines.append(f"\n## 第{i}章\n")
        lines.append(ch.get("content", ""))
        lines.append("")
    text = "\n".join(lines)
    return {"text": text, "word_count": len(text)}

# ---------- 改进6: 记忆压缩 ----------

COMPRESS_SYSTEM = """你是一位精准的文本压缩专家。你的任务是将多章小说的累积记忆总结压缩为精简版。

要求：
1. 保留所有核心人物关系和当前状态
2. 保留所有未回收的伏笔和重要悬念
3. 保留关键事件节点和时间线
4. 删除细节描写、重复信息和已回收的伏笔
5. 使用精炼的语言，控制在指定字数以内
6. 保持结构化格式，便于后续Bot理解"""

@app.post("/api/compress-summary")
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


# ============================================================
# 静态文件 & 首页
# ============================================================

@app.get("/")
async def index():
    import pathlib
    html = pathlib.Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html.read_text(encoding="utf-8"))

@app.get("/favicon.ico")
async def favicon():
    return JSONResponse(content={}, status_code=204)

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
