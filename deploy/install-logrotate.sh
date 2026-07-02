#!/usr/bin/env bash
# Install logrotate + journald size limits for amazon-spapi-workers.
#
#   sudo ./deploy/install-logrotate.sh
#   sudo ./deploy/install-logrotate.sh --user Admin

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEPLOY_USER="${SUDO_USER:-${USER:-}}"
DRY_RUN=false

usage() {
  cat <<'EOF'
Install logrotate and journald limits for amazon-spapi-workers.

  sudo ./deploy/install-logrotate.sh [选项]

选项:
  --user NAME   运行 worker 的用户（默认 $SUDO_USER）
  --dry-run     只打印，不写入
  -h, --help
EOF
}

log() { printf '[install-logrotate] %s\n' "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) DEPLOY_USER="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || { echo "请用 sudo 运行" >&2; exit 1; }
[[ -n "${DEPLOY_USER}" ]] || { echo "缺少 --user 或 SUDO_USER" >&2; exit 1; }

DEPLOY_HOME="$(getent passwd "${DEPLOY_USER}" | cut -d: -f6)"
LOG_DIR="${DEPLOY_HOME}/.amazon_spapi/logs"

run() {
  if [[ "${DRY_RUN}" == true ]]; then
    log "[dry-run] $*"
  else
    log "+ $*"
    "$@"
  fi
}

log "用户: ${DEPLOY_USER}"
log "日志目录: ${LOG_DIR}"

run mkdir -p "${LOG_DIR}"
run chown "${DEPLOY_USER}:${DEPLOY_USER}" "${LOG_DIR}"

if [[ "${DRY_RUN}" == true ]]; then
  log "[dry-run] write /etc/logrotate.d/amazon-spapi"
else
  sed \
    -e "s|@LOG_DIR@|${LOG_DIR}|g" \
    -e "s|@DEPLOY_USER@|${DEPLOY_USER}|g" \
    "${SCRIPT_DIR}/logrotate/amazon-spapi.conf.template" \
    >/etc/logrotate.d/amazon-spapi
  chmod 644 /etc/logrotate.d/amazon-spapi
fi

run mkdir -p /etc/systemd/journald.conf.d
if [[ "${DRY_RUN}" == true ]]; then
  log "[dry-run] write /etc/systemd/journald.conf.d/amazon-spapi-size.conf"
else
  cp "${SCRIPT_DIR}/journald/size-limit.conf" \
    /etc/systemd/journald.conf.d/amazon-spapi-size.conf
  chmod 644 /etc/systemd/journald.conf.d/amazon-spapi-size.conf
fi

if [[ "${DRY_RUN}" != true ]]; then
  systemctl restart systemd-journald || true
  logrotate -d /etc/logrotate.d/amazon-spapi >/dev/null 2>&1 && \
    log "logrotate 配置语法 OK" || \
    logrotate -d /etc/logrotate.d/amazon-spapi
fi

cat <<EOF

已安装:
  文件日志 logrotate: /etc/logrotate.d/amazon-spapi
    → ${LOG_DIR}/*.log, cron.log
  Worker 日志 (journald): /etc/systemd/journald.conf.d/amazon-spapi-size.conf
    → 查看: journalctl -u amazon-spapi-offers -u amazon-spapi-catalog

手动测试 logrotate:
  sudo logrotate -f /etc/logrotate.d/amazon-spapi
EOF
