# Destino de PR2 e PR3

## Veredito

Aplicar **301 de PR2 e PR3 para a PR1 canônica**. Não manter páginas quase iguais, não usar `noindex` como remendo e não redirecionar para a LP.

| Origem | Destino permanente |
|---|---|
| `https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr2/` | `https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr1/` |
| `https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr3/` | `https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr1/` |

### Por que 301

- As três páginas respondem à mesma intenção e foram usadas como variações de pre-sell, não como conteúdos autônomos.
- PR1 passa a conter a resposta consolidada; manter PR2 e PR3 criaria duplicação e rotas concorrentes.
- Um redirecionamento permanente preserva melhor sinais e acessos que as URLs antigas possam ter acumulado.
- A história curta das URLs e a ausência de mídia ativa reduzem o risco de consolidar agora.

## Ordem de implantação

1. Publicar a PR1 revisada e confirmar resposta `200`.
2. Atualizar todos os links internos, botões da LP, menus, anúncios salvos e automações para apontar diretamente à PR1.
3. Remover PR2 e PR3 do sitemap XML e de qualquer lista de URLs canônicas.
4. Criar os dois redirecionamentos 301.
5. Limpar cache do WordPress, CDN e proxy.
6. Testar versões com e sem barra final e com query string.
7. Monitorar `404`, cadeia de redirects e tráfego das três URLs por pelo menos quatro semanas.

## Configuração — escolher somente o método usado pela hospedagem

### Plugin Redirection no WordPress

Criar duas regras, sem regex:

```text
Source URL: /rec/quem-tem-direito-antecipar-fgts-pr2/
Target URL: /rec/quem-tem-direito-antecipar-fgts-pr1/
HTTP code: 301

Source URL: /rec/quem-tem-direito-antecipar-fgts-pr3/
Target URL: /rec/quem-tem-direito-antecipar-fgts-pr1/
HTTP code: 301
```

Marcar a opção de ignorar barra final, se disponível, e preservar parâmetros de consulta.

### Apache / `.htaccess`

Adicionar antes do bloco gerenciado pelo WordPress:

```apache
RewriteEngine On
RewriteRule ^rec/quem-tem-direito-antecipar-fgts-pr2/?$ /rec/quem-tem-direito-antecipar-fgts-pr1/ [R=301,L,NE]
RewriteRule ^rec/quem-tem-direito-antecipar-fgts-pr3/?$ /rec/quem-tem-direito-antecipar-fgts-pr1/ [R=301,L,NE]
```

O `RewriteRule` preserva a query string existente quando nenhuma nova query é definida.

### Nginx

Adicionar ao bloco do host e recarregar somente depois de validar a configuração:

```nginx
location ~ ^/rec/quem-tem-direito-antecipar-fgts-pr[23]/?$ {
    return 301 https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr1/$is_args$args;
}
```

## Testes de aceite

```bash
curl -sS -I 'https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr1/'
curl -sS -I 'https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr2/'
curl -sS -I 'https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr3/'
curl -sS -I 'https://creditoup.com.br/rec/quem-tem-direito-antecipar-fgts-pr2/?utm_source=redirect_test'
```

Aceite esperado:

- PR1: um único `200` e canonical para ela mesma.
- PR2 e PR3: um único `301`, com `Location` direto para PR1.
- Query de teste: preservada no destino.
- Nenhuma cadeia `PR2 → PR3 → PR1`, nenhum `302` e nenhum loop.

## Reversão

Se a PR1 não responder corretamente, desativar apenas as duas regras de redirect e restaurar temporariamente as URLs antigas. Não apagar o conteúdo antigo antes do aceite; mantê-lo como revisão privada ou backup até o monitoramento inicial terminar.
