# Local Inference Platforms

Chuzom auto-detects local LLM servers on startup and routes to them first — they're
free, private, and fast. No config needed.

## Supported platforms

| Platform | Default port | Tier | Notes |
|---|---|---|---|
| **Ollama** | 11434 | 1 | Most popular. Auto-detected. `ollama serve` |
| **LM Studio** | 1234 | 1 | macOS/Windows GUI. Enable local server in app settings |
| **Jan** | 1337 | 1 | Open-source desktop. Start server from settings panel |
| **vLLM** | 8000 | 1 | High-throughput GPU server. `vllm serve <model>` |
| **llama.cpp server** | 8080 | 1 | `llama-server -m model.gguf --port 8080` |
| **llamafile** | 8080 | 1 | Single-binary. `./model.llamafile` |
| **LocalAI** | 8080 | 1 | Docker-friendly multi-backend |
| **Msty** | 10000 | 1 | macOS GUI with local server mode |
| **MLX** (Apple Silicon) | 8080 | 1 | Fastest on M-series. `mlx_lm.server --model <model>` |
| **Cortex** | 39281 | 1 | Jan's new CLI engine. `cortex start` |
| **text-generation-webui** | 5000 | 1 | Start with `--api` flag |
| **GPT4All** | 4891 | 2 | Partial OpenAI-compat. Enable API server in settings |
| **Kobold.cpp** | 5001 | 2 | Custom KoboldAI API. Popular for creative writing |

**Tier 1** = drop-in OpenAI-compatible (zero adapter needed). **Tier 2** = light
adapter, partial compatibility.

## First-run UX

When chuzom starts and finds a local platform running, it prints:

```
🖥️  Local LLM platforms detected:
   ✓ LM Studio  →  http://localhost:1234
     models: llama-3.2-8b, mistral-7b-instruct
   ✓ Ollama  →  http://localhost:11434
     models: gemma3:4b, qwen3:8b (+2 more)
```

If nothing is detected, chuzom starts silently and routes to cloud providers.

## Port overrides

```bash
export CHUZOM_LOCAL_LMSTUDIO_PORT=1235   # LM Studio on non-default port
export CHUZOM_LOCAL_JAN_PORT=1338        # Jan on non-default port
export CHUZOM_LOCAL_VLLM_PORT=8001       # vLLM on non-default port
```

Or configure a specific endpoint manually:

```bash
export OPENAI_COMPAT_BASE_URL=http://localhost:1234/v1
export OPENAI_COMPAT_MODELS=llama-3.2-8b,mistral-7b
```

## Routing priority

```
Local (Ollama / auto-detected) → Cloud budget → Cloud balanced → Cloud premium
```

Local models are always tried first. On failure, chuzom falls through to the next
tier — silently, with no user action needed.
