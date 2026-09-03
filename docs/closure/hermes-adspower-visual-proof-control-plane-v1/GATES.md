# Gates — Secure AdsPower Broker + Visual Proof Control Plane V1

**Data:** 2026-09-02  
**Escopo:** gates locais/herméticos; nenhuma chamada AdsPower real, Supabase oficial write, Postiz, publicação ou deploy.

## Gates de entrada reproduzidos por Bia antes de editar

| Gate | Comando | Resultado |
|---|---|---:|
| Domínio Visual Proof | `python3 -m pytest backend/tests/test_visual_proof_dominio.py -q` | `73 passed` |
| Controle/aplicação | `python3 -m pytest backend/tests/test_visual_proof_controle.py -q` | `32 passed` |
| Fronteira Cofre + prontidão backend | `python3 -m pytest backend/tests/test_visual_proof_fronteira_cofre.py backend/tests/test_cofre_prontidao_visual.py -q` | `39 passed` |
| E2E broker hermético | `python3 -m pytest backend/tests/test_adspower_broker_hermetico.py -q` | `43 passed` |
| Frontend prontidão | `npm test -- --run src/features/asset-vault/__tests__/prontidao.test.ts src/features/asset-vault/__tests__/prontidao-visual.test.tsx` | `30 passed` |
| Prova estrutural | `python3 scripts/provar_visual_proof_hermetico.py --autoteste && python3 scripts/provar_visual_proof_hermetico.py` | `21 provas, 0 falhas`; `veredito: hermetico` |
| Sintaxe/imports | `python3 -m compileall -q backend/app/visual_proof tools/adspower-broker scripts/provar_visual_proof_hermetico.py` | OK |
| Diff whitespace | `git diff --check` | OK |

## Resultados reportados pelo Claude e revalidação

| Reporte Claude | Reproduzido por Bia? | Nota |
|---|---|---|
| backend focal `254 passed` | será reexecutado em gate final | Claude rodou antes de encerrar; Bia reexecutou subconjuntos equivalentes e depois roda bateria final |
| structural proof `21 provas, 0 falhas` | sim | reproduzido após correção única |
| frontend readiness `54 passed` | parcialmente | Bia rodou os 2 arquivos novos: `30 passed`; total global depende do conjunto de testes Asset Vault selecionado |
| boundary/backend adicional `29 passed` | incorporado no gate fronteira/cofre `39 passed` | conjunto atual maior |

## Correção única feita por HERMES_CODEX_REVIEW

1. Frontend removido `title={artefato.referencia}` para não expor a referência privada inteira no DOM.
2. Saúde do broker deixou de devolver `artefatos_dir` absoluto; agora informa apenas `artefatos: diretorio_privado_configurado`.
3. Testes adicionados para ambos.

## Gates finais executados por Bia

| Gate | Comando | Resultado |
|---|---|---:|
| Backend focal completo da lane | `python3 -m pytest backend/tests/test_visual_proof_dominio.py backend/tests/test_visual_proof_controle.py backend/tests/test_visual_proof_fronteira_cofre.py backend/tests/test_cofre_prontidao_visual.py backend/tests/test_adspower_broker_hermetico.py -q` | `187 passed`, 5 warnings |
| Frontend focal | `npm test -- --run src/features/asset-vault/__tests__/prontidao.test.ts src/features/asset-vault/__tests__/prontidao-visual.test.tsx` | `30 passed` |
| Frontend Asset Vault proporcional | `npm test -- --run src/features/asset-vault` | `54 passed` |
| E2E broker hermético | incluído no backend focal + executado isolado | `43 passed` |
| SSRF/redirect/endpoint | `python3 -m pytest ... -k 'ssrf or redirect or privado or privada or dominio or url or endpoint'` | `82 passed, 66 deselected` |
| Idempotência/concorrência/lease/cleanup/timeout | `python3 -m pytest ... -k 'idempot or concorr or lease or replay or cleanup or timeout'` | `4 passed, 71 deselected` |
| Prova estrutural + JSON | `python3 scripts/provar_visual_proof_hermetico.py --json`; `python3 -m json.tool`; `--autoteste` | `veredito: hermetico`; `21 provas, 0 falhas` |
| Imports/sintaxe | `python3 -m compileall -q backend/app/visual_proof tools/adspower-broker scripts/provar_visual_proof_hermetico.py` | OK |
| TypeScript | `npx tsc --noEmit` | exit `0` |
| Build | `npm run build` | exit `0`; Vite chunk warnings herdados |
| Diff whitespace | `git diff --check` | OK |
| Scanner contextual de segredo/sentinela | scan sobre produção + closure, permitindo apenas vetores negativos em testes/script | `0` hits |
| Backend amplo proporcional | `python3 -m pytest backend/tests -q` | `2719 passed, 135 skipped, 20 failed` — falhas fora da lane |
| Frontend amplo proporcional | `npm test -- --run src/features/asset-vault src/components src/pages --passWithNoTests` | `927 passed, 3 skipped, 8 failures/suites` — falhas fora da lane |

### Falhas amplas herdadas / fora do ownership

Backend amplo falhou em `backend/tests/test_criativo_execucao.py` por plugin async ausente e em `backend/tests/test_criativo_rotas_equivalentes.py` por FastAPI `0.133.1` vs golden `0.115.6`. Esses arquivos/caminhos não foram tocados pela lane.

Frontend amplo falhou em testes de `settings/meta-capi` e importações de hub/inventário por `Missing Supabase environment variables`/expectativa pré-existente. Esses caminhos não foram tocados pela lane.

Prova executada: `git diff --name-only origin/volc-os-v2 -- <arquivos/caminhos falhos>` retornou vazio; `touched_forbidden` retornou `none`.
