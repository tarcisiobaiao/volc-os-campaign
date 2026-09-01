# Preflight — Creative Factory Production Spine V1

## Procedência

| Item | Valor |
|---|---|
| Base SHA | `b6e226ab2f6d339d2c7c899b83b05ff4a95ebcac` (`origin/volc-os-v2`) |
| SHA esperado pelo prompt | `b6e226ab2f6d339d2c7c899b83b05ff4a95ebcac` — **bate, sem divergência** |
| Branch | `sprint/creative-factory-production-spine-v1` |
| Worktree | `/private/tmp/volc-creative-factory-production-spine-v1` |
| Árvore na criação | limpa (`git status --porcelain` vazio) |
| `git fetch origin --prune` | executado; único movimento remoto novo foi `origin/sprint/hermes-p04-t07-pmax-ledger-v12-03-v1` |

`node_modules` é um symlink para o repositório principal (ignorado pelo
`.gitignore`); a worktree não instala dependência nova.

## Baseline dos gates (medida NESTA worktree, no SHA base, antes de qualquer alteração)

| Gate | Comando | Baseline |
|---|---|---|
| Backend | `pytest backend/tests volc_ads` | **2972 passed, 53 skipped** · exit 0 |
| Frontend | `vitest run` | **1208 passed, 5 skipped** (89 arquivos) · exit 0 ¹ |
| TypeScript | `tsc --noEmit -p tsconfig.app.json` | **76 erros herdados** · exit 0 do wrapper |
| Build | `vite build` | verde (7,77 s) |
| SQL v11_03 | `scripts/provar-ciclo-v11_03.sh` | **129 passaram, 0 falharam** · exit 0 |

¹ **Correção factual de um baseline herdado.** O handoff
`docs/architecture/HANDOFF-CURADORIA-BANCADA-10-13-15-16.md` registra
"Frontend completo 902 (7 arq./2 testes falhos)" e trata essas falhas como
herdadas. Elas não são: `src/lib/supabase.ts:7` lança
`Missing Supabase environment variables` quando `VITE_SUPABASE_URL` /
`VITE_SUPABASE_ANON_KEY` não estão no ambiente. Rodando com placeholders
não-credenciais (`https://database.agenciavolc.com.br` + literal
`placeholder-de-teste-nao-e-credencial`) a suíte inteira passa. O baseline
antigo colapsava **ausência de variável de ambiente** em **falha de teste** —
exatamente a confusão que este projeto proíbe. O baseline honesto é verde.

## Concorrência e fronteiras proibidas

| Lane | Branch | HEAD | Relação com a base |
|---|---|---|---|
| Cofre/1Password (ativa, alheia) | `sprint/asset-vault-onepassword-production-v1` | `2c4a6b6` | ahead=1, behind=16 |
| Fechamento criativo anterior | `sprint/traffic-creative-operational-closure-v1` | `ec705bc` | **ahead=0** — já integrada por ancestralidade |
| Rodada aceita P04+P17 | `integration/accepted-round-p04-p17-harness-v1` | `eec859e` | **ahead=0** — já integrada por ancestralidade |

Nenhum arquivo da lane do Cofre é tocado por esta missão.

## Autorizações

Esta missão **não** aplica migration no Supabase oficial, não escreve no Supabase
oficial, não chama Google Ads/Meta/n8n, não publica, não faz deploy, não faz push
e não faz merge. Tudo que exigir autorização externa vai para um pacote único no
fim.
