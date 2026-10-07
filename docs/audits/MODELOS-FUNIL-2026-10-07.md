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

## Recomendação

**Agora (sem trocar modelo padrão):** manter a configuração atual. O ganho
demonstrado nesta rodada vem de não pagar por funil estruturalmente quebrado
(portão de esqueleto antes de qualquer chamada, inclusive o `engajamento`) e de
atacar a retentativa da redação (5 das 36 chamadas, todas em `write`).

**Candidatas a benchmark** (matriz `engine/benchmarks/matriz-modelos-v1.yaml`):

- `redacao_flash_3_8`: gemini-3.8-flash na redação e no widget. Estimativa pelo
  perfil do run 220001: US$ 1,10 contra 1,60 por funil (−32%). Preço
  promocional até 31/12/2026 (US$ 0,75/3,75); a partir de 2027, 1,50/7,50 —
  ainda abaixo do 3.5-flash na saída. Precisa provar qualidade, aderência
  factual e taxa de retentativa iguais ou melhores.
- `estruturados_mini`: gpt-4.1-mini em SEO, prompt visual e engajamento. Ganho
  pequeno (≈ −2%); só vale se não aumentar reprovação do `seo_limits`.
- `juiz_gpt_5_1`: gpt-5.1 como juiz/revisor (outro provedor que o redator).
  Custo semelhante (≈ −2% na estimativa); só entra se o julgamento melhorar de
  forma medida (concordância com decisão humana).

**Não recomendadas:** gemini-3.5-flash-lite na pesquisa (Google Search não
disponível no tier pago); gpt-5-pro/gpt-5.2-pro (10× o custo sem ganho
demonstrado); trocar qualquer padrão sem a rodada real da matriz; o default
`gemini-2.0-flash` do `GeminiClient` no backend, que não aparece na página
oficial consultada.

## Como rodar o benchmark real (decisão humana, custo real)

```bash
cd funnelforge-migracao/engine
PYTHONPATH=src python -m funnelforge.benchmark estimar tests/fixtures/state_run_220001.json
PYTHONPATH=src python -m funnelforge.benchmark preparar /tmp/bench-funil   # só escreve configs e imprime comandos
# rodar os comandos impressos (publish: false), depois:
PYTHONPATH=src python -m funnelforge.benchmark pontuar /caminho/runs/*/state.json
```

Comparar medianas de 3 repetições por configuração: custo pela tabela oficial,
latência, retentativas, fallbacks, páginas prontas/bloqueadas, achados
materiais da revisão global e reprovação de portões factuais/compliance.
