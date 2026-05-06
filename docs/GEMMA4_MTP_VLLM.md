# Gemma 4 MTP on vLLM

This runbook is for trying Google's Gemma 4 multi-token-prediction assistants behind vLLM, then pointing Forge NPS at the resulting OpenAI-compatible endpoint.

## What Changed

Google's May 5, 2026 announcement says Gemma 4 MTP drafters use speculative decoding and can improve responsiveness by letting a lightweight assistant propose future tokens for a heavier target model to verify. vLLM exposes this through `--speculative-config`.

The relevant Hugging Face model pairs are:

| Target model | MTP assistant |
| --- | --- |
| `google/gemma-4-31B-it` | `google/gemma-4-31B-it-assistant` |
| `google/gemma-4-26B-A4B-it` | `google/gemma-4-26B-A4B-it-assistant` |
| `google/gemma-4-E4B-it` | `google/gemma-4-E4B-it-assistant` |
| `google/gemma-4-E2B-it` | `google/gemma-4-E2B-it-assistant` |

You must accept the Gemma license on Hugging Face for the account/token used on the machine.

## Hardware Read

DGX Spark is the right first target for `31B` or `26B A4B` in BF16. Start with `--max-model-len 32768`; raise context only after the endpoint is stable.

Dual RTX 3090 is memory-constrained for the official `31B` and `26B A4B` BF16 targets. Use `dual-3090-e4b` to validate the MTP path, or use `dual-3090-quant` with a tokenizer-compatible 4-bit/AWQ/GPTQ Gemma 4 target. The official assistant can still be used as the draft model when the target is a compatible quantization of the same Gemma 4 model.

## Launch vLLM

From the repo root on the target machine:

```bash
chmod +x scripts/launch_vllm_gemma4_mtp.sh
HF_TOKEN=hf_... scripts/launch_vllm_gemma4_mtp.sh dgx-spark-31b
```

Other presets:

```bash
scripts/launch_vllm_gemma4_mtp.sh dgx-spark-26b
scripts/launch_vllm_gemma4_mtp.sh dual-3090-e4b
TARGET_MODEL=/models/gemma-4-31b-awq scripts/launch_vllm_gemma4_mtp.sh dual-3090-quant
```

Useful overrides:

```bash
PORT=8001 SPECULATIVE_TOKENS=2 MAX_MODEL_LEN=16384 scripts/launch_vllm_gemma4_mtp.sh dgx-spark-31b
CUDA_VISIBLE_DEVICES=0,1 TENSOR_PARALLEL_SIZE=2 TARGET_MODEL=/models/gemma-4-31b-awq scripts/launch_vllm_gemma4_mtp.sh dual-3090-quant
```

The launcher uses this vLLM shape:

```bash
vllm serve "$TARGET_MODEL" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE" \
  --dtype "$DTYPE" \
  --max-model-len "$MAX_MODEL_LEN" \
  --speculative-config '{"method":"mtp","model":"'"$DRAFT_MODEL"'","num_speculative_tokens":3}'
```

## Smoke Test

```bash
python3 scripts/benchmark_vllm_endpoint.py \
  --base-url http://localhost:8000/v1 \
  --model gemma4-31b-mtp \
  --requests 6 \
  --concurrency 1
```

Then test modest batching:

```bash
python3 scripts/benchmark_vllm_endpoint.py \
  --base-url http://localhost:8000/v1 \
  --model gemma4-31b-mtp \
  --requests 16 \
  --concurrency 4
```

Compare against a no-MTP vLLM launch of the same target before trusting the speedup. Speculative decoding gains are workload-dependent; high temperature, long unpredictable generations, and very high concurrency can reduce acceptance.

## Point Forge at vLLM

For a local vLLM endpoint:

```bash
export FORGE_PROFILE_PROVIDER=custom
export FORGE_PROFILE_MODEL=gemma4-31b-mtp
export FORGE_PROFILE_BASE_URL=http://localhost:8000/v1
export OPENAI_API_KEY=not-needed

export KIMI_API_KEY=not-needed
export NIM_ENDPOINT=http://localhost:8000/v1/chat/completions
export KIMI_DIRECTOR_ENDPOINT_API1=http://localhost:8000/v1/chat/completions
export KIMI_DIRECTOR_ENDPOINT_ACTIVE=api1
export KIMI_INSTRUCT_MODEL=gemma4-31b-mtp
export KIMI_THINKING_MODEL=gemma4-31b-mtp
```

For a remote DGX Spark or 3090 box, replace `localhost` with that host or IP. Forge now preserves explicit vLLM ports such as `:8000`; it no longer rewrites them to LM Studio's `:1234`.

Then run Forge:

```bash
python3 -m dashboard.forge_dashboard
```

## Sources

- Google announcement: https://blog.google/innovation-and-ai/technology/developers-tools/multi-token-prediction-gemma-4/
- Gemma 4 model card: https://huggingface.co/google/gemma-4-31B-it
- vLLM speculative decoding docs: https://docs.vllm.ai/en/v0.20.1/features/speculative_decoding/
