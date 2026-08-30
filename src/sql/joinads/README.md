# Join Ads → VOLC O.S.

Ingestão de receita do site **MI**, que não passa pelo GAM. Os dados vêm da API da
dashboard da Join Ads (`office.joinads.me`).

## Como o dado entra

```
                    ┌─ /earnings  ─────────────→ daily_project_metrics ──┐
n8n (2 flows) ──────┤                                                     ├─→ dashboard
                    └─ /key-value ─→ joinads_metrics ─(trigger)─→ daily_campaign_metrics
```

Mesmo desenho do GAM: o n8n grava uma **linha crua fina** e os triggers do banco
fazem o resto (resolvem `project_id`, convertem moeda, propagam para a tabela que
o front lê). Fonte separada na entrada, unificada na `daily_campaign_metrics`.

| endpoint da Join | destino | chave do upsert |
|---|---|---|
| `/clients-endpoints/earnings` | `daily_project_metrics` | `date,url_projeto` |
| `/clients-endpoints/key-value` | `joinads_metrics` | `date,utm_campaign_value,joinads_domain` |

`/report/advertiser/campaign` e `/top-url` ficaram **fora**: o primeiro exige
`utm_campaign` como filtro obrigatório (é drill-down, não listagem) e o segundo é
ranking. São features de painel, não de ingestão.

## Bruto, sempre

O sistema grava receita **bruta** e deixa o revshare para o consumidor final, via
`projects.revshare`. Para a Join isso significa `revshare = 0.10`.

Os dois endpoints entregam bruto e líquido: `revenue`/`revenue_client` no
`/earnings` e `earnings`/`earnings_client` no `/key-value`. O flow usa sempre o
bruto. O `EARNINGS_IS_NET` no Config governa só o *fallback*, para o caso de um
dia vir apenas o líquido.

> A doc da Join **não menciona** o campo `revenue` do `/earnings` — ele existe.
> Confirmado em dado real: `ecpm 1.25` vs `ecpm_client 1.13` = 0,904, que é o
> revshare de 10%.

> ⚠️ Se alguém mudar o flow para gravar `revenue_client` / `earnings_client` sem
> zerar o `projects.revshare`, o desconto passa a acontecer duas vezes
> (0,9 × 0,9 = 0,81) — 19% a menos, sem erro nenhum aparecer na tela.

## Ordem de aplicação

```bash
# 1. tabela + triggers
cat src/sql/joinads/01_joinads_metrics.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
  root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"

# 2. revshare do projeto (o projeto em si é criado sozinho no 1º run do flow)
cat src/sql/joinads/02_project_type_joinads.sql | ssh -i ~/.ssh/volc_hetzner_claude_ed25519 \
  root@178.156.196.149 "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1"
```

Depois, no n8n: importar os dois flows, criar a credencial Header Auth
`JoinAds - Bearer Token` (`Authorization: Bearer <token>`) e trocar o
`JOIN_DOMAIN` no nó **Config**.

## O tipo do projeto é `GAM` — não existe tipo `JOINADS`

O `project_type` não descreve o fornecedor, descreve o **comportamento** do dado.
`ADSENSE` é o tipo "receita total, sem revshare" — é por isso que o front mostra
"Revenue Total:" para ele e "Revenue (após RevShare):" para os demais. A Join tem
revshare, tem eixo de campanha e escreve nas colunas `gam_*` da
`daily_campaign_metrics`: comportamentalmente, é GAM.

Consequência: **nenhuma mudança no front**. O enum do TypeScript, o
`isAdSenseProject` e o seletor de tipo continuam como estão.

O projeto nem precisa ser cadastrado à mão — `get_or_create_project_id_by_url`
cria no primeiro run, já com `project_type = 'GAM'`. O que ele **não** acerta é o
`revshare`, que nasce `0`; sem o `02_*.sql`, os 10% da Join nunca são
descontados e `revenue_converted_revshare` sai igual ao bruto.

## Os flows

| flow | cron | janela | webhook |
|---|---|---|---|
| `JOIN ADS - REPORT - INTRA DAY` | `0 6,12,18,23 * * *` | hoje | `/webhook/joinads-intraday` |
| `JOIN ADS - REPORT - DAY BEFORE` | `0 6 * * *` | D-1 voltando 2 dias | `/webhook/joinads-day-before` |

Mesma cadência dos flows de GAM. Os webhooks servem aos botões de "atualizar
agora" e aceitam corpo opcional:

```json
{ "domain": "exemplo.com.br", "lookback_days": 3 }
```

Os JSONs são **gerados** por `n8n/gerar_flows_joinads.py` a partir de um template
único, para os dois não divergirem por typo. Editar o gerador e rodar de novo, não
editar o JSON na mão.

## O que a API faz e a doc não conta

Levantado batendo na API de verdade em 2026-08-11. Tudo aqui está coberto por
teste; são as três armadilhas que derrubaram os primeiros runs.

**1. Não existe quebra por dia dentro de um intervalo.** Com
`start_date != end_date` os dois endpoints devolvem **uma linha agregada** e o
campo `date` vira rótulo de período:

```
start=2026-08-10 end=2026-08-10 → { "date": "10/08/2026",              impressions: 8 }
start=2026-08-09 end=2026-08-10 → { "date": "09/08/2026 à 10/08/2026", impressions: 8 }
```

Por isso o `Monta janelas` emite **uma janela por dia**, e o parser recusa
qualquer string com mais de uma data (senão casaria o prefixo e atribuiria o
total do período a um dia só, calado). O teto de 15 dias da doc é irrelevante
para nós.

**2. A API troca o `custom_key` sem avisar.** Quando não há dado para a chave
pedida, ela ignora o parâmetro e devolve outra:

```
pedi utm_campaign → 1 linha, custom_key devolvida: land_uri
pedi id_post_wp   → 7 linhas, custom_key devolvida: id_post_wp
```

O normalizador confere a chave que voltou e descarta o que não bate — sem isso,
o valor `/` do `land_uri` entra em `utm_campaign_value` como se fosse id de
campanha. Enquanto o site não tiver tráfego com UTM, o eixo de campanha fica
vazio, que é o certo.

**3. Os nomes dos campos divergem da doc.** A API real usa `custom_key` /
`custom_value` (a doc escreve `custon_*`) e `active_view` (a doc,
`active_view_viewable`). O normalizador aceita as duas grafias.

Também confirmado: **data é `DD/MM/AAAA`** com `report_type=Synthetic` e **ISO**
com `Analytical` — o parser lida com os dois.

### Ainda em aberto

- **Timezone de fechamento do dia.** O sistema trabalha em `America/Sao_Paulo`.
  Se a Join fecha em UTC, o intra-day diverge nas últimas horas.
- **`Σ /key-value` bate com `/earnings`?** Só dá para conferir num dia com
  volume e com tráfego marcado por UTM.

## Diferenças em relação ao GAM (de propósito)

- **Um POST em lote por tabela**, não uma requisição por linha. As linhas são
  desduplicadas pela mesma chave do `on_conflict` antes de sair — um lote com a
  chave repetida faz o Postgres estourar `cannot affect row a second time`.
- **Uma só função de conversão de moeda** (a histórica por data). Na
  `gam_metrics` duas funções disputam a coluna `revenue_converted` e quem vence é
  a ordem alfabética do nome do trigger, o que faz backfill de mês passado sair
  com o dólar de hoje.
- **Janela deslizante** com sobreposição, para reabsorver revisão retroativa. O
  upsert é idempotente, então reprocessar não duplica.
- **Ramo de erro** gravando `system_settings.joinads_last_error`, e
  `joinads_last_update` a cada sucesso — para dar o que monitorar. O pipeline de
  GAM/AdSense ficou 6 meses parado sem ninguém perceber.
