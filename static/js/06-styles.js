// 06-styles.js - Writing style management

let allStyles=[];
let selectedStyleId='';

// 预设文风ID列表（不可删除）
const BUILTIN_STYLE_IDS=new Set(['literary','wuxia','xuanhuan','suspense','urban','romance','scifi','humor']);

async function loadStyles(){
  try{
    const r=await fetch('/api/styles');const d=await r.json();
    allStyles=d.styles||[];
    if(d.default_word_count) $('wordCountInput').value=d.default_word_count;
    renderStyleGrid();
    const last=localStorage.getItem('nf_style_id');
    if(last) selectStyle(last, true);
  }catch(e){console.warn('加载文风失败',e);}
}

function renderStyleGrid(){
  const grid=$('styleGrid');
  if(!allStyles.length){grid.innerHTML='<div style="font-size:11px;color:var(--text-muted);grid-column:1/-1">无可用文风</div>';return;}
  grid.innerHTML=allStyles.map(s=>{
    const isCustom=!BUILTIN_STYLE_IDS.has(s.id);
    const activeClass=s.id===selectedStyleId?' active':'';
    const customBadge=isCustom?'<span class="sc-custom">自定义</span>':'';
    const actions=isCustom?`<div class="sc-actions"><button onclick="event.stopPropagation();editStyle('${s.id}')">编辑</button><button class="sc-del" onclick="event.stopPropagation();deleteStyle('${s.id}')">删除</button></div>`:'';
    return `<div class="style-card${activeClass}" data-id="${s.id}" onclick="selectStyle('${s.id}')"><div class="sc-name">${s.name}${customBadge}</div><div class="sc-desc">${s.desc}</div>${actions}</div>`;
  }).join('');
}

function selectStyle(id, silent){
  if(selectedStyleId===id){
    selectedStyleId='';
    localStorage.removeItem('nf_style_id');
    $('stylePreview').classList.remove('show');
  }else{
    selectedStyleId=id;
    localStorage.setItem('nf_style_id',id);
    const style=allStyles.find(s=>s.id===id);
    if(style&&style.example){
      $('stylePreview').textContent=style.example;
      $('stylePreview').classList.add('show');
    }else{
      $('stylePreview').classList.remove('show');
    }
  }
  renderStyleGrid();
  if(!silent) addLog('system', selectedStyleId?`已选择文风：${allStyles.find(s=>s.id===selectedStyleId)?.name||id}`:'已取消文风选择');
}

function getStyleId(){ return selectedStyleId; }
function getWordCount(){ return parseInt($('wordCountInput').value)||800; }

// ---- Bot2 设置面板折叠 ----
function toggleBot2Settings(){
  const body=$('bot2SettingsBody'), arrow=$('bot2SettingsArrow');
  body.classList.toggle('collapsed');
  arrow.classList.toggle('collapsed');
}

// ---- 文风弹窗控制 ----
function openStyleModal(editId){
  $('smEditId').value=editId||'';
  if(editId){
    const s=allStyles.find(x=>x.id===editId);
    if(s){
      $('styleModalTitle').textContent='\u270f\ufe0f 编辑文风';
      $('smName').value=s.name;
      $('smDesc').value=s.desc;
      $('smExample').value=s.example;
    }
  }else{
    $('styleModalTitle').textContent='\u270f\ufe0f 导入文风';
    $('smName').value='';$('smDesc').value='';$('smExample').value='';
  }
  $('styleModalOverlay').classList.add('show');
}

function closeStyleModal(){
  $('styleModalOverlay').classList.remove('show');
}

function editStyle(id){ openStyleModal(id); }

async function deleteStyle(id){
  const s=allStyles.find(x=>x.id===id);
  if(!s)return;
  if(!confirm(`确定删除文风「${s.name}」？`))return;
  allStyles=allStyles.filter(x=>x.id!==id);
  if(selectedStyleId===id){selectedStyleId='';localStorage.removeItem('nf_style_id');$('stylePreview').classList.remove('show');}
  await _pushStylesToServer();
  renderStyleGrid();
  addLog('system',`已删除文风「${s.name}」`);
}

async function saveStyleFromModal(){
  const name=$('smName').value.trim();
  const desc=$('smDesc').value.trim();
  const example=$('smExample').value.trim();
  if(!name){alert('请填写文风名称');$('smName').focus();return;}
  if(!example){alert('请提供示例片段');$('smExample').focus();return;}

  const editId=$('smEditId').value;
  if(editId){
    // 编辑已有文风
    const idx=allStyles.findIndex(x=>x.id===editId);
    if(idx>=0){allStyles[idx].name=name;allStyles[idx].desc=desc;allStyles[idx].example=example;}
  }else{
    // 新增
    const id='custom_'+Date.now().toString(36);
    allStyles.push({id,name,desc:desc||name,example,custom:true});
  }
  await _pushStylesToServer();
  renderStyleGrid();
  closeStyleModal();
  addLog('system',editId?`文风「${name}」已更新`:`已导入文风「${name}」`);
}

async function _pushStylesToServer(){
  try{
    await fetch('/api/styles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({styles:allStyles,default_word_count:getWordCount()})});
  }catch(e){console.warn('保存文风失败',e);}
}

// ---- 文件导入 ----
function handleStyleFileImport(input){
  const file=input.files&&input.files[0];
  if(!file)return;
  const reader=new FileReader();
  reader.onload=function(e){
    const text=e.target.result;
    const ext=file.name.split('.').pop().toLowerCase();

    if(ext==='json'){
      _importFromJSON(text, file.name);
    }else{
      // txt / md → 整个内容作为示例片段
      $('smExample').value=text.trim();
      // 用文件名作为默认名称
      const baseName=file.name.replace(/\.\w+$/,'');
      if(!$('smName').value) $('smName').value=baseName;
      addLog('system',`已从文件「${file.name}」导入片段（${text.length}字）`);
    }
  };
  reader.readAsText(file,'utf-8');
  input.value=''; // 允许重复选同一文件
}

function _importFromJSON(text, fileName){
  try{
    const data=JSON.parse(text);
    // 支持两种格式：
    // 1. 单个文风对象：{name, desc, example}
    // 2. 批量数组：[{name,desc,example}, ...]  或 {styles:[...]}
    let items=[];
    if(Array.isArray(data)){
      items=data;
    }else if(data.styles&&Array.isArray(data.styles)){
      items=data.styles;
    }else if(data.name&&data.example){
      items=[data];
    }else{
      // 尝试作为纯文本
      $('smExample').value=text.trim();
      return;
    }

    let count=0;
    items.forEach(it=>{
      if(!it.name||!it.example)return;
      const id=it.id||'custom_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2,4);
      // 避免ID冲突
      if(allStyles.find(x=>x.id===id))return;
      allStyles.push({id,name:it.name,desc:it.desc||it.name,example:it.example,custom:true});
      count++;
    });

    if(count>0){
      _pushStylesToServer();
      renderStyleGrid();
      closeStyleModal();
      addLog('system',`从「${fileName}」导入了 ${count} 个文风`);
    }else if(items.length===1){
      // 只有一个且已填好字段，显示到表单里让用户确认
      $('smName').value=items[0].name||'';
      $('smDesc').value=items[0].desc||'';
      $('smExample').value=items[0].example||'';
    }else{
      alert('JSON格式无法识别，请确保包含 name 和 example 字段');
    }
  }catch(e){
    // JSON解析失败，当作纯文本
    $('smExample').value=text.trim();
    addLog('system',`文件不是有效JSON，已作为示例片段导入`);
  }
}

// 拖拽支持（需在DOM就绪后调用）
function initStyleDragDrop(){
  const drop=$('smFileDrop');
  if(!drop)return;
  ['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('dragover');}));
  ['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('dragover');}));
  drop.addEventListener('drop',e=>{
    const file=e.dataTransfer.files&&e.dataTransfer.files[0];
    if(file){
      const dt=new DataTransfer();dt.items.add(file);
      $('smFileInput').files=dt.files;
      handleStyleFileImport($('smFileInput'));
    }
  });
}
