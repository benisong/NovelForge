<template>
  <div class="settings-page">
    <van-nav-bar
      title="创作设置"
      left-arrow
      fixed
      placeholder
      safe-area-inset-top
      class="settings-nav"
      @click-left="goBack"
    >
      <template #right>
        <button
          class="nav-save-button"
          :disabled="isSaving"
          type="button"
          @click="saveCurrentConfig"
        >
          {{ isSaving ? '保存中' : '保存' }}
        </button>
      </template>
    </van-nav-bar>

    <div class="settings-scroll">
      <section class="hero-card">
        <p class="hero-kicker">Mobile Control Center</p>
        <h1 class="hero-title">把模型、审核和记忆都收在同一个入口里</h1>
        <p class="hero-copy">
          这里保存的是手机端运行配置。保存后会直接影响接下来的规划、创作、审核和总结流程。
        </p>

        <div class="hero-metrics">
          <div class="hero-metric">
            <span class="metric-caption">当前项目</span>
            <strong>{{ projectStore.projectName || '未命名项目' }}</strong>
          </div>
          <div class="hero-metric">
            <span class="metric-caption">配置名</span>
            <strong>{{ draftConfig.name || '默认配置' }}</strong>
          </div>
          <div class="hero-metric">
            <span class="metric-caption">工作空间</span>
            <strong>{{ workspaceSlug || '—' }}</strong>
          </div>
        </div>

        <div style="display:flex;gap:8px;margin-top:12px">
          <a class="nav-save-button" :href="`/w/${workspaceSlug}/logout`" style="flex:1;text-align:center;text-decoration:none;background:transparent;border:1px solid var(--border)">退出登录</a>
          <a class="nav-save-button" href="/" style="flex:1;text-align:center;text-decoration:none;background:transparent;border:1px solid var(--border)">切换工作空间</a>
        </div>
      </section>

      <section class="section-card">
        <div class="section-heading">
          <div>
            <p class="section-kicker">基础参数</p>
            <h2>全局控制</h2>
          </div>
          <p class="section-copy">先把通过阈值、重写次数和大总结节奏定好。</p>
        </div>

        <div class="metric-grid">
          <label class="metric-card">
            <span class="metric-label">Bot3 及格分</span>
            <span class="metric-hint">审核平均分达到这个值才算通过。</span>
            <input
              v-model="draftConfig.pass_score"
              class="metric-input"
              type="number"
              min="0"
              max="10"
              step="0.1"
            />
          </label>

          <label class="metric-card">
            <span class="metric-label">最大重写次数</span>
            <span class="metric-hint">审核不过时允许继续重写的上限。</span>
            <input
              v-model="draftConfig.max_retries"
              class="metric-input"
              type="number"
              min="0"
              step="1"
            />
          </label>

          <label class="metric-card">
            <span class="metric-label">大总结阈值</span>
            <span class="metric-hint">累计多少章后生成一次长期记忆。</span>
            <input
              v-model="draftConfig.big_summary_threshold"
              class="metric-input"
              type="number"
              min="1"
              step="1"
            />
          </label>
        </div>
      </section>

      <section class="section-card">
        <div class="section-heading">
          <div>
            <p class="section-kicker">视觉偏好</p>
            <h2>界面主题</h2>
          </div>
          <p class="section-copy">这里只控制移动端展示风格，不影响后端运行。</p>
        </div>

        <div class="theme-switcher">
          <button
            class="theme-card"
            :class="{ active: themeMode === 'light' }"
            type="button"
            @click="setTheme('light')"
          >
            <span class="theme-dot light"></span>
            <span class="theme-title">暖白</span>
            <span class="theme-desc">通透、轻盈，适合白天长时间创作。</span>
          </button>

          <button
            class="theme-card"
            :class="{ active: themeMode === 'dark' }"
            type="button"
            @click="setTheme('dark')"
          >
            <span class="theme-dot dark"></span>
            <span class="theme-title">夜墨</span>
            <span class="theme-desc">对比更柔和，适合夜间查看和短时修改。</span>
          </button>
        </div>
      </section>

      <section class="section-card">
        <div class="section-heading">
          <div>
            <p class="section-kicker">模型配置</p>
            <h2>四个 Bot 分开管理</h2>
          </div>
          <p class="section-copy">点一下切换当前 Bot，非必须时可以直接沿用 Bot1。</p>
        </div>

        <div class="bot-switcher">
          <button
            v-for="bot in botCards"
            :key="bot.key"
            class="bot-button"
            :class="{ active: activeBot === bot.key }"
            type="button"
            @click="activeBot = bot.key"
          >
            <span class="bot-code">{{ bot.short }}</span>
            <span class="bot-name">{{ bot.label }}</span>
            <span
              class="bot-status"
              :class="getBotStatus(bot.key).kind"
            >
              {{ getBotStatus(bot.key).text }}
            </span>
          </button>
        </div>

        <div class="bot-panel">
          <div class="bot-panel-header">
            <div>
              <h3>{{ activeBotMeta.label }}</h3>
              <p>{{ activeBotMeta.description }}</p>
            </div>
            <button
              v-if="activeBot !== 'bot1'"
              class="ghost-button"
              type="button"
              @click="copyFromBot1(activeBot)"
            >
              沿用 Bot1
            </button>
          </div>

          <div class="field-stack">
            <label class="field-card">
              <span class="field-label">API Base URL</span>
              <span class="field-hint">例如 `https://api.openai.com/v1`</span>
              <input
                v-model.trim="draftConfig[activeBot].base_url"
                class="field-input"
                type="text"
                placeholder="输入接口地址"
              />
            </label>

            <label class="field-card">
              <span class="field-label">API Key</span>
              <span class="field-hint">只保存在本地配置文件里，不会展示给读者。</span>
              <input
                v-model.trim="draftConfig[activeBot].api_key"
                class="field-input"
                type="password"
                placeholder="输入 API Key"
              />
            </label>

            <label class="field-card">
              <div class="field-head">
                <div>
                  <span class="field-label">模型名称</span>
                  <span class="field-hint">可以手填，也可以点右侧按钮自动拉取。</span>
                </div>
                <button
                  class="fetch-button"
                  :disabled="loadingBots[activeBot]"
                  type="button"
                  @click="fetchModels(activeBot)"
                >
                  {{ loadingBots[activeBot] ? '获取中' : '获取模型' }}
                </button>
              </div>
              <input
                v-model.trim="draftConfig[activeBot].model"
                class="field-input"
                type="text"
                placeholder="输入或选择模型"
              />
            </label>

            <label v-if="activeBot === 'bot4'" class="field-card">
              <span class="field-label">摘要模型</span>
              <span class="field-hint">给 Bot4 生成短摘要时使用，可留空复用主模型。</span>
              <input
                v-model.trim="draftConfig.bot4.abstract_model"
                class="field-input"
                type="text"
                placeholder="例如 gpt-4.1-mini"
              />
            </label>
          </div>
        </div>
      </section>

      <div class="scroll-spacer"></div>
    </div>

    <div class="save-bar">
      <button class="save-bar-secondary" type="button" @click="goBack">返回创作</button>
      <button
        class="save-bar-primary"
        :disabled="isSaving"
        type="button"
        @click="saveCurrentConfig"
      >
        {{ isSaving ? '保存中...' : '保存配置' }}
      </button>
    </div>

    <van-action-sheet
      v-model:show="showModelPicker"
      :actions="modelActions"
      cancel-text="取消"
      close-on-click-action
      @select="handleSelectModel"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showToast } from 'vant';

import { createDefaultConfig, useProjectStore } from '@/stores/project';
import { getWorkspace } from '@/api/url';

const workspaceSlug = getWorkspace();

const THEME_STORAGE_KEY = 'nf_theme';

const botCards = [
  {
    key: 'bot1',
    short: 'BOT1',
    label: '规划',
    description: '负责对话、总纲和章节大纲。',
  },
  {
    key: 'bot2',
    short: 'BOT2',
    label: '创作',
    description: '负责正文生成和按建议重写。',
  },
  {
    key: 'bot3',
    short: 'BOT3',
    label: '审核',
    description: '负责评分、挑错和输出修改建议。',
  },
  {
    key: 'bot4',
    short: 'BOT4',
    label: '记忆',
    description: '负责小总结和大总结，维持长线记忆。',
  },
];

const router = useRouter();
const projectStore = useProjectStore();

const draftConfig = ref(createDefaultConfig());
const activeBot = ref('bot1');
const themeMode = ref('light');
const isSaving = ref(false);
const showModelPicker = ref(false);
const modelActions = ref([]);
const pickerBotKey = ref('bot1');
const loadingBots = reactive({
  bot1: false,
  bot2: false,
  bot3: false,
  bot4: false,
});

const activeBotMeta = computed(
  () => botCards.find((item) => item.key === activeBot.value) || botCards[0],
);

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_STORAGE_KEY, theme);
  themeMode.value = theme;
}

function setTheme(theme) {
  applyTheme(theme);
}

function isBotConfigured(botKey) {
  const botConfig = draftConfig.value[botKey];
  return Boolean(
    botConfig?.base_url?.trim() &&
      botConfig?.api_key?.trim() &&
      botConfig?.model?.trim(),
  );
}

function getBotStatus(botKey) {
  if (isBotConfigured(botKey)) {
    return { kind: 'ready', text: '已配置' };
  }

  if (botKey !== 'bot1' && isBotConfigured('bot1')) {
    return { kind: 'inherit', text: '沿用 Bot1' };
  }

  return { kind: 'empty', text: '待补充' };
}

function copyFromBot1(targetBot) {
  const source = draftConfig.value.bot1;
  draftConfig.value[targetBot] = {
    ...draftConfig.value[targetBot],
    base_url: source.base_url,
    api_key: source.api_key,
    model: source.model,
  };
  showToast(`已将 Bot1 配置复制到 ${targetBot.toUpperCase()}`);
}

async function fetchModels(botKey) {
  const targetConfig = draftConfig.value[botKey];
  if (!targetConfig.base_url || !targetConfig.api_key) {
    showToast('请先填写 Base URL 和 API Key');
    return;
  }

  loadingBots[botKey] = true;
  const result = await projectStore.fetchAvailableModels({
    baseUrl: targetConfig.base_url,
    apiKey: targetConfig.api_key,
  });
  loadingBots[botKey] = false;

  if (!result.ok) {
    showToast(result.error || '获取模型失败');
    return;
  }

  if (!result.models.length) {
    showToast('没有获取到可用模型');
    return;
  }

  if (result.models.length === 1) {
    draftConfig.value[botKey].model = result.models[0];
    showToast('已自动填入可用模型');
    return;
  }

  pickerBotKey.value = botKey;
  modelActions.value = result.models.map((item) => ({ name: item }));
  showModelPicker.value = true;
}

function handleSelectModel(action) {
  draftConfig.value[pickerBotKey.value].model = action.name;
  showToast(`已选择模型 ${action.name}`);
}

async function saveCurrentConfig() {
  if (isSaving.value) {
    return;
  }

  isSaving.value = true;
  const ok = await projectStore.saveConfig(draftConfig.value);
  isSaving.value = false;

  if (!ok) {
    showToast('配置保存失败');
    return;
  }

  draftConfig.value = projectStore.createConfigDraft();
  showToast('配置已保存');
}

function goBack() {
  router.push('/project');
}

onMounted(async () => {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || 'light';
  applyTheme(savedTheme);

  await projectStore.loadConfig();
  draftConfig.value = projectStore.createConfigDraft();
});
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  background: transparent;
}

.settings-nav {
  border-bottom: 1px solid var(--app-border);
  background: transparent;
}

.settings-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 18px 16px 0;
}

.hero-card,
.section-card {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  box-shadow: var(--app-shadow);
  backdrop-filter: blur(14px);
}

.hero-card {
  padding: 22px;
  border-radius: var(--app-radius-xl);
  background:
    radial-gradient(circle at top right, rgba(255, 255, 255, 0.55), transparent 36%),
    linear-gradient(180deg, var(--app-hero-start), var(--app-hero-end));
}

.hero-card::after {
  content: '';
  position: absolute;
  right: -26px;
  top: -40px;
  width: 132px;
  height: 132px;
  border-radius: 999px;
  background: rgba(201, 104, 44, 0.12);
  filter: blur(2px);
}

.hero-kicker,
.section-kicker {
  margin: 0;
  color: var(--app-accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.hero-title,
.section-heading h2,
.bot-panel-header h3 {
  margin: 0;
  color: var(--app-text);
}

.hero-title {
  position: relative;
  z-index: 1;
  margin-top: 12px;
  font-size: 28px;
  line-height: 1.2;
}

.hero-copy,
.section-copy,
.bot-panel-header p,
.metric-hint,
.field-hint,
.theme-desc {
  color: var(--app-text-muted);
  line-height: 1.55;
}

.hero-copy {
  position: relative;
  z-index: 1;
  margin-top: 12px;
  max-width: 28em;
  font-size: 14px;
}

.hero-metrics {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.hero-metric,
.metric-card,
.field-card,
.bot-button,
.theme-card,
.bot-panel {
  border-radius: var(--app-radius-md);
}

.hero-metric {
  padding: 14px 16px;
  border: 1px solid rgba(201, 104, 44, 0.18);
  background: rgba(255, 255, 255, 0.58);
}

.metric-caption {
  display: block;
  margin-bottom: 8px;
  color: var(--app-text-muted);
  font-size: 12px;
}

.hero-metric strong {
  font-size: 15px;
}

.section-card {
  margin-top: 16px;
  padding: 20px;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.section-heading h2 {
  margin-top: 8px;
  font-size: 22px;
  line-height: 1.2;
}

.section-copy {
  max-width: 14em;
  margin: 0;
  font-size: 13px;
  text-align: right;
}

.metric-grid,
.theme-switcher,
.field-stack {
  display: grid;
  gap: 12px;
}

.metric-card,
.field-card,
.theme-card,
.bot-panel {
  border: 1px solid var(--app-border);
  background: var(--app-surface-strong);
}

.metric-card,
.field-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
}

.metric-label,
.field-label,
.theme-title,
.bot-name {
  color: var(--app-text);
  font-weight: 600;
}

.metric-input,
.field-input {
  width: 100%;
  padding: 14px 15px;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  background: var(--app-surface-muted);
  color: var(--app-text);
  outline: none;
  transition:
    border-color 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease;
}

.metric-input:focus,
.field-input:focus {
  border-color: rgba(201, 104, 44, 0.44);
  box-shadow: 0 0 0 4px rgba(201, 104, 44, 0.12);
  transform: translateY(-1px);
}

.theme-switcher {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.theme-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 16px;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.theme-card:active,
.bot-button:active,
.ghost-button:active,
.fetch-button:active,
.save-bar-primary:active,
.save-bar-secondary:active,
.nav-save-button:active {
  transform: scale(0.98);
}

.theme-card.active,
.bot-button.active {
  border-color: rgba(201, 104, 44, 0.42);
  box-shadow: 0 12px 24px rgba(201, 104, 44, 0.14);
}

.theme-dot {
  width: 16px;
  height: 16px;
  border-radius: 999px;
}

.theme-dot.light {
  background: linear-gradient(135deg, #fff8ef, #ffcfa8);
}

.theme-dot.dark {
  background: linear-gradient(135deg, #15110e, #5b3b2b);
}

.bot-switcher {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.bot-button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 14px;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.bot-code {
  display: inline-flex;
  padding: 5px 8px;
  border-radius: 999px;
  background: var(--app-accent-soft);
  color: var(--app-accent-strong);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.bot-status {
  font-size: 12px;
  font-weight: 600;
}

.bot-status.ready {
  color: var(--app-success);
}

.bot-status.inherit {
  color: var(--app-warning);
}

.bot-status.empty {
  color: var(--app-text-muted);
}

.bot-panel {
  margin-top: 14px;
  padding: 16px;
}

.bot-panel-header,
.field-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.bot-panel-header p,
.field-hint,
.theme-desc,
.metric-hint {
  margin: 4px 0 0;
  font-size: 13px;
}

.field-head {
  margin-bottom: 10px;
}

.ghost-button,
.fetch-button,
.nav-save-button,
.save-bar-secondary,
.save-bar-primary {
  border: none;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    opacity 0.18s ease,
    background 0.18s ease;
}

.ghost-button,
.fetch-button,
.nav-save-button,
.save-bar-secondary {
  background: var(--app-accent-soft);
  color: var(--app-accent-strong);
}

.ghost-button,
.fetch-button {
  padding: 10px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.fetch-button:disabled,
.nav-save-button:disabled,
.save-bar-primary:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.nav-save-button {
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
}

.save-bar {
  display: grid;
  grid-template-columns: 1fr 1.35fr;
  gap: 10px;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--app-border);
  background: var(--app-surface);
  backdrop-filter: blur(14px);
}

.save-bar-secondary,
.save-bar-primary {
  padding: 14px 16px;
  border-radius: 16px;
  font-size: 14px;
  font-weight: 700;
}

.save-bar-primary {
  background: linear-gradient(135deg, var(--app-accent), var(--app-accent-strong));
  color: #fff;
  box-shadow: 0 16px 32px rgba(201, 104, 44, 0.24);
}

.scroll-spacer {
  height: 20px;
}

@media (max-width: 360px) {
  .hero-title {
    font-size: 24px;
  }

  .hero-metrics,
  .theme-switcher,
  .bot-switcher {
    grid-template-columns: 1fr;
  }

  .section-heading,
  .bot-panel-header,
  .field-head,
  .save-bar {
    grid-template-columns: 1fr;
    display: grid;
  }

  .section-copy {
    max-width: none;
    text-align: left;
  }
}
</style>
