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
  ensureCurrentSummary as ensureCurrentSummaryTask,
  generateBigSummary as generateBigSummaryTask,
  getPendingBigSummaryBatch,
  getRuntimeConfig,
  nowString,
  readSSE,
  runBot4Maintenance,
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

  try {
    const entry = await ensureCurrentSummaryTask(projectStore, config, {
      now: nowString,
      readSSEImpl: readSSE,
      setGenerating: (value) => {
        isGeneratingSmall.value = value;
      },
      setActiveTab: (value) => {
        activeTab.value = value;
      },
      setDisplayMode,
      setActiveSmallSummaries: (value) => {
        activeSmallSummaries.value = value;
      },
    });
    return Boolean(entry);
  } catch (error) {
    showToast(error.message || '章节总结生成失败');
    return false;
  }
};

const generateBigSummary = () => {
  const batch = getPendingBigSummaryBatch(projectStore);
  if (!batch || isGeneratingBig.value) {
    showToast('没有可生成的大总结内容');
    return;
  }

  const config = getRuntimeConfig(projectStore.config);
  if (!config) {
    showToast('请先在设置页填写 Bot4 配置');
    return;
  }

  showConfirmDialog({
    title: '生成大总结',
    message: `将整合第 ${batch.fromChapter} - ${batch.toChapter} 章的记忆内容，确定继续吗？`,
  })
    .then(async () => {
      try {
        const entry = await generateBigSummaryTask(projectStore, config, {
          now: nowString,
          readSSEImpl: readSSE,
          setGenerating: (value) => {
            isGeneratingBig.value = value;
          },
          setActiveTab: (value) => {
            activeTab.value = value;
          },
        });

        if (entry) {
          showToast('大总结生成完成');
        }
      } catch (error) {
        showToast(error.message || '大总结生成失败');
      }
    })
    .catch(() => {});
};

const backToProjectList = () => {
  emit('back-home');
};

const startNextChapter = async () => {
  if (String(projectStore.outlineMode || '').trim()) {
    showToast('请先完成当前总纲设计/修正，再开始下一章规划');
    return;
  }

  const latestSummary = projectStore.summaries.at?.(-1) || null;
  const latestBigSummary = projectStore.bigSummaries.at?.(-1) || null;
  const completedChapter = latestSummary?.chapter
    || (projectStore.chapters.length > 0 ? projectStore.chapters.length : 0);

  if (completedChapter > 0) {
    const next = completedChapter + 1;
    const hasFreshBigSummary = latestBigSummary && Number(latestBigSummary.toChapter || 0) >= completedChapter;
    const memoryHint = hasFreshBigSummary
      ? '本章小总结与阶段大总结都已写入上下文记忆。'
      : '本章小总结已写入上下文记忆。';

    projectStore.pendingPlanningPrompt = `第${completedChapter}章已完成，${memoryHint}请你：\n`
      + `1. 先用一段话回顾上一章真正留下的推进结果，而不是重复表面剧情\n`
      + `2. 基于当前记忆，给出第${next}章的 2-3 个可执行走向方案，让我挑选/调整\n`
      + `3. 如果近期规划已经成形，就顺手更新当前章节大纲；如果没有，再明确还差哪个决策点`;
  }

  projectStore.currentContent = '';
  projectStore.chapterOutline = '';
  await projectStore.saveProject();
  emit('start-next');
};

defineExpose({
  ensureCurrentSummary,
  runAutoMaintenance: async () => {
    if (isGeneratingSmall.value || isGeneratingBig.value) {
      return false;
    }

    const config = getRuntimeConfig(projectStore.config);
    if (!config) {
      showToast('请先在设置页填写 Bot4 配置');
      return false;
    }

    try {
      const result = await runBot4Maintenance(projectStore, config, {
        bigSummaryThreshold: config.big_summary_threshold,
        compressWhenBigSummaryGenerated: true,
        compressSummaryOptions: {
          readSSEImpl: readSSE,
          maxChars: 800,
        },
        ensureCurrentSummaryOptions: {
          now: nowString,
          readSSEImpl: readSSE,
          setGenerating: (value) => {
            isGeneratingSmall.value = value;
          },
          setActiveTab: (value) => {
            activeTab.value = value;
          },
          setDisplayMode,
          setActiveSmallSummaries: (value) => {
            activeSmallSummaries.value = value;
          },
        },
        generateBigSummaryOptions: {
          now: nowString,
          readSSEImpl: readSSE,
          setGenerating: (value) => {
            isGeneratingBig.value = value;
          },
          setActiveTab: (value) => {
            activeTab.value = value;
          },
        },
      });
      return result;
    } catch (error) {
      showToast(error.message || 'Bot4 自动维护失败');
      return false;
    }
  },
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
