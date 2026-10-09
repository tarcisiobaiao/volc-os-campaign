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

Agenda: D0 às 06/12/18/23 h e D-1 às 06h30, horário de São Paulo
(`volc-gads-coleta-d0.timer`, `volc-gads-coleta-d1.timer`).

## Prova (09/10/2026, Crédito Up 547-809-6539, D-1 de 08/10, passo 06)

1ª passada: 10 famílias coletadas, 12 linhas no ledger com `disparo='agenda'`,
saída 0. 2ª passada do mesmo passo: as 10 famílias **puladas** pelo ledger,
nenhuma leitura no Google, saída 0. Saúde: `gads_campanha_dia` D-1 `ok`.

## Antes de instalar (decisões do dono)

1. **Credencial do Google no Hetzner** (`/opt/volc-gads-coleta/google-ads.yaml`,
   modo 600): exige autorização específica. Não foi copiada.
2. **Uma única autoridade de agenda**: os workflows n8n D0/D-1 do fato
   campanha-dia existem (inativos). Ligar estas units e o n8n ao mesmo tempo
   duplicaria leituras; o ledger aceitaria, mas a agenda deixaria de ter dono.
   O `scripts/gate_agenda_unica_gads.py` registra estes timers como alternativa
   declarada e falha se alguma unit da família aparecer instalada.
3. `conta.env` com `VOLC_GADS_CONTA=5478096539` e `VOLC_GADS_MCC=4904074301`.
4. O ledger só aceita `fonte` em `n8n | python_oneshot | backfill_manual`; a
   agenda Python grava `python_oneshot` com `disparo='agenda'` (valor novo de
   `fonte` exigiria migration, fora desta rodada).

## Operação

```bash
systemctl list-timers 'volc-gads-coleta-*'
systemctl start volc-gads-coleta@d1.service
journalctl -u volc-gads-coleta@d0.service -n 100 --no-pager
```

Batimento (somente leitura):

```sql
select job, origem_janela, resultado, idade_do_batimento
  from trafego_coleta_execucao_saude
 where execucao_chave like '%:5478096539:%'
 order by batimento_em desc limit 10;
```
