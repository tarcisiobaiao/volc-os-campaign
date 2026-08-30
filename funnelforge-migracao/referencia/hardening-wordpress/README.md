# Hardening do funil WordPress

Arquivos de produção:

- `volc-funnel-hardening.php`: MU-plugin restrito ao post type `rec`.
- `volc-funnel-hardening.css`: espaçamento entre blocos `wp:buttons` consecutivos.

## O que o patch faz

1. Remove o filtro inseguro `lt_p_img()` do tema `wgc3` e o substitui por um filtro que só desembrulha parágrafos que realmente contêm uma imagem.
2. Substitui blocos `core/html` por tokens durante `the_content` e restaura o HTML bruto no fim. Regexes do tema, contadores de parágrafo e shortcodes não atravessam essa fronteira.
3. Remove a opção `outline` do editor de posts `rec` e normaliza conteúdo legado para o botão sólido padrão.
4. Adiciona `0.5em` somente entre grupos `.wp-block-buttons` adjacentes em páginas `single-rec`.
5. Remove o suporte vazio `editor-font-sizes` declarado pelo tema, que fazia o WordPress iterar sobre um booleano e emitir warning no pipeline de estilos.

## Limites deliberados

- Nenhum arquivo do tema pai é alterado.
- Nenhuma página Elementor ou post type `r` recebe PHP, JS ou CSS do patch.
- HTML bruto passa a ser responsabilidade do próprio bloco: shortcodes e otimização automática de imagens dentro dele não são executados. A auditoria final encontrou 30 blocos HTML publicados e nenhum shortcode registrado ou imagem nesses blocos.

## Característica do rollback

Remover os dois arquivos de `wp-content/mu-plugins/` e limpar o cache do WP Rocket. Como não há migração nem alteração de conteúdo, o rollback é imediato.

## Deploy

Executar a partir da raiz deste repositório:

```bash
scp -i /Users/mac/.ssh/volc-hetzner-wordpress-2026 \
  auditoria-redator/05-hardening-wordpress/volc-funnel-hardening.php \
  auditoria-redator/05-hardening-wordpress/volc-funnel-hardening.css \
  root@5.161.111.86:/tmp/

ssh -i /Users/mac/.ssh/volc-hetzner-wordpress-2026 root@5.161.111.86 \
  'install -o www-data -g www-data -m 0644 /tmp/volc-funnel-hardening.php /var/www/creditoup.com.br/wp-content/mu-plugins/volc-funnel-hardening.php; install -o www-data -g www-data -m 0644 /tmp/volc-funnel-hardening.css /var/www/creditoup.com.br/wp-content/mu-plugins/volc-funnel-hardening.css'
```

## Purge do WP Rocket

```bash
ssh -i /Users/mac/.ssh/volc-hetzner-wordpress-2026 root@5.161.111.86 \
  'cd /var/www/creditoup.com.br; wp eval '\''rocket_clean_domain(); rocket_clean_minify(); rocket_clean_cache_busting();'\'' --allow-root'
```

## Verificação

Os scripts não gravam posts nem opções:

```bash
wp eval-file /tmp/validate-fixture.php --path=/var/www/creditoup.com.br --allow-root
wp eval-file /tmp/validate-published-content.php --path=/var/www/creditoup.com.br --allow-root
```

Resultado validado em produção: 32 posts publicados, 30 blocos `core/html`, zero bloco/ID ausente e zero warning.

## Rollback recuperável

```bash
ssh -i /Users/mac/.ssh/volc-hetzner-wordpress-2026 root@5.161.111.86 \
  'install -d -m 0750 /var/backups/creditoup-hardening/disabled; mv /var/www/creditoup.com.br/wp-content/mu-plugins/volc-funnel-hardening.php /var/www/creditoup.com.br/wp-content/mu-plugins/volc-funnel-hardening.css /var/backups/creditoup-hardening/disabled/; cd /var/www/creditoup.com.br; wp eval '\''rocket_clean_domain(); rocket_clean_minify(); rocket_clean_cache_busting();'\'' --allow-root'
```
