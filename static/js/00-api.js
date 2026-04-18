// 00-api.js - 工作空间感知的 API 路径包装
//
// 后端所有受保护接口的真实路径形如：/api/w/<slug>/projects
// 前端代码原本写的是 /api/projects；统一通过 apiUrl(path) 包装：
//   apiUrl('/api/projects') -> '/api/w/<slug>/projects'

(function () {
  // window.WORKSPACE 由后端在 HTML 模板中注入；缺失时回退到 URL 解析（/w/<slug>/...）
  let slug = window.WORKSPACE || '';
  if (!slug) {
    const m = location.pathname.match(/^\/(?:m\/)?w\/([a-z0-9][a-z0-9\-]*[a-z0-9])\//);
    if (m) slug = m[1];
  }
  if (!slug) {
    console.warn('[apiUrl] 未获取到 workspace slug，API 调用将失败');
  }
  window.WORKSPACE = slug;

  // 标题栏显示当前工作空间名（页面 DOM 就绪后刷新一次）
  document.addEventListener('DOMContentLoaded', () => {
    const el = document.getElementById('wsName');
    if (el) el.textContent = slug;
  });

  function apiUrl(path) {
    if (!path) return path;
    if (!slug) return path;
    // 把 /api/foo 替换成 /api/w/<slug>/foo
    if (path.startsWith('/api/w/')) return path; // 已带前缀
    if (path.startsWith('/api/')) {
      return '/api/w/' + slug + path.slice(4);   // path.slice(4) = '/foo'
    }
    return path;
  }

  window.apiUrl = apiUrl;

  // 401 表示 cookie 失效 → 自动跳回 picker / login
  window.apiFetch = async function apiFetch(path, init) {
    const r = await fetch(apiUrl(path), init);
    if (r.status === 401) {
      const back = encodeURIComponent(location.pathname + location.search);
      location.href = '/w/' + slug + '/login?next=' + back;
    }
    return r;
  };
})();
