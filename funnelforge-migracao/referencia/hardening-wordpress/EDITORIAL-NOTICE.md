# Aviso editorial: uma origem por resposta

`volc-editorial-notice-owner.php` e um adaptador independente dos ajustes de
botoes de `volc-funnel-hardening.php`. Pode atuar nas LPs Elementor e nas internas.

O engine continua gerando o aviso: como prefixo nas paginas internas
(Gutenberg) e como ULTIMO container da LP Elementor (15/10/2026). Nao remover
esse fallback nem acrescentar uma flag cega `site_has_disclaimer=true`.

Integracao do site: o aviso global (`creditoup-compliance-hardening.php`) e
impresso no `wp_footer`, ou antes de `</body>` quando o template nao chama
`wp_footer`, e **somente depois de imprimi-lo** emite:

```php
do_action( 'volc_editorial_disclosure_rendered' );
```

Como o sinal agora chega depois do conteudo, o dono decide no FIM da resposta
(buffer aberto em `template_redirect`, prioridade 0): com o sinal, retira o aside
canonico do motor do HTML final; sem o sinal, nao toca em nada. Resultado provado
no WordPress descartavel: exatamente um aviso em LP V1, interna, LP V2 e pagina
comum (`INSTALACAO-HARDENING.md`). Os filtros de conteudo (`the_content`,
`container_should_render`) continuam para um aviso global que seja impresso
antes do conteudo.

O aviso global precisa identificar o editor independente, ausencia de vinculo,
nao prestacao de inscricao/contratacao e nao solicitacao de credenciais. A adequacao
da copy precisa ser validada no site, nao inferida de uma configuracao booleana.

O adaptador reconhece apenas o aside canonico do engine. Conteudo desconhecido,
container com outros widgets, editor/AJAX e ausencia de DOMDocument preservam
o original. Nao inspeciona nem altera anuncios/scripts ou outras secoes.

Cache: o container canonico vira elemento dinamico do Elementor, para nao gravar
a decisao de ter/nao ter aviso global. Na primeira implantacao, invalidar apenas
os metadados `_elementor_element_cache` das LPs afetadas. Sem purge global.

Validacao isolada: `php validate-notice-owner.php` (18 cenarios, sem WordPress).
Integracao: testar renderer com e sem global, cache frio/quente e editor; comparar
conteudo e metadados salvos antes/depois. Screenshots autenticados continuam
necessarios para validar apresentacao, pois o teste PHP nao valida o layout.

Remover o adaptador restaura o aviso do engine; remover so o adaptador e manter o
hardening duplica o aviso (instalar e remover os tres arquivos juntos). Revalidar os caches pontuais;
nao reverter dados dos posts para efetuar rollback deste adaptador.
