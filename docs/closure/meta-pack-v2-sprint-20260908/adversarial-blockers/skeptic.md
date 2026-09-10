## Findings

**1. Batch review aborts on first bad asset — blockers become illegible (`revisao_de_midia.py:47-56`). Severity: high, verified.**
`revisar_pecas` raises `ErroDeRegistroDeMidia` inside the per-peça loop. One archived master or one diverged hash discards the results already computed and returns zero per-asset rows. The UI then shows a single sentence and no per-image reason — the opposite of the stated goal. The `INSPECTION_UNAVAILABLE` path at :68-78 already demonstrates the correct shape (append a non-`utilizavel` result, `continue`); custody failures should use it.

**2. Review verdict round-trips through the browser (`PrepararPackMeta.tsx:110`). Severity: high, conditional.**
`registrarMidiaMeta(accountRef, review!.resultados)` sends client-held `aprovacao_ref`/`utilizavel`/`politica` back as the upload input. If the registrar trusts any of those rather than re-deriving from `master_ref` + owned bytes, "exact complete review" is client-asserted. Also TOCTOU: a master can be archived or re-versioned between :98 and :110; `valid`/`reviewMatches` are client-side only. Not verifiable from these excerpts — must be confirmed server-side.

**3. Second review is not validated, but is reported as success (`:98-105`). Severity: moderate, verified.**
The first response is set-checked at :86-87; the re-review at :98 is not. A subset response sets `review` and prints "Conferência concluída… confira abaixo a liberação de envio" while `reviewMatches` (:54) silently disables upload with no stated reason. Feedback should key off `reviewMatches`, or apply the :86-87 check to `r`.

**4. Capability refresh failure erases state and swallows progress (`:101-104`). Severity: moderate, verified.**
`setCap(undefined)` before the await drops known capabilities; if `capacidadesMidiaMeta` rejects, `catch` at :46 shows a generic message, `cap` stays undefined until scope change, and the user is never told that approvals were registered and review passed. Refresh into a temp and assign only on success.

**5. Silent partial approval registration (`:91-95`). Severity: moderate, verified.**
Changing account/pack/adset mid-loop stops at :92 after N of M `criativosApi.decidir` calls succeeded. Durable approvals persist while `feedback`/`busy` are cleared at :33 — stale response discarded, side effects not. Surface the partial count on the next review instead of dropping it.

**6. Single-flight invariant is breakable (`:33` vs `:42`). Severity: low-moderate, verified.**
The effect sets `lock.current = null` while an action is in flight, so `run`'s guard no longer reflects outstanding requests. The `lock.current === id` check in `current()` prevents stale writes, but two overlapping in-flight mutations remain possible across an A→B→A scope cycle.

**7. Hash comparison is format-fragile (`revisao_de_midia.py:54`). Severity: low, verified.**
`!= "sha256:" + peca.content_sha256` assumes identical hex case and prefix; normalize both sides before comparing to avoid spurious `CUSTODY_HASH_DIVERGED`.

## Verdict

Request changes. #1 and #3-#4 defeat the stated legibility goal within these excerpts; #2 needs server-side proof before upload is enabled anywhere. Nothing here indicates the upload flag or authorization scope was improperly broadened.
