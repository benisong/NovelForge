// 04-review.js - Bot3 review panel rendering, editing, and review history

function buildReviewRewriteBrief(review, passScore) {
  const existing = String(review?.rewrite_brief || review?.rewrite_plan || '').trim();
  if (existing) return existing;

  const scores = review?.scores || {};
  const items = Array.isArray(review?.items) ? review.items : [];
  const analysis = String(review?.analysis || '').trim();
  const failingDims = REVIEW_DIMS
    .filter((dim) => Number(scores[dim.key] ?? 0) < passScore)
    .map((dim) => dim.label);

  const lines = [];
  if (failingDims.length) {
    lines.push(`先把${failingDims.join('、')}拉回及格线，优先处理硬伤，再做润色。`);
  } else {
    lines.push('保留当前成稿的优点，只做针对性的局部修正，不要整章推倒重来。');
  }

  const severityRank = { high: 0, medium: 1, low: 2 };
  items
    .slice()
    .sort((left, right) => {
      const gap = (severityRank[left.severity] ?? 9) - (severityRank[right.severity] ?? 9);
      if (gap !== 0) return gap;
      return String(left.dim || '').localeCompare(String(right.dim || ''));
    })
    .slice(0, 4)
    .forEach((item, index) => {
      const dimLabel = DIM_LABEL_MAP[item.dim] || item.dim || '问题';
      const location = item.location || '全文';
      const action = item.suggestion || item.problem || '请直接重写这一处';
      lines.push(`${index + 1}. [${dimLabel}] ${location}：${action}`);
    });

  if (analysis) {
    lines.push(`整体把握：${analysis.split('\n')[0].trim().slice(0, 80)}`);
  }

  return lines.join('\n').trim();
}

// editable: 是否可编辑  showActions: 是否显示用户决策按钮
function renderReviewPanel(review, attempt, editable, showActions){
  const sc = review.scores || {};
  const avg = review.average || 0;
  const p = review.passed;
  const items = Array.isArray(review.items) ? review.items : [];
  const passScore = getConfig().pass_score || 8;
  const rewriteBrief = buildReviewRewriteBrief(review, passScore);

  const grouped = {};
  REVIEW_DIMS.forEach((dim) => { grouped[dim.key] = []; });
  items.forEach((item, index) => {
    const key = item.dim || 'literary';
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push({ ...item, _idx: index });
  });

  const dimsHtml = REVIEW_DIMS.map((dim) => {
    const value = sc[dim.key] || 0;
    const dimItems = grouped[dim.key] || [];
    const hasItems = dimItems.length > 0;

    const scoreEl = editable
      ? `<input type="number" class="score-edit-input" id="edit-score-${dim.key}" value="${value}" min="0" max="10" step="0.5">`
      : `<span class="dg-score" style="color:${scoreColor(value)}">${value}</span>`;

    let itemsInner = '';
    if (hasItems) {
      dimItems.forEach((item) => { itemsInner += _renderOneItem(item, item._idx, editable); });
    } else {
      itemsInner = '<div style="font-size:11px;color:var(--text-muted);padding:8px;text-align:center;font-style:italic;">该维度暂无具体建议</div>';
    }

    const countBadge = hasItems ? `<span class="dg-count">${dimItems.length}条建议</span>` : '';

    return `<details class="dim-group${hasItems ? ' has-items' : ''}">
      <summary class="dim-group-summary" title="${dim.desc}">
        <span class="dg-label">${dim.label}</span>
        ${countBadge}
        <div class="dim-group-bar"><div class="dim-group-bar-fill" id="bar-${dim.key}" style="width:${value * 10}%;background:${scoreColor(value)}"></div></div>
        ${scoreEl}
      </summary>
      <div class="dim-group-items" id="dimItems-${dim.key}">${itemsInner}</div>
    </details>`;
  }).join('');

  const addItemHtml = editable
    ? '<div style="text-align:right;margin-top:4px;"><button class="btn-add-item" onclick="_addReviewItem()">+ 新增建议</button></div>'
    : '';

  const avgHtml = `<div class="review-avg-box"><div class="avg-label">平均分（及格线：${passScore}）</div><div class="avg-score" id="reviewAvgDisplay" style="color:${p ? 'var(--accent-green)' : 'var(--accent-red)'}">${avg}</div><div class="avg-status" id="reviewStatusDisplay" style="color:${p ? 'var(--accent-green)' : 'var(--accent-red)'}">${p ? '&#10004; 审核通过' : '&#10008; 未通过'}</div></div>`;

  const rewriteHtml = editable
    ? `<div style="font-size:12px;color:var(--text-muted);margin:10px 0 4px;font-weight:600">Bot2 重写指令 <span style="font-weight:400;color:var(--accent-blue)">(可编辑)</span></div><textarea class="review-edit-textarea" id="editRewriteBrief">${_escHtml(rewriteBrief)}</textarea>`
    : `<div style="font-size:12px;color:var(--text-muted);margin:10px 0 4px;font-weight:600">Bot2 重写指令</div><div class="review-detail-text">${_escHtml(rewriteBrief).replace(/\n/g,'<br>')}</div>`;

  const analysisHtml = editable
    ? `<div style="font-size:12px;color:var(--text-muted);margin:10px 0 4px;font-weight:600">综合评价 <span style="font-weight:400;color:var(--accent-blue)">(可编辑)</span></div><textarea class="review-edit-textarea" id="editAnalysis">${_escHtml(review.analysis || '')}</textarea>`
    : `<div style="font-size:12px;color:var(--text-muted);margin:10px 0 4px;font-weight:600">综合评价</div><div class="review-detail-text">${_escHtml(review.analysis || '无')}</div>`;

  let actionsHtml = '';
  if (showActions) {
    actionsHtml = `<div class="review-action-bar" id="reviewActionBar">
      <button class="btn-accept" onclick="userDecisionAccept()">&#10004; 通过</button>
      <button class="btn-rewrite" onclick="userDecisionRewrite()">&#128260; 按建议重写</button>
      <button class="btn-rewrite" style="background:var(--accent-red);color:#fff;" onclick="userDecisionFullRewrite()">&#128259; 全部重写</button>
    </div>`;
    if (editable) {
      actionsHtml += '<div class="edit-mode-hint">你可以直接编辑重写指令、评分和逐条建议，Bot2 会优先按这份修改稿执行。</div>';
    }
  }

  let rawHtml = '';
  if (review._raw_preview && review.retry_hint) {
    rawHtml = `<details open style="margin-top:10px;border:1px solid var(--border);border-radius:6px;padding:8px;background:var(--bg-card)">
      <summary style="cursor:pointer;font-size:12px;color:var(--accent-red);font-weight:600">&#9888; Bot3 未给出可解析的逐条建议 - 点击查看 AI 原始回复</summary>
      <pre style="margin-top:6px;white-space:pre-wrap;word-break:break-all;font-size:11px;max-height:300px;overflow:auto;color:var(--text-muted)">${_escHtml(review._raw_preview)}</pre>
    </details>`;
  }

  $('reviewScorePanel').innerHTML = dimsHtml + addItemHtml + avgHtml + rewriteHtml + analysisHtml + rawHtml + actionsHtml;

  if (editable) {
    REVIEW_DIMS.forEach((dim) => {
      const input = $('edit-score-' + dim.key);
      if (input) input.addEventListener('input', () => _updateScoreBarsLive());
    });
  }
}

function _renderOneItem(item, idx, editable) {
  const dimLabel = DIM_LABEL_MAP[item.dim] || item.dim || '其他';
  const sevLabel = SEV_LABEL[item.severity] || item.severity || 'medium';
  const sevCls = 'sev-' + (item.severity || 'medium');

  if (editable) {
    return `<div class="review-item severity-${item.severity || 'medium'}" data-idx="${idx}">
      <button class="ri-delete" onclick="_deleteReviewItem(${idx})" title="删除此条">&#10005;</button>
      <div class="ri-top">
        <select class="ri-inline-select" data-field="severity" data-idx="${idx}" onchange="_onItemFieldChange(this)">
          <option value="high"${item.severity === 'high' ? ' selected' : ''}>必须改</option>
          <option value="medium"${item.severity === 'medium' ? ' selected' : ''}>建议改</option>
          <option value="low"${item.severity === 'low' ? ' selected' : ''}>可选改</option>
        </select>
        <select class="ri-inline-select" data-field="dim" data-idx="${idx}" onchange="_onItemFieldChange(this)">
          ${REVIEW_DIMS.map((dim) => `<option value="${dim.key}"${item.dim === dim.key ? ' selected' : ''}>${dim.label}</option>`).join('')}
        </select>
        <input class="ri-edit-input" style="flex:1;min-height:auto" data-field="location" data-idx="${idx}" value="${_escHtml(item.location || '')}" placeholder="位置（如：第3段对话）">
      </div>
      <div class="ri-field"><div class="ri-field-label">问题</div><textarea class="ri-edit-input" data-field="problem" data-idx="${idx}" rows="2">${_escHtml(item.problem || '')}</textarea></div>
      <div class="ri-field"><div class="ri-field-label">建议</div><textarea class="ri-edit-input" data-field="suggestion" data-idx="${idx}" rows="2">${_escHtml(item.suggestion || '')}</textarea></div>
    </div>`;
  }

  return `<div class="review-item severity-${item.severity || 'medium'}">
    <div class="ri-top">
      <span class="ri-badge ${sevCls}">${sevLabel}</span>
      <span class="ri-badge dim-badge">${dimLabel}</span>
      <span class="ri-location">${_escHtml(item.location || '')}</span>
    </div>
    <div class="ri-field"><div class="ri-field-label">问题</div><div class="ri-text">${_escHtml(item.problem || '')}</div></div>
    <div class="ri-field"><div class="ri-field-label">建议</div><div class="ri-text">${_escHtml(item.suggestion || '')}</div></div>
  </div>`;
}

function _getAllReviewItems() {
  const all = [];
  REVIEW_DIMS.forEach((dim) => {
    const container = $('dimItems-' + dim.key);
    if (container) container.querySelectorAll('.review-item').forEach((el) => all.push(el));
  });
  return all;
}

function _deleteReviewItem(idx) {
  const all = _getAllReviewItems();
  if (all[idx]) {
    const container = all[idx].parentElement;
    all[idx].remove();
    if (container && container.querySelectorAll('.review-item').length === 0) {
      container.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:8px;text-align:center;font-style:italic;">该维度暂无具体建议</div>';
    }
    _updateDimGroupCounts();
  }
  _reindexAllItems();
}

function _addReviewItem() {
  const targetDim = 'literary';
  const container = $('dimItems-' + targetDim);
  if (!container) return;
  if (container.querySelectorAll('.review-item').length === 0) container.innerHTML = '';
  const idx = _getAllReviewItems().length;
  const newItem = { dim: targetDim, severity: 'medium', location: '', problem: '', suggestion: '' };
  container.insertAdjacentHTML('beforeend', _renderOneItem(newItem, idx, true));
  const details = container.closest('details.dim-group');
  if (details) details.open = true;
  const last = container.lastElementChild;
  if (last) last.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  _updateDimGroupCounts();
}

function _reindexAllItems() {
  _getAllReviewItems().forEach((el, index) => {
    el.dataset.idx = index;
    const delBtn = el.querySelector('.ri-delete');
    if (delBtn) delBtn.setAttribute('onclick', `_deleteReviewItem(${index})`);
    el.querySelectorAll('[data-idx]').forEach((field) => { field.dataset.idx = index; });
  });
}

function _updateDimGroupCounts() {
  REVIEW_DIMS.forEach((dim) => {
    const container = $('dimItems-' + dim.key);
    if (!container) return;
    const count = container.querySelectorAll('.review-item').length;
    const summary = container.closest('details.dim-group')?.querySelector('.dg-count');
    if (summary) summary.textContent = count ? count + '条建议' : '';
  });
}

function _onItemFieldChange(el) {
  if (el.dataset.field === 'severity') {
    const item = el.closest('.review-item');
    if (item) item.className = 'review-item severity-' + el.value;
  }
  if (el.dataset.field === 'dim') {
    const item = el.closest('.review-item');
    if (!item) return;
    const newDim = el.value;
    const target = $('dimItems-' + newDim);
    if (!target) return;
    if (target.querySelectorAll('.review-item').length === 0) target.innerHTML = '';
    const oldContainer = item.parentElement;
    target.appendChild(item);
    const details = target.closest('details.dim-group');
    if (details) details.open = true;
    if (oldContainer && oldContainer.querySelectorAll('.review-item').length === 0) {
      oldContainer.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:8px;text-align:center;font-style:italic;">该维度暂无具体建议</div>';
    }
    _reindexAllItems();
    _updateDimGroupCounts();
  }
}

function _updateScoreBarsLive() {
  let sum = 0;
  let count = 0;
  const passScore = getConfig().pass_score || 8;
  REVIEW_DIMS.forEach((dim) => {
    const input = $('edit-score-' + dim.key);
    if (!input) return;
    let value = parseFloat(input.value) || 0;
    value = Math.max(0, Math.min(10, value));
    const bar = $('bar-' + dim.key);
    if (bar) {
      bar.style.width = value * 10 + '%';
      bar.style.background = scoreColor(value);
    }
    input.style.color = scoreColor(value);
    sum += value;
    count++;
  });
  const avg = count ? Math.round(sum / count * 10) / 10 : 0;
  const passed = avg >= passScore;
  const avgEl = $('reviewAvgDisplay');
  const statusEl = $('reviewStatusDisplay');
  if (avgEl) {
    avgEl.textContent = avg;
    avgEl.style.color = passed ? 'var(--accent-green)' : 'var(--accent-red)';
  }
  if (statusEl) {
    statusEl.textContent = passed ? '✔ 审核通过' : '✘ 未通过';
    statusEl.style.color = passed ? 'var(--accent-green)' : 'var(--accent-red)';
  }
}

function readEditedReview() {
  const scores = {};
  let sum = 0;
  let count = 0;

  REVIEW_DIMS.forEach((dim) => {
    const input = $('edit-score-' + dim.key);
    let value = input ? parseFloat(input.value) || 0 : 0;
    value = Math.max(0, Math.min(10, value));
    scores[dim.key] = value;
    sum += value;
    count++;
  });

  const average = count ? Math.round(sum / count * 10) / 10 : 0;
  const passScore = getConfig().pass_score || 8;

  const items = [];
  _getAllReviewItems().forEach((el) => {
    const get = (field) => {
      const target = el.querySelector(`[data-field="${field}"]`);
      return target ? (target.value || target.textContent || '') : '';
    };
    items.push({
      dim: get('dim'),
      severity: get('severity'),
      location: get('location'),
      problem: get('problem'),
      suggestion: get('suggestion'),
    });
  });

  const analysis = $('editAnalysis') ? $('editAnalysis').value : '';
  const rewriteBrief = $('editRewriteBrief')
    ? $('editRewriteBrief').value
    : buildReviewRewriteBrief({ scores, items, analysis }, passScore);

  const suggestionsText = items.map((item, index) => {
    const dimLabel = DIM_LABEL_MAP[item.dim] || item.dim;
    const sevLabel = SEV_LABEL[item.severity] || item.severity;
    return `${index + 1}. [${sevLabel}][${dimLabel}] 位置：${item.location || '全文'}\n   问题：${item.problem}\n   建议：${item.suggestion}`;
  }).join('\n\n');

  const combinedSuggestions = rewriteBrief
    ? suggestionsText
      ? `【Bot3重写指令】\n${rewriteBrief}\n\n【逐条修改建议】\n${suggestionsText}`
      : `【Bot3重写指令】\n${rewriteBrief}`
    : suggestionsText;

  return {
    scores,
    average,
    passed: average >= passScore,
    analysis,
    rewrite_brief: rewriteBrief,
    items,
    suggestions: combinedSuggestions.trim(),
  };
}

function addReviewToHistory(review, attempt) {
  S.reviews.push({ review, attempt, time: now() });
  const el = $('rhistoryPanel');
  const item = document.createElement('div');
  item.className = 'review-history-item';
  const passed = review.passed;
  item.innerHTML = `<span>第${attempt}次审核 [${now()}]</span><span class="badge ${passed ? 'badge-pass' : 'badge-fail'}">${passed ? '通过' : '未通过'} ${review.average || 0}分</span>`;
  item.onclick = () => { renderReviewPanel(review, attempt, true); switchTab('review'); };
  el.prepend(item);
}

function rebuildReviewHistoryUI() {
  $('rhistoryPanel').innerHTML = '';
  S.reviews.forEach((record) => {
    const item = document.createElement('div');
    item.className = 'review-history-item';
    const passed = record.review && record.review.passed;
    item.innerHTML = `<span>第${record.attempt}次审核 [${record.time}]</span><span class="badge ${passed ? 'badge-pass' : 'badge-fail'}">${passed ? '通过' : '未通过'} ${(record.review && record.review.average) || 0}分</span>`;
    item.onclick = () => { renderReviewPanel(record.review, record.attempt, true); switchTab('review'); };
    $('rhistoryPanel').prepend(item);
  });
  if (S.reviews.length) {
    const last = S.reviews[S.reviews.length - 1];
    renderReviewPanel(last.review, last.attempt, true);
  }
}
