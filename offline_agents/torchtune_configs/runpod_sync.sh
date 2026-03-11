#!/usr/bin/env bash
# Sync gitignored training artifacts between a local WSL checkout and a Runpod pod.
#
# Usage:
#   bash offline_agents/torchtune_configs/runpod_sync.sh upload-data <ssh-target> [--port PORT] [--identity PATH]
#   bash offline_agents/torchtune_configs/runpod_sync.sh download-rules <ssh-target> [--port PORT] [--identity PATH]
#   bash offline_agents/torchtune_configs/runpod_sync.sh download-cards <ssh-target> [--port PORT] [--identity PATH]
#   bash offline_agents/torchtune_configs/runpod_sync.sh download-all <ssh-target> [--port PORT] [--identity PATH]

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash offline_agents/torchtune_configs/runpod_sync.sh upload-data <ssh-target> [--port PORT] [--identity PATH]
  bash offline_agents/torchtune_configs/runpod_sync.sh download-rules <ssh-target> [--port PORT] [--identity PATH]
  bash offline_agents/torchtune_configs/runpod_sync.sh download-cards <ssh-target> [--port PORT] [--identity PATH]
  bash offline_agents/torchtune_configs/runpod_sync.sh download-all <ssh-target> [--port PORT] [--identity PATH]

Examples:
  bash offline_agents/torchtune_configs/runpod_sync.sh upload-data u30jtznv8iuw50-64411218@ssh.runpod.io
  bash offline_agents/torchtune_configs/runpod_sync.sh download-all root@69.30.85.65 --port 22160
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 1
fi

ACTION="$1"
TARGET="$2"
shift 2

IDENTITY_FILE="${HOME}/.ssh/id_ed25519"
SSH_PORT=""
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
REMOTE_REPO_DIR="${RUNPOD_REPO_DIR:-/workspace/FAB_Sim}"
LOCAL_DATA_FILE="${ROOT_DIR}/offline_agents/distillation/training_data.jsonl"
LOCAL_MODELS_DIR="${ROOT_DIR}/models"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --identity)
      IDENTITY_FILE="$2"
      shift 2
      ;;
    --port)
      SSH_PORT="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

SSH_ARGS=(-o IdentitiesOnly=yes -i "$IDENTITY_FILE")
SCP_ARGS=(-o IdentitiesOnly=yes -i "$IDENTITY_FILE")

if [[ -n "$SSH_PORT" ]]; then
  SSH_ARGS+=(-p "$SSH_PORT")
  SCP_ARGS+=(-P "$SSH_PORT")
fi

run_remote() {
  ssh "${SSH_ARGS[@]}" "$TARGET" "$1"
}

copy_to_remote() {
  scp "${SCP_ARGS[@]}" "$1" "$2"
}

copy_from_remote() {
  scp "${SCP_ARGS[@]}" -r "$1" "$2"
}

case "$ACTION" in
  upload-data)
    if [[ ! -f "$LOCAL_DATA_FILE" ]]; then
      echo "Missing local training data file: $LOCAL_DATA_FILE"
      exit 1
    fi
    run_remote "mkdir -p '${REMOTE_REPO_DIR}/offline_agents/distillation' '${REMOTE_REPO_DIR}/models'"
    copy_to_remote "$LOCAL_DATA_FILE" "${TARGET}:${REMOTE_REPO_DIR}/offline_agents/distillation/training_data.jsonl"
    ;;
  download-rules)
    mkdir -p "$LOCAL_MODELS_DIR"
    copy_from_remote "${TARGET}:${REMOTE_REPO_DIR}/models/fab-rules-ft" "$LOCAL_MODELS_DIR/"
    ;;
  download-cards)
    mkdir -p "$LOCAL_MODELS_DIR"
    copy_from_remote "${TARGET}:${REMOTE_REPO_DIR}/models/fab-cards-ft" "$LOCAL_MODELS_DIR/"
    ;;
  download-all)
    mkdir -p "$LOCAL_MODELS_DIR"
    copy_from_remote "${TARGET}:${REMOTE_REPO_DIR}/models/fab-rules-ft" "$LOCAL_MODELS_DIR/"
    copy_from_remote "${TARGET}:${REMOTE_REPO_DIR}/models/fab-cards-ft" "$LOCAL_MODELS_DIR/"
    ;;
  *)
    usage
    exit 1
    ;;
esac