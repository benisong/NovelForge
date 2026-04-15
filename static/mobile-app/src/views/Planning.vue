<template>
  <div class="planning-view">
    <!-- 顶部状态栏和辅助操作 -->
    <div class="status-bar">
      <div class="status-left">
        <span class="status-text">大纲策划</span>
      </div>
      <div class="status-right">
        <van-button 
          size="mini" 
          type="primary" 
          plain 
          @click="$emit('show-outline')"
        >查看大纲</van-button>
        <van-button 
          size="mini" 
          icon="arrow" 
          type="primary" 
          @click="confirmOutlineAndNext"
          class="next-btn"
        >确认并创作</van-button>
      </div>
    </div>

    <!-- 聊天区域 -->
    <div class="chat-area" ref="chatAreaRef">
      <div 
        v-for="(msg, index) in chatHistory" 
        :key="index"
        :class="['chat-bubble', msg.role === 'user' ? 'user-msg' : 'ai-msg']"
      >
        <div class="msg-content" v-html="formatMessage(msg.content)"></div>
      </div>
      <!-- 加载动画 -->
      <div v-if="isGenerating" class="chat-bubble ai-msg loading-msg">
        <van-loading type="spinner" size="20px" />
        <span style="margin-left: 8px;">Bot1 正在思考...</span>
      </div>
    </div>

    <!-- 底部输入区域 -->
    <div class="input-area">
      <van-field
        v-model="inputMsg"
        rows="1"
        autosize
        type="textarea"
        placeholder="输入你的故事想法..."
        class="chat-input"
        :disabled="isGenerating"
        @keyup.enter="sendMessage"
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
import { ref, onMounted, nextTick } from 'vue';

const emit = defineEmits(['next', 'show-outline']);

const inputMsg = ref('');
const isGenerating = ref(false);
const chatAreaRef = ref(null);

// 模拟数据
const chatHistory = ref([
  { role: 'ai', content: '你好！我是你的大纲策划师 Bot1。我们今天想写一个什么样的故事呢？' },
  { role: 'user', content: '我想要一个赛博朋克风格的侦探故事。主角叫"夜枭"，在霓虹市。' },
  { role: 'ai', content: '好的，赛博朋克侦探故事。已记录主角“夜枭”和地点“霓虹市”。我们可以先构思一下全局故事的主线，比如他要调查什么案件？' }
]);

const scrollToBottom = () => {
  nextTick(() => {
    if (chatAreaRef.value) {
      chatAreaRef.value.scrollTop = chatAreaRef.value.scrollHeight;
    }
  });
};

const formatMessage = (text) => {
  // 简单处理换行
  return text.replace(/\n/g, '<br/>');
};

const sendMessage = async () => {
  const content = inputMsg.value.trim();
  if (!content) return;

  // 添加用户消息
  chatHistory.value.push({ role: 'user', content });
  inputMsg.value = '';
  scrollToBottom();

  // 模拟发送请求和流式响应
  isGenerating.value = true;
  
  // 模拟网络延迟
  await new Promise(resolve => setTimeout(resolve, 800));
  
  const aiMsgIndex = chatHistory.value.push({ role: 'ai', content: '' }) - 1;
  const mockResponse = '收到。那么这个案件是否和他在霓虹市的过去有关？他是否发现了一些上层社会的秘密？我们可以把这部分写入【总大纲】中。';
  
  // 模拟打字效果
  for (let i = 0; i < mockResponse.length; i++) {
    await new Promise(resolve => setTimeout(resolve, 30));
    chatHistory.value[aiMsgIndex].content += mockResponse[i];
    scrollToBottom();
  }

  isGenerating.value = false;
};

const confirmOutlineAndNext = () => {
  // 这里应该处理保存大纲的逻辑
  // 然后触发跳转到下一卡片
  emit('next');
};

onMounted(() => {
  scrollToBottom();
});
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
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
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
  background-color: #fff;
  border-bottom-left-radius: 4px;
  color: #323233;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.user-msg {
  align-self: flex-end;
  background-color: #1989fa;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.loading-msg {
  display: flex;
  align-items: center;
  color: #969799;
}

.input-area {
  padding: 10px 16px;
  background-color: #fff;
  border-top: 1px solid #ebedf0;
  flex-shrink: 0;
}

.chat-input {
  background-color: #f2f3f5;
  border-radius: 20px;
  padding: 6px 16px;
}
.chat-input :deep(.van-field__control) {
  min-height: 24px;
  max-height: 100px;
}
</style>
