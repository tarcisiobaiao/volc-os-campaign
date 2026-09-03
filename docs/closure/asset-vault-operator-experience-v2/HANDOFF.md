# HANDOFF — Asset Vault Operator Experience V2

Para a Bia: **revisão independente**. Não implementar em paralelo.

## Resultado em uma frase

`/settings/cofre-ativos` passou de um pulso de cinco células + lista + cadastro monolítico com placeholder `op://` para um control plane: visão honesta, tabela comparável, onboarding em sete etapas sem segredo, detalhe com prontidão dupla (união do candidato) e aposentar com consequência.

## SHAs

| O quê | SHA |
|---|---|
| `origin/volc-os-v2` (base desta feature) | `207e91f1da290130e8d02b78c3ba1c8e9a761111` |
| Linha oficial observada (NÃO mesclada, NÃO rebaseada) | `3331c0c5d63e31e0d068786707c75169231bdad7` |
| Candidato funcional | `5f54d25cf4375c4a43c6b8b5c819f8937106090d` |
| Merge na feature (união) | `caf4df9e350800e6a26ce236e8e4136b4f9a4a56` |
| HEAD antes da adjudicação de autoridade | `b491f4901ff0358db9adb547cde64f9998b29210` |
| Pais do merge | `207e91f` + `5f54d25` |
| Branch | `sprint/asset-vault-operator-experience-v2` |
| Worktree | `/private/tmp/volc-asset-vault-operator-experience-v2` |

`merge-tree` **não era limpo**. Cinco arquivos com CONFLICT no `merge-tree` dos pais `207e91f1` + `5f54d25c`; oito caminhos envolvidos na resolução da união (os cinco CONFLICT mais `prontidaoOperacao.ts`, `prontidao-operacao.test.ts` e `ProntidaoDeOperacao.tsx`). Sem ours/theirs silencioso.

## Commits desta missão

Ver `git log caf4df9..HEAD --oneline` após o push. Commits da experiência + microcorreção de persistência 1Password + um commit corretivo de autoridade única, sem amend, rebase ou force.

## Autoridade única (P03-T11)

`tools/adspower-broker/` é a **única** autoridade canônica. O segundo candidato (`backend/app/asset_vault/broker/`, unido a partir de `5f54d25`) foi **removido durante a adjudicação**. `inventario_perfis` / `inventario_grupos` **não** foram transplantados: inventário real de perfis/grupos continua não implementado. P03-T07 permanece `partial` conforme a linha oficial `3331c0c`. P03-T11 permanece `partial` porque AdsPower real e resolução real ainda não foram exercitados. Interface pronta **não** significa Cofre povoado.

## Arquivos (ownership)

- `src/features/asset-vault/operator/**`
- `src/features/asset-vault/AssetVaultContent.tsx`
- `src/pages/settings/AssetVaultPage.tsx`
- testes focais do Cofre
- `docs/closure/asset-vault-operator-experience-v2/**`
- remoção de `backend/app/asset_vault/broker/**` e `backend/tests/test_cofre_broker.py`
- `scripts/verificar_autoridade_unica_adspower.py` e o teste do gate
- nota de supersessão em `docs/closure/hermes-asset-vault-organic-access-v1/`

Não alterados: DESIGN.md, PRODUCT.md, tokens globais, Navigation, Tráfego, Roadmap, curadoria, grafo, schema/migrations. Sem merge da linha oficial.

## Vereditos

Remedidos após a adjudicação de autoridade única (gates em `GATES.md`):

- `ASSET_VAULT_SINGLE_BROKER_AUTHORITY_ACCEPTED`
- `ASSET_VAULT_OPERATOR_EXPERIENCE_ACCEPTED`
- `SECURE_REFERENCE_ONBOARDING_ACCEPTED`

`DESKTOP_MOBILE_A11Y_ACCEPTED` permanece da rodada anterior: esta correção não redesenhou a UI.

Estes **não** significam inventário real, Cofre povoado, segredo resolvido, AdsPower, publicação ou deploy.

## Revisão adversarial (uma rodada, já aplicada)

| Lente | Achado | Adjudicação |
|---|---|---|
| UX | Aposentar mutava no clique | Confirmação com consequência |
| Frontend | Duas CTAs de cadastro | Uma no header; empty tem a sua |
| a11y | Hit <40×40 no inspetor | Tokens `HIT` / `SECUNDARIO` / `PERIGO` |
| a11y | 320px esmagava H1+CTA | Header `flex-col` até `sm` |
| Contrato | Placeholder `op://` | Peças cofre/item/campo só em memória; montagem só no POST |
| Segredo | Chave de idempotência com localizador | Chave deriva das peças, sem endereço |
| Segredo | Rascunho em sessionStorage recompunha o localizador | Persistível = metadados; pecas efêmeras; Fechar/Concluir/remontar descartam |
| Responsivo | Abas cortadas | `basis-50%` em mobile |
| Anti-slop | Pulso 5 cards | Faixa 3 colunas |
| API | 409 genérico | `ErroDoFormulario` nomeia conflito |

## Limitações

Ver `REMAINING-RISKS.md`. Double de captura não está no repositório. `.capture-vite.mts` local **não** entra no git.

## Zero mutação externa

Nenhuma escrita no Supabase, 1Password, AdsPower, Google/Meta, deploy, ou no processo 8080/8010 do operador.
