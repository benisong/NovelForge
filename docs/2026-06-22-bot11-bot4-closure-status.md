# 2026-06-22 Bot1_1 / Bot4 闭环改造状态

## 背景

本轮改动承接移动端主流程，目标是先把章节规划提炼从前端本地影子逻辑升级为真实后端链路，再把 Bot4 章节记忆维护从 `Memory.vue` 的手动页面动作抽成可复用的自动维护链。

对应提交：`e638d98 feat: wire bot1_1 planning extraction and bot4 auto maintenance`

## 本轮已落地内容

### 1. Bot1_1：从本地摘要升级为真实后端链路

已新增：

- `app/models.py`
  - `Bot11ExtractRequest`
- `app/prompts.py`
  - `BOT1_1_SYSTEM`
- `app/routes/bot1.py`
  - `POST /api/bot1/extract-planning`

前端接线位置：

- `static/mobile-app/src/lib/workflow.js`
  - `buildPlanningExtractRequest(...)`
  - `requestPlanningExtract(...)`
- `static/mobile-app/src/views/Planning.vue`
  - 章节规划对话达到阈值后，不再走前端本地提炼，而是调用真实 Bot1_1 接口

当前口径：

- Bot1 继续负责用户可见的章节规划对话
- Bot1_1 只负责“近期规划提炼”
- 提炼失败时只 toast，不中断主聊天链

### 2. Bot4：从 Memory 页手动动作抽成可调度维护链

已抽出共享工作流函数：

- `static/mobile-app/src/lib/workflow.js`
  - `ensureCurrentSummary(...)`
  - `generateBigSummary(...)`
  - `compressSummaryMemory(...)`
  - `runBot4Maintenance(...)`

页面层接线：

- `static/mobile-app/src/views/Memory.vue`
  - 手动“小总结 / 大总结”改为复用共享函数
  - 暴露 `runAutoMaintenance()` 给外层调用
- `static/mobile-app/src/views/ProjectDetail.vue`
  - `handleApprove()` 在章节审核通过后先保存章节，再调用 `runAutoMaintenance()`，然后进入 Memory 卡片

当前口径：

- Bot4 仍复用现有后端接口，不额外造新的 4_1 路由壳
- 自动维护顺序是：章节保存 → 小总结 → 达阈值时大总结 → 大总结后压缩

### 3. 移动端总纲工作区的提交流程排障

本轮真实验证里还顺手定位并修正了总纲页的一个前端交互问题：

- `Planning.vue` 的 outline 工作区在挂载时被自动 `scrollToBottom()` 顶到错误位置
- 结果是“提交总纲”按钮可见但实际落在顶部栏下方，点击命中错误层
- 已改为：仅在非 outline workspace 模式下自动滚到底

排障后的最终结论：

- `submitOutlineDraft()` 真实代码链本身是通的
- browser 自动化点击该按钮不稳定，不等价于真实业务点击
- 用页面内 JS 主动触发按钮 click 后，正式总纲可以真实落盘并退出 `outline_mode`

## 真实验证状态

### 已确认生效

#### Bot1 总纲主流程

- workspace 创建 / 登录 / 项目创建可用
- Bot 配置保存链可用
- 总纲设计模式下，Bot1 能正常生成总纲草稿
- 提交总纲后，项目文件会真实写入：
  - `current_outline`
  - `outline_mode = ""`
  - `outline_dirty = false`

#### Bot1_1 近期规划提炼

已通过真实项目文件确认：

- `planning_digest` 会被更新
- `planning_turns_since_extract` / `planning_chars_since_extract` 会被维护
- `chapter_outline` 继续按章节规划对话更新

当前判断：

- Bot1_1 这条“近期章节规划提炼”链已经真实生效
- browser 抓 fetch 并不稳定，最终以项目 JSON 落盘为准

### 尚未完成闭环验证

#### Bot4 自动维护

代码接线已在，但本轮没有完成最终业务验证。

原因不是自动维护逻辑本身，而是测试 workspace 的实际配置层仍未补实到可完整跑通 Bot2 / Bot3 / Bot4 的状态，因此未继续强行推进完整“写作 → 审核通过 → 自动总结”链路验证。

## 涉及文件

- `app/models.py`
- `app/prompts.py`
- `app/routes/bot1.py`
- `static/mobile-app/src/lib/workflow.js`
- `static/mobile-app/src/views/Planning.vue`
- `static/mobile-app/src/views/Memory.vue`
- `static/mobile-app/src/views/ProjectDetail.vue`

## 当前可作为下一阶段基线的事实

1. 移动端 outline-first 流程已可继续作为主入口使用
2. Bot1_1 不再只是前端本地字符串拼接，而是独立后端链路
3. Bot4 自动维护已经具备共享调度层接口，后续新功能可以直接挂在这个层上，而不必再回到 `Memory.vue` 内联手写流程
4. 当前若继续做新功能，应以移动端 SPA 为主战场，而不是旧桌面页
