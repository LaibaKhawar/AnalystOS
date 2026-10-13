"""Serve an open-weight LLM on a Modal GPU behind an OpenAI-compatible API (vLLM).

AnalystOS talks to any OpenAI-compatible endpoint, so this only changes configuration:
    LLM_BASE_URL=https://<workspace>--analystos-llm-serve.modal.run/v1
    LLM_MODEL=Qwen/Qwen3-8B
    LLM_API_KEY=<the key stored in the Modal secret>

Setup (once):
    pip install modal && modal token new
    modal secret create analystos-llm LLM_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
Deploy:
    modal deploy deploy/modal/llm_server.py

Billing: Modal charges per GPU-second while a container is up. scaledown_window shuts the GPU down after
SCALEDOWN_SECONDS of inactivity, so an idle deployment costs nothing (the next request pays a cold start).
"""

from __future__ import annotations

import os
import subprocess

import modal

MODEL = os.environ.get("ANALYSTOS_MODEL", "Qwen/Qwen3-8B")
# A10G (24 GB) fits Qwen3-8B in bf16 with a 16K context; L40S (48 GB) allows 32K and more concurrency.
GPU = os.environ.get("ANALYSTOS_GPU", "A10G")
MAX_MODEL_LEN = int(os.environ.get("ANALYSTOS_MAX_MODEL_LEN", "16384"))
SCALEDOWN_SECONDS = 10 * 60
PORT = 8000

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .uv_pip_install("vllm==0.11.0", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_V1": "1"})
)
weights = modal.Volume.from_name("analystos-hf-cache", create_if_missing=True)
compile_cache = modal.Volume.from_name("analystos-vllm-cache", create_if_missing=True)

app = modal.App("analystos-llm")


@app.function(
    image=image,
    gpu=GPU,
    secrets=[modal.Secret.from_name("analystos-llm")],
    volumes={"/root/.cache/huggingface": weights, "/root/.cache/vllm": compile_cache},
    scaledown_window=SCALEDOWN_SECONDS,
    timeout=60 * 60,
    max_containers=1,
)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=PORT, startup_timeout=15 * 60)
def serve() -> None:
    cmd = [
        "vllm",
        "serve",
        MODEL,
        "--served-model-name",
        MODEL,
        "--host",
        "0.0.0.0",  # noqa: S104 - inside the container; Modal routes the public URL here
        "--port",
        str(PORT),
        "--api-key",
        os.environ["LLM_API_KEY"],
        "--max-model-len",
        str(MAX_MODEL_LEN),
        "--gpu-memory-utilization",
        "0.92",
        "--enable-prefix-caching",
        # Qwen3 reasoning is disabled per request by AnalystOS ("/no_think"); any <think> output is stripped.
        "--reasoning-parser",
        "qwen3",
    ]
    subprocess.Popen(" ".join(cmd), shell=True)  # noqa: S602 - fixed command, no user input
