<template>
  <div class="memory-view">
    <div class="memory-status-bar">
      <div class="status-left">
        <span class="status-text">
          <van-icon name="flag-o" size="18" />
          <span class="status-copy">全局记忆库</span>
        </span>
      </div>
      <div class="status-right">
        <van-button
          size="mini"
          type="primary"
          plain
          :loading="isGeneratingBig"
          @click="generateBigSummary"
        >
          生成大总结
        </van-button>
      </div>
    </div>

    <div class="memory-content">
      <van-tabs v-model:active="activeTab" sticky color="#1989fa" animated swipeable>
        <van-tab title="章节摘要" name="small">
          <div class="tab-content-area">
            <van-loading v-if="isGeneratingSmall" size="24px" vertical>正在生成章节总结...</van-loading>

            <van-collapse v-else v-model="activeSmallSummaries">
              <van-collapse-item
                v-for="summary in summaryList"
                :key="summary.chapter"
                :name="summary.chapter"
                :title="`第 ${summary.chapter} 章`"
                :value="summary.time"
              >
                <div class="summary-toggle">
                  <van-radio-group
                    :model-value="getDisplayMode(summary.chapter)"
                    direction="horizontal"
                    class="mode-radio"
                    @update:model-value="setDisplayMode(summary.chapter, $event)"
                  >
                    <van-radio name="abstract">摘要</van-radio>
                    <van-radio name="condensed">缩略原文</van-radio>
                  </van-radio-group>
                </div>

                <div class="summary-text">
                  <pre>{{ getDisplayText(summary) }}</pre>
                </div>
              </van-collapse-item>
            </van-collapse>

            <van-empty
              v-if="!isGeneratingSmall && summaryList.length === 0"
              description="暂无章节摘要"
              image="search"
            />
          </div>
        </van-tab>

        <van-tab title="全局大总结" name="big">
          <div class="tab-content-area">
            <div class="big-summary-card" v-for="(summary, index) in bigSummaryList" :key="index">
              <div class="big-header">
                <span class="big-range">第 {{ summary.fromChapter }} - {{ summary.toChapter }} 章总结</span>
                <span class="big-time">{{ summary.time }}</span>
              </div>
              <pre class="big-content">{{ formatBigSummary(summary.content) }}</pre>
            </div>
            <van-empty v-if="bigSummaryList.length === 0" description="暂无大总结记录" image="search" />
          </div>
        </van-tab>
      </van-tabs>
    </div>

    <div class="bottom-nav">
      <van-button icon="home-o" type="default" size="small" class="nav-btn" @click="backToProjectList">
        返回列表
      </van-button>

      <van-button
        icon="play-circle-o"
        type="primary"
        size="small"
        class="nav-btn"
        :disabled="isGeneratingSmall || isGeneratingBig"
        @click="startNextChapter"
      >
        进入下一章规划
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { showConfirmDialog, showToast } from 'vant';

import { useProjectStore } from '@/stores/project';
import {
  getRuntimeConfig,
  nowString,
  readSSE,
  stringifySummaryContentForDisplay,
} from '@/lib/workflow';

const emit = defineEmits(['start-next', 'back-home']);

const projectStore = useProjectStore();

const activeTab = ref('small');
const activeSmallSummaries = ref([]);
const displayModes = ref({});
const isGeneratingSmall = ref(false);
const isGeneratingBig = ref(false);

const summaryList = computed(() => projectStore.summaries || []);
const bigSummaryList = computed(() => projectStore.bigSummaries || []);

const getDisplayMode = (chapter) => displayModes.value[chapter] || 'abstract';

const setDisplayMode = (chapter, mode) => {
  displayModes.value = {
    ...displayModes.value,
    [chapter]: mode,
  };
};

const getDisplayText = (summary) => {
  const mode = getDisplayMode(summary.chapter);
  return mode === 'condensed'
    ? stringifySummaryContentForDisplay(summary.condensed)
    : stringifySummaryContentForDisplay(summary.abstract);
};

const formatBigSummary = (content) => stringifySummaryContentForDisplay(content);

const getPendingChapter = () => {
  const nextIndex = projectStore.summaries.length;
  return projectStore.chapters[nextIndex] || null;
};

const ensureCurrentSummary = async () => {
  const chapter = getPendingChapter();
  if (!chapter || isGeneratingSmall.value) {
    return false;
  }

  const config = getRuntimeConfig(projectStore.config);
  if (!config) {
    showToast('请先在设置页填写 Bot4 配置');
    return false;
  }

  const chapterNumber = projectStore.summaries.length + 1;
  isGeneratingSmall.value = true;
  activeTab.value = 'small';

  try {
    const condensed = await readSSE('/api/bot4/summarize', {
      content: chapter.content,
      outline: chapter.chapter_outline || chapter.outline || projectStore.chapterOutline || projectStore.currentOutline,
      config,
    });

    const abstract = await readSSE('/api/bot4/abstract', {
      condensed,
      content: chapter.content,
      config,
      abstract_model: config.bot4_abstract_model,
    });

    const entry = {
      chapter: chapterNumber,
      condensed,
      abstract,
      time: nowString(),
    };

    projectStore.summaries.push(entry);
    if (projectStore.chapters[chapterNumber - 1]) {
      projectStore.chapters[chapterNumber - 1].summary = condensed;
    }
    setDisplayMode(chapterNumber, 'abstract');
    activeSmallSummaries.value = [chapterNumber];
    await projectStore.saveProject();
    return true;
  } catch (error) {
    showToast(error.message || '章节总结生成失败');
    return false;
  } finally {
    isGeneratingSmall.value = false;
  }
};

const generateBigSummary = () => {
  const lastBigTo = projectStore.bigSummaries.at(-1)?.toChapter || 0;
  const pendingSummaries = projectStore.summaries.filter((item) => item.chapter > lastBigTo);
  if (pendingSummaries.length === 0 || isGeneratingBig.value) {
    showToast('没有可生成的大总结内容');
    return;
  }

  const config = getRuntimeConfig(projectStore.config);
  if (!config) {
    showToast('请先在设置页填写 Bot4 配置');
    return;
  }

  const fromChapter = pendingSummaries[0].chapter;
  const toChapter = pendingSummaries[pendingSummaries.length - 1].chapter;
  const abstractCount = Math.max(1, Math.floor(pendingSummaries.length * 0.6));
  const condensedCount = Math.max(0, pendingSummaries.length - abstractCount);

  showConfirmDialog({
    title: '生成大总结',
    message: `将整合第 ${fromChapter} - ${toChapter} 章的记忆内容，确定继续吗？`,
  })
    .then(async () => {
      isGeneratingBig.value = true;
      try {
        const content = await readSSE('/api/bot4/big-summarize', {
          summaries: pendingSummaries,
          config,
          abstract_count: abstractCount,
          condensed_count: condensedCount,
        });

        projectStore.bigSummaries.push({
          fromChapter,
          toChapter,
          content,
          time: nowString(),
        });
        activeTab.value = 'big';
        await projectStore.saveProject();
        showToast('大总结生成完成');
      } catch (error) {
        showToast(error.message || '大总结生成失败');
      } finally {
        isGeneratingBig.value = false;
      }
    })
    .catch(() => {});
};

const backToProjectList = () => {
  emit('back-home');
};

const startNextChapter = async () => {
  // 准备一条引导消息预填到 Planning 输入框 —— 让 Bot1 主动用 Bot4 写入上下文的小总结，
  // 回顾本章 + 给出下一章方案。Planning.vue 会监听 projectStore.pendingPlanningPrompt 消费。
  const completedChapter = projectStore.chapters.length > 0
    ? projectStore.chapters.length
    : (projectStore.summaries.at?.(-1)?.chapter || 0);
  if (completedChapter > 0) {
    const next = completedChapter + 1;
    projectStore.pendingPlanningPrompt = `第${completedChapter}章已完成（小总结见上下文【各章摘要】）。请你：\n`
      + `1. 用一段话回顾本章关键剧情和未回收的伏笔\n`
      + `2. 给出第${next}章的 2-3 个走向方案，让我挑选/调整\n`
      + `3. 顺带说一下是否需要微调总大纲`;
  }

  projectStore.currentContent = '';
  projectStore.chapterOutline = '';
  await projectStore.saveProject();
  emit('start-next');
};

defineExpose({
  ensureCurrentSummary,
});
</script>

<style scoped>
.memory-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #f7f8fa;
}

.memory-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background-color: #fff;
  border-bottom: 1px solid #ebedf0;
  flex-shrink: 0;
}

.status-left .status-text {
  display: flex;
  align-items: center;
  color: #323233;
  font-size: 15px;
  font-weight: bold;
}

.status-copy {
  margin-left: 4px;
}

.memory-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: hidden;
}

:deep(.van-tabs) {
  display: flex;
  flex-direction: column;
  height: 100%;
}

:deep(.van-tabs__content) {
  flex: 1;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.tab-content-area {
  padding: 12px;
}

.summary-toggle {
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #ebedf0;
}

.mode-radio {
  font-size: 13px;
}

.mode-radio :deep(.van-radio__label) {
  color: #646566;
}

.summary-text {
  color: #323233;
  font-size: 14px;
  line-height: 1.6;
}

.summary-text pre,
.big-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.big-summary-card {
  margin-bottom: 16px;
  padding: 16px;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.big-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebedf0;
}

.big-range {
  color: #323233;
  font-size: 16px;
  font-weight: bold;
}

.big-time {
  color: #969799;
  font-size: 12px;
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
