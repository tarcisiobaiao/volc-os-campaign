# Item 5 — replay estrito: antes × preliminar × pós-cutover

Mesmo código de exportação (`rodada-autorizada-20261017/export_snapshot.sql`, RR READ ONLY + ROLLBACK,
`default_transaction_read_only=on`), mesmo pseudonimizador (0 identificador cru na saída nas três) e mesmo
`rodar_replay_real.py`. Artefatos crus apagados ao fim de cada rodada; só os resumos agregados estão versionados:
`../rodada-autorizada-20261017/item1_resumo_agregado.json`, `replay_preliminar_resumo.json`, `replay_final_resumo.json`.
Variante **E** = contrato estrito (moeda só com prova no payload). **H** = moeda atestada e câmbio USD→BRL 27/5 como
**parâmetro de simulação**, não cotação.

| | Antes do item 5 | Preliminar | Pós-cutover (D-1 provado) |
|---|---|---|---|
| Snapshot (BRT) | 16/10 23:00 | 17/10 18:21 | 17/10 20:27 |
| Linhas v21 campanha-dia / JoinAds | 175 / 200 | 255 / 271 | 270 / 276 |
| Linhas Google com moeda no payload | 0 | 50 | 65 |
| Custo Google `missing` por zero sem linha (histórico v1) | 12 | 16 | **16** (nenhuma execução da versão nova gravou zero sem linha) |
| Custo Google `missing` por métrica ausente (contrato novo) | 0 | 4 | 8 |
| Custo Google `invalid` moeda não provada (v1) | 3 | 4 | 4 |
| Custo Google `observed` (janela fechada, moeda provada) | 0 | 0 | **1** |
| Receita JoinAds `invalid` moeda não provada | 100 | 110 | 110 |
| Receita JoinAds `invalid` precisão acima de micros (histórico v4) | 13 | 13 | 13 |
| Cortes / decisões (E) | 36 / 216 | 56 / 336 | 58 / 348 |
| Decisões E sha256 | `a8590ca8…` | `ac3e6109…` | `ca7ea487…` |
| Último snapshot E (custo\|receita) | ausente 12, falha 3 | ausente 16, falha 3, medido\|falha 1 | ausente 16, falha 2, **medido\|falha 2** |
| Ledger íntegro (cadeia de hash) | sim | sim | sim |
| ms por corte | 8,9 | 8,3 | 9,2 |
| Anti-baseline null→zero | 180 pausar, 180 bloqueadas | 280 / 280 | **290 / 290 bloqueadas** |
| Mudança de verba não bloqueada (todas as políticas) | 0 | 0 | 0 |

Nota sobre o contador `v21_zero_sem_linha_de_metrica` do resumo (140 → 204 → 216): ele trata métrica ausente como 0
para contar "custo e impressões 0", então mistura as linhas novas sem métrica (que **não** têm zero gravado) com o zero
sintetizado antigo. O número que separa as duas coisas é o veredito do adaptador na tabela acima (16 × 8).

## Por que continua `insuficiente` (motivos do ledger, pós-cutover)

| Política | E (estrito) | H (moeda atestada, câmbio-parâmetro) |
|---|---|---|
| equal, greedy conservador | 289 cortes "sem custo fechado > 0 em D-1"; **1 corte** "universo BRL com 1 campanha: nada a realocar" | 246 / 44 |
| regra de margem madura, guardião 72 h | "dias maduros 0 < 3" em 290 | idem |

1. **Moeda da JoinAds só atestada.** No modo estrito, atestação do dono não é prova; 110 linhas de receita ficam
   `invalid`. Nenhuma fonte da JoinAds declara moeda (0 de 276 payloads).
2. **Câmbio não provado.** A cotação do VOLC (5,25) está parada desde 18/02/2026; nada é convertido no ledger.
3. **Maturação.** A regra de margem pede 3 dias maduros com custo e receita medidos; há 0.
4. **Estrutura da conta.** Só 1 campanha ativa: realocar não tem sentido, mesmo com tudo provado.
5. **Histórico não reescrito.** 16 zeros sintetizados (v1) e 13 receitas com mais de 6 casas (v4) continuam como
   estão; o adaptador os marca `missing`/`invalid`, como deve.

O que mudou de fato: pela primeira vez o modo estrito tem custo Google **medido com moeda provada** numa janela
fechada (o D-1 de 16/10 do canário), e nenhuma execução da versão nova dos três coletores Google gravou zero sem linha de métrica.
