# Real-time progress sync, precise errors, parallel generation, gpt-image-2 sizing

**Date:** 2026-06-17
**Status:** Approved — implementing

## Problem

1. **Loading desync** — `LoadingScreen` shows a fake time-based curve; checks turn green and
   "empacotando" appears while the backend is still rendering image 2/3. Progress is a guess,
   not real state.
2. **Errors swallowed** — `main.py` returns a generic `"Internal server error"` for every
   exception, so the real OpenAI cause (no balance / `insufficient_quota`, invalid key, rate
   limit, content block) never reaches the user; only the terminal shows it.
3. **Too slow** — images render sequentially with a 3s delay between each (~109s for 4).
4. **Format safety** — confirm every front-end aspect ratio maps to a gpt-image-2-valid size.

## Decisions (user-approved)

- **Transport:** SSE streaming over `POST /generate/stream` (fetch + ReadableStream).
- **Loading UI:** live real thumbnails as each image completes, synced to real backend state.
- **Errors:** dedicated error screen with the exact translated cause + retry.
- **Parallelism:** bounded concurrency (semaphore), default 3, configurable.
- **Quality:** `IMAGE_QUALITY=medium`.

## Event protocol (SSE)

`POST /generate/stream` → `text/event-stream`. Body = existing `GenerateRequest`.

| `event:` | `data:` payload |
|---|---|
| `phase` | `{"phase":"research"\|"blueprints"\|"packaging"}` |
| `image_start` | `{"n":3,"total":4}` |
| `image_done` | `{"n":3,"total":4,"name":"aprova-ad-3.png","dataUrl":"data:image/png;base64,…"}` |
| `image_failed` | `{"n":3,"total":4,"message":"…"}` |
| `done` | `{"total":4,"delivered":3}` |
| `error` | `{"code":"insufficient_quota","message":"…(PT)…"}` |

ZIP is **not** transferred — the frontend collects images from `image_done` and builds the
`.zip` client-side with JSZip (already a dependency). One connection.

## Backend

- **`app/errors.py`** (new) — `PipelineError(code, user_message, raw)` and
  `translate_openai_error(exc) -> (code, pt_message)`. Single source of truth. Branches:
  `AuthenticationError`→invalid_api_key; 429 with code `insufficient_quota`→insufficient_quota;
  other `RateLimitError`→rate_limit; content/moderation `BadRequestError`→content_policy;
  `PermissionDeniedError`/model_not_found→no_access; `APIConnectionError`/timeout→connection;
  fallback→`Erro da OpenAI: <msg>`.
- **`app/progress.py`** (new) — event dataclasses + `to_sse()`.
- **`orchestrator.py`** — pipeline becomes `async def run_events(request)` (async generator)
  yielding the events above; legacy `run()` is implemented by draining it. Image step uses
  `asyncio.Semaphore(IMAGE_CONCURRENCY)`; per-image task: emit `image_start` → generate →
  **quality-review inline** → emit `image_done`/`image_failed`. Transient `RateLimitError`
  retried (2x, 2s/4s backoff); fatal account errors raise `PipelineError` and cancel the rest.
- **`creative_strategist.py`** — `generate_blueprint` wraps OpenAI errors → `PipelineError`
  on fatal; `research_context` keeps degrading gracefully.
- **`openai_image.py`** — size fallback picks orientation-matched standard size and the final
  resize does **crop-to-fill** (no stretch) when aspects differ; pad for out-of-1:3..3:1 ratios.
- **`main.py`** — add `POST /generate/stream` (`StreamingResponse`, cancels pipeline on client
  disconnect). Error handlers map `PipelineError`/`OpenAIError` to the specific message + code
  for the non-stream path too. Keep `POST /generate` (n8n / fallback). Exact error always logged.
- **`config.py` / `backend/.env`** — `IMAGE_QUALITY=medium`, `IMAGE_CONCURRENCY=3`.

## gpt-image-2 sizing (verified against OpenAI docs)

Constraint confirmed: free `WIDTHxHEIGHT`, edges ÷16, aspect ratio **1:3–3:1**, max 3840×2160.
All 8 current front formats comply; `native_generation_size()` already adapts (render valid +
small → Pillow upscale to exact pixels). Hardening: unit test asserting every front format →
valid native size; crop-to-fill (not stretch) on the fallback path; pad for any future
out-of-envelope ratio.

## Frontend

- **`src/lib/api.ts`** — `streamCreatives(request, handlers, signal)`: POST stream URL
  (`${VITE_API_URL}/stream`), read `body.getReader()`, parse SSE frames, dispatch
  `onPhase/onImageStart/onImageDone/onImageFailed/onDone/onError`. Keep `generateCreatives`
  fallback for the n8n webhook.
- **`LoadingScreen.tsx`** — remove the fake timer. Props: `phase`, `current`, `total`,
  `images[]` (completed thumbnails), `error`. Progress % from real counts
  (research 0–12 → blueprints 12–25 → images 25 + completed/total·65 → packaging 90–99 → 100),
  with a small bounded creep between milestones so the bar never freezes. Grid shows real
  thumbnails for done slots, spinner for active, placeholder for pending.
- **`ErrorScreen.tsx`** (new) + `"error"` AppState in `Index.tsx` — exact cause + code, with
  "Tentar novamente" and "Voltar". `handleGenerate` runs the stream, accumulates images, builds
  the zip on `done`, routes to `error` on `onError`.

## Tests

- `translate_openai_error` — each branch.
- `run_events` — event sequence with `MockImageProvider` (phase→image_start→image_done×N→done).
- All front formats → valid gpt-image-2 native size (÷16, 1:3–3:1, ≤3840×2160).
- SSE frame parser (frontend) — feed a sample byte stream, assert dispatched handlers.
