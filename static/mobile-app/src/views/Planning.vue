<template>
  <div class="planning-view">
    <div class="status-bar">
      <div class="status-left">
        <span class="status-text">大纲规划</span>
      </div>
      <div class="status-right">
        <van-button size="mini" type="primary" plain @click="$emit('show-outline')">查看大纲</van-button>
        <van-button
          size="mini"
          icon="arrow"
          type="primary"
          class="next-btn"
          :disabled="isGenerating || !hasOutline"
          @click="confirmOutlineAndNext"
        >
          确认并创作
        </van-button>
      </div>
    </div>

    <div class="chat-area" ref="chatAreaRef">
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
        placeholder="输入你的故事想法..."
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

const welcomeMessage = {
  role: 'assistant',
  content: '你好，我是 Bot1。先把这一章的剧情、人物和冲突告诉我，我会边聊边帮你整理总大纲和章节大纲。',
};

const displayHistory = computed(() => (
  projectStore.chatHistory.length > 0 ? projectStore.chatHistory : [welcomeMessage]
));

const hasOutline = computed(() => Boolean(projectStore.currentOutline || projectStore.chapterOutline));

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
  const outline = extractOutline(fullText);
  const chapterOutline = extractChapterOutline(fullText);

  if (outline) {
    projectStore.currentOutline = outline;
  }
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
    const fullText = await readSSE(
      '/api/bot1/chat',
      {
        messages: [userMessage],
        config,
        current_outline: projectStore.currentOutline,
        chapter_outline: projectStore.chapterOutline,
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
          syncOutlines(full);
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

const confirmOutlineAndNext = async () => {
  if (!hasOutline.value) {
    showToast('先让 Bot1 生成大纲再继续');
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
