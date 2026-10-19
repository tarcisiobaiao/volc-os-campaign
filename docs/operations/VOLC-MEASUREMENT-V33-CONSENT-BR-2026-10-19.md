# VOLC Measurement v3.3 — medição própria no Brasil

Data: 19/10/2026. Owner: Tarcisio. Estado: publicado e provado, incluindo o
cutover do tema e do aviso nativo.

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

## Cutover do Belvedere

O cutover foi concluído no mesmo dia:

- tema ativo: `belvedere` 1.39.5; o pacote passou por verificação de caminhos,
  integridade do ZIP e lint dos 54 arquivos PHP;
- tema anterior preservado: `wgc3` 1.0.0, instalado e disponível para rollback;
- backup 0600 no servidor em
  `/var/backups/volc-belvedere-cutover-20261019/`, contendo banco completo,
  tema, opções, widgets, menus, CSS e o MU-plugin anterior;
- logo, menus, cores, rodapé, home e aviso nativo configurados pelo script
  idempotente `scripts/configurar_belvedere_creditoup.php`;
- o Wrapper opcional do próprio tema ficou desligado, evitando duplicidade com
  a autoridade do GTM; campos de script do tema ficaram vazios;
- `r` e `rec` continuam sob o Custom Post Type UI; o tema registra somente os
  CPTs que já eram autoridade dele (`responda`, `lp` e `dis`);
- `volc-consent-manager.php` foi removido da pasta de MU-plugins e preservado no
  backup. O cache público do WP Rocket foi invalidado pela API do plugin;
- a home usa o destaque nativo e uma grade de oito conteúdos. O crédito externo
  fixo do fornecedor do tema foi ocultado por CSS adicional do WordPress, sem
  alterar os arquivos do Belvedere;
- o compartilhamento social do tema ficou desligado. Assim, LP e pré-sell não
  oferecem saídas para Facebook, X ou WhatsApp; os três links fixos do
  fornecedor permanecem no HTML do tema, mas dentro do bloco oculto e sem
  superfície clicável. Retirá-los do HTML exigiria um child theme ou hardening
  adicional e não foi misturado a este cutover;
- a LP Senac deixou `elementor_canvas` e passou a usar o shell normal apenas
  para obter `wp_head`, `wp_footer` e o aviso nativo. CSS adicional oculta
  header, footer institucional, título, autor e relacionados, mantendo o
  conteúdo Elementor full-screen.

## Provas pós-cutover

1. Home, LP, pré-sell, Privacidade, Termos e Política de Cookies responderam
   HTTP 200 e serviram assets do Belvedere.
2. QA real no Chromium em 390 px confirmou `scrollWidth = innerWidth = 390`,
   zero elementos fora do viewport, exatamente um aviso nativo e nenhum aviso
   antigo. O botão `Entendi` gravou `localStorage.cookieConsent=accepted` e
   ocultou o aviso.
3. Na LP, o conteúdo Elementor continuou presente, com nove links/botões, shell
   visual do tema oculto e aviso nativo visível; GTM e Sensor estavam ativos.
4. O verificador oficial releu o GTM v38, hashes, triggers, consentimentos,
   heartbeat, RLS/anon e origem inválida: resultado global `ok: true`.
5. Um canário institucional, sem clique em anúncio, preservou
   `utm_campaign=987654321098` e `utm_content=876543210987`. O Supabase oficial
   recebeu oito eventos: ready, quatro scrolls, render GPT, engajamento e dwell.
6. O log não registrou fatal ou parse error do Belvedere. O warning recorrente
   do plugin legado JoinAds já existia antes do cutover e ficou fora deste
   escopo.

O código do tema não foi alterado. A decisão operacional descrita aqui não
substitui revisão jurídica da base legal adotada pelo controlador.

## Rollback operacional

O rollback não depende de baixar novamente nenhum artefato:

1. ativar o tema preservado com
   `wp theme activate wgc3 --allow-root`;
2. restaurar `volc-consent-manager.php` do diretório de backup para
   `wp-content/mu-plugins/`, mantendo proprietário e modo originais;
3. restaurar o template da LP 2306 para `elementor_canvas`;
4. restaurar, se necessário, `theme_mods_wgc3`, widgets, menus e CSS a partir
   dos arquivos do backup;
5. executar `rocket_clean_domain()` e `wp cache flush --allow-root`;
6. reler as seis rotas, repetir o QA 390 px e executar o verificador de medição.

Não há rollback de GTM neste procedimento: a v38 continuou íntegra depois do
cutover. A v37 permanece como versão anterior disponível no próprio GTM.
