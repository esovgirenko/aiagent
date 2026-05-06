#!/usr/bin/env bash
set -euo pipefail

# One-shot installer for VPS deployment.
# Modes:
#   docker   -> Docker Compose deployment
#   systemd  -> Python venv + systemd + nginx (+ optional certbot)

MODE="${1:-docker}"
DOMAIN="${DOMAIN:-}"
APP_DIR="${APP_DIR:-/opt/ai-agent}"
SERVICE_USER="${SERVICE_USER:-www-data}"
ENABLE_TLS="${ENABLE_TLS:-true}"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root: sudo bash install.sh ${MODE}"
    exit 1
  fi
}

ensure_env_file() {
  if [[ ! -f "${APP_DIR}/.env" ]]; then
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    echo "Created ${APP_DIR}/.env from example."
    echo "Fill provider keys in ${APP_DIR}/.env and rerun if needed."
  fi
}

install_docker_mode() {
  echo "[1/4] Installing Docker packages..."
  apt update
  apt install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
  fi
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt update
  apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  echo "[2/4] Preparing app directory..."
  mkdir -p "${APP_DIR}"
  cp -R . "${APP_DIR}"
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}" || true
  ensure_env_file

  echo "[3/4] Starting containers..."
  cd "${APP_DIR}"
  docker compose up -d --build

  echo "[4/4] Done."
  echo "Check: docker compose -f ${APP_DIR}/docker-compose.yml ps"
  echo "Logs:  docker compose -f ${APP_DIR}/docker-compose.yml logs -f ai-agent"
}

install_systemd_mode() {
  if [[ -z "${DOMAIN}" ]]; then
    echo "Set DOMAIN for systemd mode, e.g.: DOMAIN=agent.example.com sudo bash install.sh systemd"
    exit 1
  fi

  echo "[1/6] Installing system packages..."
  apt update
  apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx

  echo "[2/6] Preparing app directory..."
  mkdir -p "${APP_DIR}"
  cp -R . "${APP_DIR}"
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}" || true
  ensure_env_file

  echo "[3/6] Installing Python dependencies..."
  su -s /bin/bash -c "cd '${APP_DIR}' && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt" "${SERVICE_USER}" || {
    cd "${APP_DIR}"
    python3 -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt
  }

  echo "[4/6] Installing systemd service..."
  cp "${APP_DIR}/deploy/ai-agent.service" /etc/systemd/system/ai-agent.service
  sed -i "s#User=.*#User=${SERVICE_USER}#g" /etc/systemd/system/ai-agent.service
  sed -i "s#Group=.*#Group=${SERVICE_USER}#g" /etc/systemd/system/ai-agent.service
  sed -i "s#WorkingDirectory=.*#WorkingDirectory=${APP_DIR}#g" /etc/systemd/system/ai-agent.service
  sed -i "s#EnvironmentFile=.*#EnvironmentFile=${APP_DIR}/.env#g" /etc/systemd/system/ai-agent.service
  sed -i "s#ExecStart=.*#ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000#g" /etc/systemd/system/ai-agent.service
  systemctl daemon-reload
  systemctl enable --now ai-agent

  echo "[5/6] Configuring nginx..."
  cp "${APP_DIR}/deploy/nginx-ai-agent.conf" /etc/nginx/sites-available/ai-agent
  sed -i "s/server_name .*/server_name ${DOMAIN};/g" /etc/nginx/sites-available/ai-agent
  ln -sf /etc/nginx/sites-available/ai-agent /etc/nginx/sites-enabled/ai-agent
  nginx -t
  systemctl reload nginx

  echo "[6/6] TLS setup..."
  if [[ "${ENABLE_TLS}" == "true" ]]; then
    certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "admin@${DOMAIN}" --redirect || true
    echo "TLS attempted. If certbot failed, run manually:"
    echo "certbot --nginx -d ${DOMAIN}"
  else
    echo "TLS skipped (ENABLE_TLS=false)."
  fi

  echo "Done. Service status:"
  systemctl --no-pager status ai-agent || true
}

main() {
  require_root
  case "${MODE}" in
    docker)
      install_docker_mode
      ;;
    systemd)
      install_systemd_mode
      ;;
    *)
      echo "Unknown mode: ${MODE}. Use 'docker' or 'systemd'."
      exit 1
      ;;
  esac
}

main "$@"
