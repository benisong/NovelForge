<template>
  <div class="project-detail-container">
    <!-- 全局顶部导航 -->
    <van-nav-bar
      title="NovelForge"
      fixed
      placeholder
      safe-area-inset-top
      class="global-nav"
    >
      <template #left>
        <van-icon name="wap-nav" size="20" @click="showDrawer = true" />
      </template>
      <template #title>
        <span class="project-title">{{ currentProjectName }}</span>
        <!-- 大纲入口，按需在卡片中显示，这里可以统一入口或者放在特定卡片 -->
      </template>
      <template #right>
        <van-icon name="setting-o" size="20" @click="openSettings" />
      </template>
    </van-nav-bar>

    <!-- 侧边抽屉导航 -->
    <van-popup
      v-model:show="showDrawer"
      position="left"
      :style="{ width: '70%', height: '100%' }"
    >
      <div class="drawer-header">
        <h3>项目列表</h3>
      </div>
      <van-cell-group>
        <van-cell title="切换项目" is-link />
        <van-cell title="导入配置" is-link />
        <van-cell title="返回PC端" is-link @click="backToPC" />
      </van-cell-group>
    </van-popup>

    <!-- 全局悬浮左右切换箭头 -->
    <div class="side-arrow left-arrow" v-show="currentCardIndex > 0" @click="goPrevCard">
      <van-icon name="arrow-left" size="24" color="#fff" />
    </div>
    <div class="side-arrow right-arrow" v-show="currentCardIndex < 3" @click="goNextCard">
      <van-icon name="arrow" size="24" color="#fff" />
    </div>

    <!-- 卡片滑动容器 -->
    <van-swipe
      class="main-swipe"
      :loop="false"
      :show-indicators="false"
      :touchable="false"
      ref="swipeRef"
      @change="onSwipeChange"
    >
      <!-- 卡片1：规划 (Bot1) -->
      <van-swipe-item class="swipe-item">
        <PlanningView 
          @next="goNextCard" 
          @show-outline="showOutline = true" 
        />
      </van-swipe-item>

      <!-- 卡片2：创作 (Bot2) -->
      <van-swipe-item class="swipe-item">
        <WritingView 
          ref="writingViewRef"
          @prev="goPrevCard"
          @next="goNextCard"
        />
      </van-swipe-item>

      <!-- 卡片3：审核 (Bot3) -->
      <van-swipe-item class="swipe-item">
        <ReviewView />
      </van-swipe-item>

      <!-- 卡片4：记忆 (Bot4) -->
      <van-swipe-item class="swipe-item">
        <MemoryView />
      </van-swipe-item>
    </van-swipe>

    <!-- 底部弹出：大纲视图 -->
    <van-action-sheet v-model:show="showOutline" title="大纲参考">
      <div class="outline-content">
        <van-collapse v-model="activeOutlineNames">
          <van-collapse-item title="总大纲" name="global">
            <p>（总大纲内容展示区）</p>
          </van-collapse-item>
          <van-collapse-item title="章节大纲" name="chapter">
            <p>（当前章节大纲内容展示区）</p>
          </van-collapse-item>
        </van-collapse>
      </div>
    </van-action-sheet>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import PlanningView from './Planning.vue';
import WritingView from './Writing.vue';
import ReviewView from './Review.vue';
import MemoryView from './Memory.vue';

const router = useRouter();

const showDrawer = ref(false);
const showOutline = ref(false);
const activeOutlineNames = ref(['global', 'chapter']);
const currentProjectName = ref('我的小说1');

const swipeRef = ref(null);
const currentCardIndex = ref(0);
const writingViewRef = ref(null);

const onSwipeChange = (index) => {
  currentCardIndex.value = index;
};

const goNextCard = () => {
  if (swipeRef.value && currentCardIndex.value < 3) {
    swipeRef.value.next();
  }
};

const goPrevCard = () => {
  if (swipeRef.value && currentCardIndex.value > 0) {
    swipeRef.value.prev();
  }
};

const openSettings = () => {
  console.log('Open Settings');
};

const backToPC = () => {
  window.location.href = '/';
};
</script>

<style scoped>
.project-detail-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.global-nav {
  z-index: 100;
  border-bottom: 1px solid #ebedf0;
}

.project-title {
  font-weight: 600;
  font-size: 16px;
}

.main-swipe {
  flex: 1;
  width: 100%;
  height: 100%;
}

.swipe-item {
  height: 100%;
  overflow-y: hidden; /* 由内部组件决定是否滚动 */
  background-color: #fff;
  display: flex;
  flex-direction: column;
}

/* 占位符卡片样式，后续会被具体组件替换 */
.placeholder-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 20px;
}

.nav-controls {
  margin-top: 20px;
  display: flex;
  gap: 20px;
}

.drawer-header {
  padding: 20px;
  border-bottom: 1px solid #ebedf0;
}
.drawer-header h3 {
  margin: 0;
}

.outline-content {
  padding: 16px;
  min-height: 40vh;
  max-height: 70vh;
  overflow-y: auto;
}

.side-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 100;
  width: 40px;
  height: 80px;
  background-color: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  backdrop-filter: blur(4px);
}
.side-arrow:active {
  background-color: rgba(0, 0, 0, 0.5);
}
.left-arrow {
  left: 0;
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
}
.right-arrow {
  right: 0;
  border-top-right-radius: 0;
  border-bottom-right-radius: 0;
}
</style>
