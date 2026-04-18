"""Bot3 审核 + 自定义提示词"""

import json
import re
import uuid
import logging
from fastapi import APIRouter

from ..models import Bot3ReviewRequest
from ..prompts import BOT3_SYSTEM
from ..styles import _get_style_by_id
from ..llm import call_llm_full
from ..config import BOT3_PROMPTS_FILE

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------- Bot3 自定义提示词 ----------

def _load_bot3_prompts() -> list[dict]:
    if BOT3_PROMPTS_FILE.exists():
        try:
            return json.loads(BOT3_PROMPTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_bot3_prompts(prompts: list[dict]):
    BOT3_PROMPTS_FILE.write_text(json.dumps(prompts, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/api/bot3-prompts")
async def get_bot3_prompts():
    """获取所有Bot3自定义提示词 + 默认提示词"""
    return {"prompts": _load_bot3_prompts(), "default_prompt": BOT3_SYSTEM}


@router.post("/api/bot3-prompts")
async def save_bot3_prompts(data: dict):
    """保存Bot3自定义提示词列表"""
    _save_bot3_prompts(data.get("prompts", []))
    return {"ok": True}


# ---------- Bot3 审核 ----------

@router.post("/api/bot3/review")
async def bot3_review(req: Bot3ReviewRequest):
    # system：核心审核规则（最稳）+ 文风评判附加（不切文风就不变）
    # 稳定内容放 system，便于上游 prompt cache 命中 prefix
    base_prompt = req.custom_prompt.strip() if req.custom_prompt and req.custom_prompt.strip() else BOT3_SYSTEM
    system_parts = [base_prompt]
    style = _get_style_by_id(req.style_id) if req.style_id else None
    if style:
        system_parts.append(
            f"【目标文风：{style['name']}】\n"
            f"风格描述：{style.get('desc', '')}\n"
            f"参考示例片段：\n---\n{style['example']}\n---\n"
            f"请在「风格一致性」维度重点评判内容是否贴合上述文风要求。"
        )
    messages = [{"role": "system", "content": "\n\n".join(system_parts)}]

    # user：cache_breaker 在最前（故意让 user 前缀 miss，避免模型缓存返回旧评审），
    #       之后按 稳定→可变→重要指令 排列；执行指令放末尾（高注意力）
    cache_breaker = f"[审核请求 #{uuid.uuid4().hex[:16]}]"
    user_content = (
        f"{cache_breaker}\n\n"
        f"【大纲要求】\n{req.outline}\n\n"
        f"【待审核的小说内容】\n{req.content}\n\n"
        f"及格分数线：{req.config.pass_score}分\n\n"
        f"请严格按系统提示词中的标签格式输出评审结果，不要输出 JSON，不要添加其他说明文字。"
    )
    messages.append({"role": "user", "content": user_content})

    try:
        result = await call_llm_full(req.config.bot3, messages)
    except Exception as e:
        return {"error": str(e)[:500], "retry_hint": True}

    logger.info("[Bot3] 回复长度 %d 字", len(result))
    logger.debug("[Bot3 原始回复预览]\n%s", result[:1000])

    review = _parse_bot3_tags(result, req.config.pass_score)
    review["_raw_preview"] = result[:800]
    return review


def _parse_bot3_tags(result: str, pass_score: float) -> dict:
    """从标签格式解析Bot3审核结果，含JSON兼容降级"""

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
        for sep in ['=', ':', '：']:
            if sep in line:
                k, v = line.split(sep, 1)
                k = k.strip().lower()
                v = v.strip()
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

    # ---- 3. 最后手段：正则逐个提取分数 ----
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

    # ---- 4. analysis 为空时从非标签文本提取 ----
    if not analysis:
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
