# NovelForge

面向 AI 辅助长篇小说创作的自托管工作台。通过**四个协同的 Bot 角色**（对话构思 / 正文创作 / 审核打分 / 记忆总结）在 OpenAI 兼容接口上自动跑一个"写—审—改—记忆"循环。**v3 起支持多工作空间**：一台服务可以承载若干位朋友，各自独立项目、配置、API Key、章节备份，互不可见。

- 后端：FastAPI + httpx（流式 SSE）
- 前端：桌面静态 HTML + 移动端 Vue/Vite SPA（`static/mobile-app/`）
- 鉴权：每个工作空间独立密码（bcrypt + 签名 cookie），管理员入口靠 `ADMIN_TOKEN`
- 部署：单容器 Docker / 裸机 Python，Nginx 一段 location 永不再改
- 资源占用：单进程 ~150 MB，N 个工作空间共用同一进程

---

## ✨ 功能概览

| 模块 | 作用 |
| --- | --- |
| Bot1 对话 | 与作者讨论大纲、世界观、人物，流式对话产出大纲 |
| Bot2 创作 / 重写 | 按大纲和历史上下文产出正文，或根据审核建议重写 |
| Bot3 审核 | 对生成内容按 4 个维度打分（文学性 / 逻辑性 / 风格一致性 / 人味）并给出逐条修改建议 |
| Bot4 记忆 | 小总结（缩略+摘要）→ 大总结 → 记忆压缩，回灌进 Bot1/2 上下文 |
| 项目管理 | 多项目并存、自动备份（保留最近 10 个版本）、导出纯文本 |
| 文风库 | 预置文风（共享）+ 工作空间内自定义文风 |
| 多工作空间 | 每个朋友一个独立空间，URL 形如 `/w/<slug>/`，密码 + cookie 鉴权 |
| 移动端 | 同样的功能，独立 Vue SPA，UA 自动跳转 |

---

## 🚀 快速开始（5 分钟跑起来）

### 1. 准备环境变量

```bash
cp .env.example .env
# 至少必须设置以下两项：
#   ADMIN_TOKEN              进管理页用，建议 openssl rand -hex 32
#   WORKSPACE_COOKIE_SECRET  cookie 签名密钥，建议 openssl rand -hex 48
```

### 2. 启动（Docker）

```bash
docker compose up -d --build
```

> 如果提示 `docker: 'compose' is not a docker command`，说明装的是旧版 Docker，没有 Compose 插件。
> Debian/Ubuntu：`apt install docker-compose-plugin`；
> CentOS/RHEL：`dnf install docker-compose-plugin`；
> 旧版的 `docker-compose`（连字符）也能用，`server_deploy.sh` 已做自动兼容。

默认对外绑 `0.0.0.0:17000`。只想本机访问：`.env` 里改 `BIND_ADDR=127.0.0.1`。**公网部署请务必前置 Nginx + HTTPS**。

### 3. 创建第一个工作空间

浏览器打开：

```
http://你的服务器地址:17000/admin?token=<你刚才设置的 ADMIN_TOKEN>
```

填 slug（例如 `alice`）、显示名、初始密码，点"创建"。

### 4. 进入工作空间

把 `http://你的域名/w/alice/` 和密码发给本人即可。首次访问要求输入密码，输完会下发一个 30 天有效的 HttpOnly cookie，之后免登。

> 只有 1 个工作空间时，首页 `/` 会自动跳进去，不出现选择页。

---

## 🏗 架构

```
┌─ 入口路由 (FastAPI) ─────────────────────────────────────┐
│  /                       picker（≥2 个工作空间时）         │
│  /admin                  管理员页（ADMIN_TOKEN）           │
│  /w/{slug}/login         密码登录（5 失败/分钟会被锁 15 分钟） │
│  /w/{slug}/              桌面端工作台                       │
│  /m/w/{slug}/            移动端 SPA                         │
│  /api/w/{slug}/...       受保护 API（require_workspace 依赖）│
│  /api/admin/workspaces   admin token 保护的 CRUD           │
│  /api/workspaces         公开列表（仅 slug + 名字）         │
│  /m/static/*             移动端 SPA 静态资源               │
│  /static/*               桌面端静态资源                    │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌─ 数据落地 ──────────────────────────────────────────────┐
│  $NOVEL_DATA_DIR/                                       │
│  ├─ workspaces.json            注册表（含密码 bcrypt 哈希）│
│  ├─ .cookie_secret             cookie 签名密钥（自动生成）  │
│  └─ w/<slug>/                  每个工作空间一份独立目录    │
│     ├─ _bot_configs.json       Bot 配置档案               │
│     ├─ writing_styles.json     该空间自定义文风            │
│     ├─ bot3_prompts.json       Bot3 自定义审核提示词       │
│     ├─ <project_id>.json       项目                        │
│     ├─ chapters/<project_id>/  导出的章节 .txt             │
│     └─ backups/                自动备份（每项目最多 10 份） │
└──────────────────────────────────────────────────────────┘
```

---

## ⚙️ 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `BIND_ADDR` | `0.0.0.0` | docker-compose 端口绑定地址；只想本机访问改 `127.0.0.1` |
| `PORT` | `17000` | 对外端口 |
| `NOVEL_DATA_DIR` | `data/`（容器内 `/app/data`） | 所有持久化数据根目录 |
| `DEV_RELOAD` | `false` | 本地开发热重载；生产必须 `false` |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CORS_ORIGINS` | 空 | 逗号分隔的允许跨域来源；同源场景留空 |
| **`ADMIN_TOKEN`** | 空 | **必填**，访问 `/admin?token=...` 用，建议 ≥32 字符随机串 |
| **`WORKSPACE_COOKIE_SECRET`** | 自动生成到 `$NOVEL_DATA_DIR/.cookie_secret` | 用于工作空间登录 cookie 签名，多机部署或频繁重建数据卷时建议显式配置 |

---

## 🔐 安全模型

威胁模型：你 + 几位朋友，不对陌生人公开，但要防同一台 VPS 上其他用户/邻居乱点。

| 威胁 | 缓解 |
| --- | --- |
| URL 被截图泄露 | slug 不是凭据，必须再过密码（除非删了密码登录） |
| 暴力猜密码 | 每个 slug 单独限速：60 秒内错 5 次锁 15 分钟 |
| Cookie 被盗 | HttpOnly + SameSite=Lax + 签名（itsdangerous）+ 30 天失效；改密码会让旧 cookie 在下次校验时仍有效（cookie 只签 slug 不签密码版本），**真要踢人就用 admin 重建工作空间** |
| 跨工作空间串数据 | 后端 cookie 名 `ws_<slug>`，`require_workspace` 依赖严格匹配 slug；不同工作空间数据物理隔离在不同子目录 |
| 路径穿越 | 工作空间 slug 用 `^[a-z0-9][a-z0-9\-]{1,30}[a-z0-9]$` 白名单 + `resolve().relative_to(root)` 双重校验；项目 ID/文件名同样过滤 |
| 上游 API 报错泄露内部信息 | `app/llm.py` 把上游响应体转成统一类目消息，详情只进日志 |
| 容器逃逸 | Dockerfile 用非 root 用户，docker-compose 加 `no-new-privileges` |
| 静态文件嗅探 | 响应统一带 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: same-origin`、`HSTS` |

**仍然必须做**：

1. **反向代理终止 TLS**（Nginx + Certbot）。默认 `BIND_ADDR=0.0.0.0:17000` 方便单机起跑，但长期公网部署必须走反代 + HTTPS，不要让浏览器直连明文 17000 端口
2. `ADMIN_TOKEN` 不要泄露到任何客户端、日志、聊天工具
3. 多机部署时显式配 `WORKSPACE_COOKIE_SECRET`，不要让两台机器各自生成不一致的密钥
4. 备份 `$NOVEL_DATA_DIR/`（已有内置 backups 自动备份，但不等于异地备份）

---

## 📦 部署

### Docker（推荐）

```bash
docker compose up -d --build
docker compose logs -f
```

**Nginx 反代（配一次永不再改）**：

```nginx
server {
    listen 443 ssl;
    server_name novel.example.com;
    # ssl_certificate / ssl_certificate_key 由 certbot 写入

    location / {
        proxy_pass http://127.0.0.1:17000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_buffering off;            # SSE 流式必需
    }
}
```

新增/删除朋友只需访问 `/admin?token=...` 点按钮，**不用碰 Nginx 配置、不用 reload 服务**。

### 裸机 Python（Systemd）

```bash
# 系统级用户 + 安装
adduser --system --group --home /opt/novelforge novelforge
cd /opt/novelforge && git clone ... .
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# 移动端 SPA 构建（一次性）
cd static/mobile-app && npm ci && npm run build && cd -
```

`/etc/systemd/system/novelforge.service`：

```ini
[Unit]
Description=NovelForge
After=network.target

[Service]
Type=simple
User=novelforge
WorkingDirectory=/opt/novelforge
EnvironmentFile=/opt/novelforge/.env
ExecStart=/opt/novelforge/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now novelforge
```

资源占用：常驻 ~80–150 MB，无论几个工作空间都基本不增加（共享 Python 进程内存）。

---

## 🔄 从 v2（单工作空间）升级

仓库里有一次性迁移脚本：

```bash
python migrate_to_workspaces.py --slug default --name "我的空间"
# 会要求交互输入密码
```

行为：

- 把 `data/` 下旧的 `*.json`、`chapters/`、`backups/`、`writing_styles.json`、`_bot_configs.json`、`bot3_prompts.json` 全部移到 `data/w/default/`
- 在 `data/workspaces.json` 注册一条 `default` 记录（带 bcrypt 密码）
- 已经迁移过会自动跳过，重复运行只补密码

迁移完后访问 `http://your-host/w/default/`，密码就是刚才设的。

---

## 📂 项目结构

```
NovelForge/
├─ run.py                        启动入口（HOST/PORT/DEV_RELOAD）
├─ requirements.txt
├─ Dockerfile                    多阶段构建：Node 打 SPA + Python 运行时
├─ docker-compose.yml            默认对外绑 0.0.0.0:17000
├─ migrate_to_workspaces.py      v2 → v3 一次性迁移
├─ .env.example                  所有环境变量样例
├─ preset_styles.json            预置文风（所有工作空间共享）
├─ app/
│  ├─ __init__.py                FastAPI 组装：picker / login / admin / 受保护路由
│  ├─ workspace.py               注册表 + bcrypt + 签名 cookie + 限速 + require_workspace 依赖
│  ├─ config.py                  per-workspace 路径函数
│  ├─ llm.py                     OpenAI 兼容流式/非流式调用，错误归一化
│  ├─ models.py                  Pydantic 请求模型
│  ├─ prompts.py                 Bot1-4 系统提示词
│  ├─ styles.py                  文风加载（预置 + 用户自定义合并）
│  └─ routes/                    所有路由都挂在 /api/w/{workspace}/
│     ├─ bot1.py                 chat + 模型列表
│     ├─ bot2.py                 write / rewrite
│     ├─ bot3.py                 review + 自定义提示词 CRUD
│     ├─ bot4.py                 summarize / abstract / big-summarize / compress
│     ├─ configs.py              Bot 配置档案 CRUD
│     └─ projects.py             项目 CRUD + 章节 + 导出 + 文风
└─ static/
   ├─ picker.html                工作空间选择页
   ├─ login.html                 单空间登录页（XSS 安全：动态值走 json.dumps 注入）
   ├─ admin.html                 管理面板（创建 / 改密 / 改名 / 删除）
   ├─ index.html                 桌面端工作台
   ├─ js/
   │  ├─ 00-api.js               apiUrl + 401 自动跳登录
   │  └─ 01..10-*.js             原桌面端业务模块
   └─ mobile-app/                Vue/Vite SPA
      ├─ src/api/url.js          移动端 apiUrl 实现
      ├─ src/router/index.js     hash 路由 base 跟随 workspace
      ├─ src/views/Settings.vue  含"切换工作空间 / 退出登录"
      └─ vite.config.js          base = /m/static/
```

---

## 🔌 API 速查

所有受保护接口都在 `/api/w/{workspace}` 前缀下，必须带 `ws_<slug>` cookie。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/healthz` | 健康检查 |
| GET | `/api/workspaces` | 公开列表（slug + 名字） |
| GET/POST/DELETE | `/api/admin/workspaces[/{slug}[/password\|rename]]` | 管理员 CRUD（`?token=`） |
| POST | `/w/{slug}/login` | 表单登录 |
| GET | `/w/{slug}/logout` | 清 cookie |
| POST | `/api/w/{slug}/models` | 列上游可用模型 |
| POST | `/api/w/{slug}/bot1/chat` | Bot1 流式对话 |
| POST | `/api/w/{slug}/bot2/write` | Bot2 生成正文 |
| POST | `/api/w/{slug}/bot2/rewrite` | Bot2 按建议重写 |
| POST | `/api/w/{slug}/bot3/review` | Bot3 审核（非流式） |
| GET/POST | `/api/w/{slug}/bot3-prompts` | Bot3 自定义审核提示词 |
| POST | `/api/w/{slug}/bot4/summarize` | 小总结（缩略） |
| POST | `/api/w/{slug}/bot4/abstract` | 小总结（结构化摘要） |
| POST | `/api/w/{slug}/bot4/big-summarize` | 大总结 |
| POST | `/api/w/{slug}/compress-summary` | 记忆压缩 |
| GET/POST/DELETE | `/api/w/{slug}/configs[/{id}]` | Bot 配置档案 |
| GET/POST/DELETE | `/api/w/{slug}/projects[/{id}]` | 项目 CRUD |
| GET | `/api/w/{slug}/projects/latest` | 最近更新的项目 |
| POST | `/api/w/{slug}/projects/save-chapter` | 保存正式章节 |
| GET | `/api/w/{slug}/projects/{id}/chapters` | 列章节文件 |
| POST | `/api/w/{slug}/projects/{id}/export` | 导出纯文本 |
| GET/POST | `/api/w/{slug}/styles[/{id}]` | 文风 CRUD |

FastAPI 自带的 OpenAPI 文档在 `/docs`。

---

## 🛠 开发

```bash
pip install -r requirements.txt
DEV_RELOAD=true LOG_LEVEL=DEBUG ADMIN_TOKEN=dev WORKSPACE_COOKIE_SECRET=dev python run.py
```

移动端 SPA 热开发：

```bash
cd static/mobile-app
npm ci
npm run dev          # vite dev server，代理 /api → 127.0.0.1:17000
npm run build        # 产物 dist/，由后端挂到 /m/static/
```

dev server 访问 `http://localhost:5173/m/static/`（base 是 `/m/static/`），SPA 内会用 localStorage 里的 slug 拼 API 路径，注意先在主服务上至少创建一个工作空间并登录过一次。

---

## ❓ 常见问题

**Q：朋友丢了密码？**
进 `/admin?token=...`，找到该 slug 点"改密码"。

**Q：朋友的 cookie 被怀疑泄露，怎么强制下线？**
当前最稳妥的方法：删掉这个工作空间再用同名 slug 重建（数据会丢，先备份 `data/w/<slug>/`）。后续可能加"轮换签名密钥"功能。

**Q：能让某个工作空间不要密码吗？**
当前不支持，slug + 密码是基线。

**Q：忘了 ADMIN_TOKEN 怎么办？**
SSH 进服务器改 `.env` 重启即可。

**Q：能多机部署吗？**
可以，但要保证：①  `WORKSPACE_COOKIE_SECRET` 在所有节点一致；② 数据目录走共享存储（NFS / 块存储），且文件锁正常工作。

---

## 📄 License

仓库根目录暂未包含许可证；如需二次分发请先与作者确认。
