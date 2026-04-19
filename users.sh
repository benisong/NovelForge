#!/usr/bin/env bash

set -euo pipefail

BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-novelforge-multi:latest}"
CONTAINER_PREFIX="${CONTAINER_PREFIX:-novelforge-user}"
RUNTIME_ROOT="${BASE_DIR}/data/users"
CONTAINER_PORT=8000

mkdir -p "${RUNTIME_ROOT}"

usage() {
  cat <<'EOF'
NovelForge 多实例管理

用法:
  ./users.sh add <name> <port>           新增或更新一个独立实例
  ./users.sh apply <name:port> [...]     批量新增或更新多个实例
  ./users.sh list                        列出已登记的实例
  ./users.sh logs <name>                 查看实例日志
  ./users.sh start <name>                启动实例
  ./users.sh stop <name>                 停止实例
  ./users.sh restart <name>              重启实例
  ./users.sh remove <name> [--delete-data]
                                         删除实例；默认保留数据
  ./users.sh rebuild <name>              重建镜像并重建指定实例
  ./users.sh rebuild --all               重建镜像并重建全部实例
  ./users.sh help                        显示帮助

示例:
  ./users.sh add friend 17001
  ./users.sh apply alice:17001 bob:17002
  ./users.sh logs friend
  ./users.sh rebuild --all

说明:
  - 每个实例都会有独立的数据目录: data/users/<name>/
  - 每个实例对应一个独立容器和独立端口
  - PC 端访问: http://服务器IP:<port>
  - 移动端访问: http://服务器IP:<port>/m/
EOF
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"
}

ensure_docker() {
  require_cmd docker
  docker info >/dev/null 2>&1 || fail "Docker 未启动或当前用户无权限访问 Docker"
}

validate_name() {
  local name="$1"
  [[ "${name}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{1,31}$ ]] \
    || fail "实例名只能包含字母、数字、下划线、短横线，且长度为 2-32"
}

validate_port() {
  local port="$1"
  [[ "${port}" =~ ^[0-9]+$ ]] || fail "端口必须是数字"
  (( port >= 1024 && port <= 65535 )) || fail "端口必须在 1024-65535 之间"
}

container_name() {
  local name="$1"
  printf '%s-%s' "${CONTAINER_PREFIX}" "${name}"
}

data_dir() {
  local name="$1"
  printf '%s/%s' "${RUNTIME_ROOT}" "${name}"
}

meta_file() {
  local name="$1"
  printf '%s/.instance.env' "$(data_dir "${name}")"
}

instance_exists() {
  local name="$1"
  docker container inspect "$(container_name "${name}")" >/dev/null 2>&1
}

save_meta() {
  local name="$1"
  local port="$2"
  local dir
  dir="$(data_dir "${name}")"
  mkdir -p "${dir}"
  cat >"$(meta_file "${name}")" <<EOF
INSTANCE_NAME=${name}
INSTANCE_PORT=${port}
INSTANCE_CONTAINER=$(container_name "${name}")
EOF
}

load_meta() {
  local name="$1"
  local file
  file="$(meta_file "${name}")"
  [[ -f "${file}" ]] || fail "未找到实例 ${name} 的配置文件: ${file}"
  # shellcheck disable=SC1090
  source "${file}"
}

known_instances() {
  local dir
  for dir in "${RUNTIME_ROOT}"/*; do
    [[ -d "${dir}" && -f "${dir}/.instance.env" ]] || continue
    basename "${dir}"
  done
}

ensure_image() {
  ensure_docker
  if ! docker image inspect "${IMAGE_NAME}" >/dev/null 2>&1; then
    echo "Building image ${IMAGE_NAME} ..."
    docker build -t "${IMAGE_NAME}" "${BASE_DIR}"
  fi
}

build_image() {
  ensure_docker
  echo "Building image ${IMAGE_NAME} ..."
  docker build -t "${IMAGE_NAME}" "${BASE_DIR}"
}

run_instance() {
  local name="$1"
  local port="$2"
  local dir
  local container

  validate_name "${name}"
  validate_port "${port}"
  ensure_image

  dir="$(data_dir "${name}")"
  container="$(container_name "${name}")"
  mkdir -p "${dir}"

  if instance_exists "${name}"; then
    echo "Replacing existing container ${container} ..."
    docker rm -f "${container}" >/dev/null
  fi

  echo "Starting ${name} on port ${port} ..."
  docker run -d \
    --name "${container}" \
    --restart unless-stopped \
    -p "${port}:${CONTAINER_PORT}" \
    -e NOVEL_DATA_DIR=/app/data \
    -v "${dir}:/app/data" \
    "${IMAGE_NAME}" >/dev/null

  save_meta "${name}" "${port}"

  cat <<EOF
OK: 实例 ${name} 已启动
  容器名: ${container}
  数据目录: ${dir}
  PC 端: http://服务器IP:${port}
  移动端: http://服务器IP:${port}/m/
EOF
}

add_instance() {
  [[ $# -eq 2 ]] || fail "add 需要两个参数: <name> <port>"
  run_instance "$1" "$2"
}

apply_instances() {
  [[ $# -ge 1 ]] || fail "apply 至少需要一个 name:port 参数"
  local pair name port
  for pair in "$@"; do
    [[ "${pair}" == *:* ]] || fail "参数格式错误: ${pair}，应为 name:port"
    name="${pair%%:*}"
    port="${pair##*:}"
    run_instance "${name}" "${port}"
  done
}

list_instances() {
  local found=0
  local name
  local status
  local ports
  local container

  printf "%-18s %-30s %-16s %s\n" "NAME" "CONTAINER" "STATUS" "PORTS"
  for name in $(known_instances); do
    found=1
    container="$(container_name "${name}")"
    if docker container inspect "${container}" >/dev/null 2>&1; then
      status="$(docker inspect -f '{{.State.Status}}' "${container}")"
      ports="$(docker port "${container}" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
    else
      status="missing"
      ports="-"
    fi
    printf "%-18s %-30s %-16s %s\n" "${name}" "${container}" "${status}" "${ports}"
  done

  (( found == 1 )) || echo "No managed instances yet."
}

logs_instance() {
  [[ $# -eq 1 ]] || fail "logs 需要一个参数: <name>"
  load_meta "$1"
  docker logs -f "${INSTANCE_CONTAINER}"
}

start_instance() {
  [[ $# -eq 1 ]] || fail "start 需要一个参数: <name>"
  load_meta "$1"
  docker start "${INSTANCE_CONTAINER}" >/dev/null
  echo "Started ${INSTANCE_NAME}"
}

stop_instance() {
  [[ $# -eq 1 ]] || fail "stop 需要一个参数: <name>"
  load_meta "$1"
  docker stop "${INSTANCE_CONTAINER}" >/dev/null
  echo "Stopped ${INSTANCE_NAME}"
}

restart_instance() {
  [[ $# -eq 1 ]] || fail "restart 需要一个参数: <name>"
  load_meta "$1"
  docker restart "${INSTANCE_CONTAINER}" >/dev/null
  echo "Restarted ${INSTANCE_NAME}"
}

remove_instance() {
  [[ $# -ge 1 && $# -le 2 ]] || fail "remove 需要: <name> [--delete-data]"
  local name="$1"
  local delete_data="${2:-}"
  local dir
  load_meta "${name}"

  if docker container inspect "${INSTANCE_CONTAINER}" >/dev/null 2>&1; then
    docker rm -f "${INSTANCE_CONTAINER}" >/dev/null
  fi

  rm -f "$(meta_file "${name}")"
  dir="$(data_dir "${name}")"

  if [[ "${delete_data}" == "--delete-data" ]]; then
    rm -rf "${dir}"
    echo "Removed ${name} and deleted ${dir}"
  else
    echo "Removed ${name}; data kept at ${dir}"
  fi
}

rebuild_one() {
  local name="$1"
  load_meta "${name}"
  run_instance "${INSTANCE_NAME}" "${INSTANCE_PORT}"
}

rebuild_instances() {
  [[ $# -eq 1 ]] || fail "rebuild 需要一个参数: <name> 或 --all"
  build_image

  if [[ "$1" == "--all" ]]; then
    local names=()
    local name
    while IFS= read -r name; do
      [[ -n "${name}" ]] && names+=("${name}")
    done < <(known_instances)

    (( ${#names[@]} > 0 )) || fail "当前没有已登记的实例可重建"

    for name in "${names[@]}"; do
      rebuild_one "${name}"
    done
    return
  fi

  rebuild_one "$1"
}

main() {
  local cmd="${1:-help}"
  shift || true

  case "${cmd}" in
    add|up)
      add_instance "$@"
      ;;
    apply)
      apply_instances "$@"
      ;;
    list|ls)
      ensure_docker
      list_instances
      ;;
    logs)
      ensure_docker
      logs_instance "$@"
      ;;
    start)
      ensure_docker
      start_instance "$@"
      ;;
    stop)
      ensure_docker
      stop_instance "$@"
      ;;
    restart)
      ensure_docker
      restart_instance "$@"
      ;;
    remove|rm)
      ensure_docker
      remove_instance "$@"
      ;;
    rebuild)
      rebuild_instances "$@"
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      fail "未知命令: ${cmd}。可用命令见 ./users.sh help"
      ;;
  esac
}

main "$@"
