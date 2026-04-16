import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useProjectStore = defineStore('project', () => {
  // === 全局配置 ===
  const config = ref(null);

  // === 当前项目状态 ===
  const projectId = ref(null);
  const projectName = ref('我的小说1');
  const chatHistory = ref([]);
  const currentOutline = ref('');
  const chapterOutline = ref('');
  const currentContent = ref('');
  const reviews = ref([]);
  const summaries = ref([]);
  const chapters = ref([]);

  // === API 方法 ===

  // 加载系统配置
  const loadConfig = async () => {
    try {
      const res = await fetch('/api/configs');
      const data = await res.json();
      if (data.configs && data.configs.length > 0) {
        config.value = data.configs.find(c => c.id === 'default') || data.configs[0];
      }
    } catch (e) {
      console.error('加载配置失败:', e);
    }
  };

  // 加载最新项目或指定项目
  const loadProject = async (id) => {
    const targetId = id || localStorage.getItem('nf_last_project');
    if (!targetId) return false;

    try {
      const res = await fetch(`/api/projects/${targetId}`);
      if (res.ok) {
        const data = await res.json();
        projectId.value = data.project_id;
        projectName.value = data.name;
        chatHistory.value = data.chat_history || [];
        currentOutline.value = data.current_outline || '';
        chapterOutline.value = data.chapter_outline || '';
        currentContent.value = data.current_content || '';
        reviews.value = data.reviews || [];
        chapters.value = data.chapters || [];
        summaries.value = data.small_summaries || [];
        localStorage.setItem('nf_last_project', data.project_id);
        return true;
      }
    } catch (e) {
      console.error('加载项目失败:', e);
    }
    return false;
  };

  // 保存项目到后端
  const saveProject = async () => {
    if (!projectId.value && chatHistory.value.length === 0 && chapters.value.length === 0) return;
    
    if (!projectId.value) {
      projectId.value = 'proj_' + Date.now().toString(36);
    }

    const payload = {
      project_id: projectId.value,
      name: projectName.value,
      chapters: chapters.value,
      chat_history: chatHistory.value,
      current_outline: currentOutline.value,
      chapter_outline: chapterOutline.value,
      current_content: currentContent.value,
      reviews: reviews.value,
      small_summaries: summaries.value,
      // 忽略部分字段以保持简洁
      logs: [],
      active_tab: 'bot1' 
    };

    try {
      await fetch('/api/projects/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      localStorage.setItem('nf_last_project', projectId.value);
    } catch (e) {
      console.error('保存项目失败:', e);
    }
  };

  return {
    config,
    projectId,
    projectName,
    chatHistory,
    currentOutline,
    chapterOutline,
    currentContent,
    reviews,
    summaries,
    chapters,
    loadConfig,
    loadProject,
    saveProject
  };
});