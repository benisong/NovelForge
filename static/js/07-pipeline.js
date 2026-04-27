// 07-pipeline.js - Pipeline orchestration (Bot2/Bot3/Bot4 loop, user decisions, retries)

// === Bot2 复制按钮 ===
function copyBot2Content(){
  const text=$('contentOutput').textContent;
  if(!text||text==='等待Bot2创作内容...'){return;}
  navigator.clipboard.writeText(text).then(()=>{
    $('bot2CopyStatus').textContent='已复制!';
    setTimeout(()=>{$('bot2CopyStatus').textContent='';},2000);
  }).catch(()=>{
    // fallback
    const ta=document.createElement('textarea');ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);
    $('bot2CopyStatus').textContent='已复制!';
    setTimeout(()=>{$('bot2CopyStatus').textContent='';},2000);
  });
}

// 显示/隐藏Bot2工具栏
function showBot2Toolbar(show){
  $('bot2Toolbar').style.display=show?'flex':'none';
}

// 审计通过后保存正式章节文件到服务端
async function saveChapterFile(content, chapterNum){
  const projectName=$('projectName').value.trim()||'未命名项目';
  const pid=currentProjectId||'unknown';
  try{
    const r=await fetch(apiUrl('/api/projects/save-chapter'),{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({project_id:pid, project_name:projectName, chapter_num:chapterNum, content})
    });
    const d=await r.json();
    if(d.ok) addLog('system',`第${chapterNum}章正式版已保存: ${d.filename}`);
    else addLog('error',`章节文件保存失败`);
  }catch(e){addLog('error',`章节文件保存失败: ${e.message}`);}
}

// 用户决策的Promise解析器（供runPipeline内await）
let _userDecisionResolve=null;

function userDecisionRewrite(){
  // 读取用户可能编辑过的审核结果
  const edited=readEditedReview();
  S._lastSuggestions=edited.suggestions;
  // 更新审核历史中最新一条
  if(S.reviews.length>0){
    const last=S.reviews[S.reviews.length-1];
    last.review={...last.review,...edited};
  }
  addLog('system','用户选择发回修改');_autoSave();
  if(_userDecisionResolve) _userDecisionResolve('rewrite');
}
function userDecisionAccept(){
  addLog('system','用户接受当前版本，继续Bot4总结');_autoSave();
  if(_userDecisionResolve) _userDecisionResolve('accept');
}
function userDecisionFullRewrite(){
  addLog('system','用户选择全部重写（从头创作）');_autoSave();
  if(_userDecisionResolve) _userDecisionResolve('full_rewrite');
}

// 等待用户在审核面板中做出决策
function waitForUserDecision(){
  return new Promise(resolve=>{_userDecisionResolve=resolve;});
}

async function confirmOutline(){
  if(!S.currentOutline&&!S.chapterOutline){alert('还没有大纲内容');return;}
  if(!validateAll())return;
  hideAllErrors();
  // 先持久化总大纲和章节大纲
  await saveProject(true);
  addLog('system','大纲已持久化，开始创作');
  // 构建Bot2上下文（大总结 + condensed）
  const bot2Context=buildBot2Context();
  await runPipeline(1, '', getConfig(), bot2Context);
}

async function runPipeline(startAttempt, prevContent, config, context){
  $('btnConfirmOutline').disabled=true;$('btnNewChat').disabled=true;$('btnSend').disabled=true;
  S.abortCtrl=new AbortController();S.isGenerating=true;
  $('pipelineBar').classList.add('show');$('btnStop').style.display='';
  setStep('ps-bot1','done');hideAllErrors();

  let currentContent=prevContent;
  let attempt=startAttempt;

  // Bot2→Bot3循环
  while(attempt<=config.max_retries+1){
    // === Bot2 ===
    setStep('ps-bot2','active');setStatus('busy',`Bot2创作中 (第${attempt}次)...`);
    addLog('bot2',`开始创作 (第${attempt}次)...`);switchTab('content');
    const contentEl=$('contentOutput');contentEl.className='output-area';contentEl.textContent='';

    try{
      const url=attempt===1?'/api/bot2/write':'/api/bot2/rewrite';
      const _sid=getStyleId(),_wc=getWordCount(),_tips=getTipsText(),_pe=getPrevEnding();
      // 传总大纲+章节大纲+上下文（condensed）
      const _chOutline=S.chapterOutline||'';
      const body=attempt===1
        ?{outline:S.currentOutline,chapter_outline:_chOutline,config,style_id:_sid,word_count:_wc,tips:_tips,prev_ending:_pe,bot2_context:context}
        :{outline:S.currentOutline,chapter_outline:_chOutline,content:currentContent,suggestions:S._lastSuggestions||'',config,style_id:_sid,word_count:_wc,tips:_tips,prev_ending:_pe,bot2_context:context};
      currentContent=await readSSE(url,body,(chunk,full)=>{contentEl.textContent=full;contentEl.scrollTop=99999;$('wordCount').textContent=`字数：${full.length}`;},S.abortCtrl.signal);
      if(!currentContent||!currentContent.trim())throw new Error('Bot2返回空内容');
      S.currentContent=currentContent;setStep('ps-bot2','done');addLog('bot2',`创作完成，共${currentContent.length}字`);_autoSave();
    }catch(e){
      if(e.name==='AbortError'){addLog('system','已停止');resetPipeline();return;}
      setStep('ps-bot2','fail');setStatus('error','Bot2出错');addLog('error',`Bot2错误: ${e.message}`);
      switchTab('content');
      S.pipelineState={stage:'bot2',attempt,currentContent,config,context};
      showError('errContent',`Bot2创作失败: ${e.message}`,()=>retryFromState());
      resetPipelineButtons();return;
    }

    // === Bot3 ===
    setStep('ps-bot3','active');setStatus('busy',`Bot3审核中 (第${attempt}次)...`);
    addLog('bot3',`开始审核 (第${attempt}次)...`);switchTab('review');
    $('reviewScorePanel').innerHTML='<div style="text-align:center;padding:30px;color:var(--text-muted)"><div class="spinner"></div><div style="margin-top:8px;font-size:12px">Bot3正在审核中...</div></div>';

    let review;
    try{
      const r=await fetch(apiUrl('/api/bot3/review'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:currentContent,outline:S.currentOutline,config,style_id:getStyleId(),custom_prompt:getBot3CustomPrompt()}),signal:S.abortCtrl.signal});
      review=await r.json();
      if(review.error&&!review.scores)throw new Error(review.error);
    }catch(e){
      if(e.name==='AbortError'){addLog('system','已停止');resetPipeline();return;}
      setStep('ps-bot3','fail');setStatus('error','Bot3出错');addLog('error',`Bot3错误: ${e.message}`);
      switchTab('review');
      S.pipelineState={stage:'bot3',attempt,currentContent,config,context};
      showError('errReview',`Bot3审核失败: ${e.message}`,()=>retryFromState());
      resetPipelineButtons();return;
    }

    addReviewToHistory(review,attempt);

    {
      // 审核完成 → 始终显示操作按钮，等待用户决策
      collectTipsFromReview(review);
      const statusMsg=review.passed
        ?`审核通过(${review.average}分) - 请选择下一步操作`
        :`审核未通过(${review.average}分) - 请选择下一步操作`;
      setStep('ps-bot3',review.passed?'done':'fail');
      addLog('bot3',review.passed?`审核通过！平均分：${review.average}`:`未通过(${review.average}分)，等待用户决策...`);
      $('retryInfo').textContent=`第${attempt}次审核`;
      renderReviewPanel(review,attempt,true,true);
      setStatus('ready',statusMsg);
      _autoSave();

      // 暂停Pipeline，保存状态，等待用户交互
      S.pipelineState={stage:'bot3_decision',attempt,currentContent,config,context};
      resetPipelineButtons();

      // 等待用户点击按钮
      const decision=await waitForUserDecision();
      _userDecisionResolve=null;

      if(decision==='accept'){
        // 用户通过 → 显示复制按钮 + 保存正式章节文件 + 继续Bot4
        showBot2Toolbar(true);
        const chNum=S.chapters.length+1;
        await saveChapterFile(currentContent, chNum);
        setStep('ps-bot3','done');break;
      }else if(decision==='full_rewrite'){
        // 全部重写 → 重置attempt为1，让Bot2从头写（走/api/bot2/write）
        S._lastSuggestions='';
        currentContent='';
        setStep('ps-bot2','');attempt=1;
        addLog('system','全部重写：Bot2将从头创作');
        $('btnConfirmOutline').disabled=true;$('btnNewChat').disabled=true;$('btnSend').disabled=true;
        S.abortCtrl=new AbortController();S.isGenerating=true;
        $('pipelineBar').classList.add('show');$('btnStop').style.display='';
        hideAllErrors();
        continue;
      }else{
        // rewrite → 按建议重写
        S._lastSuggestions=readEditedReview().suggestions;
        setStep('ps-bot2','');attempt++;
        $('btnConfirmOutline').disabled=true;$('btnNewChat').disabled=true;$('btnSend').disabled=true;
        S.abortCtrl=new AbortController();S.isGenerating=true;
        $('pipelineBar').classList.add('show');$('btnStop').style.display='';
        hideAllErrors();
        continue;
      }
    }
  }

  // === Bot4 ===
  // 恢复generating状态（可能在用户决策后被重置了）
  $('btnConfirmOutline').disabled=true;$('btnNewChat').disabled=true;$('btnSend').disabled=true;
  S.abortCtrl=new AbortController();S.isGenerating=true;
  $('pipelineBar').classList.add('show');$('btnStop').style.display='';
  await _runBot4(currentContent, config, context, attempt);
}

// 共用Bot4逻辑：两步 — 缩略版原文 + 摘要
async function _runBot4(content, config, context, attempt){
  setStep('ps-bot4','active');setStatus('busy','Bot4生成缩略版原文...');addLog('bot4','开始生成缩略版原文...');switchTab('summary');
  const detailEl=$('summaryDetailContent');
  detailEl.textContent='';

  const chapterNum=S.chapters.length+1;
  let condensed='', abstract='';

  try{
    // 第一步：缩略版原文（Bot4主模型）
    condensed=await readSSE('/api/bot4/summarize',{content,config,outline:S.currentOutline},(chunk,full)=>{
      detailEl.textContent=full;detailEl.scrollTop=99999;
    },S.abortCtrl.signal);
    if(!condensed||!condensed.trim())throw new Error('Bot4缩略版原文返回空内容');
    addLog('bot4',`缩略版原文完成(${condensed.length}字)`);

    // 第二步：摘要（Bot4廉价模型）
    setStatus('busy','Bot4生成摘要...');addLog('bot4','开始生成摘要...');
    detailEl.textContent='';
    const abstractModel=getBot4AbstractModel();
    abstract=await readSSE('/api/bot4/abstract',{condensed,content,config,abstract_model:abstractModel},(chunk,full)=>{
      detailEl.textContent=full;detailEl.scrollTop=99999;
    },S.abortCtrl.signal);
    if(!abstract||!abstract.trim())throw new Error('Bot4摘要返回空内容');
    addLog('bot4',`摘要完成(${abstract.length}字)`);

    // 存入小总结
    S.smallSummaries.push({chapter:chapterNum,condensed,abstract,time:now()});
    S.currentSummary=condensed; // 兼容旧逻辑
    setStep('ps-bot4','done');addLog('bot4','小总结完成');

    // 更新UI
    renderSmallSummaryList();
    showSummaryDetail('small',S.smallSummaries.length-1);
    toggleSummaryView('condensed');

    // 检查是否提示大总结
    const pending=checkBigSummaryReminder();
    if(pending>=config.big_summary_threshold){
      addLog('bot4',`已累积${pending}章未大总结，建议进行大总结`);
    }
  }catch(e){
    if(e.name==='AbortError'){addLog('system','已停止');resetPipeline();return;}
    setStep('ps-bot4','fail');setStatus('error','Bot4出错');addLog('error',`Bot4错误: ${e.message}`);
    switchTab('summary');
    S.pipelineState={stage:'bot4',attempt,currentContent:content,config,context};
    showError('errSummary',`Bot4总结失败: ${e.message}`,()=>retryFromState());
    resetPipelineButtons();return;
  }

  // 完成
  S.chapters.push({outline:S.currentOutline,chapter_outline:S.chapterOutline,content:S.currentContent,summary:condensed});
  updateChapterList();$('chapterInfo').textContent=`第${chapterNum}章已完成`;$('retryInfo').textContent='';
  S.pipelineState=null;
  setStatus('ready','创作完成');addLog('system',`第${chapterNum}章创作完成！`);resetPipeline();_autoSaveAfterChapter();

  // 章节归档：清掉本章的章节大纲和正文显示，给下一章腾出干净工作区。
  // 总大纲（currentOutline）保留 —— 它是全书规划，不是单章数据。
  // chapterBoundaryIdx 标记 chat_history 边界：之后 recalcOutlineFromHistory
  // 不会再把上一章的 <chapter_outline> 拉回来显示。
  S.chapterBoundaryIdx=S.chatHistory.length;
  S.chapterOutline='';
  S.currentContent='';
  const _chOutEl=$('chapterOutlinePreview');
  if(_chOutEl){_chOutEl.textContent='章节大纲将在讨论中生成';_chOutEl.className='outline-body empty';}
  const _contentEl=$('contentOutput');
  if(_contentEl){_contentEl.textContent='等待Bot2创作内容...';_contentEl.className='output-area empty';}
  const _wcEl=$('wordCount');
  if(_wcEl){_wcEl.textContent='字数：0';}

  promptBot1NextChapter(chapterNum);
}

// 从保存的状态重试当前步骤
async function retryFromState(){
  if(!S.pipelineState)return;
  const ps=S.pipelineState;
  addLog('system',`用户点击重试 ${ps.stage}...`);

  if(ps.stage==='bot2'){
    await runPipeline(ps.attempt, ps.currentContent, ps.config, ps.context);
  }else if(ps.stage==='bot3'){
    // 直接重试Bot3，然后继续后续
    await retryBot3AndContinue(ps);
  }else if(ps.stage==='bot4'){
    await retryBot4(ps);
  }
}

async function retryBot3AndContinue(ps){
  $('btnConfirmOutline').disabled=true;$('btnNewChat').disabled=true;$('btnSend').disabled=true;
  S.abortCtrl=new AbortController();S.isGenerating=true;
  $('pipelineBar').classList.add('show');$('btnStop').style.display='';
  hideAllErrors();setStep('ps-bot3','active');setStatus('busy',`Bot3重试审核中...`);
  addLog('bot3','重试审核...');switchTab('review');
  $('reviewScorePanel').innerHTML='<div style="text-align:center;padding:30px;color:var(--text-muted)"><div class="spinner"></div><div style="margin-top:8px;font-size:12px">Bot3正在审核中...</div></div>';

  let review;
  try{
    const r=await fetch(apiUrl('/api/bot3/review'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:ps.currentContent,outline:S.currentOutline,config:ps.config,style_id:getStyleId(),custom_prompt:getBot3CustomPrompt()}),signal:S.abortCtrl.signal});
    review=await r.json();if(review.error&&!review.scores)throw new Error(review.error);
  }catch(e){
    if(e.name==='AbortError'){addLog('system','已停止');resetPipeline();return;}
    setStep('ps-bot3','fail');setStatus('error','Bot3出错');addLog('error',`Bot3错误: ${e.message}`);
    showError('errReview',`Bot3审核失败: ${e.message}`,()=>retryFromState());
    resetPipelineButtons();return;
  }

  addReviewToHistory(review,ps.attempt);

  {
    collectTipsFromReview(review);
    setStep('ps-bot3',review.passed?'done':'fail');
    addLog('bot3',review.passed?`审核通过！平均分：${review.average}`:`未通过(${review.average}分)，等待用户决策...`);
    renderReviewPanel(review,ps.attempt,true,true);
    const statusMsg=review.passed
      ?`审核通过(${review.average}分) - 请选择下一步操作`
      :`审核未通过(${review.average}分) - 请选择下一步操作`;
    setStatus('ready',statusMsg);
    S.pipelineState={stage:'bot3_decision',attempt:ps.attempt,currentContent:ps.currentContent,config:ps.config,context:ps.context};
    resetPipelineButtons();

    const decision=await waitForUserDecision();
    _userDecisionResolve=null;

    if(decision==='accept'){
      await _runBot4(ps.currentContent, ps.config, ps.context, ps.attempt);
    }else if(decision==='full_rewrite'){
      await runPipeline(1, '', ps.config, ps.context);
    }else{
      S._lastSuggestions=readEditedReview().suggestions;
      await runPipeline(ps.attempt+1, ps.currentContent, ps.config, ps.context);
    }
  }
}

async function retryBot4(ps){
  $('btnConfirmOutline').disabled=true;$('btnNewChat').disabled=true;$('btnSend').disabled=true;
  S.abortCtrl=new AbortController();S.isGenerating=true;
  $('pipelineBar').classList.add('show');$('btnStop').style.display='';
  hideAllErrors();addLog('bot4','重试总结...');
  await _runBot4(ps.currentContent, ps.config, ps.context, ps.attempt);
}

// 章节
function updateChapterList(){const el=$('chapterList');el.innerHTML='';if(S.chapters.length===0){el.innerHTML='<div style="font-size:12px;color:var(--text-muted);padding:6px">暂无已完成章节</div>';return;}S.chapters.forEach((ch,i)=>{const d=document.createElement('div');d.className='chapter-item';d.textContent=`${i+1}. 第${i+1}章 (${ch.content.length}字)`;d.onclick=()=>viewChapter(i);el.appendChild(d);});}
function viewChapter(i){const ch=S.chapters[i];$('outlinePreview').textContent=ch.outline;$('outlinePreview').className='outline-body';$('contentOutput').textContent=ch.content;$('contentOutput').className='output-area';const detailEl=$('summaryDetailContent');if(detailEl){const summaryItem=(S.smallSummaries||[]).find(s=>s.chapter===i+1);if(summaryItem){showSummaryDetail('small',(S.smallSummaries||[]).indexOf(summaryItem));}else{detailEl.textContent=ch.summary||'';}}const summaryOutput=$('summaryOutput');if(summaryOutput){summaryOutput.textContent=ch.summary||'';summaryOutput.className='output-area';}switchTab('content');$('chapterInfo').textContent=`查看：第${i+1}章`;}

// 停止/重置
function stopAll(){if(S.abortCtrl)S.abortCtrl.abort();S.isGenerating=false;setStatus('ready','已停止');addLog('system','用户手动停止');resetPipeline();}
function resetPipeline(){S.isGenerating=false;$('btnSend').disabled=false;$('btnConfirmOutline').disabled=!S.currentOutline;$('btnNewChat').disabled=false;$('btnStop').style.display='none';}
function resetPipelineButtons(){S.isGenerating=false;$('btnSend').disabled=false;$('btnNewChat').disabled=false;$('btnStop').style.display='none';}
