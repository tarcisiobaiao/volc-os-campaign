# 11 — Riscos e limitações

Consolidação do integrador. Cada risco cita a prova. "Produção" significa leitura read-only feita em
16/10 (recibo `receipts/leituras-externas/RECIBO-LEITURAS-20261016.md`); nada foi escrito fora deste
repositório local.

## 1. Riscos de produção (medidos read-only)

| # | Risco | Prova | Efeito | Saída proposta | Precisa de |
|---|---|---|---|---|---|
| P1 | Sensor v3 e WEBS Wrapper descartam `utm_campaign` numérico (filtro de PII ≥ 10 dígitos) | `01` §2.4; `receipts/inventario/02-prova-filtro-pii-utm.*`; recibo L4 e `dq_cobertura_atribuicao_sensor` = 0/19 e 0/14 sessões pagas | navegação/funil do sensor não junta com campanha; só JoinAds carrega a campanha | isentar `^\d{6,20}$` só em `utm_campaign`/`utm_content`, com vetor-ouro e canário (`03` §7) | publicação GTM autorizada |
| P2 | Coletor canônico Google grava `cost=0`/`impressions=0` para campanha sem linha de métrica | `01` R3; recibo L11 e `dq_zero_sintetizado` 80% | zero sintetizado indistinguível de zero confirmado; um consumidor ingênuo "vê" campanha morta | Code node grava `null` + motivo; adaptador já trata como `missing` (`02` §9) | mudança de workflow n8n autorizada |
| P3 | Moeda inventada a montante (v21 `'BRL'` fixo; JoinAds `cfg.CURRENCY \|\| 'USD'`, `DEFAULT 'USD'`) | R1-F4; `02` §9 | o adaptador marca `moeda_nao_provada`; custo real v21 sai `invalid` até o coletor pedir `customer.currency_code` | incluir `customer.currency_code` na GAQL | mudança de workflow n8n autorizada |
| P4 | 3 runs do coletor de termos presos em `running` desde 15/10 | recibo L9 e `dq_runs_orfaos` | frescor por run engana; nada fecha o run | reaper + error workflow + dead letter (`05`) | mudança de workflow/SQL autorizada |
| P5 | Duas gerações de ledger Google aplicadas (v12/v17 e v21) sem decisão de autoridade | recibo L1; `01` §1 | dois autores possíveis da mesma verdade | decisão de autoridade única (tarefa P06-T11 proposta) | decisão do dono |
| P6 | `raw_events` dedup `UNIQUE (sid, pid, event_name, ts_sec)` colapsa eventos do mesmo nome no mesmo segundo | recibo L3; `01` R4 | sub-contagem de ad views e eventos rápidos | chave com sequência do evento no lote | migration autorizada |
| P7 | Gatilhos legados JoinAds/GAM → `daily_campaign_metrics` seguem vivos (último domínio vence; linha nova com custo 0) | recibo L2; `01` R5 | co-autoridade latest-wins com o canônico | aposentar após o canônico virar fonte única | decisão + migration |
| P8 | DDL de `raw_events`, `daily_campaign_metrics`, `gam_metrics`, `fact_page_daily` fora de qualquer ref; produção sem `schema_migrations` (só `volc_ops.migracao_evento` com 1 linha) | `01` §4; recibo L12 | não há como reconstruir o schema do repositório | versionar o DDL vivo (dump só de schema) | leitura read-only + commit |
| P9 | Código canônico (v21, JoinAds v2, economia, sensor) só em `043c77f5`/`wip/*`, sem merge-base com `main` | `00` §3; `01` §1 | qualquer integração exige reconciliar históricos disjuntos | integração planejada por domínio | decisão do dono |

## 2. Riscos de método

- **Simulação não é eficácia.** Todo número de desempenho (D, F, E) vem de mundos sintéticos cujos parâmetros
  escolhemos; a forma tem âncora real com n minúsculo (`07` §4). Nenhuma política demonstrou ganho sobre
  `equal` no simulador (`06`, resultado negativo preservado).
- **Dado real mínimo.** Uma campanha ativa, ~8 dias de JoinAds v2 e ~2 dias de Google v21. Nenhuma calibração
  é possível; limiares de qualidade, de maturação e de alarme são escolhas iniciais.
- **Replay real não executado.** A exportação read-only sanitizada foi bloqueada pelo classificador da sessão
  (recibo, "Ação negada"). Sem ela, nada passa de "testado com sintético" a "testado em replay".
- **Volume sob a regra de versão.** A regra D2 (releitura idêntica = versão nova) multiplicava o volume
  (B: 7,9 TB em 3 anos a ×100 no DDL longo); a correção D2' (versão só quando o estado muda) está com a frente
  A no fechamento desta missão — ver `handoffs/HANDOFF-A.md` §7.2 para o estado final.
- **Determinismo entre plataformas** não testado (só macOS arm64, CPython 3.13.0, PostgreSQL 16.11; produção é
  15.8).
- **Concorrência** do schema candidato provada com duas sessões, não com carga.

## 3. Riscos de segurança e privacidade

- Nenhum segredo, chave, JWT ou senha em arquivo versionado (varreduras de A, C e da R1).
- Resíduo de privacidade: ids reais (campanha, conta Google Ads) foram retirados dos arquivos atuais, mas
  **continuam no histórico** de commits anteriores desta branch (C: `a1759346`, `3c5281e8`; inventário antes de
  `e3106c05`). A branch não foi enviada a lugar nenhum; antes de qualquer push, decidir squash ou reescrita.
- O id do container GTM e ids de workflow n8n permanecem em alguns documentos e como chaves de SLA no código
  de qualidade; não são segredos, mas são identificadores operacionais.
- `docs/growth-engine/diagnostico/evidencia.json` (em `main`, fora desta missão) contém GAQL real com
  `billing_setup` — pendência de segurança herdada da 1ª execução, ainda aberta.

## 4. Limitações de escopo

- Nenhuma escrita externa existe no código: shadow com `executavel=False` por construção, coletor seguro com
  cliente só de leitura injetado e `dry_run` padrão. A trava em Python não impede código hostil de abrir a
  própria conexão (limite declarado em `05`).
- Roadmap, curadoria e grafo **não foram alterados**: a aplicação foi bloqueada pelo classificador de
  permissões; o delta validado está em `handoffs/CURADORIA-DELTA-20261016.json` e o grafo segue
  `current: false`.
- L6 (GTM API), L7/L8 (n8n API) e L13 (hash da Edge Function) não foram lidas: exigem credencial de API que esta
  missão não lê. O mecanismo que leva o id numérico à JoinAds apesar do filtro do wrapper segue não identificado.
