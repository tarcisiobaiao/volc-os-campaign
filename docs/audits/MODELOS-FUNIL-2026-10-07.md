# Modelos do funil — inventário, evidência e recomendação (07/10/2026)

Nenhuma chamada paga nesta auditoria. Evidência: o recibo do run real SENAC
`guia-cursos-senac-20260917-220001` (`engine/tests/fixtures/state_run_220001.json`)
pontuado por `python -m funnelforge.benchmark pontuar`, e as páginas oficiais
de preço consultadas em 07/10/2026 (tabela datada em
`engine/benchmarks/precos-oficiais-2026-10-07.yaml`):

- Google: https://ai.google.dev/gemini-api/docs/pricing
- OpenAI: https://developers.openai.com/api/docs/pricing

## Inventário por etapa

| Etapa | Configurado | Fallback | Temp. | Saída | Medido no run 220001 (5 páginas) | Risco |
|---|---|---|---|---|---|---|
| Arquiteto | backend `pautador_entity_funnel_model` = gemini-3.5-flash (via entidade); `pautador_funnel_gemini_model` = gemini-3.1-pro-preview (via oportunidade) | estrutura determinística COM aviso | 0.9 (docstring do orquestrador) | JSON | **não registrado no recibo** | custo/latência do arquiteto invisíveis |
| Revisor do arquiteto | gemini-3.5-flash | fail-open (funil original) | — | JSON | não registrado | idem |
| Revisor de esqueleto | determinístico (novo) | — | — | `Issue` | US$ 0 | — |
| Pesquisa | gemini-3.5-flash + Google Search | nenhum | 0.2 | JSON tipado | US$ 0,343 (22%), 5 chamadas, 1 tentativa cada | sem fallback; busca acima de 5.000/mês custa US$ 14/1.000 |
| Briefing (V2) | gpt-4.1 | gemini-3.5-flash | 0.2 | JSON + contrato | (V1 no run) | — |
| Redação LP/internas | gemini-3.5-flash | gpt-4.1 | 0.7 | JSON (LP) / Gutenberg | **US$ 0,810 (52%)**, 10 tentativas para 5 páginas | retentativa é o maior custo |
| SEO | gpt-4.1 | nenhum | 0.4 | JSON | US$ 0,034 | — |
| Juiz por página (V1) | gpt-4.1 | gemini-3.5-flash | 0.0 | JSON | US$ 0,078 (4 páginas) | — |
| Revisor contextual (V2) | gpt-4.1 | gemini-3.5-flash | 0.0 | JSON + patches conferidos | (V1 no run) | — |
| Revisão global | determinística (nova) | — | — | registro | US$ 0 | — |
| Widget | gemini-3.5-flash | gpt-4.1 | 0.5 | HTML sanitizado | US$ 0,038 | código executável na página |
| Prompt visual / revisão de imagem | gpt-4.1 | nenhum | 1.0 / 0.0 | texto / JSON | US$ 0,012 / 0,018 | — |
| Imagem | gpt-image-2 medium | nenhum | — | PNG | US$ 0,216 (declarado no ledger) | preço por imagem não está na página oficial (só por token) |
| Engajamento | gpt-4.1 | gemini-3.5-flash | 0.1 | JSON | US$ 0,004 | — |

Total do run: ledger US$ 1,5516; recalculado pela tabela oficial de hoje
US$ 1,5957; 36 chamadas pagas, 5 retentativas, 0 fallback, 671 s de latência
somada, US$ 0,319 por página pronta. O ledger usa `litellm.completion_cost`,
cuja tabela pode divergir da do provedor — o benchmark mostra as duas.

Fallback deixou de ser silencioso: `StepResult.model_requested` e, em cada
tentativa do `log.jsonl`, `model_requested`, `model` (servido) e `fallback`. O
motivo exato da troca o LiteLLM não devolve; a tentativa que caiu fica no log
com `erro` e `classe`.

## Recomendação (revisada na 2ª rodada, 07/10/2026)

Consulta adicional à documentação oficial em 07/10/2026:
https://developers.openai.com/api/docs/deprecations — **gpt-5.1 está deprecated**
(desligamento 01/04/2027; substituto oficial `gpt-6-sol`); gpt-4.1-nano desliga em
23/10/2026. gpt-4.1 e gpt-4.1-mini não constam como deprecados. Preços de
gpt-6-sol (US$ 2,00/10,00) e gpt-6-luna (US$ 0,10/0,50) na página de preços.

**Agora (sem trocar padrão):** manter a configuração. A alavanca é a
retentativa: 10 tentativas de redação para 5 páginas no run 220001 (5 extras).
O que esta rodada fez para reduzi-la sem trocar modelo: contrato da jornada
validado e normalizado antes da escrita, portão de esqueleto antes de qualquer
chamada, saída oficial que não exige link onde não cabe (`nao_aplicavel`),
ativo sem fonte que não gera chamada, uma revisão só (naturalidade no mesmo
call) e a causa de cada retentativa registrada no log para atacar a próxima.

**Candidatas a benchmark** (`engine/benchmarks/matriz-modelos-v1.yaml`,
estimativa pelo perfil do run 220001):

| Configuração | O que muda | Custo estimado por funil |
|---|---|---|
| `atual` | referência | US$ 1,60 |
| `redacao_flash_3_8` | gemini-3.8-flash na LP, internas e widget (promocional até 31/12/2026) | US$ 1,10 |
| `estruturados_luna` | gpt-6-luna em SEO, prompt visual e engajamento | US$ 1,56 |
| `juiz_gpt_6_sol` | gpt-6-sol no juiz e no revisor | US$ 1,60 |

**Não recomendadas:** gpt-5.1 (deprecated); gemini-3.5-flash-lite na pesquisa
(sem Google Search no tier pago); gpt-5-pro/gpt-5.2-pro/gpt-6-astra (5–10× o
custo sem ganho demonstrado); o default `gemini-2.0-flash` do `GeminiClient`
(ausente da página oficial); trocar padrão sem a rodada real.

## Benchmark (custo zero até a aprovação)

`PYTHONPATH=src python -m funnelforge.benchmark pontuar|estimar|preparar`.
`pontuar` mede por run: custo pela tabela oficial e do ledger, custo do
arquiteto e do revisor do arquiteto (telemetria do card), escrita da LP e das
internas separadas, retentativas por passo com a causa (log), modelo pedido ×
servido, fallbacks, páginas prontas/bloqueadas, bloqueios da revisão global e
**custo por funil aprovado** (todo o gasto, inclusive dos runs reprovados,
dividido pelos funis aprovados). `preparar` escreve um config por configuração
(com `editorial_v2`, `publish: false` e tetos de custo) e imprime os comandos.

Condições de parada da rodada real: teto do motor US$ 4,00 por run e US$ 1,20
por página (config gerado; o motor para sozinho); teto total US$ 45,00 (12 runs:
4 configurações × 3 repetições), conferido pelo operador com `pontuar` depois de
cada run. Parar também se a configuração `atual` não aprovar o funil em 2 das 3
repetições (o problema não é de modelo).
