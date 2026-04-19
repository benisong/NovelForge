import { defineStore } from 'pinia';
import { ref } from 'vue';
import { apiUrl, loginUrl } from '@/api/url';

const BOT_KEYS = ['bot1', 'bot2', 'bot3', 'bot4'];

const BOT_DEFAULTS = {
  bot1: {
    base_url: '',
    api_key: '',
    model: '',
    temperature: 0.7,
    max_tokens: 4096,
  },
  bot2: {
    base_url: '',
    api_key: '',
    model: '',
    temperature: 0.8,
    max_tokens: 8192,
  },
  bot3: {
    base_url: '',
    api_key: '',
    model: '',
    temperature: 0.3,
    max_tokens: 2048,
  },
  bot4: {
    base_url: '',
    api_key: '',
    model: '',
    temperature: 0.5,
    max_tokens: 4096,
    abstract_model: '',
  },
};

const DEFAULT_CONFIG = {
  id: 'default',
  name: '默认配置',
  pass_score: 8,
  max_retries: 3,
  big_summary_threshold: 10,
  bot1: BOT_DEFAULTS.bot1,
  bot2: BOT_DEFAULTS.bot2,
  bot3: BOT_DEFAULTS.bot3,
  bot4: BOT_DEFAULTS.bot4,
};

function cloneValue(value) {
  return JSON.parse(JSON.stringify(value));
}

function normalizeNumber(value, fallback) {
  const nextValue = Number(value);
  return Number.isFinite(nextValue) ? nextValue : fallback;
}

function normalizeWordCount(value, fallback = 800) {
  // 字数不设上限，让用户自己按 Bot2 的 max_tokens 权衡。
  // 仅保证：是正整数；非数字/0/负数都回退到 fallback。
  const nextValue = Math.round(normalizeNumber(value, fallback));
  return nextValue >= 1 ? nextValue : fallback;
}

function normalizeBotConfig(botKey, botConfig = {}) {
  const defaults = BOT_DEFAULTS[botKey];
  return {
    ...defaults,
    ...botConfig,
    base_url: String(botConfig.base_url || '').trim(),
    api_key: String(botConfig.api_key || '').trim(),
    model: String(botConfig.model || '').trim(),
    temperature: normalizeNumber(botConfig.temperature, defaults.temperature),
    max_tokens: normalizeNumber(botConfig.max_tokens, defaults.max_tokens),
    ...(botKey === 'bot4'
      ? {
          abstract_model: String(botConfig.abstract_model || '').trim(),
        }
      : {}),
  };
}

export function createDefaultConfig() {
  return cloneValue(DEFAULT_CONFIG);
}

export function normalizeConfig(rawConfig = {}) {
  return {
    ...createDefaultConfig(),
    ...rawConfig,
    id: String(rawConfig.id || 'default'),
    name: String(rawConfig.name || '默认配置'),
    pass_score: normalizeNumber(rawConfig.pass_score, DEFAULT_CONFIG.pass_score),
    max_retries: Math.max(
      0,
      Math.round(normalizeNumber(rawConfig.max_retries, DEFAULT_CONFIG.max_retries)),
    ),
    big_summary_threshold: Math.max(
      1,
      Math.round(
        normalizeNumber(
          rawConfig.big_summary_threshold,
          DEFAULT_CONFIG.big_summary_threshold,
        ),
      ),
    ),
    bot1: normalizeBotConfig('bot1', rawConfig.bot1),
    bot2: normalizeBotConfig('bot2', rawConfig.bot2),
    bot3: normalizeBotConfig('bot3', rawConfig.bot3),
    bot4: normalizeBotConfig('bot4', rawConfig.bot4),
  };
}

async function fetchLatestProjectId() {
  const response = await fetch(apiUrl('/api/projects/latest'));
  if (!response.ok) {
    return '';
  }

  const data = await response.json();
  return data.project_id || '';
}

async function fetchConfigsFromServer() {
  const response = await fetch(apiUrl('/api/configs'));
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const data = await response.json();
  const configs = Array.isArray(data.configs) ? data.configs : [];
  return configs.map((item) => normalizeConfig(item));
}

function buildConfigPayload(configValue) {
  return { configs: [normalizeConfig(configValue)] };
}

export const useProjectStore = defineStore('project', () => {
  const config = ref(createDefaultConfig());

  const projectId = ref(null);
  const projectName = ref('我的小说1');
  const chatHistory = ref([]);
  const currentOutline = ref('');
  const chapterOutline = ref('');
  const currentContent = ref('');
  const selectedStyleId = ref('');
  const wordCount = ref(800);
  const reviews = ref([]);
  const summaries = ref([]);
  const bigSummaries = ref([]);
  const chapters = ref([]);

  const setConfig = (nextConfig) => {
    config.value = normalizeConfig(nextConfig);
  };

  const createConfigDraft = () => cloneValue(config.value || createDefaultConfig());

  const loadConfig = async () => {
    try {
      const configs = await fetchConfigsFromServer();
      if (configs.length > 0) {
        const selected =
          configs.find((item) => item.id === 'default') || configs[0];
        config.value = normalizeConfig(selected);
      } else {
        config.value = createDefaultConfig();
      }
    } catch (error) {
      console.error('加载配置失败:', error);
      config.value = createDefaultConfig();
    }

    return config.value;
  };

  const saveConfig = async (nextConfig = config.value) => {
    const normalized = normalizeConfig(nextConfig);

    try {
      const response = await fetch(apiUrl('/api/configs'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildConfigPayload(normalized)),
      });

      if (!response.ok) {
        return false;
      }

      config.value = normalized;
      return true;
    } catch (error) {
      console.error('保存配置失败:', error);
      return false;
    }
  };

  const fetchAvailableModels = async ({ baseUrl, apiKey }) => {
    try {
      const response = await fetch(apiUrl('/api/models'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: String(baseUrl || '').trim(),
          api_key: String(apiKey || '').trim(),
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        return {
          ok: false,
          models: [],
          error: data.error || `HTTP ${response.status}`,
        };
      }

      return {
        ok: true,
        models: Array.isArray(data.models) ? data.models : [],
        error: '',
      };
    } catch (error) {
      console.error('获取模型列表失败:', error);
      return { ok: false, models: [], error: '网络请求失败' };
    }
  };

  const loadProject = async (id) => {
    let targetId = id || localStorage.getItem('nf_last_project') || '';

    if (!targetId) {
      try {
        targetId = await fetchLatestProjectId();
      } catch (error) {
        console.error('获取最近项目失败:', error);
      }
    }

    if (!targetId) {
      return false;
    }

    try {
      const response = await fetch(apiUrl(`/api/projects/${targetId}`));
      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      projectId.value = data.project_id || targetId;
      projectName.value = data.name || '我的小说1';
      chatHistory.value = data.chat_history || [];
      currentOutline.value = data.current_outline || '';
      chapterOutline.value = data.chapter_outline || '';
      currentContent.value = data.current_content || '';
      selectedStyleId.value = String(data.style_id || '').trim();
      wordCount.value = normalizeWordCount(data.word_count, 800);
      reviews.value = data.reviews || [];
      chapters.value = data.chapters || [];
      summaries.value = data.small_summaries || [];
      bigSummaries.value = data.big_summaries || [];
      localStorage.setItem('nf_last_project', projectId.value);
      return true;
    } catch (error) {
      console.error('加载项目失败:', error);
      return false;
    }
  };

  const saveProject = async (options = {}) => {
    const { force = false } = options;

    if (
      !force &&
      !projectId.value &&
      chatHistory.value.length === 0 &&
      chapters.value.length === 0
    ) {
      return false;
    }

    if (!projectId.value) {
      projectId.value = `proj_${Date.now().toString(36)}`;
    }

    const payload = {
      project_id: projectId.value,
      name: projectName.value,
      chapters: chapters.value,
      chat_history: chatHistory.value,
      current_outline: currentOutline.value,
      chapter_outline: chapterOutline.value,
      current_content: currentContent.value,
      style_id: selectedStyleId.value,
      word_count: normalizeWordCount(wordCount.value, 800),
      reviews: reviews.value,
      small_summaries: summaries.value,
      big_summaries: bigSummaries.value,
      logs: [],
      active_tab: 'bot1',
    };

    try {
      const response = await fetch(apiUrl('/api/projects/save'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        return false;
      }

      localStorage.setItem('nf_last_project', projectId.value);
      return true;
    } catch (error) {
      console.error('保存项目失败:', error);
      return false;
    }
  };

  return {
    config,
    projectId,
    projectName,
    chatHistory,
    currentOutline,
    chapterOutline,
    currentContent,
    selectedStyleId,
    wordCount,
    reviews,
    summaries,
    bigSummaries,
    chapters,
    setConfig,
    createConfigDraft,
    loadConfig,
    saveConfig,
    fetchAvailableModels,
    loadProject,
    saveProject,
    BOT_KEYS,
  };
});
