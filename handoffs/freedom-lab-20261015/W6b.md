# W6b — Prensa: margem de Stories/Reels nas variantes 9:16

**Estado:** `ready_for_human`
**Branch:** `mission/w6b-safe-area-qhbj6u` (nuvem)
**Base:** `mission/w6-prensa-variants` @ `6ba90123` (W6, aprovada e aguardando integração; não está no main)
Sem merge, main, Roadmap, curadoria, grafo, produção, Ads ou Supabase.

## Decisão do Tarcisio

"Reservar": variante 9:16 sem `safe_area` declarada reserva a interface de
Stories/Reels em vez de herdar a margem do feed.

## O que mudou

| Arquivo | Mudança |
|---|---|
| `services/prensa/motor/variantes.py` | `e_9x16`, `safe_area_stories`; `spec_da_variante` aplica a margem padrão à 9:16 sem `safe_area` e grava `artboard.safe_area_origem`; `valida_variantes` julga essa margem antes de custo |
| `services/prensa/tests/test_variants.py` | 21 testes novos (17 sem navegador, 2 parametrizações, 2 de render); o teste dos três PNGs agora declara a margem do feed na story |

## Valores e fonte

Zona segura do guia oficial da Meta para Instagram Stories, já registrada no
repo como **EV-META-20** em `docs/specs/creative-supply-chain-v1/OFFICIAL-API-EVIDENCE.json`
(confiança COMPROVADO, consultada em 05/09/2026, refresh até 04/12/2026):
~14% topo, 35% base, 6% laterais, tolerância de 1% na proporção.

- 1080x1920 → top 269, bottom 672, left/right 65 (arredondado para cima).
- 1440x2560 → 359 / 896 / 87.
- Por lado vale o maior entre a margem herdada da base e a da Meta (a base de
  86 nas laterais vence os 65).

Por que não o `SAFE_STORY` (220/340/72/140) dos testes: ele vem do exemplo
canônico do `PRENSA-SPEC.md` §3, que não está no repo e não cita fonte. A
EV-META-20 é a única fonte oficial versionada. A base de 35% também cobre a
área de legenda/CTA dos Reels; não há evidência separada de Reels no repo.

## Evidência (container cloud, Chromium 141 via `channel="chrome"` + Playwright 1.49 pinado)

```bash
cd services/prensa && <venv>/bin/python -m pytest tests/ -q -p no:cacheprovider
# W6 base (6ba90123): 41 passed
# esta branch:        62 passed
```

Sem a mudança no teste dos três PNGs, a story 9:16 desta branch reprova no
verify com "tinta fora da safe area" em kicker, headline, sub e handle: é a
margem nova funcionando sobre um layout ancorado para 4x5.

**Byte a byte:** `resolve.py` + `render.py` da W6 e desta branch sobre
`spec_carrossel.json` (4 PNGs, sem variants), `spec_grafico.json` (6, sem
variants) e uma spec com variants 4x5 + 9:16 com `safe_area` explícita + 1x1
(3): 13/13 sha256 idênticos (sha256 do manifesto ordenado
`982cfeb30f9429c526acbd8d7fafd0c41e578e710a570335f3c31dabe13bfcf1`).

## Lacunas

1. Render provado em Chromium 141 no Linux, não no Chrome do macOS nem na
   imagem `volc-prensa:1.0.0`. Os sha256 acima valem só entre as duas
   árvores nesta máquina. Rodar a suíte no Mac antes de integrar.
2. Layouts ancorados em px para 4x5 reprovam na story sem `safe_area`
   própria. É o comportamento pedido; quem quiser a margem antiga declara
   `safe_area` na variante.
3. Mesmas lacunas da W6 (porta HTTP, docstrings do tradutor) seguem abertas.

## Delta proposto ao integrador (não aplicado)

Na capacidade "Prensa multi-proporção por `artboard.variants"`: variante 9:16
sem `safe_area` reserva a zona segura de Stories (EV-META-20), testada em
branch, não homologada no container de produção.
