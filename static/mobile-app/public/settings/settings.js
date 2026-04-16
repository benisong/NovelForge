// 全局变量保存配置
let currentConfig = null;

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  await loadConfigs();
  renderBotConfigs();
});

// 主题控制
function initTheme() {
  const savedTheme = localStorage.getItem('nf_theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
  const themeSelect = document.getElementById('theme_mode');
  if (themeSelect) themeSelect.value = savedTheme;
}

function changeTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('nf_theme', theme);
}

// 模拟 Toast
function showToast(message, duration = 2000) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, duration);
}

// 核心逻辑：加载配置
async function loadConfigs() {
  try {
    // 调用 FastAPI 接口
    const res = await fetch('/api/configs');
    const data = await res.json();
    
    // 如果没有数据，给个默认模板
    if (!data.configs || data.configs.length === 0) {
      currentConfig = {
        id: 'default', name: '默认配置',
        pass_score: 8.0, max_retries: 3,
        bot1: { base_url: '', api_key: '', model: '', temperature: 0.7, max_tokens: 4096 },
        bot2: { base_url: '', api_key: '', model: '', temperature: 0.7, max_tokens: 4096 },
        bot3: { base_url: '', api_key: '', model: '', temperature: 0.7, max_tokens: 4096 },
        bot4: { base_url: '', api_key: '', model: '', temperature: 0.7, max_tokens: 4096, abstract_model: '' }
      };
    } else {
      // 为了简单，我们只操作 default (第一个) 配置
      currentConfig = data.configs.find(c => c.id === 'default') || data.configs[0];
    }
    
    // 填充全局参数
    document.getElementById('pass_score').value = currentConfig.pass_score;
    document.getElementById('max_retries').value = currentConfig.max_retries;

  } catch (error) {
    showToast('加载配置失败');
    console.error(error);
  }
}

// 渲染 Bot 配置区
function renderBotConfigs() {
  const container = document.getElementById('botConfigsContainer');
  container.innerHTML = '';
  
  const bots = ['bot1', 'bot2', 'bot3', 'bot4'];
  const labels = {
    bot1: 'Bot1 大纲策划',
    bot2: 'Bot2 内容创作',
    bot3: 'Bot3 质量审核',
    bot4: 'Bot4 记忆管理'
  };

  bots.forEach(bot => {
    const config = currentConfig[bot];
    let copyBtnHtml = '';
    if (bot !== 'bot1') {
      copyBtnHtml = `<button class="copy-btn" onclick="copyFromBot1('${bot}')">使用 Bot1 配置</button>`;
    }

    let abstractModelHtml = '';
    if (bot === 'bot4') {
      abstractModelHtml = `
        <div class="form-item">
          <label>摘要模型 (Abstract Model) - 可选</label>
          <input type="text" id="${bot}_abstract_model" value="${config.abstract_model || ''}" placeholder="用于生成简短摘要的廉价模型">
        </div>
      `;
    }

    const html = `
      <div class="section-title">${labels[bot]}</div>
      <div class="card">
        <div class="card-header">
          <h3>${bot.toUpperCase()}</h3>
          ${copyBtnHtml}
        </div>
        <div class="form-item">
          <label>API Base URL</label>
          <input type="text" id="${bot}_base_url" value="${config.base_url || ''}" placeholder="例如 https://api.openai.com/v1">
        </div>
        <div class="form-item">
          <label>API Key</label>
          <input type="password" id="${bot}_api_key" value="${config.api_key || ''}">
        </div>
        <div class="form-item">
          <label>模型 (Model)</label>
          <div class="input-with-button">
            <input type="text" id="${bot}_model" value="${config.model || ''}">
            <button onclick="fetchModels('${bot}')">获取可用列表</button>
          </div>
        </div>
        ${abstractModelHtml}
      </div>
    `;
    container.insertAdjacentHTML('beforeend', html);
  });
}

// 复制 Bot1 配置
function copyFromBot1(targetBot) {
  const fields = ['base_url', 'api_key', 'model'];
  fields.forEach(field => {
    const val = document.getElementById(`bot1_${field}`).value;
    document.getElementById(`${targetBot}_${field}`).value = val;
  });
  showToast(`已复制到 ${targetBot.toUpperCase()}`);
}

// 获取模型列表
async function fetchModels(bot) {
  const baseUrl = document.getElementById(`${bot}_base_url`).value.trim();
  const apiKey = document.getElementById(`${bot}_api_key`).value.trim();
  
  if (!baseUrl || !apiKey) {
    showToast('请先填写 Base URL 和 API Key');
    return;
  }
  
  showToast('正在获取模型列表...', 3000);
  try {
    const res = await fetch('/api/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
    });
    const data = await res.json();
    if (data.models && data.models.length > 0) {
      // 简单处理：把第一个模型填进去，实际可以做一个下拉列表弹窗
      document.getElementById(`${bot}_model`).value = data.models[0];
      showToast(`获取成功，共 ${data.models.length} 个。已填入首个`);
    } else {
      showToast(data.error || '未获取到模型');
    }
  } catch (error) {
    showToast('请求失败');
  }
}

// 保存配置
async function saveConfigs() {
  const pass_score = parseFloat(document.getElementById('pass_score').value);
  const max_retries = parseInt(document.getElementById('max_retries').value, 10);
  
  currentConfig.pass_score = isNaN(pass_score) ? 8.0 : pass_score;
  currentConfig.max_retries = isNaN(max_retries) ? 3 : max_retries;

  const bots = ['bot1', 'bot2', 'bot3', 'bot4'];
  bots.forEach(bot => {
    currentConfig[bot].base_url = document.getElementById(`${bot}_base_url`).value.trim();
    currentConfig[bot].api_key = document.getElementById(`${bot}_api_key`).value.trim();
    currentConfig[bot].model = document.getElementById(`${bot}_model`).value.trim();
    if(bot === 'bot4') {
       currentConfig[bot].abstract_model = document.getElementById(`${bot}_abstract_model`).value.trim();
    }
  });

  try {
    // 由于后端期望的是数组
    const res = await fetch('/api/configs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ configs: [currentConfig] })
    });
    const data = await res.json();
    if (data.ok) {
      showToast('配置保存成功');
      setTimeout(goBack, 1000); // 保存后自动返回
    } else {
      showToast('保存失败');
    }
  } catch (error) {
    showToast('网络错误');
  }
}

// 返回
function goBack() {
  window.history.back();
}