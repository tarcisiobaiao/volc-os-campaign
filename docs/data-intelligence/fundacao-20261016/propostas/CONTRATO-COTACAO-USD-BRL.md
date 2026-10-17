# Proposta — contrato append-only da cotação USD/BRL oficial (item 5, não aplicada)

Estado: **candidata**. Nada aqui toca produção sem autorização nominal do dono e o sha256 da migration.
Migration: `experiments/data-intelligence-lab/migrations_candidatas/item5_0002_cotacao_usd_brl.sql` (+ `.down.sql`).
Testes: `tests/data-intelligence/fundacao/test_item5_cotacao_candidata.py` (4, PostgreSQL 16 descartável).

## O que existe hoje (leitura read-only de 17/10/2026)

- `system_settings.dollar_exchange_rate` = 5,25 e `exchange_rate_history` com 4 linhas, 2 taxas distintas, vigências
  de 13/02 a 18/02/2026: nada mudou desde 18/02.
- `get_current_dollar_rate()`, `get_dollar_exchange_rate()` e `get_exchange_rate_for_date(date)` caem em **5,2 em
  silêncio** quando a chave falta (a leitura da manhã de 17/10 também achou 5,5 num caminho).
- Gatilhos `trigger_exchange_rate_update` / `update_all_revenue_converted` **recalculam todo o histórico** quando a
  taxa muda; `calculate_revenue_converted_by_date` converte por data em `joinads_metrics`, `daily_campaign_metrics`,
  `daily_project_metrics`, `gam_metrics` e `adsense_metrics`.
- `exchange_rate_history.created_at` é `timestamp` sem fuso; não há fonte, referência ou autor da taxa.

## Contrato proposto

1. **Cotação é observação append-only** (`fx_rate_observation`): par, taxa, tipo (`ptax_venda`, `ptax_compra`,
   `contratual`, `atestada_dono`), fonte, referência verificável, vigência `[valid_from, valid_to)`, instante de
   publicação e de registro, autor e sha256 do payload da fonte. Correção é **linha nova** com `supersedes`; UPDATE e
   DELETE são recusados.
2. **Resolução as-of sem fallback** (`fx_rate_as_of`): a taxa de um dia é a vigente **como era conhecida** no instante
   `as_of`. Sem linha válida, a resposta é vazia e quem converte grava `nao_convertido` com
   `cotacao_vigente_nao_provada`. Nenhum número implícito.
3. **Conversão única** (`revenue_conversion` + `volc_convert_revenue`): um evento append-only por observação de
   receita e cotação (`UNIQUE (fonte, observation_key, fx_id)`), com `revenue_original_micros`, `currency_original`,
   estado da moeda original (`observed`/`attested`), `fx_id`, taxa, `revenue_converted_micros` (half-even), moeda
   alvo, `as_of` e instante. Recusa: valor já na moeda alvo; moeda original não provada. Repetir é idempotente.
4. **Histórico nunca é recalculado**: uma cotação nova ou corrigida só vale para conversões novas; a conversão antiga
   permanece, e a leitura escolhe a vintage pelo `as_of`.
5. **Replay**: o adaptador do lab passa a aceitar receita convertida só com `fx_id` e vigência; sem isso, segue
   `invalid`/`nao_convertido` (comportamento de hoje).

## Decisões que só o dono toma

| Decisão | Opções | Recomendação |
|---|---|---|
| Taxa oficial | PTAX venda do BCB; taxa contratual da JoinAds; taxa do câmbio efetivo do recebimento | PTAX venda (pública, verificável, com publicação datada) para gestão; reconciliar com o câmbio efetivo quando o pagamento chegar |
| Vigência por dia de receita | PTAX do próprio dia (publicada ~13h, dia útil) ou do último dia útil anterior | último dia útil fechado anterior ao dia da receita, para a taxa existir antes da decisão |
| Coletor da taxa | workflow n8n novo lendo a API Olinda do BCB, gravando por `fx_rate_observation` | sim, com error workflow comum e canário; exige autorização própria |
| Legado | manter as funções com fallback como estão; ou trocar o fallback por NULL e parar o recálculo global | migration separada e autorização própria; não misturar com esta |

## Aplicação (quando autorizada)

1. Conferir o sha256 da candidata contra o que o dono autorizou.
2. Aplicar em transação única (`lock_timeout 5s`); a candidata cria só objetos novos e não altera o legado.
3. Prova: `fx_rate_as_of` vazio antes da primeira cotação; uma cotação PTAX real com referência; uma conversão de
   uma observação JoinAds de teste lida de volta; replay estrito repetido.
4. Rollback: `.down.sql` (recusa se já houver cotação/conversão; nesse caso, `REVOKE EXECUTE` de
   `volc_convert_revenue`, sem apagar nada).
