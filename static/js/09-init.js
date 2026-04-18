// 09-init.js - Page initialization

// ============================================================
// 主题切换逻辑
// ============================================================
function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('nf_theme', newTheme);
  
  const btn = document.getElementById('themeToggleBtn');
  if (newTheme === 'dark') {
    btn.innerHTML = '&#9728;&#65039; 白天模式';
  } else {
    btn.innerHTML = '&#127769; 夜间模式';
  }
}

function initTheme() {
  const savedTheme = localStorage.getItem('nf_theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
  
  const btn = document.getElementById('themeToggleBtn');
  if (btn) {
    if (savedTheme === 'dark') {
      btn.innerHTML = '&#9728;&#65039; 白天模式';
    } else {
      btn.innerHTML = '&#127769; 夜间模式';
    }
  }
}

// ============================================================
// 页面初始化：从服务端加载配置和项目列表
// ============================================================
(async function init(){
  initTheme();
  await loadConfigsFromServer();
  await loadStyles();
  await loadBot3Prompts();
  // 恢复上次选中的自定义提示词
  const savedB3pId=localStorage.getItem('nf_bot3_prompt_id');
  if(savedB3pId&&bot3CustomPrompts.find(x=>x.id===savedB3pId)){activeBot3PromptId=savedB3pId;_updateBot3PromptLabel();}
  await loadProjectList();
  // 初始化拖拽（此时DOM已就绪，modal在script标签之后）
  setTimeout(initStyleDragDrop, 0);
  // 自动加载最近更新的项目（从服务端获取，不依赖localStorage）
  try{
    const r=await fetch(apiUrl('/api/projects/latest'));
    if(r.ok){
      const d=await r.json();
      if(d.project_id) await loadProject(d.project_id);
    }
  }catch{}
})();
