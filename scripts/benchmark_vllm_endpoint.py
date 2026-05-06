#!/usr/bin/env python3
import argparse
import asyncio
import json
import statistics
import time
from typing import Any

import httpx


PROMPTS = [
    "Return compact JSON with keys status and one_sentence. Explain speculative decoding in one sentence.",
    "Return compact JSON with keys headline, risks, and next_step for running Gemma 4 locally with vLLM.",
    "Return compact JSON with keys summary and checklist. Make the checklist exactly three short strings.",
]


def endpoint_base(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if value.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")].rstrip("/")
    if value.endswith("/v1"):
        return value
    return f"{value}/v1"


async def request_once(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise JSON-only assistant. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    started = time.perf_counter()
    resp = await client.post(f"{base_url}/chat/completions", json=payload)
    elapsed = time.perf_counter() - started
    text = resp.text
    resp.raise_for_status()
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    usage = data.get("usage") or {}
    completion_tokens = int(usage.get("completion_tokens") or 0)
    if completion_tokens <= 0:
        completion_tokens = max(1, round(len(content) / 4))
    return {
        "elapsed_sec": elapsed,
        "completion_tokens": completion_tokens,
        "tokens_per_sec": completion_tokens / elapsed if elapsed > 0 else 0,
        "finish_reason": choice.get("finish_reason"),
        "content": content,
        "raw_len": len(text),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke and benchmark an OpenAI-compatible vLLM chat endpoint.")
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key", default="not-needed")
    parser.add_argument("--requests", type=int, default=6)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()

    base_url = endpoint_base(args.base_url)
    headers = {"Authorization": f"Bearer {args.api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=args.timeout, headers=headers) as client:
        models_resp = await client.get(f"{base_url}/models")
        models_resp.raise_for_status()
        model_ids = [m.get("id") for m in (models_resp.json().get("data") or []) if m.get("id")]
        if model_ids:
            print("models:", ", ".join(model_ids))

        semaphore = asyncio.Semaphore(max(1, args.concurrency))

        async def guarded(i: int) -> dict[str, Any]:
            async with semaphore:
                return await request_once(
                    client,
                    base_url=base_url,
                    model=args.model,
                    prompt=PROMPTS[i % len(PROMPTS)],
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                )

        started = time.perf_counter()
        results = await asyncio.gather(*(guarded(i) for i in range(args.requests)))
        wall = time.perf_counter() - started

    rates = [r["tokens_per_sec"] for r in results]
    total_tokens = sum(r["completion_tokens"] for r in results)
    print(json.dumps({
        "base_url": base_url,
        "model": args.model,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "wall_sec": round(wall, 3),
        "completion_tokens": total_tokens,
        "aggregate_completion_tokens_per_sec": round(total_tokens / wall, 3) if wall > 0 else 0,
        "per_request_tokens_per_sec_mean": round(statistics.mean(rates), 3),
        "per_request_tokens_per_sec_median": round(statistics.median(rates), 3),
        "first_finish_reason": results[0]["finish_reason"],
        "first_content": results[0]["content"][:500],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
