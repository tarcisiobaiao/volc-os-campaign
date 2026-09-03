# Counterproofs

## Red proof on authorized base
Command run from a `mktemp` archive of `207e91f1da290130e8d02b78c3ba1c8e9a761111` with the new red-proof script copied in:

```bash
PYTHONPATH=. python3 docs/closure/hermes-p09-t17-campaign-birth-authority-v1/contraprova-vermelha-bypass.py
```

Result: exit `1`, `bypass_reproduzido=true`, `chamadas_no_adapter=1`, fake created resource `customers/9999999999/campaigns/8888888888`, no real network.

## Fixed-tree proof
Same command on the fixed worktree exits `0`: `AutorizacaoAusente`, `chamadas_no_adapter=0`, `recibos_em_disco=0`.

## Minimum counterproof map
1. CLI direct without authorization: `test_o_cli_de_escrita_continua_aposentado` + `prova_cli_subir_aposentado...`.
2. Direct writer import: `caso_sem_autorizacao`, `caso_autorizacao_construida_a_mao`, direct `mutar` one-use proof.
3. Alternative route: structural gate and remover create/update static check.
4. n8n without contract: versioned workflow static test + paid-set contract rejection.
5. Missing/divergent account/MCC: `emitir` parameterized cases and `caso_autorizacao_de_outra_conta`.
6. Paid destination missing/divergent: `emitir` parameterized cases plus inherited route barrier 3.
7. Paid keyword set missing/divergent/mutated: `emitir` parameterized cases plus inherited portao conjunto pago.
8. Measurement blocked: `emitir` smart-bidding cases and readiness gate tests.
9. Ledger absent/unavailable: `test_trafego_ledger.py` and `scripts/gate_sem_mutacao_google.py`.
10. Campaign never ENABLED: `caso_nascimento_enabled`, route approved-flow PAUSED assertion.
11. `validate_only` not creation: `caso_validate_only_nao_exige_autorizacao`.
12. Timeout/no response: ledger tests keep `sem_resposta` non-retryable.
13. Idempotent repeat: `caso_autorizacao_uso_unico` rejects second call after one fake service call.
14. Unsupported channel: Demand Gen/PMax named rejection tests.
15. Any gate refusal = zero adapter calls: sentinel tests in `volc_ads/testes_subir.py` and backend P09-T17 tests.
16. Frontend cannot declare success without receipt: response receipt contains `autorizacao_de_nascimento` without signature.
17. Tests/fixtures keep fake adapters: all tests run with fake clients/sentinels and no credential read.
18. Approved canonical flow reaches fake boundary exactly once and PAUSED: `test_o_fluxo_aprovado_chega_ao_boundary_uma_vez_e_pausado`.
