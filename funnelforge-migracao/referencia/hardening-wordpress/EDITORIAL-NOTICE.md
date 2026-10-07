# Aviso editorial: uma origem por resposta

`volc-editorial-notice-owner.php` e um adaptador independente dos ajustes de
botoes de `volc-funnel-hardening.php`. Pode atuar nas LPs Elementor e nas internas.

O engine continua gerando o aviso como primeiro container/prefixo. Nao remover
esse fallback nem acrescentar uma flag cega `site_has_disclaimer=true`.

Integracao do site: instalar o adaptador como MU-plugin e, **somente depois de
imprimir efetivamente o aviso global equivalente**, emitir:

```php
do_action( 'volc_editorial_disclosure_rendered' );
```

O aviso global precisa identificar o editor independente, ausencia de vinculo,
nao prestacao de inscricao/contratacao e nao solicitacao de credenciais. A adequacao
da copy precisa ser validada no site, nao inferida de uma configuracao booleana.

O adaptador reconhece apenas o aside canonico do engine. Conteudo desconhecido,
container com outros widgets, editor/AJAX e ausencia de DOMDocument preservam
o original. Nao inspeciona nem altera anuncios/scripts ou outras secoes.

Cache: o container canonico vira elemento dinamico do Elementor, para nao gravar
a decisao de ter/nao ter aviso global. Na primeira implantacao, invalidar apenas
os metadados `_elementor_element_cache` das LPs afetadas. Sem purge global.

Validacao isolada: `php validate-notice-owner.php` (13 cenarios, sem WordPress).
Integracao: testar renderer com e sem global, cache frio/quente e editor; comparar
conteudo e metadados salvos antes/depois. Screenshots autenticados continuam
necessarios para validar apresentacao, pois o teste PHP nao valida o layout.

Remover o adaptador restaura o aviso do engine. Revalidar os caches pontuais;
nao reverter dados dos posts para efetuar rollback deste adaptador.
