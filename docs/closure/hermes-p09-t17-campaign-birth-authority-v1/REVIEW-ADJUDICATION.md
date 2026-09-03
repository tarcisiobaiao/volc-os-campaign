# Review and adjudication

## Requested reviewers

- Codex CLI: `command -v codex` returned empty. Literal status: `CODEX_REVIEW_NOT_AVAILABLE` as a CLI provider in this container.
- Gemini CLI: `command -v gemini` returned empty. Literal status: `GEMINI_REVIEW_NOT_AVAILABLE`.
- No provider harness was installed or repaired inside this mission.

## Fallback static review

A Claude fallback static review was run on the initial tracked diff. It returned several blockers. Bia/Hermes adjudication:

| Finding | Adjudication | Action |
|---|---|---|
| New files not included in diff | Procedural, caused by untracked files not shown to reviewer | `git add -N` used before later full diff; not a product blocker |
| `emitir()` mintable in-process | Partly valid limitation | Kept structural gate; documented as remaining risk. Production emitter restricted to `backend/app/routers/trafego.py`. |
| `mutar()` did not recompute payload impression | **Valid acceptance blocker** | Fixed: `volc_ads.gads.client.mutar` now recomputes `autoridade.impressao_das_operacoes(operacoes)` and compares/uses real bytes before consuming authorization. Added `writer recalcula impressão` proof. |
| Route catches exception base | Not valid: `AutorizacaoAusente`, `AutorizacaoJaUsada`, and `NascimentoAtivo` inherit from `AutorizacaoInvalida` | No code change |
| Test arms write env | Non-blocking test-safety concern; client is faked and restored | No production change; noted for future cleanup |
| `caso_nada_pede_sozinho` relaxed | Valid stale inherited assertion, not P09-T17 product blocker | Reproduced failing on base; corrected to narrower contract: importing `isencao` is allowed, auto-filling exemption fields is not |

A second fallback static review attempt on the full diff ended with `error_max_turns` and no substantive review text; not used for adjudication.

## Bia/Hermes adversarial review result

After the corrective round, the material acceptance blocker found in review was closed with an executable counterproof. Remaining limitations are explicitly recorded in `REMAINING-RISKS.md` and do not leave an identified reachable repository path that can create campaign outside the authority without failing the structural gate.
