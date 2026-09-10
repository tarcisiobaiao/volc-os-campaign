## Findings

**1. Human approval is registered before the human sees any preview — high, verified.**
`PrepararPackMeta.tsx:82-95` — the same click that fetches the review also writes durable approvals (`criativosApi.decidir`, :94). `review` is only set at :88, so the per-image previews and blocker codes render *after* the approvals are already committed. The `checked` box at :82 is therefore blanket pre-consent over `selection.master_refs`, not "explicit checkbox after final image previews." The stated approval boundary is inverted. Split into two actions: review → render → checkbox → register.

**2. Scope change mid-loop leaves partial approvals with no record — high, verified.**
`:91-95` cancellation is cooperative and only checked *between* iterations. Changing account/pack/adset after K of N `decidir` calls leaves K durable approvals; `:32-33` then wipes `review`/`feedback`, so the operator sees no trace. Stale-response discard is correct for reads but wrong for writes: the write phase is not restartable-safe from the UI's own state. At minimum, surface committed refs on abort.

**3. `decidir` omits `versao` while the server matches on it — high, conditional.**
`revisao_de_midia.py:57-63` requires `int(d["versao"]) == versao` for an approval to count; the client (`:94`) sends only `{decisao, finalidade}`. Approval therefore binds to whatever version the server resolves at decide time, not the version the human reviewed at `:84`. If a master is re-versioned between the two calls, consent silently attaches to different bytes. Conditional on `decidir`'s server-side resolution; if it does not accept an explicit version, that is the fix.

**4. Blockers travel on two incompatible channels — high, verified.**
`:49-56` raise `ErroDeRegistroDeMidia` and abort the whole batch, while `:68-78` return a per-item result with a code. So MASTER_NOT_FOUND / ARCHIVED / CUSTODY_HASH_DIVERGED yield zero results and a message that names no `master_ref` (`:50,:53,:56`), collapsing to the generic client error at `:46`. This directly defeats "make progress and blockers legible": one bad image hides the status of the other N−1. These belong in `resultados` as non-`utilizavel` entries.

**5. Unsupported provenance is mislabeled, not rejected — medium, verified.**
`:64-67` — the comment states imported content needs server-resolved rights evidence "not supported here," yet any non-synthetic master falls through to `HUMAN_UPLOAD`. The unsupported case should fail closed, not be asserted as human-captured.

**6. `review` is an unbounded upload capability token — medium, conditional.**
`:107-110` submits `review!.resultados` verbatim; `reviewMatches`/`valid` check only ref-set identity and `manifest_sha256`, never freshness. Absent scope change, a review stays valid indefinitely across revocations or re-versioning. Safe only if `registrarMidiaMeta` re-verifies hash/version/approval server-side.

**7. Linear per-image evaluation with no progress — low.**
`:46` + `:79` serialize `politica.avaliar`; only the approval loop reports progress (`:93`).

**Verdict: request changes.** Upload gating (`:107`) and stale-read discard are sound; findings 1, 2 and 4 block the stated goal.
