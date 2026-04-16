<template>
  <div class="memory-view">
    <!-- 顶部状态提示 -->
    <div class="memory-status-bar">
      <div class="status-left">
        <span class="status-text">
          <van-icon name="flag-o" size="18" />
          <span style="margin-left: 4px;">全局记忆库</span>
        </span>
      </div>
      <div class="status-right">
        <van-button 
          size="mini" 
          type="primary" 
          plain 
          @click="generateBigSummary"
          :loading="isGeneratingBig"
        >生成大总结</van-button>
      </div>
    </div>

    <!-- 记忆内容区 -->
    <div class="memory-content">
      <van-tabs v-model:active="activeTab" sticky color="#1989fa" animated swipeable>
        <!-- 标签页1：章节摘要 (小总结) -->
        <van-tab title="章节摘要" name="small">
          <div class="tab-content-area">
            <van-collapse v-model="activeSmallSummaries">
              <van-collapse-item 
                v-for="summary in smallSummaries" 
                :key="summary.chapter" 
                :name="summary.chapter"
                :title="`第 ${summary.chapter} 章`"
                :value="summary.time"
              >
                <div class="summary-toggle">
                  <van-radio-group v-model="summary.displayMode" direction="horizontal" class="mode-radio">
                    <van-radio name="abstract">摘要 (Bot1 讨论用)</van-radio>
                    <van-radio name="condensed">缩略原文 (Bot2 创作用)</van-radio>
                  </van-radio-group>
                </div>
                
                <div class="summary-text" v-if="summary.displayMode === 'abstract'">
                  <strong>主要事件：</strong>
                  <p>{{ summary.abstract.events }}</p>
                  <strong>人物状态：</strong>
                  <p>{{ summary.abstract.characters }}</p>
                  <strong>伏笔：</strong>
                  <p>{{ summary.abstract.foreshadowing }}</p>
                </div>
                
                <div class="summary-text" v-else>
                  <p class="condensed-text">{{ summary.condensed }}</p>
                </div>
              </van-collapse-item>
            </van-collapse>
            <van-empty v-if="smallSummaries.length === 0" description="暂无章节摘要" image="search" />
          </div>
        </van-tab>

        <!-- 标签页2：大总结 -->
        <van-tab title="全局大总结" name="big">
          <div class="tab-content-area">
            <div 
              class="big-summary-card" 
              v-for="(summary, index) in bigSummaries" 
              :key="index"
            >
              <div class="big-header">
                <span class="big-range">第 {{ summary.fromChapter }} - {{ summary.toChapter }} 章 总结</span>
                <span class="big-time">{{ summary.time }}</span>
              </div>
              <div class="big-content">
                <div class="content-section">
                  <h4>世界观与设定更新</h4>
                  <p>{{ summary.content.worldview }}</p>
                </div>
                <div class="content-section">
                  <h4>主线推进</h4>
                  <p>{{ summary.content.main_plot }}</p>
                </div>
                <div class="content-section">
                  <h4>核心人物小传</h4>
                  <p>{{ summary.content.character_arcs }}</p>
                </div>
              </div>
              <div class="big-actions">
                 <van-button size="small" plain type="primary" icon="edit">编辑</van-button>
              </div>
            </div>
            <van-empty v-if="bigSummaries.length === 0" description="暂无大总结记录" image="search" />
          </div>
        </van-tab>
      </van-tabs>
    </div>

    <!-- 底部导航控制区 -->
    <div class="bottom-nav">
      <van-button 
        icon="home-o" 
        type="default" 
        size="small"
        class="nav-btn"
        @click="backToProjectList"
        v-show="false"
      >返回列表</van-button>
      
      <van-button 
        icon="play-circle-o" 
        type="primary" 
        size="small"
        class="nav-btn"
        @click="startNextChapter"
        v-show="false"
      >进入下一章规划</van-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { showToast, showConfirmDialog } from 'vant';

const emit = defineEmits(['start-next', 'back-home']);

const activeTab = ref('small');
const activeSmallSummaries = ref([1]); // 默认展开第一章
const isGeneratingBig = ref(false);

// 模拟小总结数据
const smallSummaries = ref([
  {
    chapter: 1,
    time: '2026-04-15 10:30',
    displayMode: 'abstract',
    abstract: {
      events: '主角夜枭在霓虹市贫民窟发现一具被摘除记忆芯片的赛博格尸体。',
      characters: '夜枭（冷酷，执着），神秘死者。',
      foreshadowing: '死者脑内残留的乱码信息：“他们来了……”。'
    },
    condensed: '雨，像无数根银针，无情地刺向霓虹市的钢铁苍穹。夜枭拉了拉风衣的领口，试图抵挡无孔不入的寒意。他的眼前是一具倒在巷尾的赛博格躯体。这已经是这个月第三起类似的案件了。所有的受害者都被精准地摘除了记忆芯片。他蹲下身接入死者后颈的插槽。屏幕上跳动着乱码。突然，夜枭的神经接入端传来一阵强烈的刺痛，一个模糊的声音在他的脑海中回荡：『他们来了……』'
  }
]);

// 模拟大总结数据
const bigSummaries = ref([
  {
    fromChapter: 1,
    toChapter: 10,
    time: '2026-04-14 18:00',
    content: {
      worldview: '霓虹市分为上层天城和下层贫民窟。记忆芯片技术普及，但非法摘除交易泛滥。',
      main_plot: '夜枭从一具无名尸体开始调查，逐渐揭开了由控制天城的“奥林匹斯集团”主导的记忆收割阴谋。他找到了抵抗组织的联络人。',
      character_arcs: '夜枭：从一个只接底层委托的颓废侦探，逐渐找回被抹去的部分记忆，开始主动对抗集团。'
    }
  }
]);

const generateBigSummary = () => {
  showConfirmDialog({
    title: '生成大总结',
    message: '将消耗一定 Token 读取最近章节的摘要和原文生成全局总结。确定生成吗？',
  }).then(() => {
    isGeneratingBig.value = true;
    showToast({ type: 'loading', message: 'Bot4 正在总结...', duration: 2000 });
    setTimeout(() => {
      isGeneratingBig.value = false;
      showToast('大总结生成成功！');
      activeTab.value = 'big';
    }, 2000);
  }).catch(() => {});
};

const backToProjectList = () => {
  // 实际项目中应使用 router.push
  emit('back-home');
};

const startNextChapter = () => {
  emit('start-next');
};
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
  font-size: 15px;
  font-weight: bold;
  color: #323233;
  display: flex;
  align-items: center;
}

.memory-content {
  flex: 1;
  overflow-y: hidden; /* 让 tabs 内部去滚动 */
  display: flex;
  flex-direction: column;
}

/* 撑满 tabs 容器 */
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

/* 小总结样式 */
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
  font-size: 14px;
  color: #323233;
  line-height: 1.6;
}
.summary-text strong {
  color: #1989fa;
  display: block;
  margin-top: 8px;
}
.summary-text p {
  margin: 4px 0 0 0;
  color: #646566;
}
.condensed-text {
  font-family: 'Georgia', serif;
  color: #323233 !important;
  text-align: justify;
}

/* 大总结样式 */
.big-summary-card {
  background-color: #fff;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
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
  font-weight: bold;
  font-size: 16px;
  color: #323233;
}
.big-time {
  font-size: 12px;
  color: #969799;
}

.content-section {
  margin-bottom: 12px;
}
.content-section h4 {
  margin: 0 0 6px 0;
  font-size: 14px;
  color: #1989fa;
}
.content-section p {
  margin: 0;
  font-size: 14px;
  color: #646566;
  line-height: 1.5;
}

.big-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
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
