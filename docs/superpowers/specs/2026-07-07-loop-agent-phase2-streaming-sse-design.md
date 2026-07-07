# Phase 2.3 — Streaming SSE Design Spec

> Status: DRAFT (awaiting user approval)
> Date: 2026-07-07
> Project: `D:\code\loop-agent`
> Predecessor: Phase 2.2 (Persistent Sessions, commit `0b01996`)

## Goal

Add a streaming Server-Sent Events endpoint `POST /chat/stream` so clients
can observe the ReAct agent's iteration-by-iteration progress instead of
waiting for the entire run to complete. The existing `POST /chat` JSON
endpoint stays unchanged and remains the source of truth for non-streaming
clients.

## Scope

In scope:

- A new `POST /chat/stream` endpoint on the FastAPI app, returning
  `Content-Type: text/event-stream`.
- Server-Sent Events payload exposing the agent's per-iteration trace:
  iteration start, tool calls, tool results, final status, and an end
  marker. The shape mirrors the existing `TraceWriter` events so future
  tooling can consume both.
- Session persistence identical to `/chat`: pass `session_id`, end-of-run
  state is saved to `SessionStore` and echoed in the final event.
- Validation: blank `prompt` → `400` (same as `/chat`), missing `prompt`
  → `422`, oversized `session_id` → `422`.
- Tests using FastAPI `TestClient` to assert event order and final state.
- README updates: new section documenting `/chat/stream` and an example
  curl invocation that prints events as they arrive.

Out of scope:

- Bidirectional streaming (no continuous multi-turn inside one SSE
  connection). Each `POST /chat/stream` is one request → one response →
  close. Multi-turn continues to be expressed by repeating requests with
  the same `session_id`, identical to how `/chat` already works.
- Token-level streaming from the LLM (model streaming tokens). The events
  in this spec are agent-level events emitted by `AgentLoop.run`, not
  raw token chunks. Token-level streaming is a future enhancement and
  can be added later without breaking this endpoint's contract.
- Cancellation by client disconnect. A closed connection mid-run is
  detected, the running coroutine is cancelled, and the session is
  partially persisted up to that point.
- New dependencies. FastAPI already provides the SSE primitives we need
  via `StreamingResponse` and stdlib generators. No new package in
  `pyproject.toml`.

## Design

### Endpoint shape

```
POST /chat/stream
Content-Type: application/json
Accept: text/event-stream

{
  "prompt": "Use the echo tool to say hello",
  "session_id": "demo"        // optional, same rules as /chat
}
```

Response:

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

Followed by a sequence of SSE events, one event per `data:` line, with
events separated by a blank line as required by the SSE spec.

### Event types

All events share a common envelope:

```json
{
  "type": "<event-type>",
  "run_id": "<run_id>",
  "seq": <int>,             // monotonic per-connection sequence number
  "ts": "<iso-8601-utc>",   // server timestamp
  "data": { ... type-specific payload ... }
}
```

Event types, in the order they appear in a healthy run:

| `type`            | Emitted when                        | `data` payload                                       |
|-------------------|-------------------------------------|------------------------------------------------------|
| `run_start`       | First event of every stream         | `{prompt, session_id}`                               |
| `iteration_start` | Each loop iteration begins          | `{iteration}` (1-indexed)                            |
| `tool_call`       | LLM requested tool(s)               | `{tool_calls: [{name, args}]}`                       |
| `tool_result`     | A tool finished                     | `{name, output}` (output truncated to 4 KiB)         |
| `message`         | LLM produced a final assistant message with no tool calls | `{content}`              |
| `final`           | Last event — run completed          | `{status, content, run_id, run_dir, session_id, iterations}` |
| `error`           | Only on unrecoverable exception     | `{message, status: "error"}`                         |

The `final` event is always sent, even if `status` is `max_iterations`,
`cancelled`, or `error`. After `final` (or `error`), the server closes
the connection. A client that sees the connection close without `final`
should treat it as a transport-level failure.

### Status mirroring `/chat`

`final.data.status` and `final.data.content` match the JSON returned by
`POST /chat` for the same prompt and session. Existing clients that
switch from `/chat` to `/chat/stream` get equivalent final state, plus
visibility into intermediate events.

### Session persistence

Identical to `/chat`:

- If `session_id` is set and a `SessionStore` is available, prior
  messages are loaded and prepended to the run.
- After the run completes (any terminal status), the new turn's
  messages — user prompt + assistant + tool results, no system
  messages — are persisted under that `session_id`.
- `final.data.session_id` echoes the request's `session_id` (`""` when
  absent), matching `/chat` behavior.

### Backpressure & transport

- `StreamingResponse(media_type="text/event-stream")` with a Python
  generator function as `content`.
- The generator yields one SSE line at a time per agent event.
- `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers are set
  to disable buffering by intermediaries (nginx, etc.).
- Each event is flushed as soon as it's yielded. FastAPI/Starlette's
  `StreamingResponse` flushes per yield for async generators.

### Cancellation

If the client disconnects mid-stream, Starlette raises a
`ClientDisconnect` inside the generator. The handler catches this,
cancels the in-flight agent run (the `AgentLoop` coroutine), and
exits. The session row is partially persisted up to the
disconnect point (consistent with how a regular `/chat` would behave if
its LLM call timed out halfway through — that's the existing semantics
of `_persist_new_turn`, which saves whatever new messages were produced
before the cancellation).

### Error handling

- Invalid request body → `422` before streaming starts (same as `/chat`).
- Blank `prompt` → `400` before streaming starts.
- Exceptions raised mid-run by the agent are caught inside the
  generator and emitted as an `error` event. The generator then
  finishes normally and closes the connection. No 5xx is returned
  after the stream has begun — SSE clients cannot easily recover from
  mid-stream HTTP status codes.

### Why these choices

- **Agent-level events, not token-level.** Token streaming requires
  modifying `ChatLLM` and `AgentLoop` to expose a streaming channel
  per model. Each provider (OpenAI, DashScope/Qwen, DeepSeek, Moonshot,
  Ollama) has subtly different streaming semantics. Phase 2.3 ships the
  higher-value feature (visibility into the loop) without that
  surface area. A future phase can add a `?stream=tokens` mode without
  breaking this endpoint.
- **Stateless per request.** Continuous bidirectional streaming over SSE
  is possible but awkward — SSE is naturally unidirectional, and
  reusing one connection for multi-turn complicates session lifecycle
  (when does prior context expire?). Expressing multi-turn via repeated
  requests with `session_id` matches how `/chat` already works and how
  most SSE clients (EventSource, `curl -N`, browser `fetch` with
  `ReadableStream`) expect to be used.
- **`/chat/stream` as a sibling endpoint.** Easier to test, easier to
  document, and existing `/chat` callers see no change. Content-Type
  negotiation on `/chat` was considered but introduces ambiguity for
  clients that don't send `Accept` and doubles the test matrix.

## Files

Create:

- `loop_agent/api/sse.py` — SSE event formatting helpers and the
  streaming generator function `stream_agent_events(prompt, session_id)`
  that wraps `AgentLoop.run` and emits events as the run progresses.
- `tests/test_sse.py` — `TestClient`-based tests for `/chat/stream`.

Modify:

- `loop_agent/api/routes.py` — add `POST /chat/stream` route returning
  `StreamingResponse`.
- `loop_agent/api/schemas.py` — `StreamChatRequest` (re-uses
  `ChatRequest`'s fields; small wrapper or alias).
- `README.md` — add Streaming section, example curl, update test count.

No changes to:

- `loop_agent/agent/loop.py` — reuse `event_callback` hook (already
  present from Phase 1) to surface iteration / tool events to the SSE
  generator. This is the existing extension point and avoids creating
  a parallel code path.

## Testing

`tests/test_sse.py` — minimal, deterministic, no real LLM calls.

Test cases:

1. `test_stream_emits_full_event_sequence` — monkeypatch `_run_agent`
   (or `AgentLoop.run`) to emit a deterministic sequence of
   `iteration_start`, `tool_call`, `tool_result`, `message`, `final`.
   Assert the SSE event order and final `status == "success"`.
2. `test_stream_includes_session_id_in_final` — request with
   `session_id="sess-1"`; assert `final.data.session_id == "sess-1"`.
3. `test_stream_blank_prompt_returns_400_before_streaming` — blank
   prompt → response is `400`, no `text/event-stream` body, generator
   never runs.
4. `test_stream_missing_prompt_returns_422` — request without `prompt`
   → `422`.
5. `test_stream_oversized_session_id_returns_422` — 257-char
   `session_id` → `422`.
6. `test_stream_handles_agent_exception_as_error_event` —
   monkeypatch `_run_agent` to raise; assert exactly one `error` event
   is emitted, connection closes cleanly, HTTP status is `200` (not 5xx)
   because the stream started successfully.
7. `test_stream_max_iterations_status_propagates` — fake run returning
   `{"status": "max_iterations", ...}`; assert `final.data.status ==
   "max_iterations"`.

All tests use FastAPI `TestClient` with the app created via
`create_app()`. No new dependencies.

## Documentation updates

README:

- New `## Streaming` section after the existing `## Sessions` section.
- Show `curl -N` example against `/chat/stream` and print one example
  event sequence.
- Update test count badge / test count paragraph at the bottom.
- Roadmap checkbox for "Streaming SSE" flipped to `[x]`.

## Backward compatibility

- `POST /chat` endpoint, request/response shape, and behavior unchanged.
- `GET/DELETE /sessions/{id}` unchanged.
- No new dependencies; existing `pyproject.toml` is sufficient.
- No breaking schema changes. `StreamChatRequest` is additive.

## Risks

| Risk                                                       | Mitigation                                                                 |
|------------------------------------------------------------|----------------------------------------------------------------------------|
| SSE buffering by proxies prevents real-time delivery       | Set `Cache-Control: no-cache` and `X-Accel-Buffering: no`                   |
| Generator raises after client disconnect                   | Wrap agent call in `try/except`, emit `error` event, log, close cleanly    |
| Long tool output floods the stream                         | Truncate tool result bodies to 4 KiB in the SSE event; full output still in TraceWriter JSONL |
| Eventual need for token streaming                          | Deferred; this endpoint's event envelope is roomy enough to add a `token` event type later without breaking clients that ignore unknown types |

## Open questions

None blocking. Deferred items (token streaming, server-initiated
keep-alives) are documented as future enhancements in the README
roadmap.