// 工作空间感知的 URL 包装。
// 后端所有受保护接口的真实路径形如 /api/w/<slug>/projects；前端代码里仍写 "/api/projects"，
// 通过 apiUrl() 自动注入 slug。
//
// slug 来源（优先级）：
//   1) window.WORKSPACE（由后端在 dist/index.html 注入）
//   2) URL 路径解析（/m/w/<slug>/...）
//   3) localStorage（最近一次记住的 slug）

function readSlug() {
  if (typeof window === 'undefined') return '';
  if (window.WORKSPACE) return window.WORKSPACE;
  const m = window.location.pathname.match(/^\/(?:m\/)?w\/([a-z0-9][a-z0-9\-]*[a-z0-9])\//);
  if (m) return m[1];
  try {
    return localStorage.getItem('nf_workspace') || '';
  } catch {
    return '';
  }
}

let cachedSlug = readSlug();
if (cachedSlug && typeof localStorage !== 'undefined') {
  try { localStorage.setItem('nf_workspace', cachedSlug); } catch {}
}

export function getWorkspace() {
  return cachedSlug;
}

export function apiUrl(path) {
  if (!path) return path;
  if (!cachedSlug) return path;
  if (path.startsWith('/api/w/')) return path;
  if (path.startsWith('/api/')) {
    return '/api/w/' + cachedSlug + path.slice(4);
  }
  return path;
}

export function loginUrl(nextPath) {
  const slug = cachedSlug || '';
  const next = encodeURIComponent(nextPath || (window.location.pathname + window.location.hash));
  return `/w/${slug}/login?next=${next}`;
}

// fetch 包装：401 自动跳登录页
export async function apiFetch(path, init) {
  const r = await fetch(apiUrl(path), init);
  if (r.status === 401) {
    window.location.href = loginUrl();
  }
  return r;
}
