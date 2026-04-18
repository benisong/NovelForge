// 02-config.js - Bot configuration, SSE reader, outline extraction, and config profiles

// Bot2-4未填写时自动回退到Bot1配置（界面不填充，只在运行时回退）
function _botCfg(name,temp,maxTk){
  const url=$(name+'_url').value, key=$(name+'_key').value, model=$(name+'_model').value;
  // 如果该bot有完整配置就用自己的，否则回退bot1
  if(url&&key&&model) return{base_url:url,api_key:key,model:model,temperature:temp,max_tokens:maxTk};
  return{base_url:$('bot1_url').value,api_key:$('bot1_key').value,model:$('bot1_model').value,temperature:temp,max_tokens:maxTk};
}
function getConfig(){return{
  bot1:_botCfg('bot1',0.7,4096),
  bot2:_botCfg('bot2',0.8,8192),
  bot3:_botCfg('bot3',0.3,2048),
  bot4:_botCfg('bot4',0.5,4096),
  pass_score:parseFloat($('passScore').value)||8,max_retries:parseInt($('maxRetries').value)||3,
  big_summary_threshold:parseInt($('bigSummaryThreshold').value)||10,
};}
// 获取Bot4摘要模型名（复用bot4的url和key，只换model）
function getBot4AbstractModel(){
  const el=$('bot4_abstract_model');
  return el?el.value:'';
}

// 只验证Bot1必填，Bot2-4可选（空则回退Bot1）
function validateAll(){
  if(!$('bot1_url').value||!$('bot1_key').value||!$('bot1_model').value){alert('请至少填写Bot1的完整API配置（Bot2-4未填写将自动使用Bot1配置）');return false;}
  return true;
}
function validateBot(n){
  if(n==='bot1') return validateAll();
  return true; // bot2-4不强制
}
function copyBot1ToAll(){['bot2','bot3','bot4'].forEach(b=>{$(b+'_url').value=$('bot1_url').value;$(b+'_key').value=$('bot1_key').value;const s=$('bot1_model'),d=$(b+'_model');d.innerHTML=s.innerHTML;d.value=s.value;});addLog('system','已将Bot1配置复制到所有Bot');}

// 获取模型
async function fetchModels(bot){
  // bot4_abstract复用bot4的url和key
  const srcBot=(bot==='bot4_abstract')?'bot4':bot;
  const url=$(srcBot+'_url').value,key=$(srcBot+'_key').value;
  if(!url||!key){alert('请先填写API地址和密钥');return;}
  const sel=$(bot+'_model');sel.innerHTML='<option value="">获取中...</option>';
  try{const r=await fetch(apiUrl('/api/models'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_url:url,api_key:key})});const d=await r.json();if(d.error)throw new Error(d.error);sel.innerHTML='';if(!d.models||!d.models.length){sel.innerHTML='<option value="">无可用模型</option>';return;}d.models.forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;sel.appendChild(o);});addLog(bot,`获取到 ${d.models.length} 个模型`);autoSaveConfigAfterModelFetch();}
  catch(e){sel.innerHTML='<option value="">获取失败</option>';addLog('error',`${bot}获取模型失败: ${e.message}`);}
}

// ============================================================
// SSE读取 - 不自动重试，出错直接抛
// ============================================================
async function readSSE(url,body,onChunk,signal){
  const r=await fetch(apiUrl(url),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
  if(r.status===401){const back=encodeURIComponent(location.pathname+location.search);location.href='/w/'+(window.WORKSPACE||'')+'/login?next='+back;throw new Error('未登录');}
  if(!r.ok){const t=await r.text();throw new Error(`HTTP ${r.status}: ${t.slice(0,200)}`);}
  const reader=r.body.getReader(),dec=new TextDecoder();
  let buf='',full='';
  while(true){
    const{done,value}=await reader.read();
    if(done)break;
    buf+=dec.decode(value,{stream:true});
    const lines=buf.split('\n');buf=lines.pop()||'';
    for(const line of lines){
      if(!line.startsWith('data: '))continue;
      const d=line.slice(6).trim();
      if(d==='[DONE]')return full;
      try{const o=JSON.parse(d);if(o.error)throw new Error(o.error);if(o.content){full+=o.content;if(onChunk)onChunk(o.content,full);}}
      catch(pe){if(pe.message&&!pe.message.includes('Unexpected'))throw pe;}
    }
  }
  return full;
}

// outline提取
function extractOutline(text){const m=text.match(/<outline>([\s\S]*?)<\/outline>/i);return m?m[1].trim():null;}
function extractChapterOutline(text){const m=text.match(/<chapter_outline>([\s\S]*?)<\/chapter_outline>/i);return m?m[1].trim():null;}
function stripOutline(text){return text.replace(/<outline>[\s\S]*?<\/outline>/gi,'').replace(/<chapter_outline>[\s\S]*?<\/chapter_outline>/gi,'').trim();}

// ============================================================
// 配置方案 - 服务端持久化（API密钥/地址/模型）
// ============================================================
let allConfigProfiles = []; // [{id,name,bot1:{base_url,api_key,model},...}]
let activeConfigId = null;

function readCurrentBotFields(){
  const r={};
  ['bot1','bot2','bot3','bot4'].forEach(b=>{
    r[b]={base_url:$(b+'_url').value, api_key:$(b+'_key').value, model:$(b+'_model').value, models_html:$(b+'_model').innerHTML};
  });
  r.pass_score=parseFloat($('passScore').value)||8;
  r.max_retries=parseInt($('maxRetries').value)||3;
  r.style_id=getStyleId();
  r.word_count=getWordCount();
  return r;
}

function applyConfigToFields(cfg){
  ['bot1','bot2','bot3','bot4'].forEach(b=>{
    if(cfg[b]){
      if(cfg[b].base_url) $(b+'_url').value=cfg[b].base_url;
      if(cfg[b].api_key) $(b+'_key').value=cfg[b].api_key;
      if(cfg[b].models_html) $(b+'_model').innerHTML=cfg[b].models_html;
      if(cfg[b].model) $(b+'_model').value=cfg[b].model;
    }
  });
  if(cfg.pass_score) $('passScore').value=cfg.pass_score;
  if(cfg.max_retries) $('maxRetries').value=cfg.max_retries;
  if(cfg.style_id) selectStyle(cfg.style_id, true);
  if(cfg.word_count) $('wordCountInput').value=cfg.word_count;
}

async function saveConfigProfile(){
  const name=$('configProfileName').value.trim()||'未命名';
  const fields=readCurrentBotFields();
  if(!activeConfigId) activeConfigId='cfg_'+Date.now().toString(36);
  // 更新或新增
  let found=false;
  for(let i=0;i<allConfigProfiles.length;i++){
    if(allConfigProfiles[i].id===activeConfigId){allConfigProfiles[i]={id:activeConfigId,name,...fields};found=true;break;}
  }
  if(!found) allConfigProfiles.push({id:activeConfigId,name,...fields});
  await pushConfigsToServer();
  renderConfigProfiles();
  addLog('system',`配置方案「${name}」已保存到服务器`);
}

// 获取模型成功后自动保存当前配置
async function autoSaveConfigAfterModelFetch(){
  if(!activeConfigId){
    // 第一次获取模型，自动创建默认配置
    activeConfigId='cfg_'+Date.now().toString(36);
    $('configProfileName').value=$('configProfileName').value||'默认配置';
  }
  await saveConfigProfile();
}

async function pushConfigsToServer(){
  try{
    await fetch(apiUrl('/api/configs'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({configs:allConfigProfiles})});
  }catch(e){console.warn('保存配置失败',e);}
}

async function loadConfigsFromServer(){
  try{
    const r=await fetch(apiUrl('/api/configs'));const d=await r.json();
    allConfigProfiles=d.configs||[];
    renderConfigProfiles();
    // 自动加载第一个（或上次使用的）
    const lastId=localStorage.getItem('nf_active_cfg');
    const target=allConfigProfiles.find(c=>c.id===lastId)||allConfigProfiles[0];
    if(target){
      activeConfigId=target.id;
      $('configProfileName').value=target.name||'';
      applyConfigToFields(target);
      addLog('system',`已自动加载配置「${target.name}」`);
    }
  }catch{}
}

function renderConfigProfiles(){
  const el=$('configProfileList');el.innerHTML='';
  // 更新菜单按钮标签
  const activeCfg=allConfigProfiles.find(c=>c.id===activeConfigId);
  $('configMenuLabel').textContent=activeCfg?activeCfg.name:'';

  if(!allConfigProfiles.length){el.innerHTML='<div style="font-size:11px;color:var(--text-muted)">无已保存方案</div>';return;}
  allConfigProfiles.forEach(c=>{
    const row=document.createElement('div');
    row.className='dd-list-item'+(c.id===activeConfigId?' active':'');
    row.innerHTML=`<span class="dli-name">${c.id===activeConfigId?'&#9679; ':''}${c.name}</span><button class="dli-btn" title="加载">加载</button><button class="dli-btn del" title="删除">删除</button>`;
    row.querySelector('.dli-btn:first-of-type').onclick=(e)=>{
      e.stopPropagation();
      activeConfigId=c.id;$('configProfileName').value=c.name||'';
      applyConfigToFields(c);localStorage.setItem('nf_active_cfg',c.id);
      renderConfigProfiles();addLog('system',`已切换到配置「${c.name}」`);
    };
    row.querySelector('.dli-btn.del').onclick=async(e)=>{
      e.stopPropagation();
      if(!confirm(`删除配置方案「${c.name}」？`))return;
      allConfigProfiles=allConfigProfiles.filter(x=>x.id!==c.id);
      if(activeConfigId===c.id)activeConfigId=null;
      await pushConfigsToServer();renderConfigProfiles();addLog('system',`已删除配置「${c.name}」`);
    };
    el.appendChild(row);
  });
}
