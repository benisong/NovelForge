import { apiFetch, apiUrl, loginUrl } from '@/api/url';

const BOT_DEFAULTS = {
  bot1: { temperature: 0.7, max_tokens: 16384 },
  bot2: { temperature: 0.8, max_tokens: 16384 },
  bot3: { temperature: 0.3, max_tokens: 16384 },
  bot4: { temperature: 0.5, max_tokens: 16384 },
};

const REVIEW_DIM_LABELS = {
  literary: '文学性',
  logic: '逻辑性',
  style: '风格一致性',
  ai_feel: '人味',
};

const REVIEW_SEVERITY_ORDER = {
  high: 0,
  medium: 1,
  low: 2,
};

function hasCoreConfig(botConfig) {
  return Boolean(botConfig?.base_url && botConfig?.api_key && botConfig?.model);
}

function normalizeBotConfig(botConfig, fallbackConfig, defaults) {
  const source = hasCoreConfig(botConfig) ? botConfig : fallbackConfig;
  if (!hasCoreConfig(source)) {
    return null;
  }

  return {
    base_url: source.base_url,
    api_key: source.api_key,
    model: source.model,
    temperature: source.temperature ?? defaults.temperature,
    max_tokens: source.max_tokens ?? defaults.max_tokens,
  };
}

function stringifySummaryContent(content) {
  if (!content) {
    return '';
  }

  if (typeof content === 'string') {
    return content;
  }

  if (typeof content === 'object') {
    return Object.entries(content)
      .map(([key, value]) => `${key}: ${value}`)
      .join('\n');
  }

  return String(content);
}

function normalizeReviewItems(items) {
  if (!Array.isArray(items)) {
    return [];
  }

  return items
    .map((item) => ({
      dim: String(item?.dim || 'literary').trim() || 'literary',
      severity: String(item?.severity || 'medium').trim() || 'medium',
      location: String(item?.location || '').trim(),
      problem: String(item?.problem || '').trim(),
      suggestion: String(item?.suggestion || '').trim(),
    }))
    .filter((item) => item.problem || item.suggestion || item.location);
}

export function getRuntimeConfig(rawConfig) {
  if (!rawConfig) {
    return null;
  }

  const bot1 = normalizeBotConfig(rawConfig.bot1, null, BOT_DEFAULTS.bot1);
  if (!bot1) {
    return null;
  }

  const bot2 = normalizeBotConfig(rawConfig.bot2, bot1, BOT_DEFAULTS.bot2);
  const bot3 = normalizeBotConfig(rawConfig.bot3, bot1, BOT_DEFAULTS.bot3);
  const bot4 = normalizeBotConfig(rawConfig.bot4, bot1, BOT_DEFAULTS.bot4);

  return {
    bot1,
    bot2,
    bot3,
    bot4,
    pass_score: Number(rawConfig.pass_score ?? 8),
    max_retries: Number(rawConfig.max_retries ?? 3),
    big_summary_threshold: Number(rawConfig.big_summary_threshold ?? 10),
    bot4_abstract_model: rawConfig.bot4?.abstract_model || '',
  };
}

export async function readSSE(url, body, options = {}) {
  const { signal, onChunk, onReset } = options;
  const response = await fetch(apiUrl(url), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

  if (response.status === 401) {
    window.location.href = loginUrl();
    throw new Error('未登录');
  }

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`HTTP ${response.status}: ${message.slice(0, 200)}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) {
        continue;
      }

      const payload = line.slice(6).trim();
      if (payload === '[DONE]') {
        return fullText;
      }

      try {
        const parsed = JSON.parse(payload);
        if (parsed.error) {
          throw new Error(parsed.error);
        }
        if (parsed.reset) {
          fullText = '';
          if (onReset) {
            onReset(parsed);
          } else {
            onChunk?.('', fullText);
          }
          continue;
        }
        if (parsed.content) {
          fullText += parsed.content;
          onChunk?.(parsed.content, fullText);
        }
      } catch (error) {
        if (!String(error?.message || '').includes('Unexpected')) {
          throw error;
        }
      }
    }
  }

  return fullText;
}

export function extractOutline(text) {
  const matched = text.match(/<outline>([\s\S]*?)<\/outline>/i);
  return matched ? matched[1].trim() : '';
}

export function extractChapterOutline(text) {
  const matched = text.match(/<chapter_outline>([\s\S]*?)<\/chapter_outline>/i);
  return matched ? matched[1].trim() : '';
}

export function stripOutline(text, options = {}) {
  const { removeChapterOutline = true } = options;
  let content = String(text || '').replace(/<outline>[\s\S]*?<\/outline>/gi, '');
  if (removeChapterOutline) {
    content = content.replace(/<chapter_outline>[\s\S]*?<\/chapter_outline>/gi, '');
  }
  return content.trim();
}

export function shouldTriggerPlanningExtract(message, projectStore, options = {}) {
  const {
    turnThreshold = 4,
    charThreshold = 1200,
    explicitTriggers = ['整理一下', '收一下', '总结一下', '帮我归纳', '定稿', '成形'],
  } = options;
  const normalized = String(message || '').trim();
  if (!normalized) {
    return false;
  }
  if (explicitTriggers.some((keyword) => normalized.includes(keyword))) {
    return true;
  }
  return Number(projectStore?.planningTurnsSinceExtract || 0) >= turnThreshold
    || Number(projectStore?.planningCharsSinceExtract || 0) >= charThreshold;
}

export function applyPlanningExtract(projectStore, latestUserInput = '', options = {}) {
  const { recentWindowSize = 6 } = options;
  const trimmedOutline = String(projectStore?.chapterOutline || '').trim();
  if (!trimmedOutline) {
    return false;
  }

  const recentMessages = Array.isArray(projectStore?.chatHistory)
    ? projectStore.chatHistory
      .slice(-recentWindowSize)
      .map((msg) => `${msg.role === 'user' ? '用户' : 'Bot1'}：${String(msg.content || '').trim()}`)
      .filter(Boolean)
      .join('\n')
    : '';

  projectStore.planningDigest = [
    latestUserInput ? `用户本轮补充：${latestUserInput}` : '',
    '已触发一次近期规划提炼。',
    `当前章节规划：${trimmedOutline}`,
    recentMessages ? `最近对话窗口：\n${recentMessages}` : '',
  ].filter(Boolean).join('\n\n');
  projectStore.planningTurnsSinceExtract = 0;
  projectStore.planningCharsSinceExtract = 0;
  return true;
}

export function buildPlanningExtractRequest(projectStore, latestUserInput = '', options = {}) {
  const { recentWindowSize = 6, maxRecentMessages = 6 } = options;
  const history = Array.isArray(projectStore?.chatHistory) ? projectStore.chatHistory : [];
  const recentMessages = history
    .slice(-recentWindowSize)
    .filter((msg) => msg?.role === 'user' || msg?.role === 'assistant')
    .map((msg) => ({
      role: msg.role,
      content: String(msg.content || '').trim(),
    }))
    .filter((msg) => msg.content)
    .slice(-maxRecentMessages);

  if (latestUserInput) {
    const lastMessage = recentMessages[recentMessages.length - 1];
    if (!lastMessage || lastMessage.role !== 'user' || lastMessage.content !== latestUserInput) {
      recentMessages.push({ role: 'user', content: latestUserInput });
    }
  }

  return {
    messages: recentMessages,
    current_outline: String(projectStore?.currentOutline || '').trim(),
    chapter_outline: String(projectStore?.chapterOutline || '').trim(),
    context: buildBot1Context(projectStore, {
      includePlanningDigest: true,
      recentUserCount: 2,
      recentAssistantCount: 2,
    }),
  };
}

export async function requestPlanningExtract(projectStore, config, latestUserInput = '', options = {}) {
  const payload = buildPlanningExtractRequest(projectStore, latestUserInput, options);
  const response = await apiFetch('/api/bot1/extract-planning', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      config,
    }),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(`HTTP ${response.status}: ${message.slice(0, 200)}`);
  }

  const data = await response.json();
  const planningDigest = String(data?.planning_digest || '').trim();
  if (!planningDigest) {
    throw new Error('Bot1_1 未返回近期规划提炼结果');
  }

  projectStore.planningDigest = planningDigest;
  projectStore.planningTurnsSinceExtract = 0;
  projectStore.planningCharsSinceExtract = 0;
  return planningDigest;
}

export function buildOutlineDigest(projectStore, latestUserInput = '', options = {}) {
  const { isReviseMode = false, maxLength = 1200 } = options;
  const draft = String(projectStore?.outlineDraft || '').trim();
  const baseline = String(projectStore?.currentOutline || '').trim();
  const sameAsOfficial = draft && draft === baseline;
  const digest = [
    latestUserInput ? `用户本轮补充：${latestUserInput}` : '',
    isReviseMode ? '当前处于正式总纲修正模式。' : '当前处于正式总纲设计模式。',
    isReviseMode
      ? (sameAsOfficial
          ? '草稿当前仍与正式总纲基线一致，尚未形成新的修正版本。'
          : '草稿已经偏离正式总纲基线，后续提交将覆盖正式版本。')
      : '草稿会在提交后成为新的正式总纲。',
    draft ? `当前总纲草稿：${draft}` : '',
  ].filter(Boolean).join('\n\n').trim();
  if (digest.length <= maxLength) {
    return digest;
  }
  return digest.slice(digest.length - maxLength).trim();
}

export function incrementPlanningExtractCounters(projectStore, message, options = {}) {
  const { isOutlineMode = false } = options;
  if (isOutlineMode) {
    return;
  }
  const normalized = String(message || '');
  projectStore.planningTurnsSinceExtract += 1;
  projectStore.planningCharsSinceExtract += normalized.length;
}

export function clearOutlineWorkspaceState(projectStore, options = {}) {
  const { keepOfficialOutline = true } = options;
  if (!keepOfficialOutline) {
    projectStore.currentOutline = '';
  }
  projectStore.outlineDraft = '';
  projectStore.outlineMode = '';
  projectStore.outlineDirty = false;
  projectStore.outlineDigest = '';
}

export function buildBot1Context(projectStore, options = {}) {
  const {
    recentUserCount = 2,
    recentAssistantCount = 2,
    includePlanningDigest = false,
    includeOutlineDigest = false,
  } = options;
  const parts = [];
  const latestBigSummary = projectStore.bigSummaries?.at?.(-1);
  if (latestBigSummary) {
    parts.push(`【全局记忆（大总结）】\n${stringifySummaryContent(latestBigSummary.content)}`);
  }

  if (projectStore.summaries?.length) {
    const lastBigTo = latestBigSummary?.toChapter || 0;
    const abstracts = projectStore.summaries
      .filter((item) => item.chapter > lastBigTo)
      .map((item) => `第${item.chapter}章摘要：\n${stringifySummaryContent(item.abstract)}`);

    if (abstracts.length) {
      parts.push(`【各章摘要】\n${abstracts.join('\n\n')}`);
    }
  }

  if (includePlanningDigest) {
    const planningDigest = String(projectStore.planningDigest || '').trim();
    if (planningDigest) {
      parts.push(`【近期章节规划摘要】\n${planningDigest}`);
    }
  }

  if (includeOutlineDigest) {
    const outlineDigest = String(projectStore.outlineDigest || '').trim();
    if (outlineDigest) {
      parts.push(`【总纲讨论摘要】\n${outlineDigest}`);
    }
  }

  const recentUsers = [];
  const recentAssistants = [];
  const history = Array.isArray(projectStore.chatHistory) ? [...projectStore.chatHistory].reverse() : [];
  for (const msg of history) {
    if (msg?.role === 'user' && recentUsers.length < recentUserCount) {
      recentUsers.push(`用户：${String(msg.content || '').trim()}`);
    }
    if (msg?.role === 'assistant' && recentAssistants.length < recentAssistantCount) {
      recentAssistants.push(`Bot1：${String(msg.content || '').trim()}`);
    }
    if (recentUsers.length >= recentUserCount && recentAssistants.length >= recentAssistantCount) {
      break;
    }
  }

  const recentWindow = [...recentAssistants.reverse(), ...recentUsers.reverse()].filter(Boolean);
  if (recentWindow.length) {
    parts.push(`【最近对话窗口】\n${recentWindow.join('\n\n')}`);
  }

  return parts.join('\n\n');
}

export function syncPlanningResult(projectStore, fullText, latestUserInput = '', options = {}) {
  const {
    isOutlineMode = false,
    isReviseMode = false,
    appendDigest,
  } = options;

  if (isOutlineMode) {
    const draftOutline = extractOutline(fullText);
    if (!draftOutline) {
      return;
    }
    projectStore.outlineDraft = draftOutline;
    projectStore.outlineDirty = true;
    projectStore.outlineDigest = buildOutlineDigest(projectStore, latestUserInput, {
      isReviseMode,
    });
    return;
  }

  const chapterOutline = extractChapterOutline(fullText);
  if (!chapterOutline) {
    return;
  }
  projectStore.chapterOutline = chapterOutline;
  const previousDigest = String(projectStore.planningDigest || '').trim();
  projectStore.planningDigest = appendDigest(previousDigest, [
    latestUserInput ? `用户本轮补充：${latestUserInput}` : '',
    '已根据本轮讨论更新当前章节规划。',
  ]);
}

export function buildPlanningRequestContext(projectStore, options = {}) {
  const {
    isOutlineMode = false,
    recentUserCount = 2,
    recentAssistantCount = 2,
  } = options;
  return buildBot1Context(projectStore, {
    includePlanningDigest: !isOutlineMode,
    includeOutlineDigest: isOutlineMode,
    recentUserCount,
    recentAssistantCount,
  });
}

export function buildPlanningRequestPayload(projectStore, userMessage, config, options = {}) {
  const {
    isOutlineMode = false,
    currentOutline = '',
    chapterOutline = '',
    context = '',
  } = options;

  return {
    messages: [userMessage],
    config,
    current_outline: currentOutline,
    ...(isOutlineMode ? {} : { chapter_outline: chapterOutline }),
    context,
  };
}

export function buildPlanningRuntimeState(projectStore, options = {}) {
  const { isOutlineMode = false } = options;
  const stableState = {
    currentOutline: projectStore.currentOutline,
    chapterOutline: projectStore.chapterOutline,
    planningTurnsSinceExtract: projectStore.planningTurnsSinceExtract,
    planningCharsSinceExtract: projectStore.planningCharsSinceExtract,
    planningDigest: projectStore.planningDigest,
    outlineDigest: projectStore.outlineDigest,
  };

  const requestOutline = isOutlineMode
    ? String(projectStore.outlineDraft || projectStore.currentOutline || '')
    : projectStore.currentOutline;
  const requestChapterOutline = isOutlineMode ? '' : projectStore.chapterOutline;

  return {
    stableState,
    requestOutline,
    requestChapterOutline,
  };
}

export function getPendingSummaryChapter(projectStore) {
  const nextIndex = Number(projectStore?.summaries?.length || 0);
  return projectStore?.chapters?.[nextIndex] || null;
}

export function buildBot4SummaryOutline(projectStore, chapter) {
  return chapter?.chapter_outline
    || chapter?.outline
    || projectStore?.chapterOutline
    || projectStore?.currentOutline
    || '';
}

export async function ensureCurrentSummary(projectStore, config, options = {}) {
  const {
    now = nowString,
    readSSEImpl = readSSE,
    setGenerating,
    setActiveTab,
    setDisplayMode,
    setActiveSmallSummaries,
    saveProject = async () => projectStore.saveProject(),
  } = options;

  const chapter = getPendingSummaryChapter(projectStore);
  if (!chapter) {
    return false;
  }

  setGenerating?.(true);
  setActiveTab?.('small');

  const chapterNumber = Number(projectStore?.summaries?.length || 0) + 1;

  try {
    const condensed = await readSSEImpl('/api/bot4/summarize', {
      content: chapter.content,
      outline: buildBot4SummaryOutline(projectStore, chapter),
      config,
    });

    const abstract = await readSSEImpl('/api/bot4/abstract', {
      condensed,
      content: chapter.content,
      config,
      abstract_model: config.bot4_abstract_model,
    });

    const entry = {
      chapter: chapterNumber,
      condensed,
      abstract,
      time: now(),
    };

    projectStore.summaries.push(entry);
    if (projectStore.chapters[chapterNumber - 1]) {
      projectStore.chapters[chapterNumber - 1].summary = condensed;
    }

    setDisplayMode?.(chapterNumber, 'abstract');
    setActiveSmallSummaries?.([chapterNumber]);
    await saveProject();
    return entry;
  } finally {
    setGenerating?.(false);
  }
}

export function getPendingBigSummaryBatch(projectStore) {
  const lastBigTo = projectStore?.bigSummaries?.at?.(-1)?.toChapter || 0;
  const summaries = Array.isArray(projectStore?.summaries)
    ? projectStore.summaries.filter((item) => item.chapter > lastBigTo)
    : [];

  if (summaries.length === 0) {
    return null;
  }

  const fromChapter = summaries[0].chapter;
  const toChapter = summaries[summaries.length - 1].chapter;
  const abstractCount = Math.max(1, Math.floor(summaries.length * 0.6));
  const condensedCount = Math.max(0, summaries.length - abstractCount);

  return {
    summaries,
    fromChapter,
    toChapter,
    abstractCount,
    condensedCount,
  };
}

export async function generateBigSummary(projectStore, config, options = {}) {
  const {
    now = nowString,
    readSSEImpl = readSSE,
    setGenerating,
    setActiveTab,
    saveProject = async () => projectStore.saveProject(),
  } = options;

  const batch = getPendingBigSummaryBatch(projectStore);
  if (!batch) {
    return false;
  }

  setGenerating?.(true);

  try {
    const content = await readSSEImpl('/api/bot4/big-summarize', {
      summaries: batch.summaries,
      config,
      abstract_count: batch.abstractCount,
      condensed_count: batch.condensedCount,
    });

    const entry = {
      fromChapter: batch.fromChapter,
      toChapter: batch.toChapter,
      content,
      time: now(),
    };

    projectStore.bigSummaries.push(entry);
    setActiveTab?.('big');
    await saveProject();
    return entry;
  } finally {
    setGenerating?.(false);
  }
}

export async function compressSummaryMemory(summary, config, options = {}) {
  const {
    readSSEImpl = readSSE,
    maxChars = 800,
  } = options;

  const normalizedSummary = String(summary || '').trim();
  if (!normalizedSummary) {
    return '';
  }

  return readSSEImpl('/api/compress-summary', {
    summary: normalizedSummary,
    config,
    max_chars: maxChars,
  });
}

export async function runBot4Maintenance(projectStore, config, options = {}) {
  const {
    ensureCurrentSummaryOptions = {},
    generateBigSummaryOptions = {},
    bigSummaryThreshold = Number(config?.big_summary_threshold || 10),
    compressSummaryOptions = {},
    compressWhenBigSummaryGenerated = true,
  } = options;

  const summaryEntry = await ensureCurrentSummary(projectStore, config, ensureCurrentSummaryOptions);
  if (!summaryEntry) {
    return {
      summaryEntry: null,
      bigSummaryEntry: null,
      compressedBigSummary: '',
      generatedSummary: false,
      generatedBigSummary: false,
      compressedBigSummaryGenerated: false,
    };
  }

  const pendingBatch = getPendingBigSummaryBatch(projectStore);
  const shouldGenerateBigSummary = Boolean(
    pendingBatch && pendingBatch.summaries.length >= Math.max(1, Number(bigSummaryThreshold) || 1),
  );

  let bigSummaryEntry = null;
  let compressedBigSummary = '';
  if (shouldGenerateBigSummary) {
    bigSummaryEntry = await generateBigSummary(projectStore, config, generateBigSummaryOptions);
    if (
      compressWhenBigSummaryGenerated
      && bigSummaryEntry?.content
    ) {
      compressedBigSummary = await compressSummaryMemory(
        String(bigSummaryEntry.content || ''),
        config,
        compressSummaryOptions,
      );
      if (compressedBigSummary) {
        bigSummaryEntry.content = compressedBigSummary;
      }
    }
  }

  return {
    summaryEntry,
    bigSummaryEntry,
    compressedBigSummary,
    generatedSummary: Boolean(summaryEntry),
    generatedBigSummary: Boolean(bigSummaryEntry),
    compressedBigSummaryGenerated: Boolean(compressedBigSummary),
  };
}

export function restorePlanningRuntimeState(projectStore, stableState = {}) {
  projectStore.currentOutline = stableState.currentOutline ?? '';
  projectStore.chapterOutline = stableState.chapterOutline ?? '';
  projectStore.planningTurnsSinceExtract = stableState.planningTurnsSinceExtract ?? 0;
  projectStore.planningCharsSinceExtract = stableState.planningCharsSinceExtract ?? 0;
  projectStore.planningDigest = stableState.planningDigest ?? '';
  projectStore.outlineDigest = stableState.outlineDigest ?? '';
}

export function buildBot2Context(projectStore) {
  const parts = [];
  const latestBigSummary = projectStore.bigSummaries?.at?.(-1);
  if (latestBigSummary) {
    parts.push(`【全局记忆（大总结）】\n${stringifySummaryContent(latestBigSummary.content)}`);
  }

  if (projectStore.summaries?.length) {
    const lastBigTo = latestBigSummary?.toChapter || 0;
    const condensed = projectStore.summaries
      .filter((item) => item.chapter > lastBigTo)
      .map((item) => `第${item.chapter}章缩略：\n${stringifySummaryContent(item.condensed)}`);

    if (condensed.length) {
      parts.push(`【近期章节缩略原文】\n${condensed.join('\n\n')}`);
    }
  }

  return parts.join('\n\n');
}

export function getPreviousEnding(projectStore, maxLength = 500) {
  const lastChapter = projectStore.chapters?.at?.(-1);
  const content = lastChapter?.content || '';
  if (!content) {
    return '';
  }

  return content.length <= maxLength ? content : content.slice(-maxLength);
}

export function buildRewriteBrief(reviewLike, passScore = 8) {
  if (typeof reviewLike === 'string') {
    return reviewLike.trim();
  }

  const review = reviewLike && typeof reviewLike === 'object'
    ? reviewLike
    : { items: Array.isArray(reviewLike) ? reviewLike : [] };
  const existing = String(review.rewrite_brief || review.rewrite_plan || '').trim();
  if (existing) {
    return existing;
  }

  const items = normalizeReviewItems(review.items ?? reviewLike);
  const scores = review?.scores && typeof review.scores === 'object' ? review.scores : {};
  const analysis = String(review.analysis || '').trim();
  const failingDims = Object.entries(REVIEW_DIM_LABELS)
    .filter(([key]) => Number(scores[key] ?? 0) < passScore)
    .map(([, label]) => label);

  const lines = [];
  if (failingDims.length > 0) {
    lines.push(`先把${failingDims.join('、')}拉回及格线，优先处理硬伤，再做润色。`);
  } else {
    lines.push('保留当前成稿的优点，只做针对性的局部修正，不要整章推倒重来。');
  }

  const priorityItems = [...items]
    .sort((left, right) => {
      const severityGap =
        (REVIEW_SEVERITY_ORDER[left.severity] ?? 9) - (REVIEW_SEVERITY_ORDER[right.severity] ?? 9);
      if (severityGap !== 0) {
        return severityGap;
      }
      return left.dim.localeCompare(right.dim);
    })
    .slice(0, 4);

  priorityItems.forEach((item, index) => {
    const label = REVIEW_DIM_LABELS[item.dim] || item.dim || '问题';
    const location = item.location || '全文';
    const action = item.suggestion || item.problem || '请直接重写这一处';
    lines.push(`${index + 1}. [${label}] ${location}：${action}`);
  });

  if (analysis) {
    lines.push(`整体把握：${analysis.split('\n')[0].trim().slice(0, 80)}`);
  }

  return lines.join('\n').trim();
}

export function formatSuggestionsText(reviewLike, passScore = 8) {
  if (typeof reviewLike === 'string') {
    return reviewLike.trim();
  }

  const forceFullRewrite = Boolean(reviewLike?.force_full_rewrite);
  const userSuggestions = String(reviewLike?.user_suggestions || '').trim();
  const items = normalizeReviewItems(reviewLike?.items ?? reviewLike);
  const rewriteBrief = buildRewriteBrief(reviewLike, passScore);
  const parts = [];
  if (userSuggestions) {
    parts.push(`【用户补充建议（最高优先级）】\n${userSuggestions}`);
  }

  if (forceFullRewrite) {
    parts.push('【整章重写要求】\n请基于当前章节目标整章重写，不沿用旧稿句级修补思路。')
    if (rewriteBrief) {
      parts.push(`【Bot3重写指令】\n${rewriteBrief}`);
    }
    return parts.join('\n\n').trim();
  }

  if (items.length === 0) {
    if (rewriteBrief) {
      parts.push(`【Bot3重写指令】\n${rewriteBrief}`);
    }
    return parts.join('\n\n').trim();
  }

  const detailText = items
    .map((item, index) => {
      const title = item.location ? `${item.location} - ${item.problem}` : item.problem;
      return `${index + 1}. ${title}\n修改建议：${item.suggestion}`;
    })
    .join('\n\n');

  if (!rewriteBrief) {
    parts.push(detailText);
    return parts.join('\n\n').trim();
  }

  parts.push(`【Bot3重写指令】\n${rewriteBrief}\n\n【逐条修改建议】\n${detailText}`);
  return parts.join('\n\n').trim();
}

export function getBot2FreedomPolicy(rewriteAttempt = 0) {
  const normalized = Number(rewriteAttempt || 0);
  if (normalized <= 0) {
    return 'high';
  }
  if (normalized === 1) {
    return 'medium';
  }
  return 'low';
}

export function buildBot2RewritePacket(reviewLike, options = {}) {
  const {
    rewriteAttempt = 1,
    selfReviewText = '',
    reuseSystemSuggestions = true,
    passScore = 8,
  } = options;
  const userInstruction = String(selfReviewText || '').trim();
  const hasSelfReview = Boolean(userInstruction);
  const defaultFreedomPolicy = getBot2FreedomPolicy(rewriteAttempt);
  const systemReviewBrief = buildRewriteBrief(reviewLike, passScore);
  const forceFullRewrite = Boolean(reviewLike?.force_full_rewrite);

  if (!hasSelfReview) {
    return {
      rewrite_mode: forceFullRewrite ? 'full_rewrite' : 'system',
      user_review_instruction: '',
      system_review_brief: systemReviewBrief,
      instruction_priority: 'system_only',
      freedom_policy: forceFullRewrite ? 'high' : defaultFreedomPolicy,
      force_full_rewrite: forceFullRewrite,
    };
  }

  if (reuseSystemSuggestions) {
    return {
      rewrite_mode: forceFullRewrite ? 'full_rewrite_hybrid' : 'hybrid',
      user_review_instruction: userInstruction,
      system_review_brief: systemReviewBrief,
      instruction_priority: 'user_over_system',
      freedom_policy: forceFullRewrite ? 'high' : defaultFreedomPolicy,
      force_full_rewrite: forceFullRewrite,
    };
  }

  return {
    rewrite_mode: 'custom',
    user_review_instruction: userInstruction,
    system_review_brief: '',
    instruction_priority: 'user_over_system',
    freedom_policy: 'bypass',
    force_full_rewrite: forceFullRewrite,
  };
}

export function describeBot2RewritePacket(packet) {
  if (!packet || typeof packet !== 'object') {
    return null;
  }

  const rewriteMode = String(packet.rewrite_mode || 'system').trim() || 'system';
  const freedomPolicy = String(packet.freedom_policy || 'medium').trim() || 'medium';
  const instructionPriority = String(packet.instruction_priority || 'system_only').trim() || 'system_only';
  const hasUserInstruction = Boolean(String(packet.user_review_instruction || '').trim());
  const hasSystemBrief = Boolean(String(packet.system_review_brief || '').trim());

  const modeLabel = {
    system: '系统审稿驱动',
    hybrid: '用户主导 + 系统 brief',
    custom: '完全用户自定义',
    full_rewrite: '系统驱动整章重写',
    full_rewrite_hybrid: '用户主导整章重写',
  }[rewriteMode] || rewriteMode;

  const freedomLabel = {
    high: '高自由度',
    medium: '中自由度',
    low: '低自由度',
    bypass: '旁路默认自由度',
  }[freedomPolicy] || freedomPolicy;

  const priorityLabel = {
    system_only: '系统建议主导',
    user_over_system: '用户建议优先',
  }[instructionPriority] || instructionPriority;

  const modeHint = {
    system: '按 Bot3 / 系统审稿结果定点修补。',
    hybrid: '用户意图优先，系统建议只保留总体 brief。',
    custom: '只执行你的自定义改写目标，不再复用系统建议。',
    full_rewrite: '这一轮将整章重写，不再按旧稿问题点局部修补。',
    full_rewrite_hybrid: '这一轮将按你的意图主导整章重写，系统 brief 只提供方向。',
  }[rewriteMode] || '按当前 packet 执行改写。';

  const targetTypeLabel = rewriteMode.includes('full_rewrite')
    ? '整章重写'
    : '局部修补';

  return {
    modeLabel,
    freedomLabel,
    priorityLabel,
    targetTypeLabel,
    modeHint,
    hasUserInstruction,
    hasSystemBrief,
    raw: {
      rewrite_mode: rewriteMode,
      freedom_policy: freedomPolicy,
      instruction_priority: instructionPriority,
    },
  };
}

export function nowString() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function stringifySummaryContentForDisplay(content) {
  return stringifySummaryContent(content);
}
