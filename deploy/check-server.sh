#!/usr/bin/env bash
# Quick server readiness check (no Celery task execution).
#
# Usage:
#   ./deploy/check-server.sh
#   ./deploy/check-server.sh --with-workers
#   ./deploy/check-server.sh --systemd amazon-spapi-offers.service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

for env_file in \
  /etc/conf.d/celery_spapi \
  /etc/amazon-spapi/amazon-spapi.env
do
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${env_file}"
    set +a
    break
  fi
done

cd "${APP_DIR}"
exec uv run amazon-spapi-check "$@"
