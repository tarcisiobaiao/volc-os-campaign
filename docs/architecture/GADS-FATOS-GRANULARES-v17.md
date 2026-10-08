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

## Correlação com a receita (views, só leitura)

| view | custo (Google) | receita | chave |
|---|---|---|---|
| `vw_gads_arbitragem_campanha_dia` | `google_ads_campanha_dia` (linha `segmentos='{}'`) | `gam_metrics` + `joinads_metrics` (`revenue_converted`) | `campaign_id = utm_campaign_value`, data |
| `vw_gads_arbitragem_placement_dia` | família `placement` (view `detail`) | `display_gam_placements` | campanha, data, `volc_dominio()` |
| `vw_gads_arbitragem_hora` | família `hora_dispositivo` | `hourly_stats` | campanha, `(data + hora) AT TIME ZONE fuso` = `hour_bucket` |

Lucro e ROAS só existem quando a conta é BRL: as receitas estão convertidas
para BRL, e comparar com custo em outra moeda daria número falso.

## Achados de qualidade de dado (para a próxima fatia)

1. **Cotações divergentes.** O mesmo dia converte GAM a 5,50 e JoinAds a 5,20
   (triggers legados distintos). O ROAS consolidado mistura duas cotações.
2. **`utm_campaign_value` é ambíguo.** Em `gam_metrics`, ele pode ser campanha
   Google **ou** adset Meta (`vw_gam_attribution_route` já classifica). A view
   casa por igualdade de id; ids Meta e Google não colidem na prática, mas o
   roteador é a autoridade.
3. **Receita por URL não existe para GAM/JoinAds.** Só AdSense tem URL × dia.
   A família `url` está pronta; a junção espera a receita por URL.

## Próximo passo: o coletor

Um coletor Python em `volc_ads` com uma GAQL por família (todas conferidas pelo
portão `gads/catalogo.py`) chama a RPC com `job = gads_<família>`, D0 a cada 6h
e D-1 às 06h. Começa pela Crédito Up e depois passa a ler as 42 contas.
