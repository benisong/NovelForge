// 10-summary.js - Small/Big summary UI logic

// Module-level state
let _currentDetailType = null;   // 'small' | 'big'
let _currentDetailIndex = -1;
let _summaryView = 'condensed';  // 'condensed' | 'abstract'

// ============================================================
// 1. renderSmallSummaryList - render small summary list
// ============================================================
function renderSmallSummaryList() {
  const container = $('smallSummaryList');
  if (!container) return;
  container.innerHTML = '';
  if (!S.smallSummaries || S.smallSummaries.length === 0) {
    container.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:8px;">暂无小结</div>';
    return;
  }
  S.smallSummaries.forEach((item, i) => {
    const row = document.createElement('div');
    row.className = 'summary-list-item' +
      (_currentDetailType === 'small' && _currentDetailIndex === i ? ' active' : '');
    row.innerHTML = `<span class="sli-title">${_escHtml('第' + item.chapter + '章')}</span><span class="sli-time">${_escHtml(item.time || '')}</span>`;
    row.onclick = () => showSummaryDetail('small', i);
    container.appendChild(row);
  });
}

// ============================================================
// 2. renderBigSummaryList - render big summary list
// ============================================================
function renderBigSummaryList() {
  const container = $('bigSummaryList');
  if (!container) return;
  container.innerHTML = '';
  if (!S.bigSummaries || S.bigSummaries.length === 0) {
    container.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:8px;">暂无大结</div>';
    return;
  }
  S.bigSummaries.forEach((item, i) => {
    const row = document.createElement('div');
    row.className = 'summary-list-item' +
      (_currentDetailType === 'big' && _currentDetailIndex === i ? ' active' : '');
    row.innerHTML = `<span class="sli-title">${_escHtml('第' + item.fromChapter + '-' + item.toChapter + '章')}</span><span class="sli-time">${_escHtml(item.time || '')}</span>`;
    row.onclick = () => showSummaryDetail('big', i);
    container.appendChild(row);
  });
}

// ============================================================
// 3. showSummaryDetail - display detail in #summaryDetailContent
// ============================================================
function showSummaryDetail(type, index) {
  _currentDetailType = type;
  _currentDetailIndex = index;

  const detailEl = $('summaryDetailContent');
  if (!detailEl) return;

  if (type === 'small') {
    const item = S.smallSummaries[index];
    if (!item) { detailEl.textContent = '(无数据)'; return; }
    // Show condensed or abstract based on current toggle
    const btnCondensed = $('btnShowCondensed');
    const btnAbstract = $('btnShowAbstract');
    if (btnCondensed) btnCondensed.classList.toggle('active', _summaryView === 'condensed');
    if (btnAbstract) btnAbstract.classList.toggle('active', _summaryView === 'abstract');
    detailEl.textContent = _summaryView === 'abstract' ? (item.abstract || '(无摘要)') : (item.condensed || '(无缩略)');
  } else if (type === 'big') {
    const item = S.bigSummaries[index];
    if (!item) { detailEl.textContent = '(无数据)'; return; }
    detailEl.textContent = item.content || '(无内容)';
    // Hide condensed/abstract toggle for big summaries
    const btnCondensed = $('btnShowCondensed');
    const btnAbstract = $('btnShowAbstract');
    if (btnCondensed) btnCondensed.classList.remove('active');
    if (btnAbstract) btnAbstract.classList.remove('active');
  }

  // Update active states in both lists
  renderSmallSummaryList();
  renderBigSummaryList();
}

// ============================================================
// 4. toggleSummaryView - switch condensed / abstract view
// ============================================================
function toggleSummaryView(view) {
  _summaryView = view || 'condensed';

  const btnCondensed = $('btnShowCondensed');
  const btnAbstract = $('btnShowAbstract');
  if (btnCondensed) btnCondensed.classList.toggle('active', _summaryView === 'condensed');
  if (btnAbstract) btnAbstract.classList.toggle('active', _summaryView === 'abstract');

  // Re-render current detail if showing a small summary
  if (_currentDetailType === 'small' && _currentDetailIndex >= 0) {
    const item = S.smallSummaries[_currentDetailIndex];
    const detailEl = $('summaryDetailContent');
    if (item && detailEl) {
      detailEl.textContent = _summaryView === 'abstract' ? (item.abstract || '(无摘要)') : (item.condensed || '(无缩略)');
    }
  }
}

// ============================================================
// 5. checkBigSummaryReminder - check if big summary is due
// ============================================================
function checkBigSummaryReminder() {
  const threshold = (getConfig().big_summary_threshold) || 10;
  // Find the latest big summary's toChapter
  let lastBigTo = 0;
  if (S.bigSummaries && S.bigSummaries.length > 0) {
    lastBigTo = S.bigSummaries[S.bigSummaries.length - 1].toChapter || 0;
  }
  // Count small summaries created after the last big summary
  let count = 0;
  if (S.smallSummaries) {
    count = S.smallSummaries.filter(s => s.chapter > lastBigTo).length;
  }
  // Show or hide reminder badge
  const badge = $('bigSummaryBadge');
  if (badge) {
    if (count >= threshold) {
      badge.style.display = '';
      badge.textContent = count;
    } else {
      badge.style.display = 'none';
    }
  }
  return count;
}

// ============================================================
// 6. triggerBigSummary - open inline confirmation dialog
// ============================================================
function triggerBigSummary() {
  const confirmArea = $('bigSummaryConfirm');
  if (!confirmArea) return;

  // Determine chapter range
  let lastBigTo = 0;
  if (S.bigSummaries && S.bigSummaries.length > 0) {
    lastBigTo = S.bigSummaries[S.bigSummaries.length - 1].toChapter || 0;
  }
  const fromChapter = lastBigTo + 1;
  let toChapter = 0;
  if (S.smallSummaries && S.smallSummaries.length > 0) {
    toChapter = S.smallSummaries[S.smallSummaries.length - 1].chapter || 0;
  }
  if (toChapter < fromChapter) {
    addLog('system', '没有需要大结的新章节');
    return;
  }

  const totalChapters = toChapter - fromChapter + 1;
  // Estimate character count from small summaries in range
  let estimatedChars = 0;
  if (S.smallSummaries) {
    S.smallSummaries.forEach(s => {
      if (s.chapter >= fromChapter && s.chapter <= toChapter) {
        estimatedChars += (s.condensed || '').length;
      }
    });
  }

  // Auto-calculate: first N chapters use abstract, last M use condensed
  const defaultAbstractCount = Math.max(1, Math.floor(totalChapters * 0.6));
  const defaultCondensedCount = totalChapters - defaultAbstractCount;

  confirmArea.style.display = '';
  confirmArea.innerHTML = `
    <div style="padding:12px;background:var(--bg-tertiary);border-radius:8px;border:1px solid var(--border);margin:8px 0;">
      <div style="font-size:13px;font-weight:600;margin-bottom:8px;">生成大结确认</div>
      <div style="font-size:12px;color:var(--text-secondary);margin-bottom:8px;">
        章节范围：第${fromChapter}章 ~ 第${toChapter}章（共${totalChapters}章）<br>
        预估字数：约${estimatedChars}字
      </div>
      <div style="display:flex;gap:12px;align-items:center;margin-bottom:8px;font-size:12px;">
        <label>前<input id="bigSumAbstractN" type="number" min="0" max="${totalChapters}" value="${defaultAbstractCount}" style="width:48px;margin:0 4px;padding:2px 4px;background:var(--bg-input);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);text-align:center;">章用摘要</label>
        <label>后<input id="bigSumCondensedM" type="number" min="0" max="${totalChapters}" value="${defaultCondensedCount}" style="width:48px;margin:0 4px;padding:2px 4px;background:var(--bg-input);border:1px solid var(--border);border-radius:4px;color:var(--text-primary);text-align:center;">章用缩略原文</label>
      </div>
      <div style="display:flex;gap:8px;">
        <button onclick="executeBigSummary()" style="padding:5px 16px;background:var(--accent-green);color:#1e1e2e;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">确认生成</button>
        <button onclick="$('bigSummaryConfirm').style.display='none'" style="padding:5px 16px;background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:6px;font-size:12px;cursor:pointer;">取消</button>
      </div>
    </div>`;

  // Sync the two inputs so they always sum to totalChapters
  const inputN = $('bigSumAbstractN');
  const inputM = $('bigSumCondensedM');
  if (inputN && inputM) {
    inputN.oninput = () => { inputM.value = totalChapters - (parseInt(inputN.value) || 0); };
    inputM.oninput = () => { inputN.value = totalChapters - (parseInt(inputM.value) || 0); };
  }
}

// ============================================================
// 7. executeBigSummary - call API and stream result
// ============================================================
async function executeBigSummary() {
  const confirmArea = $('bigSummaryConfirm');
  if (confirmArea) confirmArea.style.display = 'none';

  // Determine range
  let lastBigTo = 0;
  if (S.bigSummaries && S.bigSummaries.length > 0) {
    lastBigTo = S.bigSummaries[S.bigSummaries.length - 1].toChapter || 0;
  }
  const fromChapter = lastBigTo + 1;
  let toChapter = 0;
  if (S.smallSummaries && S.smallSummaries.length > 0) {
    toChapter = S.smallSummaries[S.smallSummaries.length - 1].chapter || 0;
  }
  if (toChapter < fromChapter) return;

  const abstractN = parseInt(($('bigSumAbstractN') || {}).value) || 0;
  const condensedM = parseInt(($('bigSumCondensedM') || {}).value) || 0;

  // Gather small summaries in range
  const summariesInRange = (S.smallSummaries || []).filter(
    s => s.chapter >= fromChapter && s.chapter <= toChapter
  );

  const config = getConfig();
  const detailEl = $('summaryDetailContent');
  if (detailEl) { detailEl.textContent = ''; detailEl.className = 'output-area'; }

  addLog('bot4', `开始生成大结：第${fromChapter}-${toChapter}章...`);
  setStatus('busy', 'Bot4生成大结中...');
  S.isGenerating = true;

  try {
    const body = {
      from_chapter: fromChapter,
      to_chapter: toChapter,
      abstract_count: abstractN,
      condensed_count: condensedM,
      summaries: summariesInRange,
      config,
      abstract_model: getBot4AbstractModel(),
    };
    const result = await readSSE('/api/bot4/big-summarize', body, (chunk, full) => {
      if (detailEl) { detailEl.textContent = full; detailEl.scrollTop = 99999; }
    }, S.abortCtrl ? S.abortCtrl.signal : null);

    if (!result || !result.trim()) throw new Error('Bot4大结返回空内容');

    // Save to state
    const entry = {
      fromChapter,
      toChapter,
      content: result,
      time: now(),
    };
    if (!S.bigSummaries) S.bigSummaries = [];
    S.bigSummaries.push(entry);

    // Update UI
    renderBigSummaryList();
    showSummaryDetail('big', S.bigSummaries.length - 1);
    checkBigSummaryReminder();
    addLog('bot4', `大结生成完成：第${fromChapter}-${toChapter}章，共${result.length}字`);
    setStatus('ready', '大结生成完成');
    _autoSave();
  } catch (e) {
    if (e.name === 'AbortError') {
      addLog('system', '已停止大结生成');
    } else {
      addLog('error', `大结生成失败: ${e.message}`);
      setStatus('error', '大结生成失败');
    }
    if (detailEl && !detailEl.textContent) {
      detailEl.textContent = '(生成失败，请重试)';
    }
  }
  S.isGenerating = false;
}

// ============================================================
// 8. rebuildSummaryUI - rebuild both lists from saved state
// ============================================================
function rebuildSummaryUI() {
  renderSmallSummaryList();
  renderBigSummaryList();
  checkBigSummaryReminder();

  // Show the latest summary in detail if available
  if (S.bigSummaries && S.bigSummaries.length > 0) {
    showSummaryDetail('big', S.bigSummaries.length - 1);
  } else if (S.smallSummaries && S.smallSummaries.length > 0) {
    showSummaryDetail('small', S.smallSummaries.length - 1);
  }
}
