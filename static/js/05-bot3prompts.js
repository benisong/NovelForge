// 05-bot3prompts.js - Bot3 custom prompt management

let bot3CustomPrompts=[];   // [{id, name, content}]
let activeBot3PromptId='';  // 当前选中的自定义提示词ID（空=使用默认）
let bot3DefaultPrompt='';   // 从服务端加载的默认提示词

// 获取当前生效的Bot3提示词（空字符串=使用默认）
function getBot3CustomPrompt(){
  if(!activeBot3PromptId) return '';
  const p=bot3CustomPrompts.find(x=>x.id===activeBot3PromptId);
  return p?p.content:'';
}

// 重新审计：手动触发一次Bot3审核
async function manualReReview(){
  const content=S.currentContent;
  if(!content||!content.trim()){addLog('error','没有可审核的内容');return;}
  if(!validateBot('bot3')){return;}
  const config=getConfig();

  $('btnReReview').disabled=true;
  setStatus('busy','Bot3 重新审计中...');addLog('bot3','用户手动触发重新审计...');
  $('reviewScorePanel').innerHTML='<div style="text-align:center;padding:30px;color:var(--text-muted)"><div class="spinner"></div><div style="margin-top:8px;font-size:12px">Bot3正在重新审核中...</div></div>';

  let review;
  try{
    const r=await fetch(apiUrl('/api/bot3/review'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      content,outline:S.currentOutline,config,style_id:getStyleId(),custom_prompt:getBot3CustomPrompt()
    })});
    review=await r.json();
    if(review.error&&!review.scores)throw new Error(review.error);
  }catch(e){
    addLog('error',`重新审计失败: ${e.message}`);setStatus('error','重新审计失败');
    $('btnReReview').disabled=false;return;
  }

  addReviewToHistory(review,'手动');
  // 不通过时可编辑+显示操作按钮（如果pipeline暂停中）
  const isWaiting=!!_userDecisionResolve;
  if(review.passed){
    collectTipsFromReview(review);
    renderReviewPanel(review,'手动',true,isWaiting);
    addLog('bot3',`重新审计通过！平均分：${review.average}`);
  }else{
    renderReviewPanel(review,'手动',true,isWaiting);
    addLog('bot3',`重新审计未通过(${review.average}分)`);
  }
  setStatus('ready','重新审计完成');$('btnReReview').disabled=false;_autoSave();
}

// ---- Bot3 提示词弹窗管理 ----
async function loadBot3Prompts(){
  try{
    const r=await fetch(apiUrl('/api/bot3-prompts'));const d=await r.json();
    bot3CustomPrompts=d.prompts||[];
    bot3DefaultPrompt=d.default_prompt||'';
    _updateBot3PromptLabel();
  }catch(e){console.warn('加载Bot3提示词失败',e);}
}

function _updateBot3PromptLabel(){
  const el=$('bot3PromptLabel');
  if(!el) return;
  if(activeBot3PromptId){
    const p=bot3CustomPrompts.find(x=>x.id===activeBot3PromptId);
    el.textContent=p?`当前：${p.name}`:'';
  }else{
    el.textContent='';
  }
}

function openBot3PromptModal(){
  $('bot3PromptOverlay').classList.add('show');
  _renderBot3PromptList();
  // 默认：新建模式，加载系统默认提示词
  $('b3pEditId').value='';
  $('b3pName').value='';
  $('b3pContent').value=bot3DefaultPrompt;
  $('b3pDeleteBtn').style.display='none';
}

function closeBot3PromptModal(){
  $('bot3PromptOverlay').classList.remove('show');
}

function _renderBot3PromptList(){
  const el=$('bot3PromptList');
  if(!bot3CustomPrompts.length){
    el.innerHTML='<div style="padding:8px 10px;font-size:11px;color:var(--text-muted);">尚无自定义提示词，点击"新建"创建</div>';
    return;
  }
  el.innerHTML=bot3CustomPrompts.map(p=>{
    const isActive=p.id===activeBot3PromptId;
    return `<div class="b3p-item${isActive?' active':''}" onclick="_editBot3Prompt('${p.id}')">
      <span class="b3p-name">${_escHtml(p.name)}</span>
      <button class="b3p-use${isActive?' active-use':''}" onclick="event.stopPropagation();_toggleBot3Prompt('${p.id}')">${isActive?'使用中':'启用'}</button>
    </div>`;
  }).join('');
}

function _editBot3Prompt(id){
  const p=bot3CustomPrompts.find(x=>x.id===id);
  if(!p) return;
  $('b3pEditId').value=p.id;
  $('b3pName').value=p.name;
  $('b3pContent').value=p.content;
  $('b3pDeleteBtn').style.display='';
}

function _toggleBot3Prompt(id){
  if(activeBot3PromptId===id){
    activeBot3PromptId='';
    localStorage.removeItem('nf_bot3_prompt_id');
    addLog('system','已切换回默认审核提示词');
  }else{
    activeBot3PromptId=id;
    localStorage.setItem('nf_bot3_prompt_id',id);
    const p=bot3CustomPrompts.find(x=>x.id===id);
    addLog('system',`已启用自定义提示词「${p?p.name:id}」`);
  }
  _renderBot3PromptList();
  _updateBot3PromptLabel();
}

function newBot3Prompt(){
  $('b3pEditId').value='';
  $('b3pName').value='';
  $('b3pContent').value=bot3DefaultPrompt;
  $('b3pDeleteBtn').style.display='none';
}

async function saveBot3Prompt(){
  const name=$('b3pName').value.trim();
  const content=$('b3pContent').value.trim();
  if(!name){alert('请输入提示词名称');return;}
  if(!content){alert('提示词内容不能为空');return;}

  const editId=$('b3pEditId').value;
  if(editId){
    // 编辑已有
    const p=bot3CustomPrompts.find(x=>x.id===editId);
    if(p){p.name=name;p.content=content;}
  }else{
    // 新建
    bot3CustomPrompts.push({id:'b3p_'+Date.now().toString(36),name,content});
  }
  await _pushBot3Prompts();
  _renderBot3PromptList();
  addLog('system',`Bot3提示词「${name}」已保存`);
}

async function deleteBot3Prompt(){
  const editId=$('b3pEditId').value;
  if(!editId) return;
  const p=bot3CustomPrompts.find(x=>x.id===editId);
  if(!confirm(`确定删除「${p?p.name:''}」？`)) return;
  bot3CustomPrompts=bot3CustomPrompts.filter(x=>x.id!==editId);
  if(activeBot3PromptId===editId){activeBot3PromptId='';localStorage.removeItem('nf_bot3_prompt_id');}
  await _pushBot3Prompts();
  _renderBot3PromptList();
  _updateBot3PromptLabel();
  newBot3Prompt();
  addLog('system','已删除自定义提示词');
}

async function _pushBot3Prompts(){
  try{
    await fetch(apiUrl('/api/bot3-prompts'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompts:bot3CustomPrompts})});
  }catch(e){console.warn('保存Bot3提示词失败',e);}
}
