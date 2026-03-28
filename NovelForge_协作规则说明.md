# NovelForge 四Bot协作规则说明

> 版本 v3.0 | 更新于 2026-03-28

---

## 一、系统架构总览

```
用户 ↔ Bot1(策划) → Bot2(创作) ↔ Bot3(审核) → Bot4(记忆) → 回到Bot1
         │                ↑           │              │
         │                └───────────┘              │
         │                 审核不通过时回环            │
         │                                           │
         ├── 多轮对话交互（人工介入点1）               │
         │   审核面板编辑（人工介入点2）               │
         └──────────── 接收Bot4总结，规划下一章 ◄──────┘
```

**后端**：FastAPI（模块化路由） + httpx（调用 OpenAI 兼容 API）
**前端**：HTML + 独立 CSS/JS 文件（10个JS模块），SSE 流式输出
**持久化**：JSON 文件（data/ 目录） + 正式章节 TXT 文件（data/chapters/）

---

## 二、项目文件结构

```
NovelForge/
├── app/                      # 后端核心
│   ├── __init__.py           # FastAPI app 实例
│   ├── config.py             # 全局配置常量
│   ├── llm.py                # LLM 调用封装（流式/完整）
│   ├── models.py             # Pydantic 请求模型
│   ├── prompts.py            # 所有 Bot 的系统提示词
│   ├── styles.py             # 文风加载逻辑
│   └── routes/               # 路由模块
│       ├── bot1.py           # Bot1 大纲策划
│       ├── bot2.py           # Bot2 内容创作
│       ├── bot3.py           # Bot3 质量审核
│       ├── bot4.py           # Bot4 记忆管理（小总结+大总结）
│       ├── configs.py        # Bot配置持久化
│       └── projects.py       # 项目CRUD + 章节文件管理
├── static/
│   ├── index.html            # 主页面
│   ├── style.css             # 全局样式
│   └── js/
│       ├── 01-state.js       # 全局状态 S + 工具函数
│       ├── 02-config.js      # Bot配置管理
│       ├── 03-chat.js        # Bot1对话 + 上下文构建
│       ├── 04-review.js      # Bot3审核面板渲染/编辑
│       ├── 05-bot3prompts.js # Bot3自定义提示词管理
│       ├── 06-styles.js      # 文风系统UI
│       ├── 07-pipeline.js    # Pipeline流水线（Bot2→Bot3→Bot4循环）
│       ├── 08-project.js     # 项目持久化/加载/导出
│       ├── 09-init.js        # 页面初始化
│       └── 10-summary.js     # Bot4总结面板UI
├── data/                     # 数据持久化目录
│   ├── *.json                # 项目存档文件
│   └── chapters/             # 正式章节文件
│       └── {project_id}/     # 每个项目一个子文件夹
│           └── {项目名}_正式_第N章.txt
├── preset_styles.json        # 预设文风（8种）
├── run.py                    # 启动入口
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## 三、四个 Bot 的职责定义

### Bot1 — 大纲策划师
- **角色**：资深小说策划编辑
- **交互方式**：与用户多轮对话（唯一支持多轮对话的 Bot）
- **输出格式**：每次回复包含两个标签：
  - `<outline>...</outline>` — 总大纲（全局故事规划）
  - `<chapter_outline>...</chapter_outline>` — 当前章节大纲（本章详细写作计划）
- **上下文注入**（讨论阶段）：
  - 开头（高注意力）：角色设定 + 大总结
  - 中间（低注意力）：各章摘要（abstract）
  - 末尾（高注意力）：用户消息
- **面板布局**：左侧聊天区 + 右侧三个折叠区（总大纲/章节大纲/创作设置）
- **创作设置**：文风选择 + 目标字数（位于Bot1面板，非Bot2）

### Bot2 — 内容创作师
- **角色**：才华横溢的小说作家
- **交互方式**：无用户直接交互，自动执行
- **上下文注入**（创作阶段）：
  - 开头（高注意力）：角色设定 + 大总结
  - 中间（低注意力）：最近章节缩略原文（condensed）
  - 末尾（高注意力）：总大纲 + 章节大纲 + 文风 + 字数
- **动态提示词**：基础提示词 + 字数要求 + 文风要求（名称/描述/示例片段）
- **接口**：
  - 首次创作：`POST /api/bot2/write`
  - 重写：`POST /api/bot2/rewrite`（附带审核建议）
- **面板功能**：
  - 审计通过后显示**复制按钮**（一键复制正文到剪贴板）
  - 审计通过后自动保存正式章节文件到 `data/chapters/`

### Bot3 — 质量审核师
- **角色**：严格而专业的文学评审
- **交互方式**：无直接交互，但审核结果**可被用户完全编辑**
- **审核维度**（4项，每项 1-10 分）：
  1. **文学性** (literary)：语言表现力、修辞、叙事技巧
  2. **逻辑性** (logic)：情节因果、前后自洽
  3. **风格一致性** (style)：与大纲/上下文风格匹配
  4. **人味** (ai_feel)：是否像人类写作（越高越好）
- **输出格式**：结构化 JSON（scores + items + analysis）
- **审核面板**：按维度分组折叠显示，有建议的维度标红
- **用户可编辑**：分数、每条建议的所有字段、可增删条目
- **支持自定义提示词**：用户可保存多套审核提示词

### Bot4 — 记忆管理师
- **角色**：经验丰富的小说编辑
- **交互方式**：无用户交互，自动执行
- **双输出（小总结）**：每章生成两份内容
  - **缩略版原文**（condensed）：Bot4主模型生成，保留关键对话和场景描写（300-800字）
  - **摘要**（abstract）：Bot4廉价模型生成，结构化信息（人物状态/伏笔/事件节点），基于原文生成
- **大总结**：每N章（用户可配）或手动触发
  - 输入：前M章用摘要 + 后N章用缩略原文（用户可调配比）
  - 输出：全局记忆（世界观/主线/人物状态汇总）
- **面板布局**：左侧详情展示区（可切换缩略/摘要）+ 右上小总结列表 + 右下大总结列表

---

## 四、完整工作流程

### 4.1 单章创作流程

```
第1章：
  用户 ↔ Bot1 讨论 → 确认大纲
    ↓
  Bot1面板点"确认大纲" → 先持久化总大纲+章节大纲
    ↓
  组装Bot2 prompt（大总结 + condensed + 总大纲 + 章节大纲 + 文风 + 字数）
    ↓
  Bot2 创作正文（SSE流式）
    ↓
  Bot3 审核 → 显示可编辑的审核面板
    ↓
  用户三选一决策（见4.2）
    ↓
  （通过后）Bot4 生成缩略版原文（主模型）→ Bot4 生成摘要（廉价模型）
    ↓
  保存正式章节文件到 data/chapters/
    ↓
  提示用户"是否进入Bot1规划下一章"
    ↓
  切到Bot1 → 自动显示上一章摘要 → 邀请用户规划下一章
```

### 4.2 审核后的用户三选一

审核完成后（无论通过与否），Pipeline **暂停**，等待用户决策：

| 选项 | 按钮 | 行为 |
|------|------|------|
| **通过** | ✔ 通过 | 显示复制按钮 + 保存正式章节 + 进入 Bot4 总结 |
| **按建议重写** | 🔄 按建议重写 | Bot2 根据用户编辑后的建议针对性重写，attempt++ |
| **全部重写** | 🔃 全部重写 | 清空内容，attempt=1，Bot2 从头创作 |

### 4.3 重写循环

```
while (attempt ≤ max_retries + 1):
    Bot2 创作/重写
    Bot3 审核
    暂停，等待用户决策
    if 用户选"通过": → 保存章节 + Bot4
    if 用户选"按建议重写": attempt++, continue
    if 用户选"全部重写": attempt=1, continue
```

### 4.4 章节间的上下文传递

```
Bot4总结完成
  ↓
Bot1 system prompt 自动注入：大总结 + 各章摘要(abstract)
  ↓
Bot1 根据总大纲 + 摘要，与用户讨论下一章
  ↓
用户点"确认大纲"
  ↓
Bot2 prompt 注入：大总结 + 最近章节 condensed + 总大纲 + 章节大纲
  ↓
Bot2 开始创作
```

**AI 注意力 U 型分布原则**：
- 开头（高注意力）→ 全局记忆（大总结）
- 中间（低注意力）→ 辅助信息（摘要/缩略）
- 末尾（高注意力）→ 任务指令（大纲/文风/字数）

---

## 五、API 接口一览

### Bot1
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bot1/chat` | 多轮对话（SSE流式），带上下文注入 |

### Bot2
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bot2/write` | 首次创作（SSE流式） |
| POST | `/api/bot2/rewrite` | 按建议重写（SSE流式） |

### Bot3
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bot3/review` | 审核（非流式，完整JSON返回） |

### Bot4
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/bot4/summarize` | 小总结-缩略版原文（SSE流式） |
| POST | `/api/bot4/abstract` | 小总结-摘要（SSE流式，可用廉价模型） |
| POST | `/api/bot4/big-summarize` | 大总结（SSE流式） |
| POST | `/api/compress-summary` | 记忆压缩（超过3000字时） |

### 项目管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects` | 列出所有项目 |
| GET | `/api/projects/latest` | 获取最近项目ID |
| GET | `/api/projects/{id}` | 加载项目 |
| POST | `/api/projects/save` | 保存项目 |
| DELETE | `/api/projects/{id}?delete_chapters=bool` | 删除项目（可选删除章节文件） |
| POST | `/api/projects/{id}/export` | 导出TXT |
| POST | `/api/projects/save-chapter` | 保存正式章节文件 |
| GET | `/api/projects/{id}/chapters` | 列出正式章节文件 |

### 其他
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/styles` | 获取文风列表 |
| POST | `/api/styles` | 保存文风 |
| GET | `/api/styles/{id}` | 获取单个文风 |
| GET | `/api/models` | 获取可用模型列表 |
| GET/POST | `/api/configs` | Bot配置持久化 |
| GET/POST | `/api/bot3-prompts` | Bot3自定义提示词 |

---

## 六、状态管理

### 6.1 前端全局状态 S

```javascript
S = {
  chatHistory: [],       // Bot1 对话历史
  currentOutline: '',    // 总大纲
  chapterOutline: '',    // 当前章节大纲
  currentContent: '',    // Bot2 当前正文
  currentSummary: '',    // 兼容旧逻辑的总结
  chapters: [],          // 已完成章节 [{outline, chapter_outline, content, summary}]
  reviews: [],           // 审核历史
  logs: [],              // 运行日志
  accumulatedTips: [],   // 累积的写作改进建议（最多10条）
  smallSummaries: [],    // 小总结 [{chapter, condensed, abstract, time}]
  bigSummaries: [],      // 大总结 [{fromChapter, toChapter, content, time}]
  pipelineState: null,   // Pipeline中断状态（用于恢复）
  abortCtrl: null,       // AbortController
  isGenerating: false,
  _lastSuggestions: ''   // 最近审核建议（传给Bot2重写）
}
```

### 6.2 保存机制

| 触发时机 | 方式 |
|----------|------|
| AI回复完毕 | `_autoSave()` 静默保存 |
| 用户操作后 | `_autoSave()` 静默保存 |
| 章节完成后 | `_autoSaveAfterChapter()` 显式保存 |
| 每60秒 | 定时器静默保存 |
| 页面关闭/刷新 | `sendBeacon` 确保数据不丢失 |
| 启动时 | 从服务端获取最近项目自动加载 |

### 6.3 正式章节文件

审计通过后，内容写入 `data/chapters/{project_id}/{项目名}_正式_第N章.txt`。

删除项目时提示用户是否同时删除这些文件。

### 6.4 Pipeline 中断恢复

项目加载时检测 `pipelineState`，若存在则弹窗提示用户是否从断点继续。

---

## 七、Bot 配置体系

### 7.1 每个 Bot 独立配置

```
Bot1-4 各自拥有：
- base_url（API 地址）
- api_key（API 密钥）
- model（模型名称）
- temperature（默认 0.7）
- max_tokens（默认 4096）

Bot4 额外拥有：
- abstract_model（摘要模型，复用Bot4的API地址和密钥）
```

### 7.2 全局参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 及格分 pass_score | 8.0 | Bot3平均分低于此值判定不通过 |
| 最大重写 max_retries | 3 | Bot2→Bot3循环上限 |
| 大总结阈值 big_summary_threshold | 10 | 每N章提示大总结 |

### 7.3 便捷功能

- "复制Bot1配置到所有Bot"：一键同步 base_url/api_key/model
- Bot2-4 配置留空时自动使用 Bot1 配置

---

## 八、文风系统

### 8.1 工作原理

文风是 **Bot2 系统提示词的动态扩展**：
```
Bot2 系统提示词 = 基础提示词 + 字数要求 + 文风要求（名称+描述+示例片段）
```

### 8.2 预设文风（8种）

文学(literary)、武侠(wuxia)、玄幻(xuanhuan)、悬疑(suspense)、都市(urban)、言情(romance)、科幻(scifi)、幽默(humor)

### 8.3 自定义文风

支持手动填写（名称+描述+示例片段）和文件导入（.txt/.md/.json）。

### 8.4 设置位置

文风选择 + 目标字数位于 **Bot1 面板右侧"创作设置"折叠区**（默认折叠）。

---

## 九、记忆系统详解

### 9.1 小总结（每章自动）

```
Bot3通过 → Bot4主模型生成缩略版原文(condensed, 300-800字)
         → Bot4廉价模型基于原文生成摘要(abstract)
         → 存入 S.smallSummaries[]
```

- **condensed 用途**：给 Bot2 创作时衔接上下文（保留叙事细节）
- **abstract 用途**：给 Bot1 讨论时了解前情（结构化信息）

### 9.2 大总结（每N章或手动）

```
用户点"生成大总结" → 弹窗配置（前M章用摘要 + 后N章用缩略原文）
                   → 实时显示预估字数
                   → 确认后调用 /api/bot4/big-summarize
                   → 存入 S.bigSummaries[]
```

### 9.3 上下文构建逻辑

**Bot1 讨论阶段**（`buildBot1Context()`）：
```
如有大总结：最新大总结 + 大总结之后的小总结 abstract
如无大总结：所有小总结的 abstract
```

**Bot2 创作阶段**（`buildBot2Context()`）：
```
如有大总结：最新大总结 + 大总结之后的小总结 condensed
如无大总结：所有小总结的 condensed
```

### 9.4 记忆压缩

当总结超过 3000 字时，调用 `/api/compress-summary` 压缩到 800 字以内。

---

## 十、错误处理

| 阶段 | 错误时行为 |
|------|-----------|
| Bot2 出错 | 保存 pipelineState(stage='bot2')，显示重试按钮 |
| Bot3 出错 | 保存 pipelineState(stage='bot3')，显示重试按钮 |
| Bot3 JSON 解析失败 | 多级降级解析，最终返回全0分 + 原始回复预览 |
| Bot4 出错 | 保存 pipelineState(stage='bot4')，显示重试按钮 |

- API 超时：3 分钟硬限制
- 用户可随时点"停止"按钮终止 Pipeline
- Pipeline 中断后可从断点恢复

---

## 十一、技术参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| API 超时 | 180s | 所有 LLM 调用 |
| 默认温度 | 0.7 | 所有 Bot |
| 默认 max_tokens | 4096 | 所有 Bot |
| 及格分 | 8.0 | Bot3 平均分 |
| 最大重写 | 3 次 | Bot2→Bot3 循环 |
| 目标字数 | 800 字 | Bot2 创作 |
| 缩略原文字数 | 300-800 字 | Bot4 condensed |
| 自动保存 | 60s 间隔 | + 每步骤完成后 |
| 大总结阈值 | 10 章 | 用户可配置 |
| 记忆压缩阈值 | 3000 字 | 超过后自动压缩 |
| 累积建议上限 | 10 条 | 写作改进tips |
| 项目命名 | 我的小说N | 自动编号 |
