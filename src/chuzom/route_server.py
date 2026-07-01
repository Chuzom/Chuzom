"""HTTP ``/route`` endpoint — route a single prompt through Chuzom's real router
over HTTP, so external processes (e.g. LoopHole's ``chuzom:`` provider) can use
Chuzom's model selection without importing chuzom or speaking MCP.

Pure stdlib server (no FastAPI/uvicorn dependency) — the **zero-dependency
fallback**. The primary surface is ``chuzom.gateway`` (FastAPI on :17900), which
also exposes ``/route`` plus OpenAI/Anthropic/Ollama wire formats and shares this
module's :func:`route_payload` as its routing core, so both go through
``route_and_call`` identically. Use this server where FastAPI/uvicorn aren't
available. Launch it with the ``chuzom-route`` console script, or
``python -m chuzom.route_server``.

    POST /route
      {"prompt": "...",                         # required
       "complexity": "simple|moderate|complex", # optional -> routing profile
       "system": "...",                         # optional system prompt
       "task_type": "code|query|...",           # optional (default: code)
       "max_tokens": 4096, "temperature": 0.2}  # optional
      -> 200 {"text","model","provider","cost_usd",
              "input_tokens","output_tokens","complexity"}
      -> 400 on bad input · 502 if routing/provider fails

    GET /health -> {"ok": true}
"""

from __future__ import annotations

import argparse
import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def route_payload(payload: dict) -> dict:
    """Run one routing call through Chuzom's FULL router and return a JSON-able
    result. This is the single routing core shared by both HTTP surfaces — this
    zero-dep server AND ``gateway.py`` — so every external caller goes through
    ``route_and_call`` and uniformly gets budget caps, caching, the paid-spend
    cap, and cost logging. Importing inside keeps module import cheap and lets
    tests monkeypatch ``chuzom.router.route_and_call``."""
    from chuzom.router import route_and_call
    from chuzom.types import TaskType

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("missing 'prompt'")
    try:
        task_type = TaskType(payload.get("task_type", "code"))
    except ValueError:
        task_type = TaskType.CODE

    # Optional tier override (OpenAI ``model`` field / explicit model_override).
    # "chuzom-auto" or empty means "let Chuzom pick".
    _override = payload.get("model_override") or payload.get("model")
    if _override in ("chuzom-auto", "", None):
        _override = None

    resp = asyncio.run(route_and_call(
        task_type, prompt,
        complexity_hint=payload.get("complexity") or None,
        system_prompt=payload.get("system") or None,
        model_override=_override,
        max_tokens=payload.get("max_tokens"),
        temperature=payload.get("temperature"),
    ))

    # Surface this external route in the host-tagged savings pipeline so gateway /
    # LoopHole traffic shows up in the cross-surface indicators + savings_stats.
    # route_and_call already logged COST to usage.db, so we only add the
    # host-tagged savings record (never usage.db → no double count).
    _log_route_savings(resp, task_type.value,
                       payload.get("complexity") or resp.complexity or "moderate",
                       str(payload.get("host") or "gateway"))

    return {
        "text": resp.content,
        "model": resp.model,
        "provider": resp.provider,
        "cost_usd": resp.cost_usd,
        "input_tokens": resp.input_tokens,
        "output_tokens": resp.output_tokens,
        "complexity": resp.complexity,
    }


def _log_route_savings(resp, task_type: str, complexity: str, host: str) -> None:
    """Append a host-tagged record to ~/.chuzom/savings_log.jsonl for an external
    (gateway/route) call. Fire-and-forget.

    Deliberately does NOT touch session_spend.json (the CURRENT Claude Code
    session's ledger) the way the hook's log_direct_savings does — external
    traffic is not this session's spend. Cost is already in usage.db via
    route_and_call; this only adds the host-tagged savings record so the traffic
    is visible per-surface.
    """
    try:
        import json as _json
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        from chuzom.hooks.savings_logger import (
            _baseline_cost,
            _cost_for,
            _savings_log_path,
        )

        provider = resp.provider or ""
        model = resp.model or ""
        bare = model.split("/", 1)[1] if "/" in model and model.split("/", 1)[0] == provider else model
        in_tok = max(0, int(resp.input_tokens or 0))
        out_tok = max(0, int(resp.output_tokens or 0))
        external = _cost_for(provider, bare, in_tok, out_tok)
        baseline = _baseline_cost(complexity, in_tok, out_tok)
        record = {
            "timestamp": _dt.now(_tz.utc).isoformat(),
            "session_id": host,
            "task_type": task_type,
            "complexity": complexity,
            "estimated_saved": max(0.0, baseline - external),
            "external_cost": external,
            "model": model,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "host": host,
        }
        path = _savings_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(_json.dumps(record) + "\n")
    except Exception:
        pass


def make_handler():
    class _Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"ok": True})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/route":
                return self._send(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError) as e:
                return self._send(400, {"error": "bad json: {}".format(e)})
            try:
                self._send(200, route_payload(payload))
            except ValueError as e:
                self._send(400, {"error": str(e)})
            except Exception as e:                      # routing / provider failure
                self._send(502, {"error": "route failed: {}".format(e)})

        def log_message(self, *_a):                     # quiet by default
            pass

    return _Handler


def serve(host: str = "127.0.0.1", port: int = 7338) -> None:
    srv = ThreadingHTTPServer((host, port), make_handler())
    print("chuzom route endpoint -> http://{}:{}/route   (Ctrl-C to stop)".format(
        host, srv.server_address[1]))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        prog="chuzom-route",
        description="Serve Chuzom's router over HTTP for external callers (e.g. LoopHole).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7338)
    args = ap.parse_args(argv)
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
