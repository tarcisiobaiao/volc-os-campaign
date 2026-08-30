"""Camada de criativo — o que um anúncio mostra, antes de virar chamada de API.

Display, Demand Gen, Performance Max e Vídeo não pedem "uma imagem": pedem uma
imagem de proporção declarada, com dimensão mínima, peso máximo e quantidade
mínima por papel. Este pacote é a PORTA para os motores que produzem isso e o
contrato contra o qual o resultado é conferido — não é o motor.

    contrato.py    asset, procedência, especificação, lote, violação, falha
    requisitos.py  as exigências por canal, lidas de `requisitos.yaml`
    validacao.py   asset e lote contra a exigência — todas as violações
    porta.py       o Protocol do motor, com erro tipado
    catalogo.py    deduplicação por conteúdo, papéis, intenções e variantes
    adaptadores/   quem fala com motor de verdade

Nada aqui fala com o Google Ads. Subir asset é do domínio de campanha.
"""
