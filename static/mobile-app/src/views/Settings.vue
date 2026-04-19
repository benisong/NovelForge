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
            <p class="section-kicker">Writing Setup</p>
            <h2>字数与文风</h2>
          </div>
          <p class="section-copy">Bot2 写作和重写都会使用这里的目标字数，Bot3 也会按所选文风做风格一致性审核。</p>
        </div>

        <div class="field-stack">
          <label class="field-card">
            <span class="field-label">目标字数</span>
            <span class="field-hint">当前会按约 {{ normalizedDraftWordCount }} 字来创作（不设上限，请按 Bot2 max_tokens 自行权衡）。</span>
            <input
              v-model="draftWordCount"
              class="field-input"
              type="number"
              min="1"
              step="100"
            />

            <div class="word-preset-row">
              <span class="inline-label">快捷选择</span>
              <div class="word-preset-list">
                <button
                  v-for="preset in WORD_COUNT_PRESETS"
                  :key="preset"
                  class="word-preset"
                  :class="{ active: normalizedDraftWordCount === preset }"
                  type="button"
                  @click="applyWordPreset(preset)"
                >
                  {{ preset }}
                </button>
              </div>
            </div>
          </label>

          <div class="field-card">
            <div class="field-head">
              <div>
                <span class="field-label">文风设置</span>
                <span class="field-hint">会同时影响 Bot2 创作和 Bot3 的风格一致性审核。</span>
              </div>
              <button
                class="ghost-button"
                :disabled="!draftStyleId"
                type="button"
                @click="draftStyleId = ''"
              >
                清空文风
              </button>
            </div>

            <div v-if="isLoadingStyles" class="style-empty-state">正在加载文风列表...</div>
            <div v-else-if="styleOptions.length" class="style-grid">
              <button
                v-for="style in styleOptions"
                :key="style.id"
                class="style-option"
                :class="{ active: draftStyleId === style.id }"
                type="button"
                @click="draftStyleId = style.id"
              >
                <span class="style-option-name">{{ style.name }}</span>
                <span class="style-option-desc">{{ style.desc || '暂无描述' }}</span>
              </button>
            </div>
            <div v-else class="style-empty-state">暂时没有可用文风，请先在 PC 端导入或检查 `/api/styles` 数据。</div>

            <div class="style-preview" :class="{ empty: !selectedStyleMeta }">
              <template v-if="selectedStyleMeta">
                <strong>{{ selectedStyleMeta.name }}</strong>
                <p>{{ selectedStyleMeta.desc || '暂无文风描述' }}</p>
                <span>{{ selectedStyleSnippet || '该文风暂时没有示例片段。' }}</span>
              </template>
              <template v-else>
                当前未选择文风，将使用默认叙事风格。
              </template>
            </div>

            <div class="custom-style-toolbar">
              <div>
                <span class="field-label">自定义文风</span>
                <span class="field-hint">支持粘贴一段你想模仿的正文片段，保存后就能像预设文风一样直接选用。</span>
              </div>
              <button
                class="ghost-button"
                type="button"
                @click="openStyleEditor()"
              >
                新建自定义
              </button>
            </div>

            <div v-if="customStyleOptions.length" class="custom-style-list">
              <div
                v-for="style in customStyleOptions"
                :key="style.id"
                class="custom-style-card"
                :class="{ active: draftStyleId === style.id }"
              >
                <div class="custom-style-head">
                  <div>
                    <strong>{{ style.name }}</strong>
                    <p>{{ style.desc || '暂无描述' }}</p>
                  </div>
                  <span class="custom-style-badge">自定义</span>
                </div>
                <span class="custom-style-snippet">{{ getStyleExampleSnippet(style.example) || '暂无示例片段。' }}</span>
                <div class="custom-style-actions">
                  <button
                    class="mini-action-button"
                    type="button"
                    @click="draftStyleId = style.id"
                  >
                    {{ draftStyleId === style.id ? '当前已选' : '设为当前' }}
                  </button>
                  <button
                    class="mini-action-button"
                    type="button"
                    @click="openStyleEditor(style)"
                  >
                    编辑
                  </button>
                  <button
                    class="mini-action-button danger"
                    type="button"
                    @click="removeCustomStyle(style)"
                  >
                    删除
                  </button>
                </div>
              </div>
            </div>
            <div v-else class="style-empty-state">
              还没有自定义文风。点“新建自定义”后，粘贴一段有代表性的文字片段就可以保存。
            </div>
          </div>
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

    <van-popup
      v-model:show="showStyleEditor"
      round
      position="bottom"
      safe-area-inset-bottom
      class="style-editor-popup"
      @closed="resetStyleDraft"
    >
      <div class="style-editor-sheet">
        <div class="style-editor-head">
          <div>
            <h3>{{ styleDraft.id ? '编辑自定义文风' : '新建自定义文风' }}</h3>
            <p>名称和示例片段必填。Bot2 会参考这段文字的语感、节奏和叙事方式来创作。</p>
          </div>
          <button
            class="ghost-button"
            type="button"
            @click="closeStyleEditor"
          >
            关闭
          </button>
        </div>

        <div class="style-editor-body">
          <van-cell-group inset>
            <van-field
              v-model.trim="styleDraft.name"
              label="文风名称"
              placeholder="例如：冷峻悬疑风"
            />
            <van-field
              v-model.trim="styleDraft.desc"
              label="一句描述"
              placeholder="例如：短句推进，压迫感强，情绪克制"
            />
            <van-field
              v-model="styleDraft.example"
              type="textarea"
              rows="8"
              autosize
              maxlength="3000"
              show-word-limit
              label="示例片段"
              placeholder="粘贴最能体现文风的一段正文，建议 150-500 字。"
            />
          </van-cell-group>
        </div>

        <div class="style-editor-actions">
          <button
            class="save-bar-secondary"
            type="button"
            @click="closeStyleEditor"
          >
            取消
          </button>
          <button
            class="save-bar-primary"
            :disabled="isSavingStyleDraft"
            type="button"
            @click="saveCustomStyle"
          >
            {{ isSavingStyleDraft ? '保存中...' : '保存文风' }}
          </button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showConfirmDialog, showToast } from 'vant';

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
const draftWordCount = ref(800);
const draftStyleId = ref('');
const isLoadingStyles = ref(false);
const isSavingStyleDraft = ref(false);
const stylesDefaultWordCount = ref(800);
const styleOptions = ref([]);
const showStyleEditor = ref(false);
const showModelPicker = ref(false);
const modelActions = ref([]);
const pickerBotKey = ref('bot1');
const styleDraft = reactive({
  id: '',
  name: '',
  desc: '',
  example: '',
});
const loadingBots = reactive({
  bot1: false,
  bot2: false,
  bot3: false,
  bot4: false,
});

const WORD_COUNT_PRESETS = [500, 800, 1500, 3000];

const activeBotMeta = computed(
  () => botCards.find((item) => item.key === activeBot.value) || botCards[0],
);
const normalizedDraftWordCount = computed(() => normalizeWordCount(draftWordCount.value));
const selectedStyleMeta = computed(
  () =>
    styleOptions.value.find((item) => item.id === draftStyleId.value) || null,
);
const customStyleOptions = computed(() =>
  styleOptions.value.filter((item) => !item.preset),
);
const selectedStyleSnippet = computed(() => {
  return getStyleExampleSnippet(selectedStyleMeta.value?.example);
});

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_STORAGE_KEY, theme);
  themeMode.value = theme;
}

function setTheme(theme) {
  applyTheme(theme);
}

function normalizeWordCount(value) {
  // 不设上限；非法值回退 800
  const nextValue = Math.round(Number(value) || 800);
  return nextValue >= 1 ? nextValue : 800;
}

function applyWordPreset(value) {
  draftWordCount.value = value;
}

function getStyleExampleSnippet(example, maxLength = 140) {
  const text = String(example || '').trim();
  if (!text) {
    return '';
  }

  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function buildStylePayload(style) {
  return {
    id: style.id,
    name: String(style.name || '').trim(),
    desc: String(style.desc || '').trim(),
    example: String(style.example || '').trim(),
    custom: true,
  };
}

function resetStyleDraft() {
  styleDraft.id = '';
  styleDraft.name = '';
  styleDraft.desc = '';
  styleDraft.example = '';
}

function openStyleEditor(style = null) {
  if (style) {
    styleDraft.id = style.id;
    styleDraft.name = style.name || '';
    styleDraft.desc = style.desc || '';
    styleDraft.example = style.example || '';
  } else {
    resetStyleDraft();
  }

  showStyleEditor.value = true;
}

function closeStyleEditor() {
  showStyleEditor.value = false;
  resetStyleDraft();
}

async function persistCustomStyles() {
  const payload = {
    styles: customStyleOptions.value.map((item) => buildStylePayload(item)),
    default_word_count: stylesDefaultWordCount.value,
  };

  const response = await fetch('/api/styles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}

async function saveCustomStyle() {
  if (isSavingStyleDraft.value) {
    return;
  }

  const name = String(styleDraft.name || '').trim();
  const desc = String(styleDraft.desc || '').trim();
  const example = String(styleDraft.example || '').trim();
  if (!name) {
    showToast('请先填写文风名称');
    return;
  }

  if (!example) {
    showToast('请先粘贴示例片段');
    return;
  }

  const normalizedStyle = buildStylePayload({
    id:
      styleDraft.id ||
      `custom_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
    name,
    desc: desc || name,
    example,
  });

  const previousOptions = [...styleOptions.value];
  const targetIndex = styleOptions.value.findIndex((item) => item.id === normalizedStyle.id);
  if (targetIndex >= 0) {
    styleOptions.value.splice(targetIndex, 1, normalizedStyle);
  } else {
    styleOptions.value = [...styleOptions.value, normalizedStyle];
  }

  isSavingStyleDraft.value = true;
  try {
    await persistCustomStyles();
    draftStyleId.value = normalizedStyle.id;
    showToast(styleDraft.id ? '自定义文风已更新' : '自定义文风已保存');
    closeStyleEditor();
  } catch (error) {
    console.error('保存自定义文风失败:', error);
    styleOptions.value = previousOptions;
    showToast('自定义文风保存失败');
  } finally {
    isSavingStyleDraft.value = false;
  }
}

async function removeCustomStyle(style) {
  try {
    await showConfirmDialog({
      title: '删除自定义文风',
      message: `确认删除「${style.name}」吗？删除后 Bot2/Bot3 将不能再使用它。`,
    });
  } catch {
    return;
  }

  const previousOptions = [...styleOptions.value];
  styleOptions.value = styleOptions.value.filter((item) => item.id !== style.id);
  if (draftStyleId.value === style.id) {
    draftStyleId.value = '';
  }

  try {
    await persistCustomStyles();
    showToast('自定义文风已删除');
  } catch (error) {
    console.error('删除自定义文风失败:', error);
    styleOptions.value = previousOptions;
    showToast('删除自定义文风失败');
  }
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

async function loadStyles() {
  isLoadingStyles.value = true;

  try {
    const response = await fetch('/api/styles');
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    styleOptions.value = Array.isArray(data.styles) ? data.styles : [];
    stylesDefaultWordCount.value = normalizeWordCount(data.default_word_count || 800);

    if (
      draftStyleId.value &&
      !styleOptions.value.some((item) => item.id === draftStyleId.value)
    ) {
      draftStyleId.value = '';
    }
  } catch (error) {
    console.error('加载文风列表失败:', error);
    styleOptions.value = [];
    showToast('文风列表加载失败');
  } finally {
    isLoadingStyles.value = false;
  }
}

async function saveCurrentConfig() {
  if (isSaving.value) {
    return;
  }

  isSaving.value = true;
  const nextWordCount = normalizeWordCount(draftWordCount.value);
  draftWordCount.value = nextWordCount;
  projectStore.wordCount = nextWordCount;
  projectStore.selectedStyleId = draftStyleId.value;

  const configOk = await projectStore.saveConfig(draftConfig.value);
  const projectOk = await projectStore.saveProject({ force: true });
  isSaving.value = false;

  if (!configOk && !projectOk) {
    showToast('配置保存失败');
    return;
  }

  if (configOk) {
    draftConfig.value = projectStore.createConfigDraft();
  }

  if (!configOk) {
    showToast('模型配置保存失败，但创作设置已更新');
    return;
  }

  if (!projectOk) {
    showToast('模型配置已保存，但创作设置未写入项目');
    return;
  }

  showToast('配置已保存');
}

function goBack() {
  router.push('/project');
}

onMounted(async () => {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || 'light';
  applyTheme(savedTheme);

  await projectStore.loadConfig();
  await projectStore.loadProject();
  draftConfig.value = projectStore.createConfigDraft();
  draftWordCount.value = projectStore.wordCount;
  draftStyleId.value = projectStore.selectedStyleId;
  await loadStyles();
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

.word-preset-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inline-label {
  color: var(--app-text-muted);
  font-size: 12px;
  font-weight: 600;
}

.word-preset-list,
.style-grid {
  display: grid;
  gap: 10px;
}

.word-preset-list {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.word-preset,
.style-option {
  border: 1px solid var(--app-border);
  background: var(--app-surface-muted);
  color: var(--app-text);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
}

.word-preset {
  padding: 10px 0;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 700;
}

.word-preset.active,
.style-option.active {
  border-color: rgba(201, 104, 44, 0.42);
  background: rgba(201, 104, 44, 0.12);
  box-shadow: 0 12px 24px rgba(201, 104, 44, 0.1);
}

.style-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 2px;
}

.style-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 14px;
  border-radius: 16px;
  text-align: left;
}

.style-option-name {
  font-size: 14px;
  font-weight: 700;
}

.style-option-desc {
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.style-empty-state,
.style-preview {
  border: 1px solid var(--app-border);
  border-radius: 16px;
  background: var(--app-surface-muted);
}

.style-empty-state {
  padding: 14px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.style-preview {
  margin-top: 12px;
  padding: 14px 16px;
}

.custom-style-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-top: 14px;
}

.custom-style-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.custom-style-card {
  border: 1px solid var(--app-border);
  border-radius: 16px;
  background: var(--app-surface-muted);
  padding: 14px;
}

.custom-style-card.active {
  border-color: rgba(201, 104, 44, 0.42);
  box-shadow: 0 12px 24px rgba(201, 104, 44, 0.1);
}

.custom-style-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.custom-style-head strong {
  display: block;
  color: var(--app-text);
  font-size: 14px;
}

.custom-style-head p {
  margin: 6px 0 0;
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.custom-style-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--app-accent-soft);
  color: var(--app-accent-strong);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.custom-style-snippet {
  display: block;
  margin-top: 10px;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.custom-style-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.mini-action-button {
  border: none;
  border-radius: 999px;
  background: var(--app-accent-soft);
  color: var(--app-accent-strong);
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.mini-action-button.danger {
  background: rgba(238, 10, 36, 0.12);
  color: #c82333;
}

.style-preview strong {
  display: block;
  color: var(--app-text);
  font-size: 14px;
}

.style-preview p,
.style-preview span {
  margin: 8px 0 0;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.style-preview.empty {
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.style-editor-popup {
  max-height: 88vh;
}

.style-editor-sheet {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 16px calc(18px + env(safe-area-inset-bottom));
}

.style-editor-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.style-editor-head h3 {
  margin: 0;
  color: var(--app-text);
  font-size: 18px;
}

.style-editor-head p {
  margin: 8px 0 0;
  color: var(--app-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.style-editor-body {
  overflow-y: auto;
}

.style-editor-actions {
  display: grid;
  grid-template-columns: 1fr 1.3fr;
  gap: 10px;
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

.ghost-button:disabled,
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
  .style-editor-actions,
  .word-preset-list,
  .style-grid,
  .theme-switcher,
  .bot-switcher {
    grid-template-columns: 1fr;
  }

  .custom-style-toolbar,
  .custom-style-head,
  .section-heading,
  .bot-panel-header,
  .field-head,
  .style-editor-head,
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
