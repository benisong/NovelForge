// 08-project.js - Project persistence, save/load, import/export

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
      // config里的数据会很大且含敏感信息，不重复保存——恢复时从当前配置取
    };
  }
  const body={
    project_id:currentProjectId, name,
    chapters:S.chapters,
    chat_history:S.chatHistory,
    current_outline:S.currentOutline,
    current_summary:S.currentSummary,
    current_content:S.currentContent,
    reviews:S.reviews,
    logs:S.logs,
    pipeline_state:savablePipelineState,
    active_tab:_getActiveTab(),
    accumulated_tips:S.accumulatedTips||[],
    small_summaries:S.smallSummaries||[],
    big_summaries:S.bigSummaries||[],
  };
  try{const r=await fetch('/api/projects/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(d.ok){localStorage.setItem('nf_last_project',currentProjectId);if(!silent){addLog('system',`项目「${name}」已保存`);}loadProjectList();}else{if(!silent)addLog('error','保存失败');}}
  catch(e){if(!silent)addLog('error',`保存失败: ${e.message}`);}
}

// 同步保存（用于beforeunload，使用sendBeacon确保页面关闭时数据不丢失）
function saveProjectSync(){
  const name=$('projectName').value.trim()||'未命名项目';
  if(!currentProjectId&&S.chatHistory.length===0&&S.chapters.length===0) return;
  if(!currentProjectId) currentProjectId=genProjectId();
  let savablePipelineState=null;
  if(S.pipelineState){
    savablePipelineState={stage:S.pipelineState.stage,attempt:S.pipelineState.attempt,currentContent:S.pipelineState.currentContent||'',context:S.pipelineState.context||''};
  }
  const body={
    project_id:currentProjectId, name,
    chapters:S.chapters,
    chat_history:S.chatHistory,
    current_outline:S.currentOutline,
    current_summary:S.currentSummary,
    current_content:S.currentContent,
    reviews:S.reviews,
    logs:S.logs,
    pipeline_state:savablePipelineState,
    active_tab:_getActiveTab(),
    accumulated_tips:S.accumulatedTips||[],
    small_summaries:S.smallSummaries||[],
    big_summaries:S.bigSummaries||[],
  };
  navigator.sendBeacon('/api/projects/save', new Blob([JSON.stringify(body)],{type:'application/json'}));
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
  try{const r=await fetch('/api/projects');const d=await r.json();const el=$('projectList');el.innerHTML='';
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
  try{const r=await fetch(`/api/projects/${pid}`);if(!r.ok)throw new Error('加载失败');const d=await r.json();
    currentProjectId=d.project_id;
    $('projectName').value=d.name||'';
    S.chatHistory=d.chat_history||[];
    S.chapters=d.chapters||[];
    S.currentOutline=d.current_outline||'';
    S.currentSummary=d.current_summary||'';
    S.currentContent=d.current_content||'';
    S.reviews=d.reviews||[];
    S.logs=d.logs||[];
    S.accumulatedTips=d.accumulated_tips||[];
    S.smallSummaries=d.small_summaries||[];
    S.bigSummaries=d.big_summaries||[];

    // 恢复聊天UI
    rebuildChatUI();
    recalcOutlineFromHistory();
    updateChapterList();

    // 恢复正文
    if(S.currentContent){$('contentOutput').textContent=S.currentContent;$('contentOutput').className='output-area';$('wordCount').textContent=`字数：${S.currentContent.length}`;}
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
      const stageNames={bot2:'Bot2创作',bot3:'Bot3审核',bot4:'Bot4总结'};
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
  const fullState={stage:ps.stage, attempt:ps.attempt, currentContent:ps.currentContent||S.currentContent||'', config, context:ps.context||S.currentSummary||''};
  S.pipelineState=fullState;
  addLog('system',`从「${ps.stage}」阶段恢复创作...`);

  if(ps.stage==='bot2'){
    await runPipeline(ps.attempt, fullState.currentContent, config, fullState.context);
  }else if(ps.stage==='bot3'){
    await retryBot3AndContinue(fullState);
  }else if(ps.stage==='bot4'){
    await retryBot4(fullState);
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

async function deleteProject(pid,name){
  if(!confirm(`确定删除项目「${name}」？`))return;
  try{await fetch(`/api/projects/${pid}`,{method:'DELETE'});addLog('system',`已删除项目「${name}」`);
    if(currentProjectId===pid){currentProjectId=null;localStorage.removeItem('nf_last_project');resetProjectState();}
    loadProjectList();
  }catch(e){addLog('error',`删除失败: ${e.message}`);}
}

async function deleteCurrentProject(){
  if(!currentProjectId){alert('当前没有已保存的项目');return;}
  const name=$('projectName').value||'当前项目';
  if(!confirm(`确定删除项目「${name}」？所有章节、对话、审核记录将永久丢失。`))return;
  try{await fetch(`/api/projects/${currentProjectId}`,{method:'DELETE'});
    addLog('system',`已删除项目「${name}」`);
    currentProjectId=null;
    resetProjectState();
    loadProjectList();
  }catch(e){addLog('error',`删除失败: ${e.message}`);}
}

function newProject(){
  if(S.chapters.length>0||S.chatHistory.length>0){
    if(!confirm('新建项目将清空当前所有内容。如需保留请先保存。继续吗？'))return;
  }
  currentProjectId=null;
  resetProjectState();
  $('projectName').value='我的小说';
  addLog('system','已新建空项目');
  switchTab('bot1');
}

function resetProjectState(){
  S.chatHistory=[];S.chapters=[];S.reviews=[];S.logs=[];S.accumulatedTips=[];
  S.smallSummaries=[];S.bigSummaries=[];
  S.currentOutline='';S.currentContent='';S.currentSummary='';
  S.pipelineState=null;
  rebuildChatUI();updateChapterList();
  $('outlinePreview').textContent='大纲将在对话过程中自动生成和更新';$('outlinePreview').className='outline-body empty';
  $('btnConfirmOutline').disabled=true;
  $('contentOutput').textContent='等待Bot2创作内容...';$('contentOutput').className='output-area empty';
  $('summaryOutput').textContent='等待Bot4生成记忆总结...';$('summaryOutput').className='output-area empty';
  $('reviewScorePanel').innerHTML='<div style="text-align:center;color:var(--text-muted);padding:30px;font-size:13px;font-style:italic;">尚无审核结果</div>';
  $('logPanel').innerHTML='';$('rhistoryPanel').innerHTML='';
  $('wordCount').textContent='';$('retryInfo').textContent='';$('chapterInfo').textContent='新章节';
  hideAllErrors();
}

async function exportProject(){
  if(!currentProjectId&&S.chapters.length===0){alert('没有可导出的内容');return;}
  await saveProject();if(!currentProjectId)return;
  try{const r=await fetch(`/api/projects/${currentProjectId}/export`,{method:'POST'});const d=await r.json();
    const blob=new Blob([d.text],{type:'text/plain;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=($('projectName').value||'novel')+'.txt';a.click();URL.revokeObjectURL(a.href);
    addLog('system',`已导出，共${d.word_count}字`);
  }catch(e){addLog('error',`导出失败: ${e.message}`);}
}

const _autoSaveAfterChapter=()=>{saveProject(false);};

// AI回复完毕或用户操作后自动保存
const _autoSave=()=>{saveProject(true);};
