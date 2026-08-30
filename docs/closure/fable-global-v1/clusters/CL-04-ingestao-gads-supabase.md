# CL-04 · Ingestão Google Ads → Supabase oficial

**Horizonte**: A · **Resultado**: custo e fato campanha-dia entram no Supabase
oficial com identidade, moeda, NULL≠0, recibo por execução e UMA autoridade de
agenda.

## Estado factual (F018, F019, F029)

- Fato canônico D0/D-1 (`google_ads_campanha_dia` + `trafego_coleta_execucao`)
  é só proposta textual; nenhum SQL existe.
- Workflows n8n D0/D-1 adaptados (API v25, dedupe, Merge) e INATIVOS; o
  adaptador (`scripts/adaptar_gads_reports_n8n.py`) é untracked e sem teste.
- 5/5 flows de custo do núcleo ainda escrevem no Supabase hosted legado.
- daily_campaign_metrics é legado sem conta/moeda/NULL≠0.
- Candidato deadman (656d72d) com gates verdes aguarda integração (heartbeat).

## Missões

| ID | O quê | Onda | Portão |
|---|---|---|---|
| M-W2-02 | Escrever migration do fato canônico + rollback + provas em Postgres descartável (SEM aplicar) — sessão interativa (supabase/migrations/ é protegido no harness) | 2 | nenhum |
| M-W1-04 | (compartilhada) Integrar deadman 656d72d | 1 | revisão substituta |
| M-W3-07 | Aplicar migration + adaptar workflows n8n via payload já pronto + canário manual reconciliado | 3 | **D3** (agenda) + autorização de banco |
| M-W3-08 | Ativar agenda única + heartbeat/deadman ligados + alerta de rotina parada | 3 | após M-W3-07 |
| M-W4+ | Receita (GAM/JoinAds) e câmbio — depende de **D11** (modelo de câmbio) | 4 | D11 |

## Aceite do cluster

- Uma execução D0 e uma D-1 reconciliadas contra a daily legada, com projeção
  de compatibilidade preservando consumidores atuais.
- Prova de que systemd e agenda duplicada estão inativos (o contrato P10-T16
  exige uma única autoridade).
