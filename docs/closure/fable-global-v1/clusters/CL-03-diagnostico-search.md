# CL-03 · Diagnóstico e inteligência Search

**Horizonte**: A · **Resultado**: o operador vê POR QUE uma campanha Search não
entrega, com evidência real, janela e frescor — sem nenhum mutate.

## Estado factual (F007, F008, F022, F023)

- v12_01 aplicada com 10 recibos reais (Crédito Up) e ZERO consumidores no código.
- Frontend do diagnóstico pronto (`CampanhaCanonPage` + hook com degradação
  explícita 404/501); endpoint não existe.
- A tentativa Gemini reprovou no gate real de segurança (rota sem portão de
  identidade) — lição incorporada.
- Search Intelligence completo vive na branch `28d2540` (não integrada);
  na main só a semente `governanca.py`.
- Lab de decisão 100% sintético por design; kernel testado na main.

## Missões

| ID | O quê | Onda | Modelo |
|---|---|---|---|
| M-W2-01 | Endpoint `GET /api/trafego/campanhas/{id}/diagnostico` lendo v12_01, com portão de identidade + estados de ausência | 2 | Codex + reviewer |
| M-W1-08 | (compartilhada) Destino das branches órfãs `28d2540` e `b1fa53e` | 1 | read-only |
| M-W3-05 | Coleta contínua ativa (depende de D2+D3) e frescor no cockpit | 3 | Codex |
| M-W3-06 | Governança de termos/negativas (P05-T08) sobre o diagnóstico integrado | 3 | Codex |
| M-W4+ | Guardião 72h (P05-T09), analista agêntico read-only (P10-T12) | 4 | — |

## Aceite do cluster

- FGTS e Maquininha recebem explicação factual no cockpit, com fonte, janela e
  `lido_em`; ausência renderiza como ausência (null), nunca como zero.
- Zero chamadas Google no render (dados vêm do ledger v12_01).
