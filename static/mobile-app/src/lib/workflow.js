import { apiUrl, loginUrl } from '@/api/url';

const BOT_DEFAULTS = {
  bot1: { temperature: 0.7, max_tokens: 4096 },
  bot2: { temperature: 0.8, max_tokens: 4096 },
  bot3: { temperature: 0.3, max_tokens: 2048 },
  bot4: { temperature: 0.5, max_tokens: 4096 },
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
  const { signal, onChunk } = options;
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

export function stripOutline(text) {
  return String(text || '')
    .replace(/<outline>[\s\S]*?<\/outline>/gi, '')
    .replace(/<chapter_outline>[\s\S]*?<\/chapter_outline>/gi, '')
    .trim();
}

export function buildBot1Context(projectStore) {
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

  return parts.join('\n\n');
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

  const items = normalizeReviewItems(reviewLike?.items ?? reviewLike);
  const rewriteBrief = buildRewriteBrief(reviewLike, passScore);
  if (items.length === 0) {
    return rewriteBrief ? `【Bot3重写指令】\n${rewriteBrief}` : '';
  }

  const detailText = items
    .map((item, index) => {
      const title = item.location ? `${item.location} - ${item.problem}` : item.problem;
      return `${index + 1}. ${title}\n修改建议：${item.suggestion}`;
    })
    .join('\n\n');

  if (!rewriteBrief) {
    return detailText;
  }

  return `【Bot3重写指令】\n${rewriteBrief}\n\n【逐条修改建议】\n${detailText}`.trim();
}

export function nowString() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function stringifySummaryContentForDisplay(content) {
  return stringifySummaryContent(content);
}
