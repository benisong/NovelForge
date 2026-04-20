#!/bin/bash
# NovelForge 自动部署脚本
# 自动检测并安装缺失依赖（git / docker / docker compose plugin），
# 启动 Docker 服务，拉最新代码，重建容器。

set -e

echo "🚀 开始部署 NovelForge..."

# ---- 辅助：自动 sudo ----
# 非 root 时前置 sudo；root 时直接执行。
run() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

# ---- 发行版识别 ----
DISTRO="unknown"
if [ -f /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  DISTRO="$ID"
fi

# ---- 按发行版走包管理器 ----
pkg_install() {
  case "$DISTRO" in
    ubuntu|debian)
      run apt-get update -qq
      DEBIAN_FRONTEND=noninteractive run apt-get install -y "$@"
      ;;
    fedora|centos|rhel|rocky|almalinux)
      if command -v dnf >/dev/null 2>&1; then
        run dnf install -y "$@"
      else
        run yum install -y "$@"
      fi
      ;;
    arch|manjaro)
      run pacman -Sy --noconfirm "$@"
      ;;
    alpine)
      run apk add --no-cache "$@"
      ;;
    *)
      echo "❌ 未识别的发行版 \"$DISTRO\"，请手动安装: $*"
      return 1
      ;;
  esac
}

# ---- 依赖探测（先全扫一遍，再一次性装）----
MISSING=()

if ! command -v git >/dev/null 2>&1; then
  MISSING+=("git")
fi

if ! command -v docker >/dev/null 2>&1; then
  case "$DISTRO" in
    ubuntu|debian) MISSING+=("docker.io") ;;
    alpine)        MISSING+=("docker") ;;
    *)             MISSING+=("docker") ;;
  esac
fi

# Compose 探测：优先 docker 插件（docker compose），退到旧版二进制（docker-compose）
DC=""
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  case "$DISTRO" in
    ubuntu|debian|fedora|centos|rhel|rocky|almalinux)
      MISSING+=("docker-compose-plugin")
      ;;
    arch|manjaro|alpine)
      MISSING+=("docker-compose")
      ;;
    *)
      MISSING+=("docker-compose-plugin")
      ;;
  esac
fi

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "🔧 检测到缺失依赖: ${MISSING[*]}"
  echo "   (发行版: $DISTRO)"
  echo "   3 秒后开始自动安装，Ctrl+C 可中止..."
  sleep 3
  pkg_install "${MISSING[@]}"

  # 装完再探一次 compose
  if [ -z "$DC" ]; then
    if docker compose version >/dev/null 2>&1; then
      DC="docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
      DC="docker-compose"
    else
      echo "❌ 安装后仍找不到 docker compose，请手动检查"
      exit 1
    fi
  fi
fi

# ---- 启动 Docker 服务 ----
if ! run docker info >/dev/null 2>&1; then
  echo "🔌 Docker 服务未启动，尝试启动..."
  if command -v systemctl >/dev/null 2>&1; then
    run systemctl enable --now docker
  else
    run service docker start
  fi
  # 给 daemon 一秒起来
  sleep 2
fi

# ---- 权限处理：当前用户是否直接能跑 docker ----
# 如果在 docker 组里或 root，无需 sudo；否则 docker 命令都要 sudo。
if docker info >/dev/null 2>&1; then
  DC_CMD="$DC"
  DOCKER_CMD="docker"
else
  DC_CMD="sudo $DC"
  DOCKER_CMD="sudo docker"
fi

echo "🐳 使用: $DC_CMD"

# ---- 确保 .env 存在；WORKSPACE_COOKIE_SECRET 必须是随机值 ----
# ADMIN_TOKEN 默认是 "admin"（简单直接，后续想改直接 vim .env）。
# WORKSPACE_COOKIE_SECRET 必须随机，这个是 cookie 签名密钥，不能是固定默认。
gen_random() {
  local length="$1"
  local charset="${2:-A-Za-z0-9}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 $((length * 2)) 2>/dev/null | tr -dc "$charset" | head -c "$length"
  else
    tr -dc "$charset" < /dev/urandom | head -c "$length"
  fi
}

set_env_var() {
  local key="$1"
  local value="$2"
  local file=".env"
  if grep -qE "^${key}=" "$file"; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$file" && rm -f "${file}.bak"
  else
    echo "${key}=${value}" >> "$file"
  fi
}

ensure_env() {
  if [ ! -f .env ]; then
    if [ -f .env.example ]; then
      cp .env.example .env
      echo "📄 已从 .env.example 创建 .env（ADMIN_TOKEN 默认 admin）"
    else
      touch .env
    fi
  fi

  # WORKSPACE_COOKIE_SECRET：没设 或 空 → 自动生成 64 位 hex（必须随机，否则 cookie 可伪造）
  if ! grep -qE '^WORKSPACE_COOKIE_SECRET=..+' .env; then
    local secret
    secret="$(gen_random 64 'a-f0-9')"
    set_env_var WORKSPACE_COOKIE_SECRET "$secret"
    echo "🔐 自动生成 WORKSPACE_COOKIE_SECRET（已写入 .env）"
  fi

  chmod 600 .env 2>/dev/null || true
}

ensure_env

# ---- 拉代码（非 git 目录时跳过，不中断）----
if [ -d .git ]; then
  echo "📥 拉取最新代码..."
  git pull --ff-only origin "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)" \
    || echo "⚠️  git pull 失败，继续使用当前代码"
else
  echo "ℹ️  当前目录不是 git 仓库，跳过 git pull"
fi

# ---- 部署 ----
echo "🛑 停止旧容器..."
$DC_CMD down 2>/dev/null || true

echo "🐳 构建并启动..."
$DC_CMD up -d --build

echo "🧹 清理悬空镜像..."
$DOCKER_CMD image prune -f

echo ""
echo "✅ 部署完成"
echo "🌐 PC 端:    http://<服务器IP>:17000"
echo "📱 移动端:   http://<服务器IP>:17000/m/w/<slug>/"
echo "📝 查看日志: $DC_CMD logs -f"
echo ""
echo "💡 首次使用：访问 http://<服务器IP>:17000/admin"
echo "   默认账户/密码：admin / admin"
echo "   登录后到管理页点"修改密码"改成自己的"
