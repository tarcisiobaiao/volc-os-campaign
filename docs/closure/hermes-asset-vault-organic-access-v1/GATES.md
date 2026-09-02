# Gates — `hermes-asset-vault-organic-access-v1`

**Data:** 02/09/2026 · **Branch:** `sprint/hermes-asset-vault-organic-access-v1`
**Base:** `c8ca8628e83742dd7da5242f0a015f76292aafe7`
**Sessão Claude:** `553b5b9d-aa0e-4e87-9981-766952b591c7`
**Nota de procedência:** Claude Code encerrou a retomada com sucesso, mas sua camada de permissão impediu `python3`, `node` e `git add`. Hermes/Bia executou os gates e commits **após** o executor terminar, não em paralelo.

---

## 1. Gates verdes da missão

| # | Gate | Comando real | Resultado |
|---:|---|---|---|
| 1 | Autoridade Supabase | `python3 scripts/verificar_autoridade_supabase.py` | **PASSOU** — único destino oficial: `https://database.agenciavolc.com.br` |
| 2 | Graph freshness check | `python3 scripts/atualizar_grafo_volc_os.py --check` | **FALHOU controlado** — `UPDATE_STATUS.json ausente`; registrado como limitação, sem reconstruir grafo/curadoria/Roadmap |
| 3 | Testes focais Cofre + broker | `python3 -m pytest backend/tests/test_cofre_ativos.py backend/tests/test_cofre_broker.py -q` | **176 passed**, 5 warnings herdados |
| 4 | Autoteste onboarding | `python3 scripts/onboarding_pagina_facebook.py --autoteste` | **56/56 verificações passaram** |
| 5 | Autoteste broker | `cd backend && python3 -m app.asset_vault.broker.cli --autoteste` | **PASSOU** — recusas sem rede, sem AdsPower e sem 1Password |
| 6 | Preflight broker sem rede | `cd backend && python3 -m app.asset_vault.broker.cli --preflight --perfis-permitidos exemplo` | **PASSOU** — loopback, ações permitidas/bloqueadas e bearer ausente como booleano |
| 7 | Smoke 1Password CLI | `python3 tools/onepassword-smoke/run.py --autoteste` | **PASSOU** — 0 falhas; prova canário sem eco |
| 8 | Smoke 1Password MCP | `python3 tools/onepassword-mcp-smoke/run.py --json` | **BLOQUEADO HONESTO** — `blocked/binario_ausente`, exit 10; não há servidor MCP nesta máquina |
| 9 | Frontend Asset Vault | `npm test -- --run src/features/asset-vault` | **40 passed** em 3 arquivos |
| 10 | TypeScript baseline | `./node_modules/.bin/tsc --noEmit -p tsconfig.app.json` | **76 erros herdados**, **0** em `src/features/asset-vault` |
| 11 | Build frontend | `npm run build` | **PASSOU**; warning herdado de chunk grande/dynamic import |
| 12 | Python syntax | `python3 -m compileall -q backend/app/asset_vault backend/tests/test_cofre_broker.py` | **PASSOU** |
| 13 | Diff whitespace | `git diff --check` | **PASSOU** |
| 14 | Ownership proibido | lista de paths alterados vs regex de paths proibidos | **PASSOU** — zero alterações em criativo, n8n, tráfego, Roadmap, curadoria, grafo, Orakul |
| 15 | Scanner segredo/diff | scanner custom em arquivos alterados | **PASSOU COM CANÁRIOS** — sem chave real; achados são fixtures/canários/gramática, não valores reais |
| 16 | API/artefatos sem referência real | varredura de docs/closure + rota/prontidão | **PASSOU** — docs usam apenas forma mascarada/descrição; API não projeta localizador |

---

## 2. Gates ampliados / baseline herdado

### Backend completo

Comando:

```bash
python3 -m pytest backend/tests -q
```

Resultado:

```text
20 failed, 2633 passed, 135 skipped, 23 warnings
```

As 20 falhas estão em arquivos fora do ownership desta missão:

- `backend/tests/test_criativo_execucao.py`
- `backend/tests/test_criativo_rotas_equivalentes.py`

Esses testes pertencem à frente de fábrica criativa/P17, explicitamente fora do escopo. A missão não editou `backend/app/criativo/**`, `volc_ads/criativo/**` ou `services/creative_engine/**`.

### TypeScript

Comando:

```bash
./node_modules/.bin/tsc --noEmit -p tsconfig.app.json
```

Resultado:

```text
exit_code=2
error_count=76
ts_errors_asset_vault=0
```

Interpretação: baseline herdado continua vermelho, mas esta missão não adicionou erro TypeScript no Asset Vault.

### Node install

`npm ci` falhou porque `package.json` e `package-lock.json` já estavam fora de sincronia na base (`esbuild@0.28.2` ausente no lock). Para não alterar `package-lock.json`, Hermes rodou:

```bash
npm install --package-lock=false --no-audit --no-fund
```

Resultado: dependências instaladas em `node_modules`, **sem alteração rastreada** em `package.json`/`package-lock.json`.

---

## 3. Segurança e não-mutação

| Verificação | Estado |
|---|---|
| Escrita no Supabase oficial | **não aconteceu** |
| Migration aplicada | **não aconteceu** |
| Leitura autenticada no Supabase oficial | **não aconteceu** |
| AdsPower aberto/iniciado/consultado | **não aconteceu** |
| 1Password consultado/resolvido | **não aconteceu**; só smokes/autotestes locais |
| Meta/Facebook publicação/alteração | **não aconteceu** |
| Deploy | **não aconteceu** |
| Roadmap/curadoria/grafo editados | **não aconteceu** |
| Segredo real lido/impresso/hashado | **não aconteceu** |

---

## 4. Observações aceitas

1. `graphify-out/UPDATE_STATUS.json` ausente é limitação de base/worktree; não foi consertada por proibição explícita de editar/reconstruir grafo.
2. `tools/onepassword-mcp-smoke/run.py` não possui `--autoteste`; o comando real é `--json`. O resultado correto nesta VPS é `blocked/binario_ausente`.
3. O broker só prova localmente recusas, loopback, allowlist, idempotência em processo e recibo sanitizado. Nenhuma Local API AdsPower real foi exercitada.
4. A publicação permanece impossível por contrato: `P12-T09` ainda não existe e `prontidao` nomeia isso como bloqueio.

---

## 5. Revisão focal fresca

**Revisor:** Claude Opus fresco, fallback autorizado porque `codex` e `gemini` não existem nesta VPS. Primeira tentativa com pacote grande tentou ferramentas Google Drive indevidas e parou em `max_turns`; foi descartada. Segunda tentativa recebeu pacote reduzido, sem ferramentas, e completou.

**Veredito:** nenhum bloqueio confirmado no código visível. O revisor pediu verificação local de quatro pontos truncados; Hermes/Bia verificou diretamente:

| Item | Verificação local | Estado |
|---|---|---|
| `sonda` controlável pela request | rota chama `casos.prontidao(ativo_id)` e o caso de uso chama `pron.avaliar(..., sonda=None)` | **ok** |
| broker exposto por HTTP | `rotas.py` não importa nem invoca `broker.*`; broker é CLI/sidecar | **ok** |
| ações mutantes em `ACOES` | catálogo permitido contém só `status`, `inventario_perfis`, `inventario_grupos`, `estado_do_perfil`, todos `muta=False`; mutantes ficam em `ACOES_QUE_EXIGEM_CHECKPOINT` e são recusados por nome | **ok** |
| projeção AdsPower | `CAMPOS_DE_PERFIL` é allowlist e exclui `username`, `password`, `cookie`, `fakey`, `proxy_password`; proxy vira booleano `tem_proxy` | **ok** |
| handoff/curation não promovem `done` | `CURATION-HANDOFF.json` propõe no máximo `partial` para P03-T11 e mantém P03-T02/P03-T07/P12-T02/P12-T09 em `todo`; não edita Roadmap/grafo | **ok** |

Sem rodada corretiva de código necessária; só artefatos foram atualizados para refletir gates reais executados por Hermes após o encerramento do executor.

---

## 6. Microcorreção final aceita pelo dono

Após aceitação da entrega como candidata `partial`, foram corrigidos apenas estados finais incorretos e a separação de portões:

- procedência documental atualizada para HEAD final/publicação real;
- `broker_de_acesso` deixou de carregar estado editorial `todo` hardcoded no produto e passou a expor capacidade factual: `implementacao=local_verified`, `operacao_real=live_read_not_proven`, `tarefa=P03-T11`;
- `pronto_para_receber_peca`, `pronto_para_operar_acesso` e `pronto_para_publicar` foram separados;
- `publica` permanece sempre `false` nesta rota read-only.

---

## 7. Gates da microcorreção final

**HEAD anterior:** `67ac4ac5ed184eb5c4107fe2ac9285f16d6eaf2f`

| Gate limitado | Resultado |
|---|---|
| Testes focais Cofre/broker/prontidão | `178 passed`, 5 warnings herdados |
| Frontend Asset Vault | `43 passed` em 3 arquivos |
| TypeScript vs baseline | `76` erros totais herdados, `0` em `src/features/asset-vault` |
| Build | `npm run build` passou; warning herdado de chunk grande/dynamic import |
| Autoteste broker | passou: recusas sem rede, sem AdsPower e sem 1Password |
| `git diff --check` | passou |
| Scanner de segredos | 0 hits |
| Scanner `op://` em closure | 0 hits |
| Artefatos com estados superados | **0 hits** no scanner de placeholders de pós-commit, branch não publicada, commit ausente ou push ausente |

Divergência ambiental preservada: não foram reexecutados/corrigidos os 20 testes de criativos fora do ownership; o integrador deve reexecutá-los na convergência.
