// 04-review.js - Bot3 review panel rendering, editing, and review history

// editable: 是否可编辑; showActions: 是否显示用户决策按钮
function renderReviewPanel(review, attempt, editable, showActions){
  const sc=review.scores||{},avg=review.average||0,p=review.passed;
  const items=review.items||[];

  // 按维度分组items
  const grouped={};
  REVIEW_DIMS.forEach(d=>{grouped[d.key]=[];});
  items.forEach((it,i)=>{
    const key=it.dim||'literary';
    if(!grouped[key]) grouped[key]=[];
    grouped[key].push({...it,_idx:i});
  });

  // === 每个维度：分数条 + 折叠建议 ===
  let dimsHtml=REVIEW_DIMS.map(d=>{
    const v=sc[d.key]||0;
    const dimItems=grouped[d.key]||[];
    const hasItems=dimItems.length>0;
    const openAttr='';

    // 分数输入或只读
    const scoreEl=editable
      ?`<input type="number" class="score-edit-input" id="edit-score-${d.key}" value="${v}" min="0" max="10" step="0.5">`
      :`<span class="dg-score" style="color:${scoreColor(v)}">${v}</span>`;

    // 折叠建议内容
    let itemsInner='';
    if(hasItems){
      dimItems.forEach(it=>{itemsInner+=_renderOneItem(it,it._idx,editable);});
    }else{
      itemsInner=`<div style="font-size:11px;color:var(--text-muted);padding:8px;text-align:center;font-style:italic;">该维度暂无具体建议</div>`;
    }

    const countBadge=hasItems?`<span class="dg-count">${dimItems.length}条建议</span>`:'';

    return `<details class="dim-group${hasItems?' has-items':''}"${openAttr}>
      <summary class="dim-group-summary" title="${d.desc}">
        <span class="dg-label">${d.label}</span>
        ${countBadge}
        <div class="dim-group-bar"><div class="dim-group-bar-fill" id="bar-${d.key}" style="width:${v*10}%;background:${scoreColor(v)}"></div></div>
        ${scoreEl}
      </summary>
      <div class="dim-group-items" id="dimItems-${d.key}">${itemsInner}</div>
    </details>`;
  }).join('');

  // 新增建议按钮
  if(editable){
    dimsHtml+=`<div style="text-align:right;margin-top:4px;"><button class="btn-add-item" onclick="_addReviewItem()">+ 新增建议</button></div>`;
  }

  // === 平均分 ===
  const avgHtml=`<div class="review-avg-box"><div class="avg-label">平均分（及格线：${getConfig().pass_score}）</div><div class="avg-score" id="reviewAvgDisplay" style="color:${p?'var(--accent-green)':'var(--accent-red)'}">${avg}</div><div class="avg-status" id="reviewStatusDisplay" style="color:${p?'var(--accent-green)':'var(--accent-red)'}">${p?'&#10004; 审核通过':'&#10008; 未通过'}</div></div>`;

  // === 综合评价 ===
  let analysisHtml;
  if(editable){
    analysisHtml=`<div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;font-weight:600">综合评价 <span style="font-weight:400;color:var(--accent-blue)">(可编辑)</span></div><textarea class="review-edit-textarea" id="editAnalysis">${review.analysis||''}</textarea>`;
  }else{
    analysisHtml=`<div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;font-weight:600">综合评价</div><div class="review-detail-text">${review.analysis||'无'}</div>`;
  }

  // === 操作按钮 ===
  let actionsHtml='';
  if(showActions){
    actionsHtml=`<div class="review-action-bar" id="reviewActionBar">
      <button class="btn-accept" onclick="userDecisionAccept()">&#10004; 通过</button>
      <button class="btn-rewrite" onclick="userDecisionRewrite()">&#128260; 按建议重写</button>
      <button class="btn-rewrite" style="background:var(--accent-red);color:#fff;" onclick="userDecisionFullRewrite()">&#128259; 全部重写</button>
    </div>`;
    if(editable) actionsHtml+=`<div class="edit-mode-hint">可自由编辑分数和建议条目，Bot2将参考您的修改意见进行重写</div>`;
  }

  // 解析失败时显示原始回复帮助排查
  let rawHtml='';
  if(review._raw_preview && review.average===0 && review.retry_hint){
    rawHtml=`<details style="margin-top:10px;border:1px solid var(--border);border-radius:6px;padding:8px;background:var(--bg-card)">
      <summary style="cursor:pointer;font-size:12px;color:var(--accent-red);font-weight:600">&#9888; 解析失败 - 点击查看AI原始回复</summary>
      <pre style="margin-top:6px;white-space:pre-wrap;word-break:break-all;font-size:11px;max-height:300px;overflow:auto;color:var(--text-muted)">${review._raw_preview.replace(/</g,'&lt;')}</pre>
    </details>`;
  }

  $('reviewScorePanel').innerHTML=dimsHtml+avgHtml+analysisHtml+rawHtml+actionsHtml;

  // 绑定分数编辑的实时更新
  if(editable){
    REVIEW_DIMS.forEach(d=>{
      const input=$('edit-score-'+d.key);
      if(input) input.addEventListener('input',()=>_updateScoreBarsLive());
    });
  }
}

// 渲染单条建议
function _renderOneItem(it, idx, editable){
  const dimLabel=DIM_LABEL_MAP[it.dim]||it.dim||'其他';
  const sevLabel=SEV_LABEL[it.severity]||it.severity||'medium';
  const sevCls='sev-'+(it.severity||'medium');

  if(editable){
    return `<div class="review-item severity-${it.severity||'medium'}" data-idx="${idx}">
      <button class="ri-delete" onclick="_deleteReviewItem(${idx})" title="删除此条">&#10005;</button>
      <div class="ri-top">
        <select class="ri-inline-select" data-field="severity" data-idx="${idx}" onchange="_onItemFieldChange(this)">
          <option value="high"${it.severity==='high'?' selected':''}>必须改</option>
          <option value="medium"${it.severity==='medium'?' selected':''}>建议改</option>
          <option value="low"${it.severity==='low'?' selected':''}>可选改</option>
        </select>
        <select class="ri-inline-select" data-field="dim" data-idx="${idx}" onchange="_onItemFieldChange(this)">
          ${REVIEW_DIMS.map(d=>`<option value="${d.key}"${it.dim===d.key?' selected':''}>${d.label}</option>`).join('')}
        </select>
        <input class="ri-edit-input" style="flex:1;min-height:auto" data-field="location" data-idx="${idx}" value="${_escHtml(it.location||'')}" placeholder="位置（如：第3段对话）">
      </div>
      <div class="ri-field"><div class="ri-field-label">问题</div><textarea class="ri-edit-input" data-field="problem" data-idx="${idx}" rows="2">${_escHtml(it.problem||'')}</textarea></div>
      <div class="ri-field"><div class="ri-field-label">建议</div><textarea class="ri-edit-input" data-field="suggestion" data-idx="${idx}" rows="2">${_escHtml(it.suggestion||'')}</textarea></div>
    </div>`;
  }else{
    return `<div class="review-item severity-${it.severity||'medium'}">
      <div class="ri-top">
        <span class="ri-badge ${sevCls}">${sevLabel}</span>
        <span class="ri-badge dim-badge">${dimLabel}</span>
        <span class="ri-location">${_escHtml(it.location||'')}</span>
      </div>
      <div class="ri-field"><div class="ri-field-label">问题</div><div class="ri-text">${_escHtml(it.problem||'')}</div></div>
      <div class="ri-field"><div class="ri-field-label">建议</div><div class="ri-text">${_escHtml(it.suggestion||'')}</div></div>
    </div>`;
  }
}

// 获取所有维度items容器中的review-item
function _getAllReviewItems(){
  const all=[];
  REVIEW_DIMS.forEach(d=>{
    const container=$('dimItems-'+d.key);
    if(container) container.querySelectorAll('.review-item').forEach(el=>all.push(el));
  });
  return all;
}

// 删除一条建议
function _deleteReviewItem(idx){
  const all=_getAllReviewItems();
  if(all[idx]) {
    const container=all[idx].parentElement;
    all[idx].remove();
    // 如果该维度下没有items了，显示空提示
    if(container && container.querySelectorAll('.review-item').length===0){
      container.innerHTML='<div style="font-size:11px;color:var(--text-muted);padding:8px;text-align:center;font-style:italic;">该维度暂无具体建议</div>';
    }
    _updateDimGroupCounts();
  }
  // 重新编号全局idx
  _reindexAllItems();
}

// 新增一条空白建议（添加到文学性维度，用户可通过下拉框修改）
function _addReviewItem(){
  const targetDim='literary';
  const container=$('dimItems-'+targetDim);
  if(!container) return;
  // 如果只有空提示，清掉
  if(container.querySelectorAll('.review-item').length===0) container.innerHTML='';
  const idx=_getAllReviewItems().length;
  const newItem={dim:targetDim,severity:'medium',location:'',problem:'',suggestion:''};
  container.insertAdjacentHTML('beforeend',_renderOneItem(newItem,idx,true));
  // 展开该维度
  const details=container.closest('details.dim-group');
  if(details) details.open=true;
  // 滚动到新增条目
  const last=container.lastElementChild;
  if(last) last.scrollIntoView({behavior:'smooth',block:'nearest'});
  _updateDimGroupCounts();
}

// 重新编号所有items的data-idx
function _reindexAllItems(){
  _getAllReviewItems().forEach((el,i)=>{
    el.dataset.idx=i;
    const delBtn=el.querySelector('.ri-delete');
    if(delBtn) delBtn.setAttribute('onclick',`_deleteReviewItem(${i})`);
    el.querySelectorAll('[data-idx]').forEach(f=>f.dataset.idx=i);
  });
}

// 更新各维度的建议条数badge
function _updateDimGroupCounts(){
  REVIEW_DIMS.forEach(d=>{
    const container=$('dimItems-'+d.key);
    if(!container) return;
    const cnt=container.querySelectorAll('.review-item').length;
    const summary=container.closest('details.dim-group')?.querySelector('.dg-count');
    if(summary) summary.textContent=cnt?cnt+'条建议':'';
  });
}

// select变更时更新样式，维度变更时移动到对应分组
function _onItemFieldChange(el){
  if(el.dataset.field==='severity'){
    const item=el.closest('.review-item');
    if(item){item.className='review-item severity-'+el.value;}
  }
  if(el.dataset.field==='dim'){
    const item=el.closest('.review-item');
    if(!item) return;
    const newDim=el.value;
    const target=$('dimItems-'+newDim);
    if(!target) return;
    // 清空目标维度的空提示
    if(target.querySelectorAll('.review-item').length===0) target.innerHTML='';
    // 移动元素
    const oldContainer=item.parentElement;
    target.appendChild(item);
    // 展开目标维度
    const details=target.closest('details.dim-group');
    if(details) details.open=true;
    // 旧容器如果空了，添加空提示
    if(oldContainer && oldContainer.querySelectorAll('.review-item').length===0){
      oldContainer.innerHTML='<div style="font-size:11px;color:var(--text-muted);padding:8px;text-align:center;font-style:italic;">该维度暂无具体建议</div>';
    }
    _reindexAllItems();
    _updateDimGroupCounts();
  }
}

// 实时更新分数条和平均分
function _updateScoreBarsLive(){
  let sum=0,cnt=0;
  const passScore=getConfig().pass_score||8;
  REVIEW_DIMS.forEach(d=>{
    const input=$('edit-score-'+d.key);
    if(!input)return;
    let v=parseFloat(input.value)||0;
    v=Math.max(0,Math.min(10,v));
    const bar=$('bar-'+d.key);
    if(bar){bar.style.width=v*10+'%';bar.style.background=scoreColor(v);}
    input.style.color=scoreColor(v);
    sum+=v;cnt++;
  });
  const avg=cnt?Math.round(sum/cnt*10)/10:0;
  const passed=avg>=passScore;
  const avgEl=$('reviewAvgDisplay');
  const statusEl=$('reviewStatusDisplay');
  if(avgEl){avgEl.textContent=avg;avgEl.style.color=passed?'var(--accent-green)':'var(--accent-red)';}
  if(statusEl){statusEl.textContent=passed?'✔ 审核通过':'✘ 未通过';statusEl.style.color=passed?'var(--accent-green)':'var(--accent-red)';}
}

// 从编辑面板读取用户修改后的审核结果（含逐条建议）
function readEditedReview(){
  const dimKeys=REVIEW_DIMS.map(d=>d.key);
  const scores={};
  let sum=0,cnt=0;
  dimKeys.forEach(k=>{
    const input=$('edit-score-'+k);
    let v=input?parseFloat(input.value)||0:0;
    v=Math.max(0,Math.min(10,v));
    scores[k]=v;sum+=v;cnt++;
  });
  const average=cnt?Math.round(sum/cnt*10)/10:0;
  const passScore=getConfig().pass_score||8;

  // 读取逐条建议（从各维度分组容器中收集）
  const items=[];
  _getAllReviewItems().forEach(el=>{
    const get=(field)=>{
      const f=el.querySelector(`[data-field="${field}"]`);
      return f?(f.value||f.textContent||''):'';
    };
    items.push({
      dim:get('dim'),
      severity:get('severity'),
      location:get('location'),
      problem:get('problem'),
      suggestion:get('suggestion'),
    });
  });

  // 将items拼成suggestions文本传给Bot2
  const suggestionsText=items.map((it,i)=>{
    const dimLabel=DIM_LABEL_MAP[it.dim]||it.dim;
    const sevLabel=SEV_LABEL[it.severity]||it.severity;
    return `${i+1}. [${sevLabel}][${dimLabel}] 位置：${it.location}\n   问题：${it.problem}\n   建议：${it.suggestion}`;
  }).join('\n\n');

  return {
    scores,
    average,
    passed:average>=passScore,
    analysis:($('editAnalysis')?$('editAnalysis').value:''),
    items,
    suggestions:suggestionsText,
  };
}

function addReviewToHistory(review,attempt){
  S.reviews.push({review,attempt,time:now()});
  const el=$('rhistoryPanel'),item=document.createElement('div');
  item.className='review-history-item';const p=review.passed;
  item.innerHTML=`<span>${'第'+attempt+'次审核 ['+now()+']'}</span><span class="badge ${p?'badge-pass':'badge-fail'}">${p?'通过':'未通过'} ${review.average||0}分</span>`;
  item.onclick=()=>{renderReviewPanel(review,attempt,true);switchTab('review');};
  el.prepend(item);
}

function rebuildReviewHistoryUI(){
  $('rhistoryPanel').innerHTML='';
  S.reviews.forEach(r=>{
    const item=document.createElement('div');item.className='review-history-item';
    const p=r.review&&r.review.passed;
    item.innerHTML=`<span>第${r.attempt}次审核 [${r.time}]</span><span class="badge ${p?'badge-pass':'badge-fail'}">${p?'通过':'未通过'} ${(r.review&&r.review.average)||0}分</span>`;
    item.onclick=()=>{renderReviewPanel(r.review,r.attempt,true);switchTab('review');};
    $('rhistoryPanel').prepend(item);
  });
  // 如果有审核记录，显示最新一条
  if(S.reviews.length){const last=S.reviews[S.reviews.length-1];renderReviewPanel(last.review,last.attempt,true);}
}
