# P09-T17 — Authority Matrix

| Producer | Status | Write capability after fix | Proof |
|---|---:|---|---|
| `POST /api/trafego/subir` | CANÔNICO | emits signed one-use `Autorizacao` only after account, human approval, paid destination, paid keyword set, measurement, ledger, idempotency and PAUSED gates | `backend/tests/test_p09_t17_autoridade_de_nascimento.py`, `scripts/gate_sem_mutacao_google.py` |
| `volc_ads.subir.subir` direct import | DELEGADO | refuses `AutorizacaoAusente`; verifies signature/account/MCC/channel/plan and payload PAUSED before mode gate | `python3 -m volc_ads.testes_subir` cases |
| `volc_ads.gads.client.mutar` direct import | DELEGADO | consumes authorization before client/network and rejects reuse | `caso_autorizacao_uso_unico` |
| CLI `volc_ads.subir --subir` | RECUSADO | stable retirement message; no writer call | P09-T17 tests + existing CLI proof |
| versioned n8n workflows | RECUSADO/read-only | no versioned Google Ads mutate tokens; cluster without paid-set contract refused | P09-T17 n8n tests |
| Demand Gen / PMax | RECUSADO | not birth-supported; named failure before executor | P09-T17 channel tests |
| Search/Display builders | DELEGADO | builders construct payload but do not own write boundary | structural gate |
| admin/remover | LEGADO/non-birth | remover statically remove-only, not create/update | structural gate |

Acceptance claim is limited to reachable/versioned code paths in this repo. Live n8n was not touched by hard stop.
