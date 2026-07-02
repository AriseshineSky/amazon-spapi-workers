#!/usr/bin/env bash
# Ubuntu 一键部署：安装依赖、同步代码、配置 systemd
#
# 用法（在项目根目录或任意位置）：
#   cp deploy/deploy.env.example deploy/deploy.env
#   vim deploy/deploy.env          # 填 BROKER_URL、ENABLED_WORKERS 等
#   sudo ./deploy/install-ubuntu.sh
#
# 或指定配置文件：
#   sudo ./deploy/install-ubuntu.sh --env /path/to/deploy.env
#
# 仅安装依赖、不启服务：
#   sudo ./deploy/install-ubuntu.sh --no-start

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${SCRIPT_DIR}/deploy.env"
DO_START=true
DRY_RUN=false

usage() {
  cat <<'EOF'
Ubuntu 一键部署 amazon-spapi-workers

  sudo ./deploy/install-ubuntu.sh [选项]

选项:
  --env FILE       使用指定 deploy.env（默认 deploy/deploy.env）
  --no-start       只安装，不 systemctl enable/start
  --dry-run        打印将要执行的操作，不实际修改
  -h, --help       显示帮助

部署前请复制并编辑配置：
  cp deploy/deploy.env.example deploy/deploy.env
EOF
}

log() { printf '[deploy] %s\n' "$*"; }
warn() { printf '[deploy] WARN: %s\n' "$*" >&2; }
die() { printf '[deploy] ERROR: %s\n' "$*" >&2; exit 1; }

run() {
  if [[ "${DRY_RUN}" == true ]]; then
    log "[dry-run] $*"
  else
    log "+ $*"
    "$@"
  fi
}

run_as_user() {
  local user="$1"
  shift
  if [[ "${DRY_RUN}" == true ]]; then
    log "[dry-run] (as ${user}) $*"
  else
    log "+ (as ${user}) $*"
    sudo -u "${user}" -H bash -lc "$*"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_FILE="$2"
      shift 2
      ;;
    --no-start)
      DO_START=false
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数: $1（用 --help 查看）"
      ;;
  esac
done

# ── 权限与系统 ──────────────────────────────────────────────
if [[ "${EUID}" -ne 0 ]]; then
  die "请用 sudo 运行: sudo ./deploy/install-ubuntu.sh"
fi

if [[ -f /etc/os-release ]]; then
  # shellcheck source=/dev/null
  source /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) log "系统: ${PRETTY_NAME:-unknown}" ;;
    *) warn "未在 Ubuntu/Debian 上测试，当前: ${PRETTY_NAME:-unknown}" ;;
  esac
else
  warn "无法识别系统版本，继续执行…"
fi

# ── 加载配置 ────────────────────────────────────────────────
[[ -f "${ENV_FILE}" ]] || die "缺少配置文件: ${ENV_FILE}\n  请先: cp deploy/deploy.env.example deploy/deploy.env"

# shellcheck source=/dev/null
source "${ENV_FILE}"

DEPLOY_USER="${DEPLOY_USER:-${SUDO_USER:-}}"
[[ -n "${DEPLOY_USER}" ]] || die "请在 deploy.env 里设置 DEPLOY_USER"

if ! id "${DEPLOY_USER}" &>/dev/null; then
  die "用户不存在: ${DEPLOY_USER}"
fi

DEPLOY_HOME="$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)"
APP_DIR="${APP_DIR:-${DEPLOY_HOME}/src/em-workers}"
BROKER_URL="${BROKER_URL:-}"
ENABLED_WORKERS="${ENABLED_WORKERS:-offers-us}"
OFFERS_CONCURRENCY="${OFFERS_CONCURRENCY:-2}"
CATALOG_CONCURRENCY="${CATALOG_CONCURRENCY:-1}"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-info}"
START_SERVICES="${START_SERVICES:-true}"

[[ -n "${BROKER_URL}" ]] || die "请在 deploy.env 里设置 BROKER_URL"

if [[ "${DO_START}" == false ]]; then
  START_SERVICES=false
fi

log "部署用户: ${DEPLOY_USER}"
log "项目目录: ${APP_DIR}"
log "启用服务: ${ENABLED_WORKERS}"

# ── 系统包 ──────────────────────────────────────────────────
export DEBIAN_FRONTEND=noninteractive
run apt-get update -qq
run apt-get install -y -qq \
  ca-certificates \
  curl \
  git \
  sudo \
  systemd

# ── 同步代码到 ~/src/em-workers ─────────────────────────────
run mkdir -p "$(dirname "${APP_DIR}")"
run chown "${DEPLOY_USER}:${DEPLOY_USER}" "$(dirname "${APP_DIR}")"

if [[ "${REPO_ROOT}" != "${APP_DIR}" ]]; then
  if [[ -d "${APP_DIR}/.git" ]]; then
    log "更新已有仓库: ${APP_DIR}"
    run_as_user "${DEPLOY_USER}" "cd '${APP_DIR}' && git pull --ff-only"
  elif [[ ! -d "${APP_DIR}" ]] || [[ -z "$(ls -A "${APP_DIR}" 2>/dev/null || true)" ]]; then
    if [[ -n "${GIT_REPO:-}" ]]; then
      log "克隆仓库到 ${APP_DIR}"
      run_as_user "${DEPLOY_USER}" "mkdir -p '$(dirname "${APP_DIR}")' && git clone '${GIT_REPO}' '${APP_DIR}'"
    else
      log "复制当前代码到 ${APP_DIR}"
      if [[ "${DRY_RUN}" == true ]]; then
        log "[dry-run] rsync ${REPO_ROOT}/ -> ${APP_DIR}/"
      else
        run mkdir -p "${APP_DIR}"
        rsync -a --delete \
          --exclude '.venv' \
          --exclude '__pycache__' \
          --exclude '.git' \
          "${REPO_ROOT}/" "${APP_DIR}/"
        run chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"
      fi
    fi
  else
    die "${APP_DIR} 已存在且不是 git 仓库，请手动处理或改 APP_DIR"
  fi
else
  log "使用当前目录作为项目路径: ${APP_DIR}"
fi

if [[ "${DRY_RUN}" != true ]] && [[ -d "${APP_DIR}" ]]; then
  run chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"
fi

# ── 安装 uv ─────────────────────────────────────────────────
UV_BIN="${DEPLOY_HOME}/.local/bin/uv"
if [[ "${DRY_RUN}" == true ]] || [[ ! -x "${UV_BIN}" ]]; then
  log "安装 uv（用户 ${DEPLOY_USER}）"
  if [[ "${DRY_RUN}" != true ]]; then
    run_as_user "${DEPLOY_USER}" 'curl -LsSf https://astral.sh/uv/install.sh | sh'
  fi
fi

# ── Python 依赖 ─────────────────────────────────────────────
run_as_user "${DEPLOY_USER}" "cd '${APP_DIR}' && '${UV_BIN}' sync --frozen"

# ── 业务配置目录 ────────────────────────────────────────────
CONFIG_DIR="${DEPLOY_HOME}/.amazon_spapi"
CONFIG_INI="${CONFIG_DIR}/config.ini"
ENV_SYSTEM="/etc/amazon-spapi/amazon-spapi.env"

if [[ "${DRY_RUN}" != true ]]; then
  run_as_user "${DEPLOY_USER}" "mkdir -p '${CONFIG_DIR}/logs'"
fi

if [[ ! -f "${CONFIG_INI}" ]]; then
  log "创建默认 config.ini（请稍后填写 Amazon / ES 凭证）"
  if [[ "${DRY_RUN}" != true ]]; then
    run_as_user "${DEPLOY_USER}" \
      "cp '${APP_DIR}/config.ini.sample' '${CONFIG_INI}' && chmod 600 '${CONFIG_INI}'"
    warn "请编辑: ${CONFIG_INI}"
  fi
else
  log "保留已有 config.ini: ${CONFIG_INI}"
fi

# ── systemd 环境文件 ────────────────────────────────────────
run mkdir -p /etc/amazon-spapi

if [[ -f "${ENV_SYSTEM}" ]]; then
  log "保留已有 ${ENV_SYSTEM}（如需改 BROKER_URL 请手动编辑）"
else
  log "写入 ${ENV_SYSTEM}"
  if [[ "${DRY_RUN}" != true ]]; then
    cat >"${ENV_SYSTEM}" <<EOF
# Generated by deploy/install-ubuntu.sh
BROKER_URL=${BROKER_URL}
AMAZON_SPAPI_CONFIG_PATH=${CONFIG_INI}
EOF
    chmod 640 "${ENV_SYSTEM}"
    chown root:"${DEPLOY_USER}" "${ENV_SYSTEM}" || chmod 600 "${ENV_SYSTEM}"
  fi
fi

# ── 生成 systemd 单元 ─────────────────────────────────────────
queue_for_worker() {
  local token="$1"
  local kind="${token%%-*}"
  local market="${token#*-}"
  market="${market^^}"

  case "${kind}" in
    offers)  echo "SpapiItemOffersUpdate_${market}" ;;
    catalog) echo "SpapiCatalogItemsUpdate_${market}" ;;
    *) die "无法识别的服务: ${token}（应为 offers-us / catalog-us 等形式）" ;;
  esac
}

service_name_for_worker() {
  local token="$1"
  echo "amazon-spapi-${token}"
}

concurrency_for_worker() {
  local token="$1"
  local kind="${token%%-*}"
  case "${kind}" in
    offers)  echo "${OFFERS_CONCURRENCY}" ;;
    catalog) echo "${CATALOG_CONCURRENCY}" ;;
    *) echo "1" ;;
  esac
}

describe_worker() {
  local token="$1"
  local kind="${token%%-*}"
  local market="${token#*-}"
  market="${market^^}"
  case "${kind}" in
    offers)  echo "Amazon SP-API — ${market} 站报价刷新" ;;
    catalog) echo "Amazon SP-API — ${market} 站目录同步" ;;
  esac
}

INSTALLED_UNITS=()

for worker in ${ENABLED_WORKERS}; do
  unit="$(service_name_for_worker "${worker}")"
  queue="$(queue_for_worker "${worker}")"
  concurrency="$(concurrency_for_worker "${worker}")"
  description="$(describe_worker "${worker}")"
  unit_path="/etc/systemd/system/${unit}.service"

  log "生成 systemd 单元: ${unit}  →  队列 ${queue}"

  if [[ "${DRY_RUN}" == true ]]; then
    log "[dry-run] write ${unit_path}"
  else
    cat >"${unit_path}" <<EOF
[Unit]
Description=${description}
Documentation=file://${APP_DIR}/docs/生产部署.md
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${DEPLOY_USER}
Group=${DEPLOY_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_SYSTEM}

ExecStart=${UV_BIN} run celery -A amazon_spapi.worker worker \\
  -l ${CELERY_LOG_LEVEL} \\
  -c ${concurrency} \\
  -Q ${queue}

Restart=always
RestartSec=15
KillSignal=SIGTERM
TimeoutStopSec=120

[Install]
WantedBy=multi-user.target
EOF
  fi

  INSTALLED_UNITS+=("${unit}")
done

# ── 验证导入 ────────────────────────────────────────────────
run_as_user "${DEPLOY_USER}" \
  "cd '${APP_DIR}' && BROKER_URL='${BROKER_URL}' '${UV_BIN}' run python -c \"from amazon_spapi.worker import app; print('import ok')\""

# ── 启停服务 ────────────────────────────────────────────────
if [[ "${DRY_RUN}" != true ]]; then
  run systemctl daemon-reload
fi

if [[ "${START_SERVICES}" == true ]]; then
  for unit in "${INSTALLED_UNITS[@]}"; do
    run systemctl enable "${unit}.service"
    run systemctl restart "${unit}.service"
  done
else
  log "跳过 systemctl start（--no-start 或 START_SERVICES=false）"
  for unit in "${INSTALLED_UNITS[@]}"; do
    log "  手动启动: sudo systemctl enable --now ${unit}"
  done
fi

# ── 完成 ────────────────────────────────────────────────────
cat <<EOF

========================================
部署完成
========================================
  项目目录:     ${APP_DIR}
  业务配置:     ${CONFIG_INI}
  运行环境:     ${ENV_SYSTEM}
  部署用户:     ${DEPLOY_USER}

已配置的后台服务:
EOF

for unit in "${INSTALLED_UNITS[@]}"; do
  echo "  - ${unit}.service"
done

cat <<EOF

常用命令:
  sudo systemctl status amazon-spapi-offers-us
  sudo journalctl -u amazon-spapi-offers-us -f

若尚未填写 config.ini，请先编辑后再重启:
  vim ${CONFIG_INI}
  sudo systemctl restart amazon-spapi-offers-us

提交试跑任务（在调度机或本机）:
  export BROKER_URL='...'
  cd ${APP_DIR} && uv run schedule-stale-offers -m us -q 1 -t 36 -f -p 9 asins.txt

文档: ${APP_DIR}/docs/生产部署.md
========================================
EOF
