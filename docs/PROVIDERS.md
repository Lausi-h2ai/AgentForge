# OpenAI-compatible endpoints

For a Windows CUDA setup with Qwen3.5-9B Q4_K_M and an 8 GB GPU, see
the [local llama.cpp setup and measured demo](LOCAL_QWEN.md).

AgentForge's default adapter targets **Chat Completions** using LlamaIndex
[OpenAILike](https://docs.llamaindex.ai/en/stable/api_reference/llms/openai_like/).
Model names pass through unchanged without an OpenAI model catalog check. Both
synchronous chat and async SSE streaming are supported.

```bash
python -m pip install -e .[dev,openai]
```

Set these values in `.env` or your process environment:

```dotenv
LLM_PROVIDER=openai
OPENAI_BASE_URL=http://localhost:8080/v1
OPENAI_API_KEY=
LLM_MODEL=your-served-model
LLM_CONTEXT_WINDOW=32768
LLM_MAX_TOKENS=4096
LLM_REQUEST_TIMEOUT=300
EMBEDDING_PROVIDER=none
HIPPOCAMP_AI_ENABLED=false
```

Use the API root, usually ending in `/v1`, rather than `/v1/chat/completions`.
The model must support a chat template and the requested context/output lengths.
A blank key supplies a placeholder for auth-free servers; authenticated endpoints
require their actual key. Required endpoint/model configuration never silently falls
back to another service.

```bash
python orchestrator.py my_project --provider openai --prompt examples/prompts/demo_prompt.txt --new
python scripts/evaluate_portfolio.py --provider openai --model your-served-model
```

CLI provider selection overrides `LLM_PROVIDER`. Without either, `openai` is used.
Existing `.env` files selecting `ollama` remain effective until changed. `--google`
remains an alias for `--provider google`. Legacy providers use their own extras.

## Endpoint examples

| Server | API root example | Model setting |
|---|---|---|
| llama.cpp | `http://localhost:8080/v1` | Served model/alias |
| vLLM | `http://localhost:8000/v1` | Served model name |
| Hosted compatible service | Service's documented API root | Service's exact model ID |
| OpenAI | `https://api.openai.com/v1` | Model supporting the required Chat Completions parameters |

[llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
and [vLLM serving](https://docs.vllm.ai/en/latest/serving/online_serving/) document
their compatible routes. The transport is OpenAI-style
[text generation and Chat Completions](https://developers.openai.com/api/docs/guides/text), not
Responses-only compatibility. Tests use a local scripted HTTP server; every
third-party deployment has not been tested.

ReAct uses textual `Action` / `Action Input` decisions; native function calling is
not required. The model still needs to follow the agent prompts. Reasoning,
sampling, and parameter support vary between services.

## Optional embeddings

For `openai`, vector retrieval defaults to disabled. File tools supply code context,
and workspace inventory loads on resume. No Ollama embedding model is required.
For legacy providers, an unset `EMBEDDING_PROVIDER` retains previous embedding
selection; `none` disables vector retrieval for those providers too.

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=your-embedding-model
OPENAI_EMBEDDING_BASE_URL=http://localhost:9090/v1
OPENAI_EMBEDDING_API_KEY=
```

The embedding URL and key fall back to chat settings when unset. Set both for a
separate authenticated service. The embedding model must be served on `/embeddings`.
[OpenAILikeEmbedding](https://docs.llamaindex.ai/en/stable/api_reference/embeddings/openai_like/)
also accepts arbitrary model names. Optional HippocampAI memory is configured
independently and defaults to disabled.

## Overrides and escalation

`--planning-model` and `--execution-model` select different models on the same endpoint.
`LLM_ESCALATION_MODEL` supplies a stronger model for existing task/planner escalation.
Enable the corresponding policy settings in `.env.example`; all selected models must
be available at the configured endpoint.

`OPENAI_ADDITIONAL_KWARGS` accepts a JSON object of OpenAI client parameters. Unknown
server parameters go inside `extra_body`, for example `{"extra_body":{"top_k":40}}`
when supported by the service. Model, messages, stream, and credentials cannot be
overridden here. Keep credentials out of that object. Adapter calls use
`LLM_REQUEST_TIMEOUT` and two retries, alongside the harness's existing retry policy.
