# NovelForge

一个面向 AI 辅助长篇小说创作的本地化工作台。通过**四个协同的 Bot 角色**（对话构思 / 正文创作 / 审核打分 / 记忆总结）在 OpenAI 兼容接口上自动跑一个"写—审—改—记忆"循环，并把项目、章节、审核记录持久化到本地。

- 后端：FastAPI + httpx（流式 SSE）
- 前端：桌面版静态 HTML + 独立的移动端 SPA（`static/mobile-app/`）
- 部署：单容器 Docker / 裸机 Python / Nginx 反代 + HTTPS

> ⚠️ **这是一个面向单用户的自托管工具，默认不带身份认证**。对外开放前，请务必放在反向代理 + HTTPS + 访问控制（Basic Auth / IP 白名单 / 私网）之后。

---

## ✨ 功能概览

| 模块 | 作用 |
| --- | --- |
| Bot1 对话 | 与作者讨论大纲、世界观、人物，流式对话 |
| Bot2 创作 / 重写 | 按大纲和历史上下文产出正文，或根据审核建议重写 |
| Bot3 审核 | 对生成内容按 4 个维度打分（文学性 / 逻辑性 / 风格一致性 / 人味）并给出逐条修改建议 |
| Bot4 记忆 | 小总结（缩略+摘要）→ 大总结 → 记忆压缩，用于上下文回灌 |
| 项目管理 | 多项目并存、自动备份（保留最近 10 个版本）、导出纯文本 |
| 文风库 | 预置文风 + 用户自定义文风，参与 Bot2/Bot3 的提示词 |
| 移动端 | `/m/` 独立 SPA，桌面 UA 访问根路径自动返回桌面版，移动 UA 自动跳转 |

---

## 🚀 快速开始

### 方式一：Docker（推荐）

```bash
cp .env.example .env           # 按需调整端口、绑定地址、CORS 等
docker compose up -d --build
```

默认只绑定到 `127.0.0.1:8000`，外网访问请在 `.env` 中设置 `BIND_ADDR=0.0.0.0`，**并且配置 Nginx + HTTPS**（见下文）。

数据持久化在 Docker Volume `novel-data` 中，容器重建不会丢数据。

### 方式二：本地 Python

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                   # 默认监听 127.0.0.1:8000
```

打开浏览器访问 `http://127.0.0.1:8000`。

开发模式（自动热重载）：

```bash
DEV_RELOAD=true python run.py
```

### 方式三：Nginx 反代 + HTTPS（生产推荐）

```bash
apt install nginx certbot python3-certbot-nginx
```

`/etc/nginx/sites-available/novelforge`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_buffering off;            # SSE 流式必需

        # 建议再加一层 Basic Auth
        # auth_basic "NovelForge";
        # auth_basic_user_file /etc/nginx/.htpasswd;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/novelforge /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d your-domain.com
```

### 方式四：Systemd（无 Docker）

`/etc/systemd/system/novelforge.service`：

```ini
[Unit]
Description=NovelForge
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/novelforge
EnvironmentFile=/opt/novelforge/.env
ExecStart=/usr/bin/python3 run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now novelforge
```

---

## ⚙️ 配置项（环境变量）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `BIND_ADDR` | `127.0.0.1` | docker-compose 的绑定地址；开放到公网改为 `0.0.0.0` |
| `PORT` | `8000` | 对外端口 |
| `NOVEL_DATA_DIR` | 项目内 `data/` | 项目、配置、文风、备份的持久化目录 |
| `DEV_RELOAD` | `false` | 本地开发热重载；生产必须为 `false` |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CORS_ORIGINS` | 空 | 逗号分隔的允许跨域来源；留空表示不开放跨域 |

API 密钥、base_url、使用的模型**由前端在浏览器中配置并随每次请求提交**，后端不落库保存密钥明文；关闭浏览器后可以选择保留在 localStorage 或清空。

---

## 📂 目录结构

```
NovelForge/
├─ run.py                    # 启动入口（读取 HOST/PORT/DEV_RELOAD）
├─ requirements.txt
├─ Dockerfile                # 多阶段构建（移动端打包 + Python 后端）
├─ docker-compose.yml        # 默认绑 127.0.0.1，带 no-new-privileges
├─ .env.example
├─ preset_styles.json        # 预置文风示例
├─ app/
│  ├─ __init__.py            # FastAPI 组装 + 安全头 + CORS 中间件
│  ├─ config.py              # 路径/超时常量
│  ├─ llm.py                 # OpenAI 兼容接口调用（流式/非流式）
│  ├─ models.py              # 所有 Pydantic 请求模型
│  ├─ prompts.py             # Bot1-4 系统提示词
│  ├─ styles.py              # 文风加载/合并
│  └─ routes/
│     ├─ bot1.py             # /api/bot1/chat, /api/models
│     ├─ bot2.py             # /api/bot2/write, /api/bot2/rewrite
│     ├─ bot3.py             # /api/bot3/review, /api/bot3-prompts
│     ├─ bot4.py             # /api/bot4/summarize, abstract, big-summarize, compress
│     ├─ configs.py          # /api/configs CRUD
│     └─ projects.py         # /api/projects CRUD + 导出 + 文风
└─ static/
   ├─ index.html             # 桌面端
   ├─ mobile.html / mobile.css
   └─ mobile-app/            # 移动端 SPA 源码（构建产物挂载为 /m/）
```

运行时 `data/` 下会产生：

```
data/
├─ <project_id>.json         # 每个项目一个 JSON
├─ _bot_configs.json         # 保存的 Bot 配置档案
├─ writing_styles.json       # 自定义文风
├─ bot3_prompts.json         # Bot3 自定义审核提示词
├─ backups/                  # 自动备份（每个项目最多保留 10 份）
└─ chapters/<project_id>/    # 导出的正式章节 txt
```

---

## 🔌 API 速查

所有接口走 JSON，流式接口走 SSE（`text/event-stream`）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/healthz` | 健康检查 |
| POST | `/api/models` | 列出某个 base_url 下可用模型 |
| POST | `/api/bot1/chat` | Bot1 流式对话 |
| POST | `/api/bot2/write` | Bot2 生成正文 |
| POST | `/api/bot2/rewrite` | Bot2 按审核建议重写 |
| POST | `/api/bot3/review` | Bot3 审核打分（非流式） |
| GET/POST | `/api/bot3-prompts` | Bot3 自定义审核提示词 |
| POST | `/api/bot4/summarize` | 小总结：缩略版原文 |
| POST | `/api/bot4/abstract` | 小总结：结构化摘要 |
| POST | `/api/bot4/big-summarize` | 大总结 |
| POST | `/api/compress-summary` | 记忆压缩 |
| GET/POST/DELETE | `/api/configs[/<id>]` | Bot 配置档案 |
| GET/POST/DELETE | `/api/projects[/<id>]` | 项目 CRUD |
| GET | `/api/projects/latest` | 最近更新的项目 |
| POST | `/api/projects/save-chapter` | 保存正式章节 |
| GET | `/api/projects/{id}/chapters` | 列出章节文件 |
| POST | `/api/projects/{id}/export` | 导出为纯文本 |
| GET/POST | `/api/styles[/<id>]` | 文风 CRUD |

FastAPI 自带的 OpenAPI 文档位于 `/docs`。

---

## 🔐 安全须知

NovelForge 的**威胁模型是单用户本地工具**，默认配置也是围绕"只在本机访问"来的：

- `run.py` 默认绑 `127.0.0.1`，`docker-compose.yml` 端口映射默认也是 `127.0.0.1`
- Docker 镜像以非 root 的 `app` 用户运行，并启用 `no-new-privileges`
- 响应统一带 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: same-origin`、`HSTS`
- 项目 ID / 项目名会先做白名单正则清理，再用 `resolve().relative_to()` 二次校验，防路径穿越
- 上游 API 报错不再把响应体原样回前端，只返回归纳后的错误类型；详细信息进日志

**对外开放时请至少做到**：

1. 反向代理终止 TLS（Nginx + Certbot）
2. 在反代层加一层访问控制（Basic Auth / OAuth2 Proxy / Cloudflare Access / IP 白名单）
3. `BIND_ADDR=0.0.0.0` 时确认前面有反代，不要直接把 8000 端口暴露到公网
4. 定期备份 `data/` 目录（已有自动备份，但不等于异地备份）

---

## 🛠 开发

```bash
pip install -r requirements.txt
DEV_RELOAD=true LOG_LEVEL=DEBUG python run.py
```

移动端 SPA：

```bash
cd static/mobile-app
npm ci
npm run dev        # 开发模式
npm run build      # 产物输出到 dist/，会被后端挂到 /m/
```

---

## 📄 License

项目根目录暂未包含许可证文件；如需二次分发请先与作者确认。
