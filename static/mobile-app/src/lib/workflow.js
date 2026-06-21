import { apiUrl, loginUrl } from '@/api/url';

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

  const userSuggestions = String(reviewLike?.user_suggestions || '').trim();
  const items = normalizeReviewItems(reviewLike?.items ?? reviewLike);
  const rewriteBrief = buildRewriteBrief(reviewLike, passScore);
  const parts = [];
  if (userSuggestions) {
    parts.push(`【用户补充建议（最高优先级）】\n${userSuggestions}`);
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

export function nowString() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function stringifySummaryContentForDisplay(content) {
  return stringifySummaryContent(content);
}
