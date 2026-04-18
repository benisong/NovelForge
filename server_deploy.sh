#!/bin/bash

# Exit on error
set -e

echo "🚀 开始从 GitHub 拉取并部署 NovelForge..."

# 1. 拉取最新代码
echo "📥 正在从远程仓库拉取最新代码..."
git pull origin main

# 2. 停止旧容器
echo "🛑 停止旧的 Docker 容器..."
docker-compose down

# 3. 重新构建并启动 Docker 容器 (由于 Dockerfile 已经配置了多阶段构建，这里会自动构建前端)
echo "🐳 构建并启动 Docker 容器..."
docker-compose up -d --build

# 4. 清理无用的镜像，释放空间
echo "🧹 清理悬空镜像..."
docker image prune -f

echo "✅ 部署完成！"
echo "🌐 PC 端访问: http://您的服务器IP:17000"
echo "📱 移动端访问: http://您的服务器IP:17000/m/w/<slug>/"
echo "📝 查看日志: docker-compose logs -f"
