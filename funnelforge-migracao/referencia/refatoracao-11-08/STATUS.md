# Status — Funil 2, Saque-Aniversário FGTS

Atualizado em 11/08/2026, 10h. **Backup de todas as 7 páginas antes de qualquer
edição** em `../99-backup-pre-edicao/`.

## No ar e verificado

| página | id | o que mudou |
|---|---|---|
| LP | 2064 | mapa de botões novo; sai a inflação falsa e a promessa de aprovação |
| PR1 | 2067 | refeita como **hub qualificador**, 728 palavras, 6 botões coloridos |
| P1 | 2077 | reescrita, 1.083 palavras, **calculadora** + tabela legal |
| P2 | 2080 | reescrita, 973 palavras, **roteador de elegibilidade** |
| P3 | 2083 | reescrita, 843 palavras, **diagnóstico de estado** |

**LP — mapa de botões**, batendo com `_BUTTON_HREF` do engine:

```
mobile    [hub PR1] [P1]
desktop   [hub PR1] [P1] [P2]
corpo     [P2]  +  P3 como link contextual no fechamento
```

**Convenção de cor por destino**, do topo ao rodapé, em todas as páginas:
`P1 #008353 verde · P2 #ea580c laranja · P3 #2563eb azul`.

**As afirmações falsas sumiram do site inteiro** (conferido no HTML renderizado
das 5 páginas): "rende menos que a inflação", "restrição no nome podem contratar
normalmente", "nenhum banco ou fintech", "situações de quitação total",
"buscando pelo nome do programa", links para `meutudo.com.br`.

**Os 90 dias agora dizem a mesma coisa em todas as páginas:** prazo para
autorizar a consulta. A contradição com o 25º mês acabou.

**Widgets** — três, todos com regra determinística, `dataLayer` completo
(`widget_start`, `widget_validation_error`, `widget_complete`, `widget_result`,
`widget_cta_click`), `aria-live`/`role=status`/`aria-invalid`, foco programático,
troca de estado por atributo `hidden`, CTA interno no resultado. Zero porcentagem
fabricada, zero `Math.random`, zero link externo.

```
P1  Calculadora de saque anual      tabela do Anexo da Lei 8.036/90
P2  Roteador de elegibilidade       5 perguntas, 11 desfechos
P3  Diagnóstico de estado           4 perguntas, âncoras internas
```

A calculadora foi conferida contra a lei: saldo R$ 1.000 → R$ 450 (exemplo
oficial), R$ 3.000 → R$ 1.050. Abaixo de R$ 100 de saque anual ela avisa que a
antecipação não é possível, em vez de inventar um caminho.

## Depende de você

**1 · O 301 de PR2/PR3.** Snippet pronto em `DEPLOY-nginx-301.conf`. Não deu para
fazer pela API: o site não tem plugin de redirect e o `_yoast_wpseo_canonical` não
está registrado no REST. As duas páginas já estão **órfãs** — nenhum link interno
aponta para elas —, então o risco atual é baixo, mas o 301 é o que consolida.

**2 · Conferir os links da `caixa.gov.br` no navegador.** Esse domínio devolve
`302` para qualquer cliente automatizado, inclusive a home. É bloqueio de bot, não
link morto, mas eu não pude confirmar. Há um link da CAIXA em P1 e um em P2.

**3 · A verificação de serviços financeiros do Google.** Gate de conta, não de
conteúdo. Pode segurar o lançamento com o funil perfeito.

## O bug que quebrava os três widgets — e o anúncio dentro do widget

**Causa raiz: `<p>` vazio com atributos é removido pelo `the_content`, e leva o
`id` junto.** Os widgets usavam `<p class="…error" id="…" aria-live="polite"></p>`
como placeholder de mensagem de erro. O WordPress apagava o elemento inteiro, o
`getElementById` devolvia `null`, e o JS morria em
`Cannot set properties of null (setting 'textContent')` — antes de qualquer
clique. O `<div>` vazio, ao lado, sobrevivia.

Comprovado comparando o arquivo com o HTML servido: **faltavam exatamente os 6
ids dos elementos vazios**, e nenhum outro.

**A correção resolve os dois problemas de uma vez.** Todo `<p>` foi trocado por
`<div>` dentro dos três widgets — hoje eles têm **zero** `<p>`. Isso:

1. acaba com a remoção do placeholder, e o JS volta a funcionar;
2. **tira o widget da contagem do injetor de anúncio.** Injetores de anúncio em
   nível de conteúdo escolhem onde inserir contando `<p>` do artigo. O widget do
   P3 tinha 14 `<p>`; a contagem caía dentro dele, e o anúncio era inserido entre
   o rótulo e o título. Com zero `<p>`, o widget deixa de existir para essa conta.

**Regra para o motor:** *bloco `wp:html` não pode conter nenhum `<p>`. Placeholder
vazio é `<div>` ou `<span>`, nunca `<p>`.* Está registrada no docstring de
`blocos.py`.

⚠️ **O que eu não consegui provar:** em navegador headless os anúncios não
carregam, então o `anúncio_dentro = 0` do teste não é prova. O injetor desta
página parece ser `script.joinads.me`, não o AdSense. **Confira visualmente.** Se
ainda acontecer, o conserto definitivo é na configuração do injetor — a estrutura
já não oferece ponto de inserção.

## O validador — `blocos.py::validar()`

Roda antes de publicar; lista vazia libera. **Cada regra existe porque um defeito
chegou ao ar**, e a data entre parênteses é o caso que a originou.

```
1   copy direcional no corpo ("responda abaixo") ............ P3, 11/08
1b  parágrafo colado num bloco wp:html ..................... P1/P3, 11/08
2   <p> dentro de wp:html .................................. 3 widgets, 11/08
3   is-style-outline (botão fantasma) ...................... PR1, 11/08
4   wp:buttons consecutivas sem spacer ..................... P1, 11/08
5   cor do botão diferente da do destino ................... convenção
6   blocos abertos ≠ fechados .............................. sanidade
```

As regras 1 e 1b são de **política de anúncio**, não de estética. O injetor
insere entre blocos do conteúdo; um parágrafo que apresenta o que vem em seguida
vira legenda do anúncio quando o anúncio cai no meio. Por isso:

> **Nada apresenta o widget de fora.** O widget se apresenta sozinho — tem título
> e chamada próprios. Antes dele só pode vir um heading ou um separador, nunca um
> parágrafo.

Foi assim que "Responda abaixo em que estado você está" acabou logo acima de um
anúncio em P3. A frase virou copy interna do widget e o lugar dela na página
virou um `<h2>`.

⚠️ **O validador tinha o mesmo defeito que caçava.** A primeira versão só casava
`<p>` sem atributos, então deixou passar a nota `<p class="has-text-align-center">`
que estava colada no widget do P3. Corrigido para `<p\b[^>]*>` nas duas regras.

## Espaçamento: margem no bloco, não spacer ao lado

O tema zera margem de `wp-block-group` e `wp-block-details`, e o `gap` do flex
só vale dentro de um mesmo `wp:buttons`. Medido em produção depois do conserto:

```
botões consecutivos    8px      (wp:spacer, inserido por botoes())
callouts consecutivos  18px     (margin no próprio bloco)
FAQ consecutivas       10px     (margin no próprio bloco)
```

O `spacer` entre botões continua sendo remendo — é uma das três falhas no
`PROMPT-CODEX-03-BLINDAGEM-TEMA.md`, para virar CSS de tema.

## Detalhe operacional que custou tempo

O Elementor serve a LP de um cache de elemento que **não invalida** quando se
escreve direto no `_elementor_data` via REST — nem forçando `save_post`, nem
limpando `_elementor_css`. O que resolve:

```
curl -X DELETE -u USER:APP_PASSWORD https://creditoup.com.br/wp-json/elementor/v1/cache
```

Vale para qualquer edição futura de página Elementor por API.

## Manutenção com data marcada

**Todo julho** — conferir o Anexo da Lei 8.036/90. O Executivo pode alterar
faixas, alíquotas e parcelas adicionais **até 30 de junho**, com vigência em **1º
de janeiro** seguinte (art. 20-D, § 2º). Se mudar: tabela de P1, exemplos e a
calculadora mudam juntos.

**01/11/2026** — acaba a regra transitória de cinco direitos anuais e passa a
valer o limite de três. Citado em PR1, P1 e P2.
