<template>
  <div class="writing-view">
    <!-- 顶部状态提示 -->
    <div class="writing-status-bar">
      <div class="status-left">
        <span class="status-text" v-if="isGenerating">Bot2 正在创作中...</span>
        <span class="status-text success-text" v-else>创作完成</span>
      </div>
      <div class="status-right">
         <van-button 
          v-if="isGenerating"
          size="mini" 
          type="danger" 
          plain 
          @click="stopGenerating"
        >停止生成</van-button>
        <van-button 
          v-else
          size="mini" 
          type="primary" 
          plain 
          @click="rewriteContent"
        >重新生成</van-button>
      </div>
    </div>

    <!-- 正文阅读区 -->
    <div class="content-area" ref="contentAreaRef">
      <div class="chapter-content" v-html="formattedContent"></div>
      
      <!-- 打字机光标效果 -->
      <span v-if="isGenerating" class="typing-cursor">|</span>
    </div>

    <!-- 底部导航控制区 -->
    <div class="bottom-nav">
      <van-button 
        icon="arrow-left" 
        type="default" 
        size="small"
        class="nav-btn"
        @click="$emit('prev')"
        v-show="false"
      >返回修改大纲</van-button>
      
      <van-button 
        icon="arrow" 
        type="primary" 
        size="small"
        class="nav-btn"
        :disabled="isGenerating || !content"
        @click="$emit('next')"
        v-show="false"
      >去审计</van-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue';

const emit = defineEmits(['prev', 'next']);

const contentAreaRef = ref(null);

// 模拟状态
const isGenerating = ref(false);
const content = ref('');

// 格式化文本，处理换行
const formattedContent = computed(() => {
  if (!content.value) return '<span style="color:#969799;font-style:italic;">等待生成...</span>';
  return content.value.replace(/\n/g, '<br/>');
});

const scrollToBottom = () => {
  nextTick(() => {
    if (contentAreaRef.value) {
      contentAreaRef.value.scrollTop = contentAreaRef.value.scrollHeight;
    }
  });
};

// 监听内容变化，自动滚动到底部
watch(content, () => {
  if (isGenerating.value) {
    scrollToBottom();
  }
});

// 模拟生成过程
const startGenerating = async () => {
  content.value = '';
  isGenerating.value = true;
  
  const mockParagraphs = [
    "雨，像无数根银针，无情地刺向霓虹市的钢铁苍穹。",
    "夜枭拉了拉风衣的领口，试图抵挡无孔不入的寒意。他的眼前是一具倒在巷尾的赛博格躯体，电子眼还在微弱地闪烁着红光。",
    "这已经是这个月第三起类似的案件了。所有的受害者都被精准地摘除了记忆芯片，手法干净利落，不像是普通的街头混混所为。",
    "他蹲下身，从口袋里掏出一个便携式数据接口，小心翼翼地接入了死者后颈的插槽。屏幕上跳动着乱码，试图解读残留的碎片信息。",
    "突然，夜枭的神经接入端传来一阵强烈的刺痛，一个模糊的声音在他的脑海中回荡：『他们来了……』"
  ];

  for (let p of mockParagraphs) {
    if (!isGenerating.value) break; // 支持中断
    
    // 模拟逐字输出
    for (let i = 0; i < p.length; i++) {
      if (!isGenerating.value) break;
      await new Promise(resolve => setTimeout(resolve, 50)); // 打字速度
      content.value += p[i];
    }
    
    if (isGenerating.value) {
      content.value += '\n\n'; // 段落换行
      await new Promise(resolve => setTimeout(resolve, 800)); // 段落停顿
    }
  }
  
  isGenerating.value = false;
};

const stopGenerating = () => {
  isGenerating.value = false;
};

const rewriteContent = () => {
  startGenerating();
};

// 组件挂载时自动开始模拟生成 (仅为演示)
onMounted(() => {
  startGenerating();
});

// 暴露方法给父组件调用
defineExpose({
  startGenerating
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
  font-size: 14px;
  color: #1989fa;
  display: flex;
  align-items: center;
}

.success-text {
  color: #07c160;
}

.content-area {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  font-size: 16px;
  line-height: 1.8;
  color: #323233;
  font-family: 'Georgia', 'Times New Roman', 'Kaiti', 'STKaiti', serif; /* 增加一点文学感 */
  letter-spacing: 1px;
}

.chapter-content {
  text-align: justify;
}

/* 闪烁的光标动画 */
.typing-cursor {
  display: inline-block;
  width: 2px;
  height: 1.2em;
  background-color: #1989fa;
  vertical-align: text-bottom;
  animation: blink 1s step-end infinite;
  margin-left: 2px;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.bottom-nav {
  display: flex;
  justify-content: space-between;
  padding: 12px 16px;
  background-color: #fff;
  border-top: 1px solid #ebedf0;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.02);
  flex-shrink: 0;
}

.nav-btn {
  flex: 1;
  margin: 0 8px;
}
.nav-btn:first-child {
  margin-left: 0;
}
.nav-btn:last-child {
  margin-right: 0;
}
</style>
