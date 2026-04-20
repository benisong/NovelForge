#!/bin/bash

# Exit on error
set -e

echo "🚀 开始从 GitHub 拉取并部署 NovelForge..."

# ---- 自动探测 Docker Compose 命令 ----
# 新版 Docker（≥20.10）用 `docker compose`（空格，插件形式）；
# 旧版用 `docker-compose`（连字符，独立二进制）。
# 优先新版，否则回退旧版，都没有就提示安装。
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "❌ 没有找到 Docker Compose。请选择以下任一方式安装："
  echo "   Debian/Ubuntu:  apt install docker-compose-plugin"
  echo "   CentOS/RHEL:    dnf install docker-compose-plugin"
  echo "   或参考 https://docs.docker.com/compose/install/"
  exit 1
fi
echo "🐳 使用: $DC"

# 1. 拉取最新代码
echo "📥 正在从远程仓库拉取最新代码..."
git pull origin main

# 2. 停止旧容器
echo "🛑 停止旧的 Docker 容器..."
$DC down

# 3. 重新构建并启动 Docker 容器 (Dockerfile 多阶段构建会自动构建前端)
echo "🐳 构建并启动 Docker 容器..."
$DC up -d --build

# 4. 清理无用的镜像，释放空间
echo "🧹 清理悬空镜像..."
docker image prune -f

echo "✅ 部署完成！"
echo "🌐 PC 端访问: http://您的服务器IP:17000"
echo "📱 移动端访问: http://您的服务器IP:17000/m/w/<slug>/"
echo "📝 查看日志: $DC logs -f"
