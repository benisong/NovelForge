<template>
  <div class="review-view">
    <div class="review-status-bar" :class="{ 'pass': isPassed, 'fail': !isPassed }">
      <div class="status-left">
        <span class="status-text">
          <van-icon :name="isPassed ? 'passed' : 'close'" size="18" />
          <span style="margin-left: 4px;">
            审核{{ isPassed ? '通过' : '未通过' }} (平均分: {{ averageScore }})
          </span>
        </span>
      </div>
      <div class="status-right">
        <van-tag :type="isPassed ? 'success' : 'danger'" plain>及格线: 8.0</van-tag>
      </div>
    </div>

    <div class="review-content">
      <!-- 评分卡 (用户可滑动编辑) -->
      <div class="score-card">
        <h3 class="section-title">维度评分</h3>
        <div class="score-item" v-for="(item, key) in scores" :key="key">
          <div class="score-header">
            <span class="score-label" :class="{ 'has-issue': item.hasIssue }">
              {{ item.label }}
              <van-tag v-if="item.hasIssue" type="danger" round size="medium">需改进</van-tag>
            </span>
            <span class="score-value">{{ item.value.toFixed(1) }}</span>
          </div>
          <van-slider 
            v-model="item.value" 
            :min="0" :max="10" :step="0.5" 
            :button-size="'20px'"
            :active-color="item.value >= 8 ? '#07c160' : '#ee0a24'"
          />
        </div>
      </div>

      <!-- 修改建议列表 -->
      <div class="suggestions-card" v-if="hasSuggestions">
        <h3 class="section-title">修改建议</h3>
        <van-collapse v-model="activeNames" accordion>
          <van-collapse-item 
            v-for="(group, key) in groupedSuggestions" 
            :key="key" 
            :name="key"
            :title="scores[key].label"
            :value="group.length + '条'"
            :title-class="'collapse-title-error'"
          >
            <div class="suggestion-item" v-for="(sug, index) in group" :key="index">
              <div class="sug-header">
                <span class="sug-issue">{{ sug.issue }}</span>
                <div class="sug-actions">
                  <van-icon name="edit" size="16" @click="editSuggestion(key, index)" />
                  <van-icon name="delete-o" size="16" color="#ee0a24" @click="deleteSuggestion(key, index)" />
                </div>
              </div>
              <div class="sug-fix">{{ sug.fix }}</div>
            </div>
          </van-collapse-item>
        </van-collapse>
      </div>
      <van-empty v-else description="太棒了，完美的一章！" image="search" />
    </div>

    <!-- 底部操作按钮 -->
    <div class="bottom-actions">
      <!-- 如果不通过，主要动作是重写 -->
      <template v-if="!isPassed">
        <van-button 
          icon="replay" 
          type="warning" 
          class="action-btn"
          @click="handleRewrite('all')"
        >全部重写</van-button>
        <van-button 
          icon="edit" 
          type="primary" 
          class="action-btn"
          @click="handleRewrite('suggested')"
        >按建议重写</van-button>
      </template>

      <!-- 如果通过，主要动作是下一步或强行重写 -->
      <template v-else>
        <van-button 
          icon="replay" 
          type="default" 
          class="action-btn"
          @click="handleRewrite('all')"
        >仍要重写</van-button>
        <van-button 
          icon="passed" 
          type="success" 
          class="action-btn"
          @click="handleApprove"
          v-show="false"
        >通过并总结</van-button>
      </template>
    </div>

    <!-- 编辑建议弹窗 -->
    <van-dialog v-model:show="showEditDialog" title="编辑建议" show-cancel-button @confirm="saveSuggestion">
      <van-form>
        <van-cell-group inset>
          <van-field
            v-model="editingForm.issue"
            rows="2"
            autosize
            label="存在问题"
            type="textarea"
            placeholder="描述问题"
          />
          <van-field
            v-model="editingForm.fix"
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
import { ref, computed } from 'vue';
import { showConfirmDialog, showToast } from 'vant';

const emit = defineEmits(['rewrite', 'approve']);

// 模拟审核数据
const scores = ref({
  literary: { label: '文学性', value: 8.5, hasIssue: false },
  logic: { label: '逻辑性', value: 7.5, hasIssue: true },
  style: { label: '风格一致性', value: 9.0, hasIssue: false },
  ai_feel: { label: '人味', value: 8.0, hasIssue: false }
});

const suggestions = ref([
  { dim: 'logic', issue: '夜枭在上一段描述中右手受了枪伤，但在这里却用右手拔枪，逻辑冲突。', fix: '改为使用左手拔枪，或者描述忍痛使用右手的细节。' }
]);

const activeNames = ref('logic'); // 默认展开有问题的一项

const showEditDialog = ref(false);
const editingForm = ref({ dim: '', index: -1, issue: '', fix: '' });

const averageScore = computed(() => {
  let total = 0;
  for (let key in scores.value) {
    total += scores.value[key].value;
  }
  return (total / Object.keys(scores.value).length).toFixed(2);
});

const isPassed = computed(() => averageScore.value >= 8.0);

const hasSuggestions = computed(() => suggestions.value.length > 0);

const groupedSuggestions = computed(() => {
  const groups = {};
  suggestions.value.forEach(sug => {
    if (!groups[sug.dim]) groups[sug.dim] = [];
    groups[sug.dim].push(sug);
  });
  return groups;
});

const deleteSuggestion = (dim, index) => {
  showConfirmDialog({
    title: '确认删除',
    message: '删除这条建议后，Bot2 重写时将忽略此问题。',
  }).then(() => {
    const globalIndex = suggestions.value.findIndex(s => s.dim === dim && suggestions.value.filter(s => s.dim === dim).indexOf(s) === index);
    if (globalIndex !== -1) {
      suggestions.value.splice(globalIndex, 1);
      // 更新 scores 的 hasIssue 状态
      scores.value[dim].hasIssue = groupedSuggestions.value[dim] && groupedSuggestions.value[dim].length > 0;
    }
  }).catch(() => {});
};

const editSuggestion = (dim, index) => {
  const group = groupedSuggestions.value[dim];
  editingForm.value = { 
    dim, 
    index, 
    issue: group[index].issue, 
    fix: group[index].fix 
  };
  showEditDialog.value = true;
};

const saveSuggestion = () => {
  const { dim, index, issue, fix } = editingForm.value;
  const globalIndex = suggestions.value.findIndex(s => s.dim === dim && suggestions.value.filter(s => s.dim === dim).indexOf(s) === index);
  if (globalIndex !== -1) {
    suggestions.value[globalIndex].issue = issue;
    suggestions.value[globalIndex].fix = fix;
  }
};

const handleRewrite = (type) => {
  let msg = type === 'all' ? '确定要完全推翻这一章重新生成吗？' : '将根据当前的修改建议重新生成正文，确定吗？';
  showConfirmDialog({
    title: '确认重写',
    message: msg,
  }).then(() => {
    emit('rewrite', { type, suggestions: type === 'suggested' ? suggestions.value : [] });
  }).catch(() => {});
};

const handleApprove = () => {
  showToast('章节已通过审核并保存！');
  emit('approve');
};
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
  font-size: 15px;
  font-weight: bold;
  display: flex;
  align-items: center;
}

.review-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.score-card, .suggestions-card {
  background-color: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.section-title {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 16px;
  color: #323233;
  border-left: 4px solid #1989fa;
  padding-left: 8px;
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
  font-size: 14px;
  color: #646566;
  display: flex;
  align-items: center;
  gap: 8px;
}
.score-label.has-issue {
  color: #ee0a24;
  font-weight: 500;
}

.score-value {
  font-size: 16px;
  font-weight: bold;
  color: #323233;
}

/* 覆盖 Vant Collapse 样式以强调错误 */
:deep(.collapse-title-error .van-cell__title) {
  color: #ee0a24;
  font-weight: 500;
}

.suggestion-item {
  background-color: #f7f8fa;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
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
  font-weight: bold;
  color: #323233;
  font-size: 14px;
  flex: 1;
  padding-right: 12px;
}

.sug-actions {
  display: flex;
  gap: 12px;
  color: #969799;
}

.sug-fix {
  font-size: 14px;
  color: #646566;
  line-height: 1.5;
  border-left: 2px solid #07c160;
  padding-left: 8px;
}

.bottom-actions {
  display: flex;
  padding: 12px 16px;
  background-color: #fff;
  border-top: 1px solid #ebedf0;
  gap: 12px;
  flex-shrink: 0;
}

.action-btn {
  flex: 1;
}
</style>
