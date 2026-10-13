"""Serve Qwen3 on Modal *CPU* containers behind an OpenAI-compatible API (llama.cpp), at no GPU cost.

The GPU deployment (`llm_server.py`, vLLM, following Modal's "deploy a Qwen chatbot" guide) is faster but Modal only
allows GPUs on workspaces with a payment method. CPU containers run on the free monthly credits, so this variant
keeps the same architecture (OpenAI-compatible `/v1` endpoint, scale to zero, weights cached on a Volume) with
llama.cpp instead of vLLM and a 4-bit GGUF model.

    modal secret create analystos-llm LLM_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
    modal deploy deploy/modal/llm_cpu.py

Then: LLM_BASE_URL=https://<workspace>--analystos-llm-cpu-serve.modal.run/v1, LLM_MODEL=qwen3, LLM_API_KEY=<key>.
"""

from __future__ import annotations

import os
import subprocess

import modal

# Qwen3-4B-Instruct-2507 passed 88% of the AnalystOS benchmark (Qwen3 8B: 93%) at about a third of the latency;
# on CPU that difference decides whether a question takes minutes or tens of minutes.
REPO = os.environ.get("ANALYSTOS_GGUF_REPO", "unsloth/Qwen3-4B-Instruct-2507-GGUF")
FILE = os.environ.get("ANALYSTOS_GGUF_FILE", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
CPUS = float(os.environ.get("ANALYSTOS_LLM_CPUS", "16"))
CONTEXT = 16384
PORT = 8000
MODELS = "/models"

image = (
    modal.Image.from_registry("ghcr.io/ggml-org/llama.cpp:server", add_python="3.12")
    .entrypoint([])
    .pip_install("huggingface_hub[hf_transfer]==0.36.0")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)
weights = modal.Volume.from_name("analystos-gguf", create_if_missing=True)
app = modal.App("analystos-llm-cpu")


@app.function(image=image, volumes={MODELS: weights}, timeout=30 * 60)
def download() -> str:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(REPO, FILE, local_dir=MODELS)
    weights.commit()
    return path


@app.function(
    image=image,
    cpu=CPUS,
    memory=16384,
    secrets=[modal.Secret.from_name("analystos-llm")],
    volumes={MODELS: weights},
    scaledown_window=10 * 60,
    timeout=60 * 60,
    max_containers=1,
)
@modal.concurrent(max_inputs=4)
@modal.web_server(port=PORT, startup_timeout=10 * 60)
def serve() -> None:
    model = f"{MODELS}/{FILE}"
    if not os.path.exists(model):
        from huggingface_hub import hf_hub_download

        hf_hub_download(REPO, FILE, local_dir=MODELS)
    cmd = [
        "/app/llama-server",
        "--model", model,
        "--alias", "qwen3",
        "--host", "0.0.0.0",  # noqa: S104 - inside the container; Modal routes the public URL here
        "--port", str(PORT),
        "--api-key", os.environ["LLM_API_KEY"],
        "--ctx-size", str(CONTEXT),
        "--threads", str(int(CPUS)),
        "--parallel", "1",
        "--jinja",
    ]  # fmt: skip
    subprocess.Popen(cmd)
