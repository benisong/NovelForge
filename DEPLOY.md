# NovelForge 部署指南

## 方式一：直接运行（开发/本地）

```bash
cd NovelForge
cp .env.example .env    # 至少填 ADMIN_TOKEN 和 WORKSPACE_COOKIE_SECRET
pip install -r requirements.txt
python run.py
# 访问 http://localhost:17000
```

> 详细说明见根目录的 `README.md`。

## 方式二：Docker 部署（推荐用于VPS）

```bash
# 1. 上传项目到VPS
scp -r novel-assistant/ user@your-vps:/opt/novel-assistant/

# 2. SSH到VPS
ssh user@your-vps
cd /opt/novel-assistant

# 3. 构建并启动
docker compose up -d --build

# 4. 查看日志
docker compose logs -f

# 5. 停止
docker compose down
```

数据持久化在 Docker Volume `novel-data` 中，容器重建不会丢失数据。

## 方式三：Nginx 反向代理（生产环境 + HTTPS）

安装 Nginx 和 Certbot：
```bash
apt install nginx certbot python3-certbot-nginx
```

Nginx 配置（`/etc/nginx/sites-available/novel`）：
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:17000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

启用并申请SSL：
```bash
ln -s /etc/nginx/sites-available/novel /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d your-domain.com
```

## 方式四：Systemd 服务（无Docker的VPS）

创建 `/etc/systemd/system/novel-assistant.service`：
```ini
[Unit]
Description=NovelForge Novel Assistant
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/novel-assistant
Environment=NOVEL_DATA_DIR=/opt/novel-assistant/data
ExecStart=/usr/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 17000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now novel-assistant
systemctl status novel-assistant
```

## 数据说明

- 项目数据保存在 `data/` 目录下，每个项目一个 `.json` 文件
- 前端配置（API密钥等）保存在浏览器 localStorage，不会上传到服务器
- 建议定期备份 `data/` 目录
