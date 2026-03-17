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

IS_RUNPOD_GATEWAY=false
if [[ "$TARGET" == *@ssh.runpod.io || "$TARGET" == "ssh.runpod.io" ]]; then
  IS_RUNPOD_GATEWAY=true
fi

SSH_ARGS=(-o IdentitiesOnly=yes -i "$IDENTITY_FILE")
if [[ "$IS_RUNPOD_GATEWAY" == true ]]; then
  SSH_ARGS+=(-tt)
else
  SSH_ARGS+=(-T)
fi

if [[ -n "$SSH_PORT" ]]; then
  SSH_ARGS+=(-p "$SSH_PORT")
fi

run_remote() {
  if [[ "$IS_RUNPOD_GATEWAY" == true ]]; then
    # Gateway opens interactive PTY and ignores command arguments; pipe via stdin.
    printf '%s\n' "$1" | ssh "${SSH_ARGS[@]}" "$TARGET"
  else
    ssh "${SSH_ARGS[@]}" "$TARGET" "$1"
  fi
}

# Use ssh pipe instead of scp — Runpod's gateway doesn't support the SCP/SFTP subsystem.
copy_to_remote() {
  local local_path="$1"
  local remote_path="$2"
  if [[ "$IS_RUNPOD_GATEWAY" == true ]]; then
    # Gateway requires PTY (-tt) and ignores command-line args.
    # Stream a single Python heredoc through stdin: base64-encode the file locally,
    # embed it as a Python bytes literal, and let Python decode+write it on the remote.
    # base64.decodebytes() ignores embedded newlines so line-wrapping is safe.
    {
      printf "python3 << 'PYEOF'\nimport base64\ndata = b\"\"\"\n"
      base64 -w60 "$local_path"
      printf "\"\"\"\nwith open('%s', 'wb') as _f:\n    _f.write(base64.decodebytes(data))\nprint('__UPLOAD_OK__')\nPYEOF\n" "$remote_path"
    } | ssh "${SSH_ARGS[@]}" "$TARGET"
  else
    ssh "${SSH_ARGS[@]}" "$TARGET" "cat > '${remote_path}'" < "$local_path"
  fi
}

copy_from_remote() {
  local remote_path="$1"
  local local_dest="$2"
  if [[ "$IS_RUNPOD_GATEWAY" == true ]]; then
    echo "Download actions are not supported through ssh.runpod.io gateway."
    echo "Use the direct pod endpoint: root@<pod-ip> --port <pod-port>"
    exit 1
  fi
  # tar over ssh for directory transfers
  ssh "${SSH_ARGS[@]}" "$TARGET" "tar -czf - -C '$(dirname "${remote_path}")' '$(basename "${remote_path}")'" \
    | tar -xzf - -C "$local_dest"
}

case "$ACTION" in
  upload-data)
    if [[ ! -f "$LOCAL_DATA_FILE" ]]; then
      echo "Missing local training data file: $LOCAL_DATA_FILE"
      exit 1
    fi
    run_remote "mkdir -p '${REMOTE_REPO_DIR}/offline_agents/distillation' '${REMOTE_REPO_DIR}/models'"
    copy_to_remote "$LOCAL_DATA_FILE" "${REMOTE_REPO_DIR}/offline_agents/distillation/training_data.jsonl"
    ;;
  download-rules)
    mkdir -p "${LOCAL_MODELS_DIR}/fab-rules-ft"
    copy_from_remote "${REMOTE_REPO_DIR}/models/fab-rules-ft/epoch_2" "${LOCAL_MODELS_DIR}/fab-rules-ft"
    ;;
  download-cards)
    mkdir -p "${LOCAL_MODELS_DIR}/fab-cards-ft"
    copy_from_remote "${REMOTE_REPO_DIR}/models/fab-cards-ft/epoch_2" "${LOCAL_MODELS_DIR}/fab-cards-ft"
    ;;
  download-all)
    mkdir -p "${LOCAL_MODELS_DIR}/fab-rules-ft" "${LOCAL_MODELS_DIR}/fab-cards-ft"
    copy_from_remote "${REMOTE_REPO_DIR}/models/fab-rules-ft/epoch_2" "${LOCAL_MODELS_DIR}/fab-rules-ft"
    copy_from_remote "${REMOTE_REPO_DIR}/models/fab-cards-ft/epoch_2" "${LOCAL_MODELS_DIR}/fab-cards-ft"
    ;;
  *)
    usage
    exit 1
    ;;
esac