<template>
  <div class="writing-view">
    <div class="writing-status-bar">
      <div class="status-left">
        <span class="status-text" v-if="isGenerating">Bot2 正在创作中...</span>
        <span class="status-text success-text" v-else-if="hasContent">创作完成</span>
        <span class="status-text idle-text" v-else>等待开始创作</span>
      </div>
      <div class="status-right">
        <van-button
          v-if="isGenerating"
          size="mini"
          type="danger"
          plain
          @click="stopGenerating"
        >
          停止生成
        </van-button>
        <van-button
          v-else
          size="mini"
          type="primary"
          plain
          :disabled="!canGenerate"
          @click="rewriteContent"
        >
          重新生成
        </van-button>
      </div>
    </div>

    <div class="content-area" ref="contentAreaRef">
      <div v-if="!projectStore.currentContent" class="chapter-placeholder">等待生成...</div>
      <div v-else class="chapter-content">{{ projectStore.currentContent }}</div>
      <span v-if="isGenerating" class="typing-cursor">|</span>
    </div>

    <div class="bottom-nav">
      <van-button
        icon="arrow-left"
        type="default"
        size="small"
        class="nav-btn"
        @click="$emit('prev')"
      >
        返回修改大纲
      </van-button>

      <van-button
        icon="arrow"
        type="primary"
        size="small"
        class="nav-btn"
        :disabled="isGenerating || !hasContent"
        @click="$emit('next')"
      >
        去审核
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue';
import { showToast } from 'vant';

import { useProjectStore } from '@/stores/project';
import {
  buildBot2Context,
  formatSuggestionsText,
  getPreviousEnding,
  getRuntimeConfig,
  readSSE,
} from '@/lib/workflow';

const emit = defineEmits(['prev', 'next']);

const projectStore = useProjectStore();
const contentAreaRef = ref(null);
const isGenerating = ref(false);
const abortController = ref(null);

const hasContent = computed(() => Boolean(String(projectStore.currentContent || '').trim()));
const canGenerate = computed(() => Boolean(projectStore.currentOutline || projectStore.chapterOutline));
const requestStyleId = computed(() =>
  String(projectStore.selectedStyleId || projectStore.defaultStyleId || '').trim(),
);
const requestWordCount = computed(() => {
  // 字数不设上限，用户按 Bot2 的 max_tokens 自行权衡
  const nextValue = Math.round(
    Number(projectStore.wordCount || projectStore.defaultWordCount) || 800,
  );
  return nextValue >= 1 ? nextValue : 800;
});

// 旧版用 v-html + replace(\\n, <br/>) 渲染正文，但没转义 < > & 等 HTML 字符。
// 模型生成的小说里只要出现 "<"（对话/不等号/特殊符号），浏览器会把它当作 HTML 标签起点，
// 后续内容被吞掉直到遇到 ">" 才"恢复"，表现为"生成到一半就不再继续显示"。
// 现在改用 textContent + white-space: pre-wrap（见 .chapter-content 样式），
// 浏览器把所有字符当作纯文本，\\n 由 CSS 渲染成换行。

const scrollToBottom = async () => {
  await nextTick();
  if (contentAreaRef.value) {
    contentAreaRef.value.scrollTop = contentAreaRef.value.scrollHeight;
  }
};

watch(() => projectStore.currentContent, () => {
  if (isGenerating.value) {
    scrollToBottom();
  }
});

const startGenerating = async (suggestions = []) => {
  if (isGenerating.value) {
    return;
  }

  const config = getRuntimeConfig(projectStore.config);
  if (!config) {
    showToast('请先在设置页填写 Bot2 配置');
    return;
  }

  if (!canGenerate.value) {
    showToast('先确认总大纲或章节大纲');
    return;
  }

  // suggestions can be:
  //   string                              → use as-is (legacy callers)
  //   []                                  → "全部重写" / fresh generation, no suggestions
  //   review-like object with items/brief → format via formatSuggestionsText
  //   non-empty array of items            → format via formatSuggestionsText
  // Without explicit branching, an object would coerce to "[object Object]" via String()
  // and Bot2 would receive nonsense as the rewrite directive.
  const passScoreForFormat = Number(projectStore.config?.pass_score ?? 8);
  let suggestionsText = '';
  if (typeof suggestions === 'string') {
    suggestionsText = suggestions.trim();
  } else if (Array.isArray(suggestions)) {
    suggestionsText = suggestions.length === 0
      ? ''
      : formatSuggestionsText(suggestions, passScoreForFormat);
  } else if (suggestions && typeof suggestions === 'object') {
    suggestionsText = formatSuggestionsText(suggestions, passScoreForFormat);
  }
  const isRewrite = Boolean(suggestionsText);
  const previousContent = String(projectStore.currentContent || '');

  projectStore.currentContent = '';
  isGenerating.value = true;
  abortController.value = new AbortController();
  await scrollToBottom();

  const body = isRewrite
    ? {
        outline: projectStore.currentOutline,
        chapter_outline: projectStore.chapterOutline,
        content: previousContent,
        suggestions: suggestionsText,
        config,
        style_id: requestStyleId.value,
        word_count: requestWordCount.value,
        tips: '',
        prev_ending: getPreviousEnding(projectStore),
        bot2_context: buildBot2Context(projectStore),
      }
    : {
        outline: projectStore.currentOutline,
        chapter_outline: projectStore.chapterOutline,
        config,
        style_id: requestStyleId.value,
        word_count: requestWordCount.value,
        tips: '',
        prev_ending: getPreviousEnding(projectStore),
        bot2_context: buildBot2Context(projectStore),
      };

  try {
    const fullText = await readSSE(
      isRewrite ? '/api/bot2/rewrite' : '/api/bot2/write',
      body,
      {
        signal: abortController.value.signal,
        onChunk: (_chunk, full) => {
          projectStore.currentContent = full;
          scrollToBottom();
        },
      },
    );

    projectStore.currentContent = fullText;
    await projectStore.saveProject();
  } catch (error) {
    if (!projectStore.currentContent && previousContent) {
      projectStore.currentContent = previousContent;
    }
    if (error.name !== 'AbortError') {
      showToast(error.message || 'Bot2 生成失败');
    }
  } finally {
    isGenerating.value = false;
    abortController.value = null;
  }
};

const stopGenerating = () => {
  abortController.value?.abort();
  isGenerating.value = false;
};

const rewriteContent = () => {
  startGenerating();
};

defineExpose({
  startGenerating,
});
</script>

<style scoped>
.writing-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #fff;
}

.writing-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background-color: #f7f8fa;
  border-bottom: 1px solid #ebedf0;
  flex-shrink: 0;
}

.status-text {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: #1989fa;
}

.success-text {
  color: #07c160;
}

.idle-text {
  color: #969799;
}

.content-area {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  color: #323233;
  font-size: 16px;
  line-height: 1.8;
  font-family: 'Georgia', 'Times New Roman', 'Kaiti', 'STKaiti', serif;
  letter-spacing: 1px;
}

.chapter-content {
  text-align: justify;
  white-space: pre-wrap;        /* 保留模型输出的换行与连续空格，无需用 v-html */
  word-break: break-word;
}

.chapter-placeholder {
  color: #969799;
  font-style: italic;
}

.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1.2em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background-color: #1989fa;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0;
  }
}

.bottom-nav {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background-color: #fff;
  border-top: 1px solid #ebedf0;
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.02);
  flex-shrink: 0;
}

.nav-btn {
  flex: 1;
}
</style>
