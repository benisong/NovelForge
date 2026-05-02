// 08-project.js - Project persistence, save/load, import/export

// 防抖函数用于自动保存
function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => {
      func.apply(this, args);
    }, wait);
  };
}

// 绑定输入框自动保存
document.addEventListener('DOMContentLoaded', () => {
  const debouncedSave = debounce(() => {
    if (S.chatHistory.length > 0 || S.chapters.length > 0) {
      saveProject(true);
    }
  }, 3000);

  // 监听所有textarea和input的输入事件
  document.querySelectorAll('textarea, input[type="text"]').forEach(el => {
    el.addEventListener('input', debouncedSave);
  });
});

// ============================================================
// 项目持久化
// ============================================================
let currentProjectId = null;
function genProjectId(){return 'proj_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,6);}

function _getActiveTab(){
  const active=document.querySelector('.tab.active');
  return active?active.id.replace('tab-',''):'bot1';
}

async function saveProject(silent){
  const name=$('projectName').value.trim()||'未命名项目';
  if(!currentProjectId) currentProjectId=genProjectId();
  // 清理pipelineState中的不可序列化字段（AbortController等），只保留可持久化数据
  let savablePipelineState=null;
  if(S.pipelineState){
    savablePipelineState={
      stage:S.pipelineState.stage,
      attempt:S.pipelineState.attempt,
      currentContent:S.pipelineState.currentContent||'',
      context:S.pipelineState.context||'',
      lastSuggestions:S._lastSuggestions||'',
      // config里的数据会很大且含敏感信息，不重复保存——恢复时从当前配置取
    };
  }
  const body={
    project_id:currentProjectId, name,
    chapters:S.chapters,
    chat_history:S.chatHistory,
    current_outline:S.currentOutline,
    chapter_outline:S.chapterOutline||'',
    current_summary:S.currentSummary,
    current_content:S.currentContent,
    reviews:S.reviews,
    logs:S.logs,
    pipeline_state:savablePipelineState,
    active_tab:_getActiveTab(),
    accumulated_tips:S.accumulatedTips||[],
    last_rewrite_suggestions:S._lastSuggestions||'',
    small_summaries:S.smallSummaries||[],
    big_summaries:S.bigSummaries||[],
    chapter_boundary_idx:S.chapterBoundaryIdx||0,
  };
  try{const r=await fetch(apiUrl('/api/projects/save'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(d.ok){localStorage.setItem('nf_last_project',currentProjectId);if(!silent){addLog('system',`项目「${name}」已保存`);}loadProjectList();}else{if(!silent)addLog('error','保存失败');}}
  catch(e){if(!silent)addLog('error',`保存失败: ${e.message}`);}
}

// 同步保存（用于beforeunload，使用sendBeacon确保页面关闭时数据不丢失）
function saveProjectSync(){
  const name=$('projectName').value.trim()||'未命名项目';
  if(!currentProjectId&&S.chatHistory.length===0&&S.chapters.length===0) return;
  if(!currentProjectId) currentProjectId=genProjectId();
  let savablePipelineState=null;
  if(S.pipelineState){
    savablePipelineState={stage:S.pipelineState.stage,attempt:S.pipelineState.attempt,currentContent:S.pipelineState.currentContent||'',context:S.pipelineState.context||'',lastSuggestions:S._lastSuggestions||''};
  }
  const body={
    project_id:currentProjectId, name,
    chapters:S.chapters,
    chat_history:S.chatHistory,
    current_outline:S.currentOutline,
    chapter_outline:S.chapterOutline||'',
    current_summary:S.currentSummary,
    current_content:S.currentContent,
    reviews:S.reviews,
    logs:S.logs,
    pipeline_state:savablePipelineState,
    active_tab:_getActiveTab(),
    accumulated_tips:S.accumulatedTips||[],
    last_rewrite_suggestions:S._lastSuggestions||'',
    small_summaries:S.smallSummaries||[],
    big_summaries:S.bigSummaries||[],
    chapter_boundary_idx:S.chapterBoundaryIdx||0,
  };
  navigator.sendBeacon(apiUrl('/api/projects/save'), new Blob([JSON.stringify(body)],{type:'application/json'}));
  localStorage.setItem('nf_last_project',currentProjectId);
}

// 页面关闭/刷新时自动保存
window.addEventListener('beforeunload',()=>{
  saveProjectSync();
});

// 定期自动保存（每60秒，静默保存）
setInterval(()=>{
  if(currentProjectId||S.chatHistory.length>0||S.chapters.length>0){
    saveProject(true);
  }
},60000);

async function loadProjectList(){
  try{const r=await fetch(apiUrl('/api/projects'));const d=await r.json();const el=$('projectList');el.innerHTML='';
    // 更新菜单按钮标签
    $('projectMenuLabel').textContent=currentProjectId?($('projectName').value||''):'';

    if(!d.projects||!d.projects.length){el.innerHTML='<div style="font-size:11px;color:var(--text-muted)">无已保存项目</div>';return;}
    d.projects.forEach(p=>{
      const row=document.createElement('div');
      row.className='dd-list-item'+(p.id===currentProjectId?' active':'');
      row.innerHTML=`<span class="dli-name">${p.id===currentProjectId?'&#9679; ':''}${p.name}</span><span class="dli-meta">${p.chapters}章</span><button class="dli-btn" title="加载">加载</button><button class="dli-btn del" title="删除">删除</button>`;
      row.querySelector('.dli-btn:first-of-type').onclick=(e)=>{e.stopPropagation();loadProject(p.id);};
      row.querySelector('.dli-btn.del').onclick=(e)=>{e.stopPropagation();deleteProject(p.id,p.name);};
      el.appendChild(row);
    });
  }catch{}
}

async function loadProject(pid){
  try{const r=await fetch(apiUrl(`/api/projects/${pid}`));if(!r.ok)throw new Error('加载失败');const d=await r.json();
    currentProjectId=d.project_id;
    $('projectName').value=d.name||'';
    S.chatHistory=d.chat_history||[];
    S.chapters=d.chapters||[];
    S.currentOutline=d.current_outline||'';
    S.chapterOutline=d.chapter_outline||'';
    S.currentSummary=d.current_summary||'';
    S.currentContent=d.current_content||'';
    S.reviews=d.reviews||[];
    S.logs=d.logs||[];
    S.accumulatedTips=d.accumulated_tips||[];
    S._lastSuggestions=d.last_rewrite_suggestions||'';
    S.smallSummaries=d.small_summaries||[];
    S.bigSummaries=d.big_summaries||[];
    S.chapterBoundaryIdx=Number(d.chapter_boundary_idx)||0;

    // 恢复聊天UI
    rebuildChatUI();
    recalcOutlineFromHistory();
    // 恢复章节大纲UI
    if(S.chapterOutline){
      $('chapterOutlinePreview').textContent=S.chapterOutline;
      $('chapterOutlinePreview').className='outline-body';
    }
    updateChapterList();

    // 恢复正文
    if(S.currentContent){$('contentOutput').textContent=S.currentContent;$('contentOutput').className='output-area';$('wordCount').textContent=`字数：${S.currentContent.length}`;}
    // 如果有已完成章节，显示复制按钮
    showBot2Toolbar(S.chapters.length>0);
    // 恢复总结面板
    rebuildSummaryUI();
    // 恢复日志
    rebuildLogUI();
    // 恢复审核历史
    rebuildReviewHistoryUI();

    localStorage.setItem('nf_last_project',currentProjectId);
    addLog('system',`已加载项目「${d.name}」(${S.chapters.length}章)`);

    // 恢复上次激活的Tab页
    const savedTab=d.active_tab||'bot1';
    switchTab(savedTab);

    // 检测并恢复中断的Pipeline
    if(d.pipeline_state&&d.pipeline_state.stage){
      const ps=d.pipeline_state;
      const stageNames={bot2:'Bot2创作',bot3:'Bot3审核',bot3_decision:'Bot3审核（等待决策）',bot4:'Bot4总结'};
      const stageName=stageNames[ps.stage]||ps.stage;
      addLog('system',`检测到上次中断的流水线：${stageName}（第${ps.attempt}次）`);
      showPipelineResumePrompt(ps, stageName);
    }
  }catch(e){addLog('error',`加载项目失败: ${e.message}`);}
}

// 显示Pipeline恢复提示
function showPipelineResumePrompt(ps, stageName){
  // 创建恢复提示横幅
  let banner=$('pipelineResumeBanner');
  if(!banner){
    banner=document.createElement('div');
    banner.id='pipelineResumeBanner';
    banner.style.cssText='position:fixed;top:50px;left:50%;transform:translateX(-50%);z-index:9999;background:var(--bg-surface);border:1px solid var(--accent-yellow);border-radius:10px;padding:16px 24px;display:flex;align-items:center;gap:16px;box-shadow:0 8px 32px rgba(0,0,0,0.4);max-width:520px;';
    document.body.appendChild(banner);
  }
  banner.innerHTML=`
    <div style="flex:1;">
      <div style="font-size:14px;font-weight:600;color:var(--accent-yellow);margin-bottom:4px;">⚠ 检测到未完成的创作流程</div>
      <div style="font-size:12px;color:var(--text-secondary);">上次在「${stageName}」阶段（第${ps.attempt}次尝试）中断。是否从断点继续？</div>
    </div>
    <div style="display:flex;gap:8px;flex-shrink:0;">
      <button id="btnResumeYes" style="padding:6px 16px;background:var(--accent-green);color:#1e1e2e;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">继续创作</button>
      <button id="btnResumeNo" style="padding:6px 16px;background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:6px;font-size:12px;cursor:pointer;">放弃</button>
    </div>`;
  $('btnResumeYes').onclick=()=>{
    banner.remove();
    resumePipelineFromSaved(ps);
  };
  $('btnResumeNo').onclick=()=>{
    banner.remove();
    S.pipelineState=null;
    addLog('system','已放弃恢复中断的流水线');
    saveProject(true);
  };
}

// 从保存的Pipeline状态恢复执行
async function resumePipelineFromSaved(ps){
  if(!validateAll()){addLog('error','请先完成Bot配置后再恢复');return;}
  const config=getConfig();
  // 用当前配置替换（因为保存时没有存config）
  const fullState={stage:ps.stage, attempt:ps.attempt, currentContent:ps.currentContent||S.currentContent||'', config, context:ps.context||S.currentSummary||'', lastSuggestions:ps.lastSuggestions||''};
  S._lastSuggestions=fullState.lastSuggestions||S._lastSuggestions||'';
  S.pipelineState=fullState;
  addLog('system',`从「${ps.stage}」阶段恢复创作...`);

  if(ps.stage==='bot2'){
    await runPipeline(ps.attempt, fullState.currentContent, config, fullState.context);
  }else if(ps.stage==='bot3'){
    await retryBot3AndContinue(fullState);
  }else if(ps.stage==='bot3_decision'){
    await resumePipelineAtBot3Decision(fullState);
  }else if(ps.stage==='bot4'){
    await retryBot4(fullState);
  }
}

// 从 bot3_decision 阶段恢复：Bot3 审核已完成、等待用户决定 accept / rewrite / full_rewrite。
// 历史 review 已经在 rebuildReviewHistoryUI 里渲染过但没带操作按钮——这里带按钮重渲一次，
// 然后等用户点按钮，按结果走和 retryBot3AndContinue 末尾完全一致的分支。
async function resumePipelineAtBot3Decision(ps){
  switchTab('review');
  if(S.reviews.length>0){
    const last=S.reviews[S.reviews.length-1];
    renderReviewPanel(last.review,last.attempt,true,true);
  }
  const attemptLabel=(typeof ps.attempt==='number')?`第${ps.attempt}次`:String(ps.attempt||'手动');
  setStatus('ready',`审核完成（${attemptLabel}）- 请选择下一步操作`);
  S.pipelineState=ps;

  const decision=await waitForUserDecision();
  _userDecisionResolve=null;

  // ps.attempt 来自 pipeline 是数字；来自 manualReReview 可能是 '手动'。
  // rewrite 分支要走 /bot2/rewrite（attempt>1），用 2 作为安全起点。
  const numericAttempt=(typeof ps.attempt==='number'&&ps.attempt>0)?ps.attempt:1;

  if(decision==='accept'){
    showBot2Toolbar(true);
    const chNum=S.chapters.length+1;
    await saveChapterFile(ps.currentContent, chNum);
    await _runBot4(ps.currentContent, ps.config, ps.context, numericAttempt);
  }else if(decision==='full_rewrite'){
    S._lastSuggestions='';
    await runPipeline(1, '', ps.config, ps.context);
  }else{
    S._lastSuggestions=readEditedReview().suggestions;
    await runPipeline(numericAttempt+1, ps.currentContent, ps.config, ps.context);
  }
}

function rebuildLogUI(){
  $('logPanel').innerHTML='';
  S.logs.forEach(l=>{
    const e=document.createElement('div');e.className=`log-entry ${l.bot}`;
    e.innerHTML=`<span class="lt">[${l.time}]</span><span class="lb">[${l.bot.toUpperCase()}]</span><span>${l.msg}</span>`;
    $('logPanel').appendChild(e);
  });
  $('logPanel').scrollTop=99999;
}

async function _deleteProjectWithChapterCheck(pid, name, isCurrent){
  // 先检查是否有正式章节文件
  let hasChapters=false;
  let chapterFiles=[];
  try{
    const r=await fetch(apiUrl(`/api/projects/${pid}/chapters`));
    const d=await r.json();
    chapterFiles=d.files||[];
    hasChapters=chapterFiles.length>0;
  }catch{}

  if(!confirm(`确定删除项目「${name}」？${isCurrent?'所有章节、对话、审核记录将永久丢失。':''}`))return;

  let deleteChapters=false;
  if(hasChapters){
    deleteChapters=confirm(`该项目有 ${chapterFiles.length} 个已生成的正式章节文件：\n${chapterFiles.slice(0,5).join('\n')}${chapterFiles.length>5?'\n...等':''}}\n\n是否同时删除这些章节文件？\n（点击"取消"将只删除项目数据，保留章节文件）`);
  }

  try{
    await fetch(apiUrl(`/api/projects/${pid}?delete_chapters=${deleteChapters}`),{method:'DELETE'});
    addLog('system',`已删除项目「${name}」${deleteChapters?'（含章节文件）':''}`);
    if(isCurrent||currentProjectId===pid){currentProjectId=null;localStorage.removeItem('nf_last_project');resetProjectState();}
    loadProjectList();
  }catch(e){addLog('error',`删除失败: ${e.message}`);}
}

async function deleteProject(pid,name){
  await _deleteProjectWithChapterCheck(pid, name, false);
}

async function deleteCurrentProject(){
  if(!currentProjectId){alert('当前没有已保存的项目');return;}
  const name=$('projectName').value||'当前项目';
  await _deleteProjectWithChapterCheck(currentProjectId, name, true);
}

function newProject(){
  if(S.chapters.length>0||S.chatHistory.length>0){
    if(!confirm('新建项目将清空当前所有内容。如需保留请先保存。继续吗？'))return;
  }
  currentProjectId=null;
  resetProjectState();
  // 根据已有项目数量自动编号
  const existingItems=$('projectList').querySelectorAll('.dd-list-item');
  const nextNum=existingItems.length+1;
  $('projectName').value='我的小说'+nextNum;
  addLog('system','已新建空项目');
  switchTab('bot1');
}

function resetProjectState(){
  S.chatHistory=[];S.chapters=[];S.reviews=[];S.logs=[];S.accumulatedTips=[];
  S.smallSummaries=[];S.bigSummaries=[];
  S.currentOutline='';S.chapterOutline='';S.currentContent='';S.currentSummary='';
  S._lastSuggestions='';
  S.pipelineState=null;
  S.chapterBoundaryIdx=0;
  rebuildChatUI();updateChapterList();
  $('outlinePreview').textContent='总大纲将在对话过程中自动生成和更新';$('outlinePreview').className='outline-body empty';
  $('chapterOutlinePreview').textContent='章节大纲将在讨论中生成';$('chapterOutlinePreview').className='outline-body empty';
  $('btnConfirmOutline').disabled=true;
  if($('editUserSuggestions')) $('editUserSuggestions').value='';
  $('contentOutput').textContent='等待Bot2创作内容...';$('contentOutput').className='output-area empty';
  showBot2Toolbar(false);
  if($('summaryOutput')){$('summaryOutput').textContent='等待Bot4生成记忆总结...';$('summaryOutput').className='output-area empty';}
  if($('summaryDetailContent')) $('summaryDetailContent').innerHTML='<div style="text-align:center;color:var(--text-muted);padding:40px;font-size:13px;font-style:italic;">点击列表查看总结详情</div>';
  $('reviewScorePanel').innerHTML='<div style="text-align:center;color:var(--text-muted);padding:30px;font-size:13px;font-style:italic;">尚无审核结果</div>';
  $('logPanel').innerHTML='';$('rhistoryPanel').innerHTML='';
  $('wordCount').textContent='';$('retryInfo').textContent='';$('chapterInfo').textContent='新章节';
  hideAllErrors();
}

async function exportProject(){
  if(!currentProjectId&&S.chapters.length===0){alert('没有可导出的内容');return;}
  await saveProject();if(!currentProjectId)return;
  try{const r=await fetch(apiUrl(`/api/projects/${currentProjectId}/export`),{method:'POST'});const d=await r.json();
    const blob=new Blob([d.text],{type:'text/plain;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=($('projectName').value||'novel')+'.txt';a.click();URL.revokeObjectURL(a.href);
    addLog('system',`已导出，共${d.word_count}字`);
  }catch(e){addLog('error',`导出失败: ${e.message}`);}
}

const _autoSaveAfterChapter=()=>saveProject(false);

// AI回复完毕或用户操作后自动保存
const _autoSave=()=>{saveProject(true);};
