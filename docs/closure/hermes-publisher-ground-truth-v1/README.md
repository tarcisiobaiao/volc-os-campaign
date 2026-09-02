# Hermes Publisher Ground Truth V1

## Status

`IMPLEMENTATION_COMPLETE_GEMINI_REVIEW_PASSED_INTEGRATION_HARDENED`.

## Base

- Base branch: `origin/volc-os-v2`
- Base SHA: `c8ca8628e83742dd7da5242f0a015f76292aafe7`
- Feature branch: `sprint/hermes-publisher-ground-truth-v1`
- Worktree: `/root/work/volc-runs/hermes-publisher-ground-truth-v1`

## Capacidade entregue

Capacidade pequena e isolada para produzir `PublisherSurfaceSnapshot`, um JSON versionado e determinístico que inventaria, em modo read-only:

- identidade de página: `site_id`, `project_id`, host/path/canonical, `page_type`, `template_key`, `content_category`, `ad_layout_version`, `device_class`;
- slots: `slot_key`, `div_id`, ad unit path sanitizado, tamanhos, breakpoints, posição ATF/BTF/unknown, dimensões reservadas, loader, lazy-load, política de refresh e evidência;
- dataLayer observado;
- achados/riscos sem autorização de correção em site real.

Cada campo semântico usa status explícito:

- `observed`
- `absent_confirmed`
- `unavailable`
- `not_applicable`
- `failed`

Ausência não vira zero, `false` nem lista vazia: campos ausentes omitem `value`.

## Arquivos de implementação

- `backend/app/publisher_quality/__init__.py`
- `backend/app/publisher_quality/snapshot.py`
- `backend/app/publisher_quality/fetch.py`
- `backend/tests/test_publisher_quality_snapshot.py`
- `scripts/auditar_publisher_quality.py`

## Reuso do FunnelForge

A entrada local aceita o formato `AdManifest` já existente no FunnelForge (`slots`, `slot_id`, `placement`, `sizes`, `min_height_px`, `refresh_eligible`, `source_key`) sem criar um segundo gerador de manifesto. O scanner apenas lê e reconcilia esse artefato contra DOM/HTML observado.

Fonte consultada: `funnelforge-migracao/engine/src/funnelforge/pipeline/admanifest.py`.

## Contratos Google usados como base factual local

A revisão Gemini 3.7 Flash foi concluída com veredito `pass`, sem achados bloqueantes. A implementação codifica observações conservadoras compatíveis com documentação oficial:

- GPT carrega a biblioteca `https://securepubads.g.doubleclick.net/tag/js/gpt.js`, define slots com `googletag.defineSlot(adUnitPath, size, divId)` e renderiza em um `div` correspondente.
- GPT permite separar registro/carregamento com `disableInitialLoad` e `refresh`; refresh sem política observável é risco, não conclusão de violação.
- Google recomenda reservar espaço de anúncio com CSS (`min-height`/`min-width`) para reduzir CLS; slots no topo têm risco maior; slots fluid podem causar layout shift e são preferíveis abaixo da dobra ou tratados com cuidado.
- dataLayer deve ser organizado e previsível; excesso/cardinalidade e PII são tratados como risco de contrato, não como métrica de performance.
- Core Web Vitals são campo e lab com diferenças; LCP/INP/CLS usam p75 por mobile/desktop. Esta missão não implementa Web Vitals Monetized View e não afirma causalidade.

Fontes oficiais consultadas:

- https://developers.google.com/publisher-tag/guides/get-started
- https://developers.google.com/publisher-tag/guides/control-ad-loading
- https://developers.google.com/publisher-tag/guides/minimize-layout-shift
- https://developers.google.com/tag-platform/tag-manager/datalayer
- https://web.dev/articles/vitals
- https://developers.google.com/analytics/devguides/collection/ga4/event-parameters
- https://support.google.com/analytics/answer/9267744

## Leitura real

`REAL_TARGET_NOT_PROVEN`.

Foram encontrados URLs públicos no repositório, mas nenhum alvo rastreado foi considerado prova segura de ativo VOLC autorizado para uma observação real desta missão. Nenhuma URL pública foi lida pelo scanner nesta execução.

## Zero mutação externa

- Sem Supabase write.
- Sem migration.
- Sem GTM/GA4/GAM/AdSense write.
- Sem WordPress write.
- Sem n8n.
- Sem Google Ads mutate.
- Sem deploy, merge ou main.

## Endurecimento na integração

A integração na linha oficial acrescentou contraprovas e correções para três
lacunas que não apareceram na revisão original:

- host sem resolução comprovada e IP multicast agora falham fechado na guarda SSRF;
- `div` comum com `id` não é mais classificado como slot de anúncio;
- valores crus do `dataLayer` não são serializados no snapshot; permanecem apenas
  contagem e nomes de chaves, suficientes para o contrato estrutural.

O fetch público ainda não é uma sandbox nem elimina sozinho toda janela de DNS
rebinding. A capacidade continua `partial` e uma leitura real futura deve usar
alvo explicitamente autorizado e ambiente contido.
