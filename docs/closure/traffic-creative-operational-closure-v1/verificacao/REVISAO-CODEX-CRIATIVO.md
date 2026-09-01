# Revisão Codex — cluster criativo (gpt-5.6-sol, high, read-only)

Duas rodadas anteriores (núcleo de contrato e dois clusters) **não produziram
veredito**: o Codex carregou o skill `adversarial-review`, gerou sub-revisores e
estourou explorando antes de responder. Registrado como fato, não como aprovação.
Esta terceira rodada, com escopo estreito e instrução explícita de não carregar
skill, respondeu.

## Veredito literal do Codex

```
P1. **BLOQUEADOR** — `volc_ads/criativo_ponte.py:876-884` reconstrói o `Asset` de pasta sem informar `natureza`, resultando em `NAO_DECLARADA`, aceita em produção por `volc_ads/criativo_ponte.py:155-168`. Cenário: PNG gerado pelo motor `LOCAL` (`volc_ads/criativo/adaptadores/png_local.py:267`) é salvo em `marketing/` → `lote_de_pasta` o recria como `NAO_DECLARADA` → `imagens_de_display` admite o arquivo em `Destino.PRODUCAO` → fixture vira payload de produção.

P2. **SEM ACHADO** — `volc_ads/criativo/adaptadores/png_local.py:156-161` deriva a semente apenas de campos estáveis; o `set` de `volc_ads/criativo/adaptadores/png_local.py:195-217` só é consultado, nunca iterado. A variação entre versões de zlib está explicitamente fora da garantia “mesmo processo” em `volc_ads/criativo/adaptadores/png_local.py:49-57`.

--
P1. **BLOQUEADOR** — `volc_ads/criativo_ponte.py:876-884` reconstrói o `Asset` de pasta sem informar `natureza`, resultando em `NAO_DECLARADA`, aceita em produção por `volc_ads/criativo_ponte.py:155-168`. Cenário: PNG gerado pelo motor `LOCAL` (`volc_ads/criativo/adaptadores/png_local.py:267`) é salvo em `marketing/` → `lote_de_pasta` o recria como `NAO_DECLARADA` → `imagens_de_display` admite o arquivo em `Destino.PRODUCAO` → fixture vira payload de produção.

P2. **SEM ACHADO** — `volc_ads/criativo/adaptadores/png_local.py:156-161` deriva a semente apenas de campos estáveis; o `set` de `volc_ads/criativo/adaptadores/png_local.py:195-217` só é consultado, nunca iterado. A variação entre versões de zlib está explicitamente fora da garantia “mesmo processo” em `volc_ads/criativo/adaptadores/png_local.py:49-57`.

```
