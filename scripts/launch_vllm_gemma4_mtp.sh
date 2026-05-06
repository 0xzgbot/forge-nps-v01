#!/usr/bin/env bash
set -euo pipefail

preset="${1:-dgx-spark-31b}"

case "$preset" in
  dgx-spark-31b)
    : "${TARGET_MODEL:=google/gemma-4-31B-it}"
    : "${DRAFT_MODEL:=google/gemma-4-31B-it-assistant}"
    : "${SERVED_MODEL_NAME:=gemma4-31b-mtp}"
    : "${TENSOR_PARALLEL_SIZE:=1}"
    : "${DTYPE:=bfloat16}"
    : "${MAX_MODEL_LEN:=32768}"
    : "${GPU_MEMORY_UTILIZATION:=0.88}"
    ;;
  dgx-spark-26b)
    : "${TARGET_MODEL:=google/gemma-4-26B-A4B-it}"
    : "${DRAFT_MODEL:=google/gemma-4-26B-A4B-it-assistant}"
    : "${SERVED_MODEL_NAME:=gemma4-26b-a4b-mtp}"
    : "${TENSOR_PARALLEL_SIZE:=1}"
    : "${DTYPE:=bfloat16}"
    : "${MAX_MODEL_LEN:=32768}"
    : "${GPU_MEMORY_UTILIZATION:=0.88}"
    ;;
  dual-3090-e4b)
    : "${TARGET_MODEL:=google/gemma-4-E4B-it}"
    : "${DRAFT_MODEL:=google/gemma-4-E4B-it-assistant}"
    : "${SERVED_MODEL_NAME:=gemma4-e4b-mtp}"
    : "${TENSOR_PARALLEL_SIZE:=1}"
    : "${DTYPE:=half}"
    : "${MAX_MODEL_LEN:=32768}"
    : "${GPU_MEMORY_UTILIZATION:=0.90}"
    ;;
  dual-3090-quant)
    : "${TARGET_MODEL:?Set TARGET_MODEL to a local or Hugging Face 4-bit/AWQ/GPTQ Gemma 4 target model for the dual 3090 preset.}"
    : "${DRAFT_MODEL:=google/gemma-4-31B-it-assistant}"
    : "${SERVED_MODEL_NAME:=gemma4-quant-mtp}"
    : "${TENSOR_PARALLEL_SIZE:=2}"
    : "${DTYPE:=half}"
    : "${MAX_MODEL_LEN:=16384}"
    : "${GPU_MEMORY_UTILIZATION:=0.92}"
    ;;
  *)
    cat >&2 <<'EOF'
Usage: scripts/launch_vllm_gemma4_mtp.sh <preset>

Presets:
  dgx-spark-31b     google/gemma-4-31B-it + matching MTP assistant
  dgx-spark-26b     google/gemma-4-26B-A4B-it + matching MTP assistant
  dual-3090-e4b     smaller official E4B target, useful for validating MTP
  dual-3090-quant   user-supplied quantized target across two RTX 3090s

Override with env vars:
  TARGET_MODEL DRAFT_MODEL SERVED_MODEL_NAME HOST PORT
  TENSOR_PARALLEL_SIZE DTYPE MAX_MODEL_LEN GPU_MEMORY_UTILIZATION
  SPECULATIVE_TOKENS QUANTIZATION CUDA_VISIBLE_DEVICES EXTRA_VLLM_ARGS
EOF
    exit 2
    ;;
esac

: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${SPECULATIVE_TOKENS:=3}"
: "${TRUST_REMOTE_CODE:=true}"
: "${CUDA_VISIBLE_DEVICES:=}"
: "${QUANTIZATION:=}"
: "${EXTRA_VLLM_ARGS:=}"

speculative_config=$(
  python3 - <<PY
import json
print(json.dumps({
    "method": "mtp",
    "model": "${DRAFT_MODEL}",
    "num_speculative_tokens": int("${SPECULATIVE_TOKENS}"),
}))
PY
)

cmd=(
  vllm serve "$TARGET_MODEL"
  --host "$HOST"
  --port "$PORT"
  --served-model-name "$SERVED_MODEL_NAME"
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE"
  --dtype "$DTYPE"
  --max-model-len "$MAX_MODEL_LEN"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --speculative-config "$speculative_config"
)

if [[ "$TRUST_REMOTE_CODE" == "true" ]]; then
  cmd+=(--trust-remote-code)
fi

if [[ -n "$QUANTIZATION" ]]; then
  cmd+=(--quantization "$QUANTIZATION")
fi

if [[ -n "$EXTRA_VLLM_ARGS" ]]; then
  # shellcheck disable=SC2206
  extra_args=( $EXTRA_VLLM_ARGS )
  cmd+=("${extra_args[@]}")
fi

echo "Preset: $preset"
echo "Target: $TARGET_MODEL"
echo "Draft:  $DRAFT_MODEL"
echo "Name:   $SERVED_MODEL_NAME"
echo "URL:    http://$HOST:$PORT/v1"
echo "Spec:   $speculative_config"
echo

if [[ -n "$CUDA_VISIBLE_DEVICES" ]]; then
  export CUDA_VISIBLE_DEVICES
fi

exec "${cmd[@]}"
