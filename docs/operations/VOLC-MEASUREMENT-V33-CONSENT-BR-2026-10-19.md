# VOLC Measurement v3.3 — medição própria no Brasil

Data: 19/10/2026. Owner: Tarcisio. Estado: publicado e provado, com uma
pendência de tema descrita abaixo.

## Decisão operacional

Para a operação brasileira, o aviso nativo do tema será informativo. As duas
tags próprias do VOLC não dependem do Consent Mode do Google:

- `VOLC Sensor v3.3`;
- `WEBS Wrapper v2`.

A decisão não foi aplicada a Google Analytics, Google Ads, Google Tag,
Conversion Linker ou tags de conversão. Os filtros de PII, a minimização do
payload, Global Privacy Control e `window.volcOptOut()` do Sensor foram
preservados. Este recibo registra implementação e prova técnica; não substitui
revisão jurídica da base legal adotada pelo controlador.

## Delta publicado

- container: `GTM-N4KS27ZV`;
- versão anterior e rollback: v37, `VOLC Measurement v3.2 - 2026-10-19`;
- versão live: v38, `VOLC Measurement v3.3 - 2026-10-19`;
- workspace isolado: 40;
- tags alteradas: IDs 23 e 39, somente;
- requisitos adicionais de consentimento: lista vazia nas duas tags;
- triggers preservados: Initialization no Wrapper e DOM Ready no Sensor;
- quick preview: zero erros de compilação.

O código do Sensor deixou de consultar `analytics_storage` no início e no
flush. O Wrapper deixou de condicionar o `sessionStorage` ao Consent Mode. Os
dois continuam bloqueando PII e IDs de clique; campanha e conteúdo numéricos
continuam permitidos somente nas chaves UTM conhecidas.

## Provas

1. Três testes focados passaram: allowlist numérica, não herança de campanha
   inválida e ausência dos gates de Consent Mode com GPC/opt-out preservados.
2. O verificador read-only confirmou v38, hashes dos dois HTMLs, triggers,
   consentimento adicional vazio, heartbeat recente, REST anônimo bloqueado e
   origem inválida recusada.
3. Em canário público, o estado final do `dataLayer` foi
   `analytics_storage=denied` e `ad_storage=denied`. Depois disso chegaram quatro
   eventos `volc_scroll_mark` ao Supabase oficial. O Sensor e o Wrapper estavam
   ativos e a campanha numérica foi preservada.
4. Nenhum clique em anúncio ou conversão artificial foi gerado.

## Termos e políticas

As páginas públicas foram atualizadas e relidas:

- `/privacidade/` — post 3, Elementor preservado;
- `/termos/` — post 101, Elementor preservado;
- `/politica-de-cookies/` — post 2503, Gutenberg preservado.

As páginas descrevem os campos efetivamente medidos, `sessionStorage`, filtros
de PII, finalidades, terceiros e controles. QA em 390×844 e 1440×900 retornou
HTTP 200, títulos e seções presentes e zero overflow horizontal. O conteúdo
Elementor anterior está em backup 0600 no servidor em
`/var/backups/volc-legal-20261019/`; as revisões WordPress 2529, 2530 e 2531
também preservam o ciclo de edição.

## Limite e próximo passo

O tema ativo ainda é o checkout atual `wgc3` e o MU-plugin
`volc-consent-manager.php` continua exibindo o gerenciador antigo e enviando
`granted`. Nenhum arquivo do tema foi alterado nesta missão. No cutover já
planejado para o Belvedere atualizado, a sequência segura é:

1. provar em preview que o aviso nativo aparece e aponta para a Política de
   Privacidade;
2. desativar o MU-plugin antigo para não haver dois avisos;
3. publicar o tema sem alterar seu código;
4. repetir o canário de medição e o QA mobile;
5. manter v37 como rollback de GTM até o fechamento do cutover.
