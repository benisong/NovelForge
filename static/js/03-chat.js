// 03-chat.js - Bot1 chat functions, context building, and chat UI management

// ---- 改进3: 构建Bot1增强上下文（章节脉络 + 故事记忆）----
function buildBot1Context(){
  let parts=[];
  if(S.chapters.length>0){
    const outlines=S.chapters.map((ch,i)=>{
      // 从大纲中提取第一行作为标题
      const firstLine=(ch.outline||'').split('\n').find(l=>l.trim())||`第${i+1}章`;
      return `第${i+1}章：${firstLine.replace(/^#+\s*/,'').substring(0,40)}`;
    });
    parts.push('【已完成章节脉络】\n'+outlines.join('\n'));
  }
  if(S.currentSummary){
    parts.push('【故事记忆】\n'+S.currentSummary);
  }
  return parts.join('\n\n');
}

// ---- 改进4: 获取累积的审核tips文本 ----
function getTipsText(){
  if(!S.accumulatedTips||S.accumulatedTips.length===0) return '';
  return S.accumulatedTips.map((t,i)=>`${i+1}. ${t}`).join('\n');
}

// ---- 改进5: 获取上一章结尾片段（最多500字）----
function getPrevEnding(maxLen){
  maxLen=maxLen||500;
  if(S.chapters.length===0) return '';
  const lastContent=S.chapters[S.chapters.length-1].content||'';
  if(!lastContent) return '';
  return lastContent.length<=maxLen ? lastContent : lastContent.slice(-maxLen);
}

// ---- 改进6: 记忆压缩（当summary超过阈值时调用）----
async function maybeCompressSummary(config){
  if(!S.currentSummary||S.currentSummary.length<=SUMMARY_COMPRESS_THRESHOLD) return;
  addLog('system',`记忆总结已达${S.currentSummary.length}字，正在压缩...`);
  try{
    const compressed=await readSSE('/api/compress-summary',{summary:S.currentSummary,config,max_chars:800},(chunk,full)=>{},null);
    if(compressed&&compressed.trim()){
      const oldLen=S.currentSummary.length;
      S.currentSummary=compressed;
      addLog('system',`记忆压缩完成: ${oldLen}字 → ${compressed.length}字`);
    }
  }catch(e){
    addLog('error',`记忆压缩失败(不影响创作): ${e.message}`);
  }
}

// ---- 改进4: 从审核结果中提取low建议追加到tips ----
function collectTipsFromReview(review){
  if(!review||!review.items) return;
  const DIM_LABEL={literary:'文学性',logic:'逻辑性',style:'风格一致性',ai_feel:'人味'};
  const lowItems=review.items.filter(it=>it.severity==='low');
  lowItems.forEach(it=>{
    const tip=`[${DIM_LABEL[it.dim]||it.dim}] ${it.location||'全文'}: ${it.problem}`;
    // 去重
    if(!S.accumulatedTips.includes(tip)){
      S.accumulatedTips.push(tip);
    }
  });
  // 保留最近10条
  if(S.accumulatedTips.length>10) S.accumulatedTips=S.accumulatedTips.slice(-10);
}

// ============================================================
// Bot1 对话 + 删除/清空
// ============================================================
function appendMsg(role,content,idx){
  const wrap=document.createElement('div');
  wrap.className='msg '+role;
  wrap.dataset.idx=idx;
  const label=role==='user'?'你':'Bot1 · 大纲策划师';
  wrap.innerHTML=`<div class="msg-label">${label}</div><div class="msg-text"></div><button class="msg-del" title="删除此消息" onclick="deleteMsg(${idx})">&#10005;</button>`;
  wrap.querySelector('.msg-text').textContent=content;
  $('chatMessages').appendChild(wrap);
  $('chatMessages').scrollTop=99999;
  return wrap;
}

function deleteMsg(idx){
  if(S.isGenerating)return;
  if(idx<0||idx>=S.chatHistory.length)return;
  // 删除该条及之后所有消息（保持对话一致性）
  const removeCount=S.chatHistory.length-idx;
  S.chatHistory.splice(idx,removeCount);
  rebuildChatUI();
  // 重新从历史中提取最新大纲
  recalcOutlineFromHistory();
  addLog('system',`已删除第${idx+1}条及之后共${removeCount}条消息`);
}

function clearChat(){
  if(S.isGenerating)return;
  if(S.chatHistory.length===0)return;
  if(!confirm('确定清空所有对话消息？大纲也会被清除。'))return;
  S.chatHistory=[];
  S.currentOutline='';
  rebuildChatUI();
  $('outlinePreview').textContent='大纲将在对话过程中自动生成和更新';
  $('outlinePreview').className='outline-body empty';
  $('btnConfirmOutline').disabled=true;
  addLog('system','已清空全部对话');
}

function rebuildChatUI(){
  $('chatMessages').innerHTML='';
  if(S.chatHistory.length===0){
    $('chatMessages').innerHTML='<div class="chat-welcome" style="text-align:center;color:var(--text-muted);font-size:13px;padding:40px 20px;">&#128075; 向Bot1描述你的创作想法<br>它会和你对话并实时生成大纲<br>满意后点击右侧「确认大纲，开始创作」</div>';
    return;
  }
  S.chatHistory.forEach((m,i)=>{
    const displayText=m.role==='assistant'?stripOutline(m.content):m.content;
    appendMsg(m.role,displayText,i);
  });
}

function recalcOutlineFromHistory(){
  // 从最后一条assistant消息中提取outline
  let found=false;
  for(let i=S.chatHistory.length-1;i>=0;i--){
    if(S.chatHistory[i].role==='assistant'){
      const ol=extractOutline(S.chatHistory[i].content);
      if(ol){S.currentOutline=ol;$('outlinePreview').textContent=ol;$('outlinePreview').className='outline-body';$('btnConfirmOutline').disabled=false;found=true;break;}
    }
  }
  if(!found){S.currentOutline='';$('outlinePreview').textContent='大纲将在对话过程中自动生成和更新';$('outlinePreview').className='outline-body empty';$('btnConfirmOutline').disabled=true;}
}

function chatKeydown(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat();}}

async function sendChat(){
  if(S.isGenerating)return;
  if(!validateBot('bot1'))return;
  const text=$('chatInput').value.trim();
  if(!text)return;
  $('chatInput').value='';
  const userIdx=S.chatHistory.length;
  S.chatHistory.push({role:'user',content:text});
  appendMsg('user',text,userIdx);

  S.isGenerating=true;S.abortCtrl=new AbortController();
  $('btnSend').disabled=true;$('outlineLive').style.display='';
  setStatus('busy','Bot1思考中...');addLog('bot1','正在回复...');

  const assistIdx=S.chatHistory.length; // 预留位置
  const bubble=appendMsg('assistant','',assistIdx);
  const textEl=bubble.querySelector('.msg-text');
  textEl.innerHTML='<span class="typing-cursor"></span>';

  try{
    const config=getConfig();
    const fullText=await readSSE('/api/bot1/chat',{messages:S.chatHistory,config,context:buildBot1Context()},
    (chunk,full)=>{
      textEl.textContent=stripOutline(full)||'...';
      const ol=extractOutline(full);
      if(ol){$('outlinePreview').textContent=ol;$('outlinePreview').className='outline-body';S.currentOutline=ol;$('btnConfirmOutline').disabled=false;}
      $('chatMessages').scrollTop=99999;
    },S.abortCtrl.signal);

    S.chatHistory.push({role:'assistant',content:fullText});
    bubble.dataset.idx=assistIdx;
    textEl.textContent=stripOutline(fullText);
    const ol=extractOutline(fullText);
    if(ol){S.currentOutline=ol;$('outlinePreview').textContent=ol;$('outlinePreview').className='outline-body';$('btnConfirmOutline').disabled=false;}
    addLog('bot1','回复完成');setStatus('ready','就绪 - 可继续对话或确认大纲');
    _autoSave();
  }catch(e){
    if(e.name==='AbortError'){addLog('system','已停止');}
    else{addLog('error',`Bot1错误: ${e.message}`);setStatus('error','Bot1出错');}
    textEl.textContent=textEl.textContent||'(生成失败，请重试)';
  }
  S.isGenerating=false;$('btnSend').disabled=false;$('outlineLive').style.display='none';
}

function newChat(){
  S.chatHistory=[];S.currentOutline='';
  rebuildChatUI();
  $('outlinePreview').textContent='大纲将在对话过程中自动生成和更新';
  $('outlinePreview').className='outline-body empty';
  $('btnConfirmOutline').disabled=true;
  addLog('system','已开始新对话');
}
