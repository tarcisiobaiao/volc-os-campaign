# Meta creative studio — parallel production and photographic blueprint

Status: **local implementation verified; live visual acceptance pending**. Work is
in the operational worktree on `execution/volc-os-operacao-80-20`. No commit,
push, Webgo change, migration, Meta mutation or paid generation in this sprint.

## Reference analysis and adaptation

Read the Aprova Ad Studio reference, without editing it: `creative_strategist.py`,
`image_generator.py`, `orchestrator.py`, the Meta sections of `prompts.py`, and its
realtime-progress design. The useful pattern is researched context → distinct
creative angle → spatial/photographic blueprint → image rendering. Its renderer
receives a composition, not another open-ended request to invent strategy.

Adapted into VOLC's existing typed agent/spec/approval pipeline rather than adding
another paid agent hop. Five art-direction fields reach the effective render
prompt: scene, treatment, composition, typography and palette/contrast. New
proposals prefer a congruent photographic scene and one short message, not dense
infographics, diagram cards or generic icons. Emotional angles are hypotheses,
not claims about the viewer; factual qualifiers and the landing page's actual
next step remain intact. External ad copy does not become image text.

Not imported: client branding, colors, logos, audience assumptions, credentials,
model choices, fake weighted progress, or cancelling accepted image work when a
browser disconnects. Existing `gpt-image-2` / `medium` constants remain unchanged.
Official references checked: [GPT Image 2](https://developers.openai.com/api/docs/models/gpt-image-2)
and [image generation](https://developers.openai.com/api/docs/guides/image-generation#earlier-gpt-image-models).
Concurrency does not bypass the account's rate limits and is not a latency guarantee.

## Execution and interface

- Three image-production slots shared across executors/event loops in one process,
  including file persistence. Both concept jobs and their formats can progress
  concurrently. This is not a distributed semaphore across server replicas.
- Register generation bridges before dispatch, so GET can discover the work while
  the POST is still pending. The local POST still waits for completion; the gallery
  no longer depends on that response to show progress.
- On generate, immediately open the assets gallery with non-asset placeholders.
  Registry polls are read-only; job polling updates completed images independently.
  Each placeholder occupies its image's position. Loading respects reduced motion.
- Persisted queued/running/ready/failed/cancelled states determine visible counts;
  no invented percentage, elapsed ETA or claim of all-success for partial work.
- Retain known thumbnails and selection on transient GET failure. Terminal callback
  refreshes operation details once per job set, without reloading the browser or
  submitting another paid generation.
- Cooperative cancellation prevents queued slots but retains in-flight results.
  Retry preserves ready renditions; no automatic new image-version purchase.

## Compatibility

`volc.art-direction/2` explicitly opts a newly proposed direction into
`volc.creative-spec/2`. The five blueprint fields are required by that spec.
Unmarked historic directions retain v1 compilation; nested serialization omits the
new field when absent to preserve historical hashes and frozen approvals. If a
model omits the marker, the existing legacy behavior remains; this is not silently
promoted to v2. Tests cover effective prompt persistence and model/quality payload
using fake transport, not an actual provider call.

**For the next test, create a new strategy or refine unfrozen pieces.** Merely
requesting a new image version of an old approved infographic still uses the old
approved direction. Inspect the proposed scene and headline before authorizing.

## Verification and limits

- Root integration: 135 backend tests (execution, concurrency, blueprint, agent,
  approval and adapter). Additional worker/studio suites passed in the executor
  subtask. Fake provider and repository; no live generation or database proof here.
- Frontend: 65 tests in 12 files passed; Vite production build passed. Global
  TypeScript still reports inherited errors outside the creative files.
- Browser: actual gallery component with hermetic fixtures, 375/1440 × light/dark,
  initial placeholders → first image → partial completion, keyboard/selection,
  reduced motion, zero overflow/JS errors. See `browser-qa.md`; it records the exact
  scope and pre-polish captures. Not authenticated full-page QA.
- The placeholder footer and initial secondary count were adjusted after those
  captures. Unit tests cover the count and progressive states.
- Local frontend 8080 and backend health 8010 returned HTTP 200.
- No new image quality claim, CTR/conversion gain, or paid throughput benchmark.
  The user's failed image from the prior run was not diagnosed from the screenshot.

Operational memory: P11-T17 remains **partial**, node
`doc:meta-creative-closure-20260909`, capability `cap_creative_engines`.

## Operator test

1. Open `/trafego/meta/assistente-criativo`; create a new briefing with the actual LP.
2. Review extracted facts and the proposed photographic angles, headline and CTA.
3. Approve chosen pieces, select formats and explicitly authorize the render count.
4. Confirm that the gallery opens immediately, shows pending/active states, and
   progressively replaces placeholders with files, including any per-piece error.
5. Review actual composition, wording and legibility at mobile size. Keep or refine
   based on the result; a passing software test is not creative approval.
