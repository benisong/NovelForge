# 2026-06-22 Bot2 自由度控制与“我自己审”设计

## 背景

当前 Bot2 已具备两条基本能力：

- `write`：根据正式总纲、章节大纲、记忆上下文直接生成正文
- `rewrite`：根据 Bot3 审核建议对当前正文进行重写

但现状仍存在三个结构性问题：

1. **写作输入结构偏平**：Bot2 直接吃 outline / chapter outline / memory / suggestions，缺少显式任务整形层。
2. **写作行为控制不足**：首次写作与多轮重写仍共享过于接近的写作控制方式，程序没有明确表达“本轮允许改多大范围”。
3. **重写主导权不清晰**：当用户希望自己接管审稿意见时，现有链路只能把用户建议当成 Bot3 建议的附加文本，缺少显式优先级与旁路规则。

本设计的目标不是给 Bot2 新增一个独立模型调度员，而是由**本地程序**补出一层写作阶段与 rewrite 模式控制，让 Bot2 接收到的任务更明确、更可预测。

---

## 设计目标

### 1. 用本地程序控制 Bot2 自由度

Bot2 第一版不引入独立的 `Bot2_1` / `Bot2 dispatcher` 模型节点。

改为由程序根据写作阶段，先计算一个明确的自由度策略：

- 首次写作：高自由度
- 第一次重写：中自由度
- 第二次及以后重写：低自由度
- 全自定义重写：旁路默认自由度规则

### 2. 在 Bot3 页面引入“我自己审”入口

用户可以在 Review 页面中直接写自己的审稿意见，而不是只能接受 Bot3 自动生成的建议。

该入口不是新页面，而是在现有 Review 页面中补：

- 一个按钮：`我自己审`
- 一块输入区：用户填写自定义审稿意见
- 一个开关：`是否复用系统建议`

### 3. 把 Bot2 rewrite 从“字符串建议”升级为“结构化任务包”

Bot2 rewrite 不再只接收单一字符串 `suggestions`，而改为接收一份明确表达：

- 当前 rewrite 模式
- 当前建议的主导权
- 当前自由度是否默认收紧
- 当前用户建议与系统建议的组合方式

---

## 核心设计

## 一、Bot2 自由度控制

### 默认自由度分档

第一版先做稳定、可预期的简单分档：

- `rewriteAttempt = 0` → `high`
- `rewriteAttempt = 1` → `medium`
- `rewriteAttempt >= 2` → `low`

这里的 `rewriteAttempt` 是程序态写作阶段计数：

- 首次进入 Writing 卡片、尚未有正文时，属于首次写作
- 第一次基于审核结果重写，属于第一次 rewrite
- 再次重写或后续重写，进入低自由度

### 四种自由度策略

#### `high`
用于首次写作。

允许：
- 根据章节大纲主动组织场景顺序
- 为了流畅度补少量过渡
- 扩写细节、情绪、动作与环境
- 在不偏离章节目标的前提下决定段落展开比例

禁止：
- 偏离章节大纲核心任务
- 提前泄露后续总纲信息
- 自行新增重大设定
- 把正文写成解释性总结稿

#### `medium`
用于第一次 rewrite。

允许：
- 调整局部段落顺序
- 重写局部场景
- 修节奏、修逻辑、修人物反应
- 对命中问题附近做有限扩写或收缩

禁止：
- 改掉本章核心推进方向
- 无故整章重写
- 借修文之名改剧情走向

#### `low`
用于第二次及以后 rewrite。

允许：
- 只改命中的问题点
- 在问题点附近做最小必要改动
- 微调措辞、衔接、局部逻辑

禁止：
- 重排整段结构
- 新增场景
- 改写未命中段落
- 任何“顺手优化全篇”的行为

#### `bypass`
用于全自定义 rewrite。

它的含义不是“完全放飞”，而是：

- 跳过系统默认的高 / 中 / 低自由度收紧逻辑
- 本轮优先执行用户自己定义的改写目标
- 仍然必须服从章节目标、连续性与当前项目上下文

---

## 二、“我自己审”入口与三种 rewrite 模式

### UI 形态

Review 页面新增一块“我自己审”区域，包含：

- 按钮：`我自己审`
- 文本输入区：用户填写本轮自定义审稿意见
- 开关：`是否复用系统建议`

这不是切页面，也不是新卡片；它是现有 Review 页面上的扩展交互。

### 三种 rewrite 模式

#### 1. `system`
条件：
- `selfReviewText` 为空

含义：
- 完全按 Bot3 系统审核建议驱动 rewrite

#### 2. `hybrid`
条件：
- `selfReviewText` 非空
- `reuseSystemSuggestions = true`

含义：
- 用户建议与系统建议同时存在
- 但**用户建议优先**
- 系统建议只保留总体 brief，不再继续携带逐条 item 列表

#### 3. `custom`
条件：
- `selfReviewText` 非空
- `reuseSystemSuggestions = false`

含义：
- 本轮 rewrite 完全由用户自己定义目标
- Bot3 系统建议不参与
- 同时 `freedom_policy = bypass`

---

## 三、hybrid 模式的优先级规则

`hybrid` 模式下，必须把“系统建议”和“用户建议”的关系写成硬规则：

- 用户建议是**最高优先级**
- 如果用户建议和系统建议冲突，以用户建议为准
- 系统建议只作为补充参考，不得覆盖用户明确要求

此外，这一轮已经明确采用 **B 方案**：

- `hybrid` 模式下 **只保留系统 brief**
- **不再把系统逐条建议 items 继续交给 Bot2**

理由：
- 避免系统建议过多、过细，在 token 注意力上重新压过用户意图
- 让 `hybrid` 更像“用户主导 + 系统补充”，而不是“系统主导 + 用户附注”

---

## 四、Bot2 rewrite packet

### 目标

Bot2 rewrite 不再只接收拼好的单字符串建议，而是接收一份结构化任务包。

### v1 结构

```js
{
  rewrite_mode: 'system' | 'hybrid' | 'custom',

  user_review_instruction: '',

  system_review_brief: '',

  instruction_priority: 'system_only' | 'user_over_system',

  freedom_policy: 'high' | 'medium' | 'low' | 'bypass',
}
```

### 字段说明

#### `rewrite_mode`
表示当前 rewrite 的主导模式：

- `system`
- `hybrid`
- `custom`

#### `user_review_instruction`
保存用户“我自己审”输入的原始文本。

#### `system_review_brief`
保存 Bot3 当前生成的总体重写指令（即现有 `rewrite_brief`）。

#### `instruction_priority`
用于明确当前建议主导权：

- `system_only`
- `user_over_system`

#### `freedom_policy`
明确本轮 Bot2 执行 rewrite 时的自由度控制：

- `high`
- `medium`
- `low`
- `bypass`

---

## 五、UI 状态到 rewrite packet 的映射规则

## 第一步：判定 rewrite_mode

### `system`
如果：
- `selfReviewText.trim()` 为空

则：

```js
rewrite_mode = 'system'
```

### `hybrid`
如果：
- `selfReviewText.trim()` 非空
- `reuseSystemSuggestions === true`

则：

```js
rewrite_mode = 'hybrid'
```

### `custom`
如果：
- `selfReviewText.trim()` 非空
- `reuseSystemSuggestions === false`

则：

```js
rewrite_mode = 'custom'
```

---

## 第二步：判定默认自由度

程序根据当前写作阶段得到：

```js
defaultFreedomPolicy =
  rewriteAttempt === 0 ? 'high'
  : rewriteAttempt === 1 ? 'medium'
  : 'low'
```

注意：
- `rewriteAttempt` 只决定默认自由度
- 它**不直接决定** `system / hybrid / custom`

---

## 第三步：判定最终 freedom_policy

### `system`

```js
freedom_policy = defaultFreedomPolicy
```

### `hybrid`

```js
freedom_policy = defaultFreedomPolicy
```

### `custom`

```js
freedom_policy = 'bypass'
```

这条是硬规则：

> 只要用户输入了“我自己审”内容，且关闭“复用系统建议”，本轮 Bot2 rewrite 就必须旁路默认自由度规则。

---

## 第四步：生成任务包内容

### `system`

```js
{
  rewrite_mode: 'system',
  user_review_instruction: '',
  system_review_brief: review.rewrite_brief,
  instruction_priority: 'system_only',
  freedom_policy: defaultFreedomPolicy,
}
```

### `hybrid`

```js
{
  rewrite_mode: 'hybrid',
  user_review_instruction: selfReviewText.trim(),
  system_review_brief: review.rewrite_brief,
  instruction_priority: 'user_over_system',
  freedom_policy: defaultFreedomPolicy,
}
```

### `custom`

```js
{
  rewrite_mode: 'custom',
  user_review_instruction: selfReviewText.trim(),
  system_review_brief: '',
  instruction_priority: 'user_over_system',
  freedom_policy: 'bypass',
}
```

---

## 六、Prompt 层重构方向

当前 Bot2 不应继续只依赖一个统一 `BOT2_SYSTEM` 再在 user prompt 里手工堆 rewrite 规则。

更合理的方向是：

### 1. 稳定底座
始终存在：

- Bot2 writer 角色定义
- 基础质量要求
- anti-slop 规则
- 忠于章节目标
- 不泄露后续总纲
- 直接输出正文，不输出解释

### 2. 自由度规则块
由 `freedom_policy` 决定拼哪一段：

- `high`
- `medium`
- `low`
- `bypass`

### 3. 建议优先级规则块
由 `instruction_priority` 决定拼哪一段：

- `system_only`
- `user_over_system`

### 4. 模式说明块
由 `rewrite_mode` 决定拼哪一段：

- `system`
- `hybrid`
- `custom`

---

## 七、前后端改造边界

### 后端路由
第一版不改路由：

- `/api/w/{workspace}/bot2/write`
- `/api/w/{workspace}/bot2/rewrite`

### 后端请求模型

`Bot2RewriteRequest` 在保留现有 `suggestions` 字段兼容旧逻辑的前提下，新增：

- `rewrite_packet`

推荐方向：

```python
class Bot2RewritePacket(BaseModel):
    rewrite_mode: str
    user_review_instruction: str = ""
    system_review_brief: str = ""
    instruction_priority: str
    freedom_policy: str
```

然后：

```python
class Bot2RewriteRequest(BaseModel):
    ...
    suggestions: str = ""
    rewrite_packet: Optional[Bot2RewritePacket] = None
```

这样可以平滑迁移：

- 老前端仍可继续走 `suggestions`
- 新前端可逐步切换到 `rewrite_packet`

### 前端改造点

#### `Review.vue`
新增并持久化：

- `self_review_text`
- `reuse_system_suggestions`

#### `Writing.vue`
不再直接把 `formatSuggestionsText(...)` 的结果作为 Bot2 rewrite 的唯一输入。

改为：

1. 先生成 `rewrite_packet`
2. 再与必要的 fallback `suggestions` 一起发送给 `/api/bot2/rewrite`

#### `workflow.js`
建议补一层共享函数，例如：

- `buildBot2RewritePacket(reviewState, uiState, projectStore)`

用于集中处理：

- rewrite 模式判定
- 默认自由度判定
- 结构化任务包生成

---

## 八、一个明确边界：首次写作不使用 rewrite packet

需要明确区分：

### 写作（write）
只需要：
- 正式总纲
- 章节大纲
- 记忆上下文
- 首次写作自由度（默认高自由度）

### 重写（rewrite）
才需要：
- `rewrite_packet`

因此长期看，Bot2 程序层最终会有两种不同的任务包：

- `write_packet`
- `rewrite_packet`

但本轮设计先聚焦 `rewrite_packet`。

---

## 结论

本轮设计的最终落点是：

> Bot2 不新增独立模型调度员，而是由本地程序根据写作阶段与用户自审状态，生成一个带有“自由度控制 + 建议主导权 + rewrite 模式”的结构化任务包，再交给 Bot2 执行。

这会把 Bot2 从“直接吃一坨建议字符串”升级成“接收一份明确、分层、有优先级的重写任务说明”，并为后续进一步完善写作任务包层打下基础。
