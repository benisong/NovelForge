# NovelForge 四Bot协作规则说明

> 版本 v2.3 | 自动生成于当前代码审查

---

## 一、系统架构总览

```
用户 ↔ Bot1(策划) → Bot2(创作) ↔ Bot3(审核) → Bot4(记忆) → 下一章循环
         │                ↑           │
         │                └───────────┘
         │                 审核不通过时回环
         └── 多轮对话交互（唯一的人工介入点1）
                          审核面板（人工介入点2）
```

**后端**：FastAPI + httpx（调用 OpenAI 兼容 API）
**前端**：单文件 HTML（无框架），SSE 流式输出
**持久化**：JSON 文件（data/ 目录下）

---

## 二、四个 Bot 的职责定义

### Bot1 — 大纲策划师
- **角色**：资深小说策划编辑
- **交互方式**：与用户多轮对话（唯一支持多轮对话的 Bot）
- **核心规则**：**每次回复都必须包含 `<outline>...</outline>` 标签包裹的完整大纲**
- **大纲内容**：章节主题、核心冲突、场景设计、人物安排、情节节点（起承转合）、情感基调、悬念/伏笔
- **输入**：用户消息 + 历史对话 + 上下文记忆（可选，由 Bot4 提供）
- **输出**：对话回复 + 结构化大纲

### Bot2 — 内容创作师
- **角色**：才华横溢的小说作家
- **交互方式**：无用户直接交互，自动执行
- **核心规则**：根据大纲创作正文，直接输出小说内容，不添加额外说明
- **动态提示词构建**（`_build_bot2_system`函数）：
  - **基础提示词**：固定的创作指导
  - **字数要求**：用户设置的目标字数（默认 800），拼接到系统提示词
  - **文风要求**：如果用户选择了文风，会拼接文风名称、描述、示例片段，要求 Bot2 "深度学习其语言风格并自然运用"
- **首次写作**（`/api/bot2/write`）：接收大纲 + 上下文
- **重写**（`/api/bot2/rewrite`）：接收大纲 + 上一版内容 + 审核修改建议 + 上下文
- **输出**：流式输出的小说正文

### Bot3 — 质量审核师
- **角色**：严格而专业的文学评审
- **交互方式**：无直接交互，但**审核结果可被用户编辑**
- **审核维度**（4项，每项 1-10 分）：
  1. **文学性** (literary)：语言表现力、修辞、叙事技巧
  2. **逻辑性** (logic)：情节因果、前后自洽
  3. **风格一致性** (style)：与大纲/上下文风格匹配
  4. **AI感** (ai_feel)：是否像人类写作（越高越好）
- **输出格式**：严格 JSON，包含：
  - `scores`：各维度分数
  - `average`：平均分（后端重新计算，不信任 LLM 给的值）
  - `passed`：是否通过（average ≥ 及格分）
  - `analysis`：2-3 句综合评价
  - `items`：逐条修改建议（dim/severity/location/problem/suggestion）
- **及格规则**：平均分 ≥ 用户设定的及格分（默认 8.0）
- **items 要求**：未通过时至少 5 条，通过时也需给出 low 级别的改进建议

### Bot4 — 记忆管理师
- **角色**：经验丰富的小说编辑
- **交互方式**：无用户交互，自动执行
- **核心规则**：对通过审核的章节进行精炼总结，提取关键信息
- **总结内容**：情节摘要、人物状态、世界观更新、伏笔追踪、时间线
- **输入**：本章内容 + 之前的故事总结/记忆
- **输出**：结构化总结文本（作为后续章节的上下文记忆）

---

## 三、Pipeline 协作流程

### 3.1 正常流程

```
1. 用户与 Bot1 多轮对话 → 确认大纲
2. Pipeline 启动（用户点击"确认大纲，开始创作"）
3. Bot2 创作（第1次，调用 /api/bot2/write）
4. Bot3 审核
   ├── 通过（average ≥ 及格分）→ 继续到 Bot4
   └── 未通过 → 暂停，等待用户决策
5. Bot4 总结 → 章节完成，记忆存入上下文
6. 回到 Bot1 对话，开始下一章
```

### 3.2 审核未通过时的用户三选一

当 Bot3 评分未达到及格线时，Pipeline **暂停**，用户看到可编辑的审核面板，可以：

| 选项 | 按钮 | 行为 |
|------|------|------|
| **发回修改** | 🔄 修改后重写 | 用户可先编辑分数/建议条目，然后 Bot2 根据编辑后的建议重写 |
| **接受当前版本** | ✓ 接受并继续 | 跳过重写，直接进入 Bot4 总结 |
| **跳过** | ⏭ 跳过本章 | 跳过 Bot4 总结，直接保存章节（summary 标记为"用户跳过总结"）|

### 3.3 重写循环机制

```
while (attempt ≤ max_retries + 1):
    Bot2 创作/重写
    Bot3 审核
    if 通过: break → Bot4
    if 未通过:
        暂停，等待用户决策
        if 用户选"发回修改": attempt++, continue
        if 用户选"接受": break → Bot4
        if 用户选"跳过": return（不经过 Bot4）
```

- **最大重写次数**：用户配置（默认 3 次）
- **达到上限后**：仍然显示决策面板，用户可以选择接受或跳过
- **用户可编辑的内容**：各维度分数、每条建议的所有字段（维度/严重度/位置/问题/建议）、可增删条目

### 3.4 用户编辑审核 → 发回修改的数据流

```
1. 前端 readEditedReview() 从 DOM 读取用户编辑后的分数和 items
2. items 被编译为纯文本格式的 suggestions 字符串：
   "[文学性/high] 第3段对话: 问题描述 → 建议内容"
3. suggestions 传入 Bot2RewriteRequest
4. Bot2 的重写提示词中包含"【审核反馈和修改建议】"段落
5. Bot2 根据这些反馈进行定向修改
```

---

## 四、数据流与 API 调用链

### 4.1 Bot1 对话

```
前端 messages[] → POST /api/bot1/chat
                   → stream_llm(bot1_config, [system + context? + messages])
                   ← SSE 流式返回
前端解析 <outline>...</outline> 标签提取大纲
```

### 4.2 Bot2 创作

```
首次：POST /api/bot2/write  {outline, config, context, style_id, word_count}
重写：POST /api/bot2/rewrite {outline, content, suggestions, config, context, style_id, word_count}
     → _build_bot2_system(style_id, word_count) 构建动态系统提示词
     → stream_llm(bot2_config, messages)
     ← SSE 流式返回
```

### 4.3 Bot3 审核

```
POST /api/bot3/review {content, outline, config}
     → call_llm_full(bot3_config, messages)  ← 注意：非流式，完整返回
     → 后端解析 JSON，重新计算 average，校验 passed
     ← 返回结构化 JSON（scores, items, analysis...）
```

### 4.4 Bot4 总结

```
POST /api/bot4/summarize {content, config, previous_summary}
     → stream_llm(bot4_config, messages)
     ← SSE 流式返回
```

---

## 五、状态管理与持久化

### 5.1 前端状态对象 S

```javascript
S = {
  currentOutline,    // Bot1 输出的当前大纲
  currentContent,    // Bot2 输出的当前正文
  currentSummary,    // Bot4 输出的累计记忆
  chapters[],        // 已完成章节 [{outline, content, summary}]
  chatHistory[],     // Bot1 对话历史
  reviews[],         // 审核历史记录
  logs[],            // 运行日志
  pipelineState,     // Pipeline 中断状态（用于恢复）
  abortCtrl,         // AbortController（用于停止）
  isGenerating,      // 是否正在生成
  _lastSuggestions   // 最近一次审核建议（传给 Bot2 重写用）
}
```

### 5.2 保存机制

- **自动保存**：每 60 秒 + 每个 Bot 步骤完成后
- **退出保存**：`beforeunload` 事件触发 `navigator.sendBeacon`
- **保存内容**：chapters, chatHistory, currentOutline/Content/Summary, reviews, logs, pipelineState, activeTab

### 5.3 Pipeline 中断恢复

保存的 `pipelineState` 结构：
```javascript
{
  stage: 'bot2' | 'bot3' | 'bot3_decision' | 'bot4',
  attempt: number,
  currentContent: string,
  config: ProjectConfig,  // 注意：包含 API key，恢复时用当前活跃配置替代
  context: string
}
```

恢复时根据 `stage` 决定从哪个步骤继续。

---

## 六、Bot 配置体系

### 6.1 每个 Bot 独立配置

```
Bot1-4 各自拥有独立的：
- base_url（API 地址）
- api_key（API 密钥）
- model（模型名称）
- temperature（温度，默认 0.7）
- max_tokens（最大 token，默认 4096）
```

### 6.2 全局参数

- **及格分** (pass_score)：默认 8.0，Bot3 平均分低于此值判定不通过
- **最大重写次数** (max_retries)：默认 3

### 6.3 "复制Bot1配置到所有Bot"

前端提供一键复制功能，将 Bot1 的 base_url/api_key/model 同步到 Bot2-4。

---

## 七、文风系统

### 7.1 工作原理

文风不是独立 Bot，而是 **Bot2 系统提示词的动态扩展**：

```
Bot2 系统提示词 = 基础提示词 + 字数要求 + 文风要求（如果选择了文风）
```

文风要求包含：文风名称、描述、示例片段（要求 Bot2 学习该风格后创作）

### 7.2 预设文风

8 种内置文风：文学(literary)、武侠(wuxia)、玄幻(xuanhuan)、悬疑(suspense)、都市(urban)、言情(romance)、科幻(scifi)、幽默(humor)

### 7.3 自定义文风

用户可通过以下方式导入：
- 手动填写（名称 + 描述 + 示例片段）
- 文件导入（.txt/.md/.json）
- 拖拽导入

### 7.4 文风设置位置

文风选择 + 目标字数控件位于 **Bot2 正文页面顶部**（可折叠工具栏）。

---

## 八、错误处理与重试

### 8.1 各阶段错误处理

| 阶段 | 错误时行为 |
|------|-----------|
| Bot2 出错 | 保存 pipelineState(stage='bot2')，显示重试按钮 |
| Bot3 出错 | 保存 pipelineState(stage='bot3')，显示重试按钮 |
| Bot3 JSON 解析失败 | 返回全0分 + retry_hint，前端可重试 |
| Bot4 出错 | 保存 pipelineState(stage='bot4')，显示重试按钮 |

### 8.2 API 级别错误

- 超时：3 分钟硬限制
- 连接失败：直接报错，不自动重试
- 空内容返回：视为错误
- HTTP 非200：返回错误信息

### 8.3 用户可随时停止

Pipeline 运行时显示"停止"按钮，通过 AbortController 取消所有进行中的请求。

---

## 九、当前存在的问题与待确认项

### 9.1 Bot3 审核未接收文风信息

**现状**：Bot3 审核时只接收 content + outline + config，**不接收 style_id**。
**影响**：Bot3 的"风格一致性"维度审核时，不知道用户选择了什么文风，只能根据大纲推测目标风格。
**建议**：考虑将选中的文风信息（名称+描述）传给 Bot3，使风格审核更精准。

### 9.2 Bot4 总结未接收大纲

**现状**：Bot4 只接收 content + previous_summary，**不接收 outline**。
**影响**：Bot4 无法对比大纲中的伏笔设置与实际内容，伏笔追踪可能不完整。
**建议**：考虑将当前章大纲传给 Bot4 辅助总结。

### 9.3 Bot1 上下文仅为 summary

**现状**：Bot1 的上下文记忆来自 `S.currentSummary`（Bot4 的总结）。
**可选增强**：可以同时传入前几章的大纲摘要，帮助 Bot1 更好地规划后续章节。

### 9.4 审核通过后的建议未利用

**现状**：Bot3 审核通过（passed=true）时，也会产生 low 级别的改进建议，但这些建议没有传给 Bot2 用于后续章节的创作。
**可选增强**：积累审核建议作为"写作注意事项"传给后续的 Bot2 调用。

### 9.5 多章间的文风一致性

**现状**：每次 Bot2 创作都独立接收文风示例。但 LLM 没有看到前几章的实际文本来学习已建立的风格。
**可选增强**：将上一章的最后 N 段作为"风格参考"传给 Bot2，增强跨章节风格连贯性。

### 9.6 Bot2 重写时 context 传递

**现状**：重写时 context 字段仍然传递之前的 summary，这是正确的。但如果 summary 非常长（多章累积），可能消耗过多 token。
**可选增强**：对超长 context 进行截断或二次总结。

---

## 十、技术参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| API 超时 | 180s (3分钟) | 所有 LLM 调用 |
| 默认温度 | 0.7 | 所有 Bot |
| 默认 max_tokens | 4096 | 所有 Bot |
| 及格分 | 8.0 | Bot3 平均分 |
| 最大重写 | 3 次 | Bot2→Bot3 循环 |
| 目标字数 | 800 中文字 | Bot2 创作 |
| 自动保存 | 60s 间隔 | + 每步骤完成后 |
| Bot3 items | 未通过≥5条，通过≥3条(low) | 修改建议 |
