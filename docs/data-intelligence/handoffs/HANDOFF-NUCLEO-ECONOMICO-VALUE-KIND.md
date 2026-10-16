# Handoff proposto — núcleo econômico, `value_kind` e snapshot `as_of`

**Estado:** proposta, não aplicada. Áreas-alvo são somente leitura para esta missão.
**Dono da decisão:** integrador único da linha oficial.

## Por que

O laboratório provou em fixture sintética o contrato que a cadeia econômica precisa
(`docs/data-intelligence/CONTRATO-DADO-ECONOMICO.md`). Na base oficial, porém:

1. `volc_ads/economia/` não existe (só em `wip/original-worktree-pre-qg-real-20261007`, `043c77f5`);
2. custo e receita são latest-wins/upsert — não há como reconstruir o que se sabia em um `as_of`;
3. existem três vocabulários de estado/ausência (núcleo wip `Estado`, `services/orakul_predictive` `EstadoSemantico`, lab `EstadoMedida`) e dois de `value_kind` (3 valores em `SPEC-DATA-MANAGER-E-COPILOTO-GOOGLE-ADS.md:62-71`, 5 no lab).

## Mudanças propostas (ordem)

| # | Onde | O quê | Prova que já existe no lab |
|---|---|---|---|
| 1 | integração | Trazer `volc_ads/economia/` + P06-T09 da wip, renumerando o ledger v21 (colide com `v21_01_meta_capi…`/`v21_02_v6_rbac…`) | auditoria A |
| 2 | `volc_ads/economia/nucleo.py` | Acrescentar `ValueKind` (5 classes) e as regras: receita exige `value_kind`; `observed_auction_signal` nunca é receita; `reconciled_revenue` exige método determinístico/agregado declarado; agregado não vira reconciliado por sessão | `test_contracts.py::test_sinal_de_leilao_nao_e_receita` e vizinhos |
| 3 | núcleo | Acrescentar `disponivel_em` (knowledge time), `maturidade` e `cobertura` categórica à `Metrica` | `test_snapshot_*` |
| 4 | núcleo ou módulo irmão | Snapshot `as_of` com versões por chave lógica, contagem do futuro excluído e fingerprint; política `falhar` para consumidores | `contracts/snapshot.py` |
| 5 | unificação | Um único vocabulário de ausência para núcleo, ORAKUL e lab; decidir se `medido` com 0 é aceito (lab aceita como `zero_confirmado`; ORAKUL recusa) | REPLAY-RESULTS §5 |
| 6 | contrato | Declarar a moeda esperada da unidade (um `null` hoje não tem grupo de moeda) e o câmbio datado (`cotacao_id`, fonte, defasagem) | pedidos 3 e 5 da frente C |
| 7 | contrato | Política de outcome parametrizável: primeira vintage fechada × verdade madura | pedido 6 da frente C |
| 8 | coleta | Fonte de receita append-only com valor lido (não só hash) a cada coleta; nunca `DEFAULT 0` | DATA-CAPABILITY-MATRIX §6(a) |

Depois de 1–4 integrados, o lab apaga sua cópia (`volc_dil.contracts`) e passa a importar o núcleo.

## Rollback

Cada item é aditivo; reverter é remover o campo/regra novos. Nenhum item muda dado existente.
