# Coleta recorrente Google Ads → ledger (preparada, não instalada)

Agenda do coletor `python -m volc_ads.coleta` (fatos v12_04 + v17_01). Somente
leitura no Google; escreve só pelas RPCs `volc_registrar_gads_campanha_dia` e
`volc_registrar_gads_fatos`. **Nada aqui está instalado no Hetzner.**

| exigência | como |
|---|---|
| **dono** | `flock` em `/run/lock/volc-gads-coleta.lock`: uma execução por vez, qualquer modo; a concorrente sai 75 sem ler nada (`SuccessExitStatus=75`) |
| **batimento** | cada lote grava `batimento_em` no ledger; `trafego_coleta_execucao_saude` dá a idade do batimento por fechamento (consulta abaixo) |
| **idempotência** | `--agenda PASSO` põe o passo na `execucao_chave` e, antes de ler o Google, pula a família cujo passo já tem tentativa concluída no ledger. Cada tentativa mantém chave e recibo próprios (a falha fica registrada e a recuperação também) |
| **recibo** | `--recibo` grava JSON em `/var/lib/volc-gads-coleta/recibos/`; o ledger guarda o recibo de cada lote |

Agenda: D0 às 06/12/18/23 h, D-1 às 06h30 e recoleta às 07h15, horário de São
Paulo (`volc-gads-coleta-d0.timer`, `volc-gads-coleta-d1.timer`,
`volc-gads-coleta-recoleta.timer`).

## Recoleta da janela madura (W11, 15/10/2026)

O Google ajusta custo (estorno de cliques inválidos) e conversões depois que o
dia fecha, e o D-1 lê cada dia uma vez só. `run.sh recoleta` relê os **N dias
fechados antes do D-1** (`[hoje-1-N, hoje-2]` no fuso da conta;
`VOLC_GADS_RECOLETA_DIAS`, padrão 7, máximo 90) e grava pelo mesmo fato
canônico `google_ads_campanha_dia`, sem migration nova:

| exigência | como |
|---|---|
| chave | `(customer_id, campaign_id, metric_date, segments_hash)` da v12_04; `segmentos` é `{}` no campanha-dia, então a chave efetiva é conta + campanha + data |
| a leitura nova vence | grava como `origem_janela='backfill'` (precedência 3 > D-1 2 > D0 1); entre duas recoletas, vence a de `colhida_em` mais novo |
| dinheiro | `custo_micros` inteiro (bigint) com `currency_code` da conta |
| proveniência | `colhida_em` por linha; `execucao_id` → ledger com `disparo='agenda'`, janela, `contrato_sha256` e recibo |
| idempotência | passo fixo `rec`: a janela muda todo dia, então o passo só impede reler no mesmo dia (catch-up do timer, disparo manual) |
| escopo | só a família `campanha_dia` por padrão (`--familias` amplia, se um dia fizer sentido) |
| concorrência | mesmo `flock` do D0/D-1, mas a recoleta **espera** até 30 min; se não pegar a vez, sai **1** (não 75, que a unit trataria como sucesso) |
| tabela legada | **não projeta** em `daily_campaign_metrics` (`projetar_compat=false`): lá o UPDATE de `spend` dispara a comissão do operador, e reabrir dias fechados mexeria em comissão já apurada. O custo maduro fica só no fato canônico; o legado segue com o valor do D-1 |

Invocação única, igual para qualquer agenda (o script não sabe quem o chama):

```bash
/opt/volc-gads-coleta/run.sh recoleta      # systemd: volc-gads-coleta@recoleta.service
# direto, sem o wrapper:
python -m volc_ads.coleta --conta 5478096539 --mcc 4904074301 \
  --recoleta-dias 7 --agenda rec --recibo /var/lib/volc-gads-coleta/recibos/rec.json
```

**Se o dono da agenda for systemd:** copiar a unit `volc-gads-coleta@.service`
e `volc-gads-coleta-recoleta.timer` e `systemctl enable --now` no timer. **Se for
n8n:** um Schedule Trigger diário às 07h15 (America/Sao_Paulo) seguido de um nó
que execute `/opt/volc-gads-coleta/run.sh recoleta` **no host** (Execute Command
só serve se o n8n rodar no host; em container, o nó SSH para o próprio host). A
saída 75 é "outra coleta em curso", não falha. Nenhuma das duas está ligada;
ligar as duas daria duas agendas para o mesmo ledger.

Várias contas: `VOLC_GADS_CONTAS=5478096539,<outra>` em `conta.env` (todas sob
o mesmo `VOLC_GADS_MCC`). Cada conta tem recibo próprio; uma conta que falha
não impede as outras, e a saída é 1 se qualquer uma falhou.

**Limites conhecidos** (antes de ligar):
- o deadman classifica a recoleta (`job_da_recoleta` em
  `backend/app/trafego/deadman_coleta.py`: expectativa lida deste timer, só
  conta fechamento com `:passorec:` na chave, então backfill manual não a
  pinta de verde), mas o deadman inteiro ainda não tem consumidor que alerte;
- o tamanho do ajuste tardio em `cost_micros` não foi medido: rode
  `--recoleta-dias 7 --seco` na Crédito Up (`5478096539`) e compare com as
  linhas D-1 já gravadas;
- campo que a releitura não trouxer vira NULL sobre o que o D-1 trouxe (o
  `ON CONFLICT` da v12_04 substitui a linha inteira);
- as contas vêm de `VOLC_GADS_CONTAS`, não de `trafego_inventario_conta`.

Custo maduro por conta e dia (somente leitura):

```sql
select customer_id, metric_date, currency_code, sum(custo_micros) as custo_micros,
       string_agg(distinct origem_janela, ',') as origens, max(colhida_em) as colhida_em
  from google_ads_campanha_dia
 where customer_id = '5478096539' and metric_date >= current_date - 10
 group by 1, 2, 3 order by 2 desc;
```

## Prova (09/10/2026, Crédito Up 547-809-6539, D-1 de 08/10, passo 06)

1ª passada: 10 famílias coletadas, 12 linhas no ledger com `disparo='agenda'`,
saída 0. 2ª passada do mesmo passo: as 10 famílias **puladas** pelo ledger,
nenhuma leitura no Google, saída 0. Saúde: `gads_campanha_dia` D-1 `ok`.

## Contas (confirmado pelo Tarcisio em 15/10/2026)

- `547-809-6539` (`5478096539`) é a conta real do **creditoup.com.br**. No
  Google ela se chama "Portal Mundo Mais"; é a única filha ativa do MCC.
- `801-785-1692` (`8017851692`) está **desativada**: leitura read-only em
  15/10 devolveu `CUSTOMER_NOT_ENABLED`. Ela aparece em fixtures de teste, em
  scripts de lab e em medições datadas (ex.: `backend/app/trafego/escopo.py`,
  18/08) como dado histórico ou sintético; não é padrão de nenhum coletor.

## Antes de instalar (decisões do dono)

1. **Credencial do Google no Hetzner** (`/opt/volc-gads-coleta/google-ads.yaml`,
   modo 600): exige autorização específica. Não foi copiada.
2. **Uma única autoridade de agenda**: os workflows n8n D0/D-1 do fato
   campanha-dia existem (inativos). Ligar estas units e o n8n ao mesmo tempo
   duplicaria leituras; o ledger aceitaria, mas a agenda deixaria de ter dono.
   O `scripts/gate_agenda_unica_gads.py` registra estes timers como alternativa
   declarada e falha se alguma unit da família aparecer instalada.
3. `conta.env` com `VOLC_GADS_CONTAS=5478096539` (ou `VOLC_GADS_CONTA`, uma só),
   `VOLC_GADS_MCC=4904074301` e, opcional, `VOLC_GADS_RECOLETA_DIAS=7`.
4. O ledger só aceita `fonte` em `n8n | python_oneshot | backfill_manual`; a
   agenda Python grava `python_oneshot` com `disparo='agenda'` (valor novo de
   `fonte` exigiria migration, fora desta rodada).

## Operação

```bash
systemctl list-timers 'volc-gads-coleta-*'
systemctl start volc-gads-coleta@d1.service
systemctl start volc-gads-coleta@recoleta.service
journalctl -u volc-gads-coleta@d0.service -n 100 --no-pager
```

Batimento (somente leitura):

```sql
select job, origem_janela, resultado, idade_do_batimento
  from trafego_coleta_execucao_saude
 where execucao_chave like '%:5478096539:%'
 order by batimento_em desc limit 10;
```
