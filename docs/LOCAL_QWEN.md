# Local Qwen3.5-9B with llama.cpp

AgentForge can run all agent roles through one local CUDA server. This setup uses
[Unsloth's Qwen3.5-9B Q4_K_M GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF)
and [llama.cpp b11438](https://github.com/ggml-org/llama.cpp/releases/tag/b11438).
The model is 5,680,522,464 bytes (5.29 GiB); the setup script checks its SHA-256.
Weights, binaries, logs, and private configuration backups stay under ignored
`artifacts/local-llm/`.

## Windows setup

Requires an NVIDIA GPU with a CUDA-compatible driver, Git, PowerShell, curl, and
[uv](https://docs.astral.sh/uv/). The recorded machine has a Ryzen 7 7800X3D,
32 GB RAM, and RTX 3070 with 8 GB VRAM. Other applications were using about
1.9 GB VRAM before starting the server. Q4_K_M uses more memory than Q3_K_M;
partial GPU offloading leaves room for the desktop and inference buffers.
Quantization trades accuracy for memory.

```powershell
./scripts/setup_local_qwen.ps1 -InstallPython
./scripts/start_local_qwen.ps1
```

Keep the server terminal open. In a second terminal, merge the settings from
[`examples/local-qwen.env`](../examples/local-qwen.env) into `.env`, then run:

```powershell
./.venv/Scripts/python.exe orchestrator.py local_qwen_project --provider openai --prompt examples/evaluation/slugify.txt --new
```

The server binds to `127.0.0.1:8080`, exposes `/health` and `/v1/models`, and serves
the exact alias `qwen3.5-9b-q4_k_m`. AgentForge uses `/v1/chat/completions` via its
existing OpenAI-compatible adapter; no cloud API key is needed. Server-specific
thinking control is sent through `extra_body`. Embeddings, memory, and model
escalation are disabled for this profile.

The default is 16,384 context tokens, one inference slot, a 256-token batch and
128-token microbatch, with 28 layers on the GPU. AgentForge caps each answer at
4,096 tokens. If VRAM is
tight, reduce GPU layers, for example `-GpuLayers 24`, or use `-GpuLayers 0` for
CPU inference. Reducing `-ContextSize` also requires updating
`LLM_CONTEXT_WINDOW`. CPU inference will be slower; no CPU timing is claimed.

For a background server, use `./scripts/start_local_qwen.ps1 -Background`.
The helper prints the PID and saves it in `artifacts/local-llm/server.pid`;
stop that process with `Stop-Process -Id <printed-pid>`. It refuses to start
over an occupied port. Background persistence depends on the shell host; the
foreground command is the reliable restart path. Logs are saved beside the PID.

## Reproduce the GitHub demo

With the local server running:

```powershell
./.venv/Scripts/python.exe scripts/local_qwen_demo.py
```

This command applies the local profile to its agent processes, executes the
slugify acceptance case with a minimal three-file prompt through the full
pipeline, rechecks independent acceptance, and loads state/checkpoints into a fresh orchestrator
object. It publishes sanitized evidence under
[`docs/evidence/local-qwen-demo/`](evidence/local-qwen-demo/), including JSON,
exact generated Python snapshots (`.py.txt`), and an animated replay. The GIF
presents actual captured events; it is not a screen recording. If independent
tests fail after review, it sends the captured failure back through the real
developer/reviewer pipeline as a corrective task. The report retains the initial
failure and the measured repair time. A remaining failure is reported as a failure.
Optional Docker testing is disabled; independent acceptance runs separately.

Raw evaluation logs and dependency versions remain under ignored
`artifacts/evaluations/`. To regenerate the presentation from an existing run:

```powershell
./.venv/Scripts/python.exe scripts/local_qwen_demo.py --evaluation artifacts/evaluations/<run-id>/report.json
```

One small coding case demonstrates integration. It does not establish reliability
on larger projects or compare this quantization with other models.
