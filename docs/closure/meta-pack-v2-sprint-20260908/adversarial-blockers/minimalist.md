## Findings

**1. `revisao_de_midia.py:49-56` — abort-on-first-peça destroys the stated goal. Severity: high. Verified.**
Three conditions (`MASTER_NOT_FOUND`, `ARCHIVED`, `CUSTODY_HASH_DIVERGED`) `raise` out of the loop, so one bad ref collapses the whole batch into a single opaque error and the operator never learns the status of the other images. The same function already demonstrates the right shape at lines 68-78, where unavailability is appended as a per-item result with a `codigo`. Make these three per-item results with `utilizavel: False` and the existing codes; keep raising only for authorization failures. This is also the cheaper path — it deletes the frontend's need to distinguish thrown vs. returned blockers.

**2. `PrepararPackMeta.tsx:88-95` — displayed review goes stale on partial approval failure. Severity: medium-high. Verified.**
`setReview(existing)` publishes the pre-approval snapshot; the loop then approves refs one by one; if `decidir` throws at index *k*, `run`'s catch sets a generic error and `review` still shows all *k* approved refs as `META_ASSET_FINAL_APPROVAL_REQUIRED`. Progress made is invisible and the blocker isn't attributed to a ref. Cheapest fix: don't `setReview` before the loop, and on failure include the failing `master_ref` in the message.

**3. `PrepararPackMeta.tsx:23,36,49` — `loadedScope` is redundant state. Severity: low. Verified.**
`pack` is cleared on every scope change (line 32) and only assigned under the `scopeRef.current === scope` guard (line 36), so `pack !== undefined` already implies `loadedScope === scope`. Delete the state, the setter, and the first conjunct of `valid`.

**4. `PrepararPackMeta.tsx:86-87` vs `54-56` — the exactness check exists twice. Severity: low. Verified.**
The throw at 87 guarantees `reviewMatches` for any `review` ever set, and the effect resets `review` on scope change, so `reviewMatches` (54-56) can never be false when `review` is defined. Keep the throw (it carries the "nenhuma aprovação registrada" guarantee); drop `reviewMatches` from line 107's guard, which already tests `valid`.

**5. `PrepararPackMeta.tsx:26-28,31,43-47` — four overlapping in-flight guards. Severity: low. Verified.**
`cancelled`, `live`, `scopeRef`, and `sequence`/`lock` all encode "is this response still wanted." `sequence` only covers cases `scopeRef` already rejects, since the effect nulls the lock on every scope change. Collapse to `scopeRef` + lock.

**6. `PrepararPackMeta.tsx:101-104` — `setCap(undefined)` then refetch. Severity: low. Conditional.**
Blanks `policyReady` mid-action for a flicker; assigning `updatedCap` directly is sufficient. Conditional on whether any consumer outside this excerpt needs the intermediate undefined.

**Verdict: request changes.** Finding 1 is a genuine goal miss and must land; 2 is a real correctness/legibility defect. 3-6 are pure subtraction and should land with them rather than as a follow-up.
