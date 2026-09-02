# Curation handoff — Hermes Publisher Ground Truth V1

Este branch **não edita** `ROADMAP-VIVO.json`, `curadoria-operacional.json`, `volc-os-graph.json` nem `graphify-out/**`.

## Estado observado das fontes

- `AGENTS.md` exige handoff de curadoria por worker lane.
- `graphify-out/UPDATE_STATUS.json` não existe nesta worktree; portanto o frescor do grafo não foi tratado como atual.
- `docs/volc-os-graph/curadoria-operacional.json` registra `cap_publisher_quality` como `todo` com evidência ClickUp: 11 tarefas em “to do”.
- `volc-os-workbook/ROADMAP-VIVO.json` contém as tarefas FG do Performance Lab e seus critérios, incluindo FG-BASE-001, FG-PERF-005 e FG-ADS-001.

## Proposta de impacto por nó/tarefa

| Nó/tarefa | Impacto sugerido | Justificativa |
|---|---|---|
| `cap_publisher_quality` | `todo` → `partial` após revisão Gemini e integração | passa a existir engine local read-only para inventário canônico de página/template/dataLayer/slots; ainda sem RUM/CWV real, sem alvo real provado e sem dashboard. |
| `cap_revenue_ingestion` | sem promoção | snapshot cria chaves futuras por URL/template/device/ad_layout_version, mas não ingere receita. |
| `cap_behavior` | sem promoção | snapshot prepara correlação futura com comportamento, mas não altera sensor comportamental nem eventos. |
| `P06-T03` | relacionar como dependência/ponte, não concluir | contrato de tracking/dataLayer ganha base de inventário, sem GA4/GTM write e sem drift real. |
| `P06-T07` | relacionar como insumo, não concluir | Publisher QA ganha achados determinísticos, mas sem operação em ativo real. |
| `P08-T03` | relacionar como insumo, não concluir | por URL/template/dispositivo vira chave operacional futura; não há decisão de pauta/tópico ainda. |
| `FG-BASE-001` | pode receber evidência parcial local | mapa de superfície/slots agora tem scanner versionado, mas leitura real foi `REAL_TARGET_NOT_PROVEN`. |
| `FG-PERF-005` | pode receber evidência parcial local | contrato mínimo de dataLayer é inventariado e riscos de PII/cardinalidade são detectados, sem publicação no GTM/site. |
| `FG-ADS-001` | pode receber evidência parcial local | loader, slots, reservas, fluid ATF, BTF sem lazy-load e refresh sem política são detectados em fixture/artefato. |

## Não propor novo Pxx

A capacidade encaixa nas frentes existentes acima. Não há necessidade de criar novo Pxx.

## Limitações honestas

- Revisão factual Gemini 3.7 Flash ainda pendente.
- Sem leitura real de ativo VOLC por falta de alvo rastreado seguro.
- Sem Core Web Vitals em campo, CrUX, RUM ou receita.
- Sem dashboard paralelo.
- Achados são observações/riscos; não autorizam modificação no site.
