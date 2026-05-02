"""Pydantic 请求模型"""

from typing import Optional
from pydantic import BaseModel


class BotConfig(BaseModel):
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 16384


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
    current_outline: Optional[str] = ""
    chapter_outline: Optional[str] = ""
    context: Optional[str] = ""


class Bot2WriteRequest(BaseModel):
    outline: str
    chapter_outline: Optional[str] = ""
    config: ProjectConfig
    style_id: Optional[str] = ""
    word_count: Optional[int] = 800
    tips: Optional[str] = ""
    prev_ending: Optional[str] = ""
    bot2_context: Optional[str] = ""   # 大总结+condensed


class Bot2RewriteRequest(BaseModel):
    outline: str
    chapter_outline: Optional[str] = ""
    content: str
    suggestions: str
    config: ProjectConfig
    style_id: Optional[str] = ""
    word_count: Optional[int] = 800
    tips: Optional[str] = ""
    prev_ending: Optional[str] = ""
    bot2_context: Optional[str] = ""   # 大总结+condensed


class Bot3ReviewRequest(BaseModel):
    content: str
    outline: str
    config: ProjectConfig
    style_id: Optional[str] = ""
    custom_prompt: Optional[str] = ""
    previous_suggestions: Optional[str] = ""
    review_attempt: Optional[int] = 1


class Bot4SummarizeRequest(BaseModel):
    content: str
    config: ProjectConfig
    previous_summary: Optional[str] = ""
    outline: Optional[str] = ""


class CompressSummaryRequest(BaseModel):
    """改进6: 超长记忆二次压缩"""
    summary: str
    config: ProjectConfig
    max_chars: Optional[int] = 800


class Bot4AbstractRequest(BaseModel):
    """用廉价模型生成摘要，优先用原文，回退用缩略版"""
    condensed: str = ""
    content: str = ""  # 原文，优先使用
    config: ProjectConfig
    abstract_model: str = ""  # 摘要模型名，空则用bot4主模型


class BigSummarizeRequest(BaseModel):
    """大总结：汇总多个小总结"""
    summaries: list[dict]  # [{chapter, condensed, abstract}]
    config: ProjectConfig
    abstract_count: int = 5   # 前N章用摘要
    condensed_count: int = 5  # 后N章用缩略原文


class BotConfigEntry(BaseModel):
    """单个配置条目（一组Bot1-4的配置）"""
    id: str
    name: str
    bot1: dict
    bot2: dict
    bot3: dict
    bot4: dict
    pass_score: float = 8.0
    max_retries: int = 3


class SaveConfigRequest(BaseModel):
    configs: list[dict]


class SaveProjectRequest(BaseModel):
    project_id: str
    name: str
    chapters: list[dict]
    chat_history: list[dict]
    current_outline: str = ""
    chapter_outline: str = ""
    current_summary: str = ""
    current_content: str = ""
    style_id: str = ""
    word_count: int = 800
    reviews: list[dict] = []
    logs: list[dict] = []
    pipeline_state: Optional[dict] = None
    active_tab: str = ""
    accumulated_tips: list[str] = []
    last_rewrite_suggestions: str = ""
    small_summaries: list[dict] = []   # [{chapter, condensed, abstract, time}]
    big_summaries: list[dict] = []     # [{fromChapter, toChapter, content, time}]
    # 章节边界标记：chat_history 中的下标，<= 此值的消息属于已完成章节，
    # 不应该再用来回填 chapter_outline。Bot4 完成时设为 chat_history.length。
    chapter_boundary_idx: int = 0
