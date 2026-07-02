#!/usr/bin/env bash
# Quick server readiness check (no Celery task execution).
#
# Usage:
#   ./deploy/check-server.sh
#   ./deploy/check-server.sh --with-workers
#   ./deploy/check-server.sh --systemd amazon-spapi-offers-us.service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f /etc/amazon-spapi/amazon-spapi.env ]]; then
  set -a
  # shellcheck source=/dev/null
  source /etc/amazon-spapi/amazon-spapi.env
  set +a
fi

cd "${APP_DIR}"
exec uv run amazon-spapi-check "$@"
