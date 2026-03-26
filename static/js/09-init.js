// 09-init.js - Page initialization

// ============================================================
// 页面初始化：从服务端加载配置和项目列表
// ============================================================
(async function init(){
  await loadConfigsFromServer();
  await loadStyles();
  await loadBot3Prompts();
  // 恢复上次选中的自定义提示词
  const savedB3pId=localStorage.getItem('nf_bot3_prompt_id');
  if(savedB3pId&&bot3CustomPrompts.find(x=>x.id===savedB3pId)){activeBot3PromptId=savedB3pId;_updateBot3PromptLabel();}
  await loadProjectList();
  // 初始化拖拽（此时DOM已就绪，modal在script标签之后）
  setTimeout(initStyleDragDrop, 0);
  // 自动加载上次打开的项目
  const lastPid=localStorage.getItem('nf_last_project');
  if(lastPid){
    try{
      const r=await fetch(`/api/projects/${lastPid}`);
      if(r.ok) await loadProject(lastPid);
    }catch{}
  }
})();
