# Fatos granulares Google Ads (v17_01) e correlação com a receita

Fase B da blindagem do motor Google Ads (08/10/2026). Migration:
`supabase/migrations/v17_01_gads_fatos_granulares.sql`. Provas:
`scripts/provas-v17_01.sql` (12 cenários em transação desfeita) e o ciclo
rollback → reaplicação.

## Por que existe

Medido em 08/10/2026: das 515 campanhas com gasto nos últimos 30 dias (R$ 833 mil), o banco
tinha 5. Mesmo o fato canônico de campanha-dia (v12_04) não responde às
perguntas que decidem a arbitragem: **qual hora, qual URL, qual país, qual
placement e qual termo pagam a conta**. A API devolve tudo isso; faltava onde
guardar com a mesma disciplina do fato diário.

## Modelo

```
trafego_coleta_execucao  (ledger, v12_04)  ◄── recibo de toda escrita
        ▲ execucao_id (FK DEFERRABLE)
        │
google_ads_campanha_dia (v12_04)          campanha × dia × segments_hash
google_ads_fato_granular (v17_01)         particionada por família:
   ├─ hora_dispositivo   campanha × dia × hora × dispositivo × rede (+ fuso)
   ├─ url                campanha × dia × URL (final | expandida)
   ├─ geo                campanha × dia × geoTargetConstant × (interesse | física)
   ├─ placement          campanha × dia × placement × view (detail | group | pmax)
   ├─ termo              campanha × dia × [ad group] × termo × match
   ├─ keyword            campanha × dia × ad group × critério (+ Quality Score)
   └─ asset              campanha × dia × contexto × asset × campo (+ rótulo)
google_ads_mudanca  (change_event, append-only, 1 linha por evento)
google_ads_estado   (status/política por entidade, nova linha só quando muda)
```

**Invariantes**, as mesmas da v12_04 e defendidas pelo schema e pela RPC:
- identidade completa;
- NULL ≠ 0, e número em string vira rejeição nomeada;
- precedência D0 < D-1 < backfill;
- idempotência com memória;
- fato sem recibo não sobrevive;
- escrita só pela `volc_registrar_gads_fatos`;
- RLS forçada, com `anon` e `authenticated` sem nenhum acesso.

## Correlação com a receita (views, só leitura) — revisada pela v17_04

A v17_01 publicou três views que cruzavam custo e receita. A revisão de
09/10/2026 achou cinco defeitos demonstrados; a v17_04
(`supabase/migrations/v17_04_arbitragem_reconciliada.sql`, provada no espelho,
**ainda não aplicada em produção**) os corrige.

| view | custo | receita | regra |
|---|---|---|---|
| `vw_gads_arbitragem_campanha_dia` | `google_ads_campanha_dia` (linha `segmentos='{}'`) | JoinAds (`utm_campaign_value = campaign_id`) e GAM **só** pela rota `GOOGLE_CAMPAIGN` do `vw_gam_attribution_route` | lucro, ROAS e receita por clique só com `receita_status = reconciliada_fonte_unica` |
| `vw_gads_arbitragem_placement_dia` | família `placement` (view `detail`) | **nenhuma** | o placement de compra é o site de terceiro onde o anúncio rodou; não há ingestão no VOLC que atribua receita a ele |
| `vw_gads_arbitragem_hora` | família `hora_dispositivo` | **nenhuma** | `hourly_stats` não declara moeda nem atribuição (e está vazia) |

`receita_status` da view de campanha, avaliado nesta ordem:

| status | quando | lucro? |
|---|---|---|
| `sem_receita_registrada` | nenhuma fonte para a chave | não |
| `nao_reconciliada_atribuicao` | existe linha GAM da chave fora da rota `GOOGLE_CAMPAIGN` (Meta, ambígua ou sem campanha legada) | não |
| `nao_reconciliada_sobreposicao` | GAM e JoinAds ao mesmo tempo: sem prova de que são receitas distintas | não |
| `nao_reconciliada_projeto` | receita de mais de um projeto, ou projeto do vínculo ≠ projeto da receita | não |
| `nao_reconciliada_moeda` | conta fora de BRL (receitas estão convertidas para BRL) | não |
| `janela_aberta` | custo D0 (intradia) | não (receita parcial visível) |
| `reconciliada_fonte_unica` | uma fonte atribuída, projeto coerente, BRL, janela fechada | **sim** |

Nos status `nao_reconciliada_*`, `receita_brl` é NULL e o rótulo é "receita
não reconciliada"; os componentes (`receita_gam_brl`, `receita_joinads_brl`,
`gam_linhas_nao_atribuidas`) seguem visíveis para a reconciliação manual.

**Leitura real (09/10, consulta somente leitura com o corpo da v17_04):**
Senac 24278665189 em 07/10 → `reconciliada_fonte_unica`, custo R$ 59,66,
JoinAds R$ 4,515, lucro −R$ 55,15, ROAS 0,0757.

## Fatos de receita medidos em produção (09/10/2026)

- `gam_metrics`, `display_gam_placements` e `hourly_stats`: **0 linhas**.
  `joinads_metrics`: 17 linhas (29/08–09/10, 3 campanhas) — a única receita viva.
  `adsense_metrics`: só fevereiro.
- GAM e JoinAds convertem pela **mesma** função
  (`calculate_revenue_converted_by_date`, cotação da data; 5,25 em produção).
  ⚠️ **Correção:** a "divergência de cotação 5,50 × 5,20" registrada em 08/10
  foi medida no espelho, que tem schema sem dados em `system_settings`; não vale
  para produção.
- Receita por URL para GAM/JoinAds não existe; só AdSense tem URL × dia. A
  família `url` está pronta, sem junção de receita.

## Próximo passo: o coletor

Um coletor Python em `volc_ads` com uma GAQL por família (todas conferidas pelo
portão `gads/catalogo.py`) chama a RPC com `job = gads_<família>`, D0 a cada 6h
e D-1 às 06h. Começa pela Crédito Up e depois passa a ler as 42 contas.
