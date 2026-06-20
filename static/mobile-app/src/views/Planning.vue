<template>
  <div class="planning-view">
    <div class="status-bar">
      <div class="status-left">
        <span class="status-text">{{ pageTitle }}</span>
      </div>
      <div class="status-right">
        <van-button size="mini" type="primary" plain @click="$emit('show-outline')">查看大纲</van-button>
        <van-button
          v-if="isNormalPlanningMode"
          size="mini"
          icon="arrow"
          type="primary"
          class="next-btn"
          :disabled="isGenerating || !canProceedToWriting"
          @click="confirmOutlineAndNext"
        >
          确认并创作
        </van-button>
      </div>
    </div>

    <div class="mode-banner" :class="isOutlineDesignMode ? 'outline-design-banner' : 'chapter-planning-banner'">
      <div class="mode-banner-title">{{ modeTitle }}</div>
      <div class="mode-banner-copy">{{ modeDescription }}</div>
    </div>

    <div class="chat-area" ref="chatAreaRef">
      <div v-if="isOutlineWorkspaceMode" class="outline-draft-panel">
        <div class="outline-draft-header">
          <span class="outline-draft-title">当前总纲草稿</span>
          <span class="outline-draft-status">{{ outlineDraftStatus }}</span>
        </div>
        <div class="outline-draft-content">{{ outlineDraftPreview }}</div>
        <div class="outline-draft-actions">
          <van-button
            size="small"
            plain
            :disabled="isGenerating || !canDiscardOutlineDraft"
            @click="discardOutlineDraft"
          >
            放弃草稿
          </van-button>
          <van-button
            size="small"
            type="primary"
            :disabled="isGenerating || !canSubmitOutlineDraft"
            @click="submitOutlineDraft"
          >
            提交总纲
          </van-button>
        </div>
      </div>

      <div
        v-for="(msg, index) in displayHistory"
        :key="index"
        :class="['chat-bubble', msg.role === 'user' ? 'user-msg' : 'ai-msg']"
      >
        <div class="msg-content" v-html="formatMessage(msg.content, msg.role)"></div>
      </div>
      <div v-if="isGenerating" class="chat-bubble ai-msg loading-msg">
        <van-loading type="spinner" size="20px" />
        <span class="loading-text">Bot1 正在思考...</span>
      </div>
    </div>

    <div class="input-area">
      <van-field
        v-model="inputMsg"
        rows="1"
        autosize
        type="textarea"
        :placeholder="inputPlaceholder"
        class="chat-input"
        :disabled="isGenerating"
        @keydown.enter.exact.prevent="sendMessage"
      >
        <template #button>
          <van-button
            size="small"
            type="primary"
            :loading="isGenerating"
            :disabled="!inputMsg.trim()"
            @click="sendMessage"
          >
            发送
          </van-button>
        </template>
      </van-field>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { showToast } from 'vant';

import { useProjectStore } from '@/stores/project';
import {
  buildBot1Context,
  extractChapterOutline,
  extractOutline,
  getRuntimeConfig,
  readSSE,
  stripOutline,
} from '@/lib/workflow';

const emit = defineEmits(['next', 'show-outline']);

const projectStore = useProjectStore();
const inputMsg = ref('');
const isGenerating = ref(false);
const chatAreaRef = ref(null);

// Memory.vue 进入下一章规划时会写入 pendingPlanningPrompt。
// 这里监听一次：输入框为空就填入引导消息；不论是否填入都消费掉信号，避免反复触发。
watch(
  () => projectStore.pendingPlanningPrompt,
  (next) => {
    if (!next) {
      return;
    }
    if (!inputMsg.value.trim()) {
      inputMsg.value = next;
    }
    projectStore.pendingPlanningPrompt = '';
  },
  { immediate: true },
);

const isOutlineDesignMode = computed(() => projectStore.outlineMode === 'design');
const isOutlineReviseMode = computed(() => projectStore.outlineMode === 'revise');
const isOutlineWorkspaceMode = computed(() => isOutlineDesignMode.value || isOutlineReviseMode.value);
const isNormalPlanningMode = computed(() => !isOutlineDesignMode.value && !isOutlineReviseMode.value);

const welcomeMessage = computed(() => ({
  role: 'assistant',
  content: isOutlineDesignMode.value
    ? '你好，我是 Bot1。现在我们先做正式总纲设计。你可以直接告诉我这本书的题材、主角、时代背景、核心冲突，或你已经想好的世界观设定，我会先帮你把总纲方向梳理出来。'
    : '你好，我是 Bot1。先把你当前想推进的剧情、人物、冲突或设定告诉我，我会帮你梳理当前章节规划，并结合已有正式总纲继续讨论。',
}));

const displayHistory = computed(() => (
  projectStore.chatHistory.length > 0 ? projectStore.chatHistory : [welcomeMessage.value]
));
const pageTitle = computed(() => {
  if (isOutlineDesignMode.value) {
    return '总纲设计';
  }
  if (isOutlineReviseMode.value) {
    return '总纲修正';
  }
  return '章节规划';
});
const modeTitle = computed(() => {
  if (isOutlineDesignMode.value) {
    return '当前处于正式总纲设计模式';
  }
  if (isOutlineReviseMode.value) {
    return '当前处于正式总纲修正模式';
  }
  return '当前处于章节规划模式';
});
const modeDescription = computed(() => {
  if (isOutlineDesignMode.value) {
    return '这一页先不做章节推进，而是先把作品的正式总纲、核心设定和整体走向定下来。';
  }
  if (isOutlineReviseMode.value) {
    return '这一页会围绕既有正式总纲做修正讨论，当前创作流程先暂时让位给总纲修订。';
  }
  return '这一页用于讨论当前章节该怎么推进，只有正式总纲和章节大纲都齐备后，才能进入正文创作。';
});
const outlineDraftPreview = computed(() => {
  const draft = String(projectStore.outlineDraft || '').trim();
  if (draft) {
    return draft;
  }
  if (isOutlineDesignMode.value) {
    return '总纲草稿还没有生成。先和 Bot1 讨论题材、主角、世界观、主线冲突，它生成后会显示在这里。';
  }
  if (isOutlineReviseMode.value) {
    return '当前还没有新的修正草稿。你可以先提出要修改的方向，Bot1 生成后会显示在这里。';
  }
  return '';
});
const outlineDraftStatus = computed(() => {
  if (!String(projectStore.outlineDraft || '').trim()) {
    return '未生成';
  }
  return projectStore.outlineDirty ? '未提交' : '草稿已载入';
});
const inputPlaceholder = computed(() => {
  if (isOutlineDesignMode.value) {
    return '输入题材、主角、世界观、时代背景或主线冲突...';
  }
  if (isOutlineReviseMode.value) {
    return '输入你想修改的总纲方向、设定问题或结构调整点...';
  }
  return '输入你的故事想法...';
});

const hasOfficialOutline = computed(() => Boolean(String(projectStore.currentOutline || '').trim()));
const hasChapterOutline = computed(() => Boolean(String(projectStore.chapterOutline || '').trim()));
const hasOutlineDraft = computed(() => Boolean(String(projectStore.outlineDraft || '').trim()));
const canSubmitOutlineDraft = computed(() => isOutlineWorkspaceMode.value && hasOutlineDraft.value);
const canDiscardOutlineDraft = computed(() => isOutlineWorkspaceMode.value && (hasOutlineDraft.value || projectStore.outlineDirty));
const canProceedToWriting = computed(() => isNormalPlanningMode.value && hasOfficialOutline.value && hasChapterOutline.value);

const scrollToBottom = async () => {
  await nextTick();
  if (chatAreaRef.value) {
    chatAreaRef.value.scrollTop = chatAreaRef.value.scrollHeight;
  }
};

const formatMessage = (text, role) => {
  const content = role === 'assistant' ? stripOutline(text) : String(text || '');
  return (content || '已更新大纲').replace(/\n/g, '<br/>');
};

const syncOutlines = (fullText) => {
  if (isOutlineDesignMode.value || isOutlineReviseMode.value) {
    const draftOutline = extractOutline(fullText);
    if (draftOutline) {
      projectStore.outlineDraft = draftOutline;
      projectStore.outlineDirty = true;
    }
    return;
  }

  const chapterOutline = extractChapterOutline(fullText);

  if (chapterOutline) {
    projectStore.chapterOutline = chapterOutline;
  }
};

const sendMessage = async () => {
  const message = inputMsg.value.trim();
  if (!message || isGenerating.value) {
    return;
  }

  const config = getRuntimeConfig(projectStore.config);
  if (!config) {
    showToast('请先在设置页填写 Bot1 配置');
    return;
  }

  const userMessage = { role: 'user', content: message };
  const assistantMessage = { role: 'assistant', content: '' };
  const stableOutline = projectStore.currentOutline;
  const stableChapterOutline = projectStore.chapterOutline;
  const requestOutline = isOutlineDesignMode.value || isOutlineReviseMode.value
    ? String(projectStore.outlineDraft || projectStore.currentOutline || '')
    : projectStore.currentOutline;
  const requestChapterOutline = isNormalPlanningMode.value ? projectStore.chapterOutline : '';
  const restoreStableOutlines = () => {
    projectStore.currentOutline = stableOutline;
    projectStore.chapterOutline = stableChapterOutline;
  };

  projectStore.chatHistory.push(userMessage);
  projectStore.chatHistory.push(assistantMessage);
  inputMsg.value = '';
  isGenerating.value = true;
  await scrollToBottom();

  try {
    const endpoint = isOutlineWorkspaceMode.value ? '/api/bot1/outline-chat' : '/api/bot1/chat';

    const fullText = await readSSE(
      endpoint,
      {
        messages: [userMessage],
        config,
        current_outline: requestOutline,
        chapter_outline: requestChapterOutline,
        context: buildBot1Context(projectStore),
      },
      {
        onReset: () => {
          restoreStableOutlines();
          assistantMessage.content = '格式校验未通过，正在自动重试...';
          scrollToBottom();
        },
        onChunk: (_chunk, full) => {
          assistantMessage.content = full;
          scrollToBottom();
        },
      },
    );

    assistantMessage.content = fullText;
    syncOutlines(fullText);
    await projectStore.saveProject();
  } catch (error) {
    restoreStableOutlines();
    projectStore.chatHistory.pop();
    showToast(error.message || 'Bot1 请求失败');
  } finally {
    isGenerating.value = false;
    await scrollToBottom();
  }
};

const submitOutlineDraft = async () => {
  if (!canSubmitOutlineDraft.value) {
    showToast('请先生成总纲草稿，再提交');
    return;
  }

  projectStore.currentOutline = String(projectStore.outlineDraft || '').trim();
  projectStore.outlineDraft = '';
  projectStore.outlineMode = '';
  projectStore.outlineDirty = false;
  await projectStore.saveProject();
  showToast('正式总纲已更新');
};

const discardOutlineDraft = async () => {
  if (!canDiscardOutlineDraft.value) {
    return;
  }

  projectStore.outlineDraft = '';
  projectStore.outlineMode = '';
  projectStore.outlineDirty = false;
  await projectStore.saveProject();
  showToast('已放弃本次总纲草稿');
};

const confirmOutlineAndNext = async () => {
  if (!hasOfficialOutline.value) {
    showToast('请先完成正式总纲设计，再进入创作');
    return;
  }

  if (!hasChapterOutline.value) {
    showToast('请先让 Bot1 生成当前章节大纲');
    return;
  }

  await projectStore.saveProject();
  emit('next');
};

onMounted(scrollToBottom);
</script>

<style scoped>
.planning-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #f7f8fa;
}

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background-color: #fff;
  border-bottom: 1px solid #ebedf0;
  flex-shrink: 0;
}

.mode-banner {
  margin: 12px 16px 0;
  padding: 14px 16px;
  border-radius: 16px;
  flex-shrink: 0;
}

.outline-design-banner {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(99, 102, 241, 0.18));
  border: 1px solid rgba(79, 70, 229, 0.12);
}

.chapter-planning-banner {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.10), rgba(59, 130, 246, 0.10));
  border: 1px solid rgba(16, 185, 129, 0.12);
}

.mode-banner-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.mode-banner-copy {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
}

.status-left .status-text {
  font-size: 14px;
  color: #969799;
}

.status-right {
  display: flex;
  gap: 8px;
}

.next-btn {
  font-weight: bold;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
}

.outline-draft-panel {
  padding: 14px 16px;
  border-radius: 16px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
}

.outline-draft-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.outline-draft-title {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.outline-draft-status {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.10);
  font-size: 12px;
  color: #2563eb;
}

.outline-draft-content {
  margin-top: 10px;
  white-space: pre-wrap;
  font-size: 14px;
  line-height: 1.7;
  color: #374151;
}

.outline-draft-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 14px;
}

.chat-bubble {
  max-width: 85%;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 15px;
  line-height: 1.5;
  word-wrap: break-word;
}

.ai-msg {
  align-self: flex-start;
  color: #323233;
  background-color: #fff;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.user-msg {
  align-self: flex-end;
  color: #fff;
  background-color: #1989fa;
  border-bottom-right-radius: 4px;
}

.loading-msg {
  display: flex;
  align-items: center;
  color: #969799;
}

.loading-text {
  margin-left: 8px;
}

.input-area {
  padding: 10px 16px;
  background-color: #fff;
  border-top: 1px solid #ebedf0;
  flex-shrink: 0;
}

.chat-input {
  padding: 6px 16px;
  background-color: #f2f3f5;
  border-radius: 20px;
}

.chat-input :deep(.van-field__control) {
  min-height: 24px;
  max-height: 100px;
}
</style>
