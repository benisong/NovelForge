// 01-state.js - Global state, constants, and UI utilities

const S = {
  chatHistory: [],
  currentOutline: '',      // 总大纲
  chapterOutline: '',      // 当前章节大纲
  currentContent: '',
  currentSummary: '',      // 保留兼容旧项目
  chapters: [],
  reviews: [],
  logs: [],              // [{bot, msg, time}] 持久化日志
  accumulatedTips: [],   // 改进4: 历史审核经验（错题本），最多保留10条
  smallSummaries: [],    // [{chapter, condensed, abstract, time}]
  bigSummaries: [],      // [{fromChapter, toChapter, content, time}]
  abortCtrl: null,
  isGenerating: false,
  pipelineState: null,
  // chat_history 中的"章节边界"下标。Bot4 完成时设为 chatHistory.length。
  // recalcOutlineFromHistory 只在 i >= chapterBoundaryIdx 的范围内回填 chapter_outline，
  // 防止已完成章节的 <chapter_outline> 在新章节里被误显示。
  chapterBoundaryIdx: 0,
};

const $ = id => document.getElementById(id);
const now = () => { const d=new Date(); return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`; };

function _syncMenuState(){
  const anyOpen=Array.from(document.querySelectorAll('.dropdown-panel')).some(p=>p.classList.contains('show'));
  document.body.classList.toggle('menu-open', anyOpen);
}

function addLog(bot,msg){
  const t=now();
  S.logs.push({bot,msg,time:t});
  if(S.logs.length>200) S.logs=S.logs.slice(-200); // 限制大小
  const e=document.createElement('div');e.className=`log-entry ${bot}`;e.innerHTML=`<span class="lt">[${t}]</span><span class="lb">[${bot.toUpperCase()}]</span><span>${msg}</span>`;$('logPanel').appendChild(e);$('logPanel').scrollTop=99999;
}
function setStatus(cls,text){$('statusDot').className='sd '+cls;$('statusLabel').textContent=text;$('statusText').textContent=text;}
function switchTab(name){
  const tab=$('tab-'+name), pane=$('pane-'+name);
  if(!tab||!pane){
    if(name!=='bot1') return switchTab('bot1');
    return;
  }
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('[data-tab-name]').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.pane').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.dropdown-panel').forEach(p=>p.classList.remove('show'));
  document.querySelectorAll('.menu-btn').forEach(b=>b.classList.remove('open'));
  _syncMenuState();
  tab.classList.add('active');
  document.querySelectorAll(`[data-tab-name="${name}"]`).forEach(t=>t.classList.add('active'));
  pane.classList.add('active');
}
function switchRight(name){
  const tab=$('rt-'+name), log=$('logPanel'), history=$('rhistoryPanel');
  if(!tab||!log||!history) return;
  document.querySelectorAll('.right-tab').forEach(t=>t.classList.remove('active'));
  tab.classList.add('active');
  log.style.display=name==='log'?'':'none';
  history.style.display=name==='rhistory'?'':'none';
}
function setStep(id,cls){$(id).className='p-step '+cls;}
function hideAllErrors(){['errContent','errReview','errSummary'].forEach(id=>$(id).classList.remove('show'));}

// 顶部下拉菜单
function toggleMenu(id){
  const panel=$(id);
  if(!panel) return;
  const isOpen=panel.classList.contains('show');
  // 关闭所有菜单
  document.querySelectorAll('.dropdown-panel').forEach(p=>p.classList.remove('show'));
  document.querySelectorAll('.menu-btn').forEach(b=>b.classList.remove('open'));
  if(!isOpen){
    panel.classList.add('show');
    const trigger=document.querySelector(`.menu-btn[data-menu-target="${id}"]`) || panel.previousElementSibling;
    if(trigger && trigger.classList) trigger.classList.add('open');
  }
  _syncMenuState();
}
// 点击外部关闭菜单
document.addEventListener('click',e=>{
  if(!e.target.closest('.menu-btn')&&!e.target.closest('.dropdown-panel')){
    document.querySelectorAll('.dropdown-panel').forEach(p=>p.classList.remove('show'));
    document.querySelectorAll('.menu-btn').forEach(b=>b.classList.remove('open'));
    _syncMenuState();
  }
});

// ============================================================
// 显示错误+重试按钮
// ============================================================
function showError(bannerId, msg, retryFn){
  const banner=$(bannerId);
  banner.classList.add('show');
  banner.querySelector('.eb-msg').textContent=msg;
  const retryBtn=banner.querySelector('.eb-btn-retry');
  retryBtn.onclick=()=>{banner.classList.remove('show');retryFn();};
}

function restartPipeline(){
  hideAllErrors();
  S.pipelineState=null;
  resetPipeline();
  setStatus('ready','已重置，请重新确认大纲开始创作');
  addLog('system','用户选择从头开始');
  switchTab('bot1');
}

// ============================================================
// Bot3审核面板渲染（新版：文学性/逻辑性/风格一致性/AI感 + 逐条可编辑建议）
// ============================================================
const REVIEW_DIMS=[
  {key:'literary',label:'文学性',desc:'语言表现力、修辞、叙事技巧'},
  {key:'logic',label:'逻辑性',desc:'情节因果、前后自洽'},
  {key:'style',label:'风格一致性',desc:'与大纲/上下文风格匹配'},
  {key:'ai_feel',label:'人味(越高越自然)',desc:'越像真人写作分越高，AI痕迹越少'},
];
const DIM_LABEL_MAP={literary:'文学性',logic:'逻辑性',style:'风格一致性',ai_feel:'人味'};
const SEV_LABEL={high:'必须改',medium:'建议改',low:'可选改'};

function scoreColor(v){if(v>=8)return'var(--accent-green)';if(v>=6)return'var(--accent-yellow)';return'var(--accent-red)';}

function _escHtml(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

// ---- 改进6: 记忆压缩（当summary超过阈值时调用）----
const SUMMARY_COMPRESS_THRESHOLD=3000; // 超过3000字触发压缩
