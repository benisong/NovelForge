<template>
  <div class="project-detail-container">
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
      </template>
      <template #right>
        <van-icon name="setting-o" size="20" @click="openSettings" />
      </template>
    </van-nav-bar>

    <van-popup
      v-model:show="showDrawer"
      position="left"
      :style="{ width: '70%', height: '100%' }"
    >
      <div class="drawer-header">
        <h3>项目菜单</h3>
      </div>
      <van-cell-group>
        <van-cell title="查看大纲" is-link @click="openOutlineFromDrawer" />
        <van-cell title="打开设置" is-link @click="openSettings" />
        <van-cell title="返回 PC 端" is-link @click="backToPC" />
      </van-cell-group>
    </van-popup>

    <div class="side-arrow left-arrow" v-show="currentCardIndex > 0" @click="goPrevCard">
      <van-icon name="arrow-left" size="24" color="#fff" />
    </div>
    <div class="side-arrow right-arrow" v-show="currentCardIndex < 3" @click="goNextCard">
      <van-icon name="arrow" size="24" color="#fff" />
    </div>

    <van-swipe
      ref="swipeRef"
      class="main-swipe"
      :loop="false"
      :show-indicators="false"
      :touchable="false"
      @change="onSwipeChange"
    >
      <van-swipe-item class="swipe-item">
        <PlanningView @next="goNextCard" @show-outline="showOutline = true" />
      </van-swipe-item>

      <van-swipe-item class="swipe-item">
        <WritingView ref="writingViewRef" @prev="goPrevCard" @next="goNextCard" />
      </van-swipe-item>

      <van-swipe-item class="swipe-item">
        <ReviewView ref="reviewViewRef" @rewrite="handleRewrite" @approve="handleApprove" />
      </van-swipe-item>

      <van-swipe-item class="swipe-item">
        <MemoryView ref="memoryViewRef" @start-next="startNextChapter" @back-home="backToPC" />
      </van-swipe-item>
    </van-swipe>

    <van-action-sheet v-model:show="showOutline" title="大纲参考">
      <div class="outline-content">
        <van-collapse v-model="activeOutlineNames">
          <van-collapse-item title="总大纲" name="global">
            <div class="outline-text">{{ projectStore.currentOutline || '暂无总大纲' }}</div>
          </van-collapse-item>
          <van-collapse-item title="章节大纲" name="chapter">
            <div class="outline-text">{{ projectStore.chapterOutline || '暂无当前章节大纲' }}</div>
          </van-collapse-item>
        </van-collapse>
      </div>
    </van-action-sheet>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useProjectStore } from '@/stores/project';

import MemoryView from './Memory.vue';
import PlanningView from './Planning.vue';
import ReviewView from './Review.vue';
import WritingView from './Writing.vue';

const projectStore = useProjectStore();
const router = useRouter();

const showDrawer = ref(false);
const showOutline = ref(false);
const activeOutlineNames = ref(['global', 'chapter']);
const swipeRef = ref(null);
const writingViewRef = ref(null);
const reviewViewRef = ref(null);
const memoryViewRef = ref(null);
const currentCardIndex = ref(0);

const currentProjectName = computed(() => projectStore.projectName || '我的小说');

onMounted(async () => {
  await projectStore.loadConfig();
  await projectStore.loadProject();
});

const onSwipeChange = (index) => {
  currentCardIndex.value = index;
};

const ensureCurrentChapterSaved = async () => {
  const content = String(projectStore.currentContent || '').trim();
  if (!content) {
    return;
  }

  const latestChapter = projectStore.chapters.at(-1);
  if (!latestChapter || latestChapter.content !== content) {
    projectStore.chapters.push({
      outline: projectStore.currentOutline,
      chapter_outline: projectStore.chapterOutline,
      content,
      summary: '',
    });
  }

  await projectStore.saveProject();
};

const goToCard = async (index) => {
  if (!swipeRef.value) {
    return;
  }

  swipeRef.value.swipeTo(index);
  currentCardIndex.value = index;
  await nextTick();

  if (index === 1 && !String(projectStore.currentContent || '').trim()) {
    writingViewRef.value?.startGenerating?.();
  }

  // 切到 Review 卡片时不再自动触发审核。首次进入展示空状态，用户主动点「重新审核」再调。
  // 上一次的审核结果仍由 Review.vue 的 onMounted 从 projectStore.reviews 恢复。

  if (index === 3) {
    await memoryViewRef.value?.ensureCurrentSummary?.();
  }
};

const goNextCard = async () => {
  if (currentCardIndex.value >= 3) {
    return;
  }

  await goToCard(currentCardIndex.value + 1);
};

const goPrevCard = async () => {
  if (currentCardIndex.value <= 0) {
    return;
  }

  await goToCard(currentCardIndex.value - 1);
};

const handleRewrite = async (data) => {
  await goToCard(1);
  writingViewRef.value?.startGenerating?.(data?.suggestions ?? []);
};

const handleApprove = async () => {
  await ensureCurrentChapterSaved();
  await goToCard(3);
};

const startNextChapter = async () => {
  showOutline.value = false;
  showDrawer.value = false;
  projectStore.currentContent = '';
  projectStore.chapterOutline = '';
  await projectStore.saveProject();
  await goToCard(0);
};

const openOutlineFromDrawer = () => {
  showDrawer.value = false;
  showOutline.value = true;
};

const openSettings = async () => {
  showDrawer.value = false;
  await projectStore.saveProject();
  router.push('/settings');
};

const backToPC = async () => {
  showDrawer.value = false;
  await projectStore.saveProject();
  window.location.assign('/');
};
</script>

<style scoped>
.project-detail-container {
  display: flex;
  flex-direction: column;
  height: 100dvh;
}

.global-nav {
  z-index: 100;
  border-bottom: 1px solid var(--app-border);
  background: transparent;
}

.project-title {
  font-size: 16px;
  font-weight: 600;
}

.main-swipe {
  flex: 1;
  width: 100%;
  height: 100%;
}

.swipe-item {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: hidden;
  background-color: transparent;
}

.drawer-header {
  padding: 20px;
  border-bottom: 1px solid var(--app-border);
}

.drawer-header h3 {
  margin: 0;
}

.outline-content {
  min-height: 40vh;
  max-height: 70vh;
  padding: 16px;
  overflow-y: auto;
}

.outline-text {
  white-space: pre-wrap;
  line-height: 1.6;
}

.side-arrow {
  position: absolute;
  top: 50%;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 80px;
  background-color: rgba(31, 24, 19, 0.24);
  border-radius: 8px;
  backdrop-filter: blur(4px);
  transform: translateY(-50%);
}

.side-arrow:active {
  background-color: rgba(31, 24, 19, 0.42);
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
