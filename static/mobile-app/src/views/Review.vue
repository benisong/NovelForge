<template>
  <div class="review-view">
    <div class="review-status-bar" :class="{ pass: isPassed, fail: !isPassed }">
      <div class="status-left">
        <span class="status-text">
          <van-icon :name="isPassed ? 'passed' : 'close'" size="18" />
          <span class="status-copy">
            审核{{ isPassed ? '通过' : '未通过' }} (平均分 {{ averageScore }})
          </span>
        </span>
      </div>
      <div class="status-right">
        <van-tag :type="isPassed ? 'success' : 'danger'" plain>及格线 {{ passScore }}</van-tag>
      </div>
    </div>

    <div class="review-content">
      <div class="score-card">
        <div class="section-head">
          <h3 class="section-title">维度评分</h3>
          <van-button size="small" plain type="primary" :loading="isLoading" @click="runReview">
            重新审核
          </van-button>
        </div>

        <div class="score-item" v-for="item in scoreList" :key="item.key">
          <div class="score-header">
            <span class="score-label" :class="{ 'has-issue': item.hasIssue }">
              {{ item.label }}
              <van-tag v-if="item.hasIssue" type="danger" round size="medium">需改进</van-tag>
            </span>
            <span class="score-value">{{ item.value.toFixed(1) }}</span>
          </div>
          <van-slider
            v-model="item.value"
            :min="0"
            :max="10"
            :step="0.5"
            :button-size="'20px'"
            :active-color="item.value >= passScore ? '#07c160' : '#ee0a24'"
          />
        </div>
      </div>

      <div class="suggestions-card" v-if="suggestions.length > 0">
        <h3 class="section-title">修改建议</h3>
        <van-collapse v-model="activeNames" accordion>
          <van-collapse-item
            v-for="group in groupedSuggestions"
            :key="group.key"
            :name="group.key"
            :title="scoreLabels[group.key]"
            :value="`${group.items.length} 条`"
            :title-class="'collapse-title-error'"
          >
            <div class="suggestion-item" v-for="(item, index) in group.items" :key="`${group.key}-${index}`">
              <div class="sug-header">
                <span class="sug-issue">{{ item.problem }}</span>
                <div class="sug-actions">
                  <van-icon name="edit" size="16" @click="editSuggestion(group.key, index)" />
                  <van-icon name="delete-o" size="16" color="#ee0a24" @click="deleteSuggestion(group.key, index)" />
                </div>
              </div>
              <div class="sug-meta" v-if="item.location || item.severity">
                {{ item.location || '全文' }} · {{ severityLabels[item.severity] || item.severity }}
              </div>
              <div class="sug-fix">{{ item.suggestion }}</div>
            </div>
          </van-collapse-item>
        </van-collapse>
      </div>

      <van-empty v-else description="当前没有待处理建议" image="search" />
    </div>

    <div class="bottom-actions">
      <template v-if="!isPassed">
        <van-button icon="replay" type="warning" class="action-btn" @click="handleRewrite('all')">
          全部重写
        </van-button>
        <van-button icon="edit" type="primary" class="action-btn" @click="handleRewrite('suggested')">
          按建议重写
        </van-button>
      </template>

      <template v-else>
        <van-button icon="replay" type="default" class="action-btn" @click="handleRewrite('all')">
          仍要重写
        </van-button>
        <van-button icon="passed" type="success" class="action-btn" @click="handleApprove">
          通过并总结
        </van-button>
      </template>
    </div>

    <van-dialog v-model:show="showEditDialog" title="编辑建议" show-cancel-button @confirm="saveSuggestion">
      <van-form>
        <van-cell-group inset>
          <van-field
            v-model="editingForm.problem"
            rows="2"
            autosize
            label="存在问题"
            type="textarea"
            placeholder="描述问题"
          />
          <van-field
            v-model="editingForm.suggestion"
            rows="2"
            autosize
            label="修改建议"
            type="textarea"
            placeholder="如何修改"
          />
        </van-cell-group>
      </van-form>
    </van-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { showConfirmDialog, showToast } from 'vant';

import { useProjectStore } from '@/stores/project';
import { getRuntimeConfig, nowString } from '@/lib/workflow';
import { apiUrl, loginUrl } from '@/api/url';

const emit = defineEmits(['rewrite', 'approve']);

const projectStore = useProjectStore();

const scoreLabels = {
  literary: '文学性',
  logic: '逻辑性',
  style: '风格一致性',
  ai_feel: '人味',
};

const severityLabels = {
  high: '高优先级',
  medium: '中优先级',
  low: '低优先级',
};

const scoreList = ref([
  { key: 'literary', label: scoreLabels.literary, value: 0, hasIssue: false },
  { key: 'logic', label: scoreLabels.logic, value: 0, hasIssue: false },
  { key: 'style', label: scoreLabels.style, value: 0, hasIssue: false },
  { key: 'ai_feel', label: scoreLabels.ai_feel, value: 0, hasIssue: false },
]);
const suggestions = ref([]);
const activeNames = ref('');
const showEditDialog = ref(false);
const editingForm = ref({ dim: '', index: -1, problem: '', suggestion: '' });
const isLoading = ref(false);
const lastReviewedSignature = ref('');

const passScore = computed(() => Number(projectStore.config?.pass_score ?? 8));
const currentStyleId = computed(() =>
  String(projectStore.selectedStyleId || projectStore.defaultStyleId || '').trim(),
);

const averageScore = computed(() => {
  const total = scoreList.value.reduce((sum, item) => sum + Number(item.value || 0), 0);
  return (total / scoreList.value.length).toFixed(2);
});

const isPassed = computed(() => Number(averageScore.value) >= passScore.value);

const groupedSuggestions = computed(() => {
  const groups = {};
  for (const item of suggestions.value) {
    if (!groups[item.dim]) {
      groups[item.dim] = [];
    }
    groups[item.dim].push(item);
  }

  return Object.entries(groups).map(([key, items]) => ({ key, items }));
});

const getReviewSignature = (content, styleId = currentStyleId.value) =>
  `${String(styleId || '').trim()}::${String(content || '').trim()}`;

const findPersistedReview = (signature) => {
  for (let index = projectStore.reviews.length - 1; index >= 0; index -= 1) {
    const item = projectStore.reviews[index];
    if (getReviewSignature(item.content, item.style_id) === signature) {
      return item;
    }
  }

  return null;
};

const applyReview = (review) => {
  const items = Array.isArray(review.items) ? review.items : [];
  const scores = review.scores || {};

  scoreList.value = scoreList.value.map((item) => ({
    ...item,
    value: Number(scores[item.key] ?? 0),
    hasIssue: items.some((reviewItem) => reviewItem.dim === item.key),
  }));
  suggestions.value = items.map((item) => ({
    dim: item.dim || 'literary',
    severity: item.severity || 'medium',
    location: item.location || '',
    problem: item.problem || '',
    suggestion: item.suggestion || '',
  }));
  activeNames.value = suggestions.value[0]?.dim || '';
};

const persistReview = () => {
  const record = {
    time: nowString(),
    content: projectStore.currentContent,
    style_id: currentStyleId.value,
    review: {
      scores: Object.fromEntries(scoreList.value.map((item) => [item.key, item.value])),
      average: Number(averageScore.value),
      passed: isPassed.value,
      items: suggestions.value,
    },
  };

  const latestIndex = projectStore.reviews.findIndex(
    (item) => getReviewSignature(item.content, item.style_id) === getReviewSignature(projectStore.currentContent),
  );
  if (latestIndex >= 0) {
    projectStore.reviews.splice(latestIndex, 1, record);
  } else {
    projectStore.reviews.push(record);
  }
};

const runReview = async () => {
  if (isLoading.value) {
    return;
  }

  const content = String(projectStore.currentContent || '').trim();
  const reviewSignature = getReviewSignature(content);
  if (!content) {
    showToast('先生成正文再审核');
    return;
  }

  if (lastReviewedSignature.value === reviewSignature && projectStore.reviews.length > 0) {
    const cachedReview = findPersistedReview(reviewSignature)?.review;
    if (cachedReview) {
      applyReview(cachedReview);
      return;
    }
  }

  const config = getRuntimeConfig(projectStore.config);
  if (!config) {
    showToast('请先在设置页填写 Bot3 配置');
    return;
  }

  isLoading.value = true;
  try {
    const response = await fetch(apiUrl('/api/bot3/review'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content,
        outline: projectStore.currentOutline || projectStore.chapterOutline,
        config,
        style_id: currentStyleId.value,
        custom_prompt: '',
      }),
    });

    if (response.status === 401) {
      window.location.href = loginUrl();
      return;
    }
    const review = await response.json();
    if (review.error && !review.scores) {
      throw new Error(review.error);
    }

    applyReview(review);
    persistReview();
    lastReviewedSignature.value = reviewSignature;
    await projectStore.saveProject();
  } catch (error) {
    showToast(error.message || 'Bot3 审核失败');
  } finally {
    isLoading.value = false;
  }
};

const deleteSuggestion = (dim, index) => {
  showConfirmDialog({
    title: '确认删除',
    message: '删除后，这条建议不会再参与重写。',
  })
    .then(() => {
      const target = groupedSuggestions.value.find((group) => group.key === dim)?.items[index];
      const globalIndex = suggestions.value.indexOf(target);
      if (globalIndex >= 0) {
        suggestions.value.splice(globalIndex, 1);
      }
    })
    .catch(() => {});
};

const editSuggestion = (dim, index) => {
  const target = groupedSuggestions.value.find((group) => group.key === dim)?.items[index];
  if (!target) {
    return;
  }

  editingForm.value = {
    dim,
    index,
    problem: target.problem,
    suggestion: target.suggestion,
  };
  showEditDialog.value = true;
};

const saveSuggestion = () => {
  const { dim, index, problem, suggestion } = editingForm.value;
  const target = groupedSuggestions.value.find((group) => group.key === dim)?.items[index];
  const globalIndex = suggestions.value.indexOf(target);
  if (globalIndex >= 0) {
    suggestions.value[globalIndex] = {
      ...suggestions.value[globalIndex],
      problem,
      suggestion,
    };
  }
};

const handleRewrite = (type) => {
  const message = type === 'all'
    ? '确定要整章重写吗？'
    : '将按当前审核建议重新生成正文，确定继续吗？';

  showConfirmDialog({
    title: '确认重写',
    message,
  })
    .then(() => {
      persistReview();
      emit('rewrite', {
        type,
        suggestions: type === 'suggested' ? suggestions.value : [],
      });
    })
    .catch(() => {});
};

const handleApprove = async () => {
  persistReview();
  await projectStore.saveProject();
  showToast('章节审核通过');
  emit('approve');
};

onMounted(() => {
  const reviewSignature = getReviewSignature(projectStore.currentContent);
  const latest = findPersistedReview(reviewSignature);
  if (latest?.review) {
    applyReview(latest.review);
    lastReviewedSignature.value = reviewSignature;
  }
});

defineExpose({
  runReview,
});
</script>

<style scoped>
.review-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #f7f8fa;
}

.review-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  color: #fff;
  flex-shrink: 0;
}

.review-status-bar.pass {
  background-color: #07c160;
}

.review-status-bar.fail {
  background-color: #ee0a24;
}

.status-left .status-text {
  display: flex;
  align-items: center;
  font-size: 15px;
  font-weight: bold;
}

.status-copy {
  margin-left: 4px;
}

.review-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  overflow-y: auto;
}

.score-card,
.suggestions-card {
  padding: 16px;
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.section-title {
  margin: 0;
  padding-left: 8px;
  color: #323233;
  font-size: 16px;
  border-left: 4px solid #1989fa;
}

.score-item {
  margin-bottom: 24px;
}

.score-item:last-child {
  margin-bottom: 8px;
}

.score-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.score-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #646566;
  font-size: 14px;
}

.score-label.has-issue {
  color: #ee0a24;
  font-weight: 500;
}

.score-value {
  color: #323233;
  font-size: 16px;
  font-weight: bold;
}

:deep(.collapse-title-error .van-cell__title) {
  color: #ee0a24;
  font-weight: 500;
}

.suggestion-item {
  margin-bottom: 12px;
  padding: 12px;
  background-color: #f7f8fa;
  border-radius: 6px;
}

.suggestion-item:last-child {
  margin-bottom: 0;
}

.sug-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.sug-issue {
  flex: 1;
  padding-right: 12px;
  color: #323233;
  font-size: 14px;
  font-weight: bold;
}

.sug-actions {
  display: flex;
  gap: 12px;
  color: #969799;
}

.sug-meta {
  margin-bottom: 8px;
  color: #969799;
  font-size: 12px;
}

.sug-fix {
  padding-left: 8px;
  color: #646566;
  font-size: 14px;
  line-height: 1.5;
  border-left: 2px solid #07c160;
}

.bottom-actions {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background-color: #fff;
  border-top: 1px solid #ebedf0;
  flex-shrink: 0;
}

.action-btn {
  flex: 1;
}
</style>
