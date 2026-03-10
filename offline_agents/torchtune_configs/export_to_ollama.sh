#!/usr/bin/env bash
# export_to_ollama.sh — Convert a torchtune fine-tuned Qwen2.5 7B model to GGUF and load into Ollama
#
# Run from FAB_Sim_v2/:
#   bash offline_agents/torchtune_configs/export_to_ollama.sh rules
#   bash offline_agents/torchtune_configs/export_to_ollama.sh cards
#
# Requires: llama.cpp installed (pip install llama-cpp-python or build from source)
# Base model: Qwen/Qwen2.5-7B-Instruct (no gated access required)

set -e
ROLE="${1:-rules}"   # "rules" or "cards"

if [[ "$ROLE" == "rules" ]]; then
    FT_DIR="./models/fab-rules-ft"
    MODEL_NAME="fab-rules-ft"
elif [[ "$ROLE" == "cards" ]]; then
    FT_DIR="./models/fab-cards-ft"
    MODEL_NAME="fab-cards-ft"
else
    echo "Usage: $0 [rules|cards]"
    exit 1
fi

GGUF_OUT="${FT_DIR}/${MODEL_NAME}.Q4_K_M.gguf"
LATEST_EPOCH_DIR="$(ls -d "${FT_DIR}"/epoch_* 2>/dev/null | sort -V | tail -n 1)"

if [[ -z "$LATEST_EPOCH_DIR" ]]; then
    echo "No trained checkpoints found under ${FT_DIR}/epoch_*"
    echo "Run training first: tune run lora_finetune_single_device --config offline_agents/torchtune_configs/fab_${ROLE}_lora.yaml"
    exit 1
fi

echo "=== Using latest trained checkpoint ==="
echo "${LATEST_EPOCH_DIR}"

echo "=== Converting to GGUF (Q4_K_M quantisation) ==="
python -m llama_cpp.convert \
    "${LATEST_EPOCH_DIR}" \
    --outfile "${GGUF_OUT}" \
    --outtype q4_k_m

echo "=== Creating Ollama Modelfile ==="
cat > "${FT_DIR}/Modelfile" <<EOF
FROM ${GGUF_OUT}

SYSTEM """You are an expert Flesh and Blood TCG ${ROLE} agent. Be precise, cite rules sections, and flag implementation bugs clearly."""

PARAMETER temperature 0.2
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
EOF

echo "=== Loading into Ollama ==="
ollama create "${MODEL_NAME}" -f "${FT_DIR}/Modelfile"

echo "=== Done. Test with: ==="
echo "  ollama run ${MODEL_NAME} 'What does Arcane Barrier N do?'"
