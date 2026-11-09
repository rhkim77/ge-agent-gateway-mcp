#!/bin/bash
set -e

export DEBIAN_FRONTEND=noninteractive
export HOME=/root

retry() {
  for i in 1 2 3 4 5; do
    "$@" && return 0
    echo "Retry $i failed... retrying in 5s"
    sleep 5
  done
  return 1
}

sleep 10

apt-get clean
rm -rf /var/lib/apt/lists/*
retry apt-get update -o Acquire::Retries=3
retry apt-get install -y ca-certificates curl gnupg lsb-release unzip jq git python3-pip python3-venv

# Clone the lab repository into /webtop-config/ge-agent-gateway-mcp
mkdir -p /webtop-config
if [ ! -d "/webtop-config/ge-agent-gateway-mcp" ]; then
  git clone https://github.com/rhkim77/ge-agent-gateway-mcp.git /webtop-config/ge-agent-gateway-mcp || true
fi

PROJECT_ID=$(curl -s "http://metadata.google.internal/computeMetadata/v1/project/project-id" -H "Metadata-Flavor: Google" || true)
if [ -n "${PROJECT_ID}" ] && [ -d "/webtop-config/ge-agent-gateway-mcp" ]; then
  cp /webtop-config/ge-agent-gateway-mcp/.env.example /webtop-config/ge-agent-gateway-mcp/.env || true
  sed -i "s/your-gcp-project-id/${PROJECT_ID}/g" /webtop-config/ge-agent-gateway-mcp/.env || true
fi

# Background sync loop for Qwiklabs StorageV1 assessment fallback (runs every 15s)
if [ -n "${PROJECT_ID}" ]; then
  nohup bash -c '
    while true; do
      if [ -d "/webtop-config/ge-agent-gateway-mcp/artifacts" ]; then
        gcloud storage cp -r /webtop-config/ge-agent-gateway-mcp/artifacts "gs://'"${PROJECT_ID}"'-ge-agw-state/workspace-sync/" >/dev/null 2>&1 || true
      fi
      sleep 15
    done
  ' >/var/log/agw-workspace-sync.log 2>&1 &
fi
