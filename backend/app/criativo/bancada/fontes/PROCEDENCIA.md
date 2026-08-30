# Fontes empacotadas do motor tipográfico

## Por que a fonte mora no repositório

`Recibo.versoes.fonte_sha256` entra na `assinatura_determinista`. Uma fonte
resolvida por caminho de máquina faz o **mesmo pedido** produzir **assinaturas
diferentes** em máquinas diferentes — e a assinatura existe justamente para
responder "o motor repetiu?". Versionar o arquivo é o que torna a resposta
verdadeira em checkout limpo.

A versão anterior deste motor listava
`/Users/mac/Desktop/Volc Mídia Global/motor-imagem/compartilhado/prensa-poc/fonts`
como primeira pista, e a docstring afirmava "não há caminho absoluto embutido".
As duas coisas eram verdade ao mesmo tempo, e a segunda era falsa.

## O que está aqui

| Arquivo | Família | Licença | Origem |
|---|---|---|---|
| `Inter-Variable.ttf` | Inter | **SIL Open Font License 1.1** | https://github.com/rsms/inter |

Strings lidas da própria tabela `name` do arquivo:

- copyright: `Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)`
- licença: `This Font Software is licensed under the SIL Open Font License, Version 1.1`
- url: `https://openfontlicense.org`

A OFL 1.1 permite uso, estudo, modificação e **redistribuição**, inclusive
embutida em software, desde que a fonte não seja vendida sozinha e o aviso de
licença acompanhe. Este arquivo é o aviso.

## Ordem de resolução

1. **esta pasta** — determinística em qualquer checkout;
2. `CRIATIVO_FONTES_DIR` — para quem quiser outra família de propósito;
3. **falha com motivo** — nunca uma fonte de sistema escolhida por acaso, que
   mudaria o pixel sem mudar nada do pedido.
