#!/usr/bin/env bash
# 安装 systemd 单元（队列/并发/名字从 /etc/conf.d/celery_spapi 读取）
#
#   sudo ./deploy/install-systemd.sh --user Admin --app-dir ~/src/em-workers

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEPLOY_USER=""
APP_DIR=""
ENV_FILE="/etc/conf.d/celery_spapi"
DRY_RUN=false

usage() {
  cat <<'EOF'
安装 amazon-spapi systemd 单元（参数来自 EnvironmentFile）

  sudo ./deploy/install-systemd.sh [选项]

选项:
  --user NAME       运行用户（必填）
  --app-dir PATH    项目目录（必填）
  --env-file PATH   环境文件（默认 /etc/conf.d/celery_spapi）
  --dry-run         只打印
  -h, --help
EOF
}

log() { printf '[install-systemd] %s\n' "$*"; }
die() { printf '[install-systemd] ERROR: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) DEPLOY_USER="$2"; shift 2 ;;
    --app-dir) APP_DIR="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知参数: $1" ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || die "请用 sudo 运行"
[[ -n "${DEPLOY_USER}" ]] || die "缺少 --user"
[[ -n "${APP_DIR}" ]] || die "缺少 --app-dir"
[[ -f "${ENV_FILE}" ]] || die "缺少环境文件: ${ENV_FILE}（先 cp deploy/conf.d/celery_spapi.example）"

DEPLOY_HOME="$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)"
UV_BIN="${DEPLOY_HOME}/.local/bin/uv"
[[ -x "${UV_BIN}" ]] || UV_BIN="$(command -v uv || true)"
[[ -n "${UV_BIN}" ]] || die "找不到 uv"

log "验证 ${ENV_FILE} …"
run_as_user() {
  sudo -u "${DEPLOY_USER}" -H bash -lc "$*"
}
run_as_user "cd '${APP_DIR}' && '${UV_BIN}' run python -m amazon_spapi.config.workers \
  --env-file '${ENV_FILE}' --systemd-plan" >/dev/null \
  || die "环境文件缺少 OFFERS_* / CATALOG_* 配置"

install_unit() {
  local src="$1"
  local name
  name="$(basename "${src}")"
  local dest="/etc/systemd/system/${name}"

  log "安装 ${dest}"
  if [[ "${DRY_RUN}" == true ]]; then
    return 0
  fi

  sed \
    -e "s|^User=.*|User=${DEPLOY_USER}|" \
    -e "s|^Group=.*|Group=${DEPLOY_USER}|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" \
    -e "s|^EnvironmentFile=.*|EnvironmentFile=${ENV_FILE}|" \
    -e "s|/home/Admin/.local/bin/uv|${UV_BIN}|g" \
    -e "s|file:///home/Admin/src/em-workers|file://${APP_DIR}|g" \
    "${src}" >"${dest}"
  chmod 644 "${dest}"
}

install_unit "${SCRIPT_DIR}/systemd/amazon-spapi-offers.service"
install_unit "${SCRIPT_DIR}/systemd/amazon-spapi-catalog.service"

if [[ "${DRY_RUN}" != true ]]; then
  systemctl daemon-reload
fi

log "完成。编辑 ${ENV_FILE} 后执行: systemctl restart amazon-spapi-offers amazon-spapi-catalog"
