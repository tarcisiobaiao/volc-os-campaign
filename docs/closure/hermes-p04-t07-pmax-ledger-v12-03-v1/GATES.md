# Gates da lane v12_03 — execução verificada

**Data:** 2026-09-01
**Branch:** `sprint/hermes-p04-t07-pmax-ledger-v12-03-v1`
**Base:** `36bec04ee1cc9f85c2db6d0d082be6a39350a421`
**Executor canônico:** Claude Code Opus, `session_id=06934060-2248-40bd-ab03-15ac039e1297`

## Resultado curto

| Gate | Resultado |
|---|---:|
| Ciclo SQL aplicar → provar → rollback → reaplicar | **171 ok / 0 falhas** |
| Focais PMax + persistência + contrato + v12_03 | **257 passed / 0 failed** |
| `backend/tests` no venv do repo | **2136 passed / 101 skipped / 0 failed** |
| `volc_ads` no venv do repo | **706 passed / 0 failed** |
| `git diff --check` | **limpo** |
| `compileall` focado | **limpo** |
| JSON dos artefatos | **válido** |
| Varredura de segredos | **sem segredo real**; somente literais de teste e senha descartável do container |
| Ausência de Google Ads mutate na lane | **sem chamada alcançável**; hits restantes são comentários/testes/capacidades pré-existentes |

## Comandos executados

```bash
# SQL em Postgres descartável Docker; sem Supabase oficial
bash scripts/provar-google-inteligencia-v12_03.sh
# => passaram 171 · falharam 0
# => CICLO v12_03 COMPLETO: aplicar → provar → reverter → reaplicar

# focais exigidos
python3 -m pytest backend/tests/test_google_inteligencia_pmax.py \
                  backend/tests/test_google_inteligencia_persistente.py \
                  backend/tests/test_trafego_contrato_canais.py \
                  backend/tests/test_google_inteligencia_v12_03_releitura.py \
                  -q -p no:randomly
# => 257 passed, 5 warnings

# suíte backend no venv criado a partir de backend/requirements-dev.txt
python3 -m venv .venv-p04-t07
. .venv-p04-t07/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest backend/tests -q -p no:randomly
# => 2136 passed, 101 skipped, 6 warnings

# suíte volc_ads no mesmo venv
python -m pytest volc_ads -q -p no:randomly
# => 706 passed, 25 warnings

python3 -m compileall -q volc_ads/inteligencia_google backend/app/trafego \
  backend/tests/test_google_inteligencia_pmax.py \
  backend/tests/test_google_inteligencia_persistente.py \
  backend/tests/test_trafego_contrato_canais.py \
  backend/tests/test_google_inteligencia_v12_03_releitura.py
# => exit 0

git diff --check
# => exit 0

python3 -m json.tool docs/closure/hermes-p04-t07-pmax-ledger-v12-03-v1/MATRIZ-CONTRAPROVAS.json
python3 -m json.tool docs/closure/hermes-p04-t07-pmax-ledger-v12-03-v1/curation-handoff.json
# => exit 0
```

## Observações honestas

1. A primeira tentativa de `backend/tests` fora do venv correto falhou por ambiente: faltava `python-docx`, `pytest-asyncio` e o FastAPI global era `0.133.1` em vez do `0.115.6` provado pelo projeto. Depois de criar `.venv-p04-t07` com `backend/requirements-dev.txt`, a suíte passou. O venv foi removido antes do fechamento para não sujar a árvore.
2. A primeira versão da contraprova SQL tratava `vazio_confirmado` com `quantidade null` como recusa obrigatória. O comportamento medido da v12_01 aceita esse caso, preservando ausência distinta de zero. O teste foi corrigido para medir a invariância existente sem alterar v12_01.
3. Nenhum comando tocou o Supabase oficial; o SQL rodou apenas em container Docker `postgres:16-alpine` descartável.
4. Nenhum comando abriu `/root/google-ads.yaml`; não houve chamada Google Ads real nesta lane.

## Revisão focal independente

Codex/Gemini não estavam disponíveis (`command -v` vazio); usei Claude Opus fresco como fallback autorizado.

- Reviewer session_id: `98c6cb93-5b8a-4864-8824-11583543a672`
- Achado bloqueante B1: releitura truncada podia parecer completa por `order desc` + `limit`.
- Correção aplicada: `coletas_por_identidade` agora pede `limite + 1` e levanta `ErroReleitura` se vier sentinela; teste `test_i_releitura_truncada_nao_vira_fotografia_completa` cobre o caso.
- Achados N1/N2/N3 classificados como não bloqueantes e registrados no `MATRIZ-CONTRAPROVAS.json`/`curation-handoff.json`.
