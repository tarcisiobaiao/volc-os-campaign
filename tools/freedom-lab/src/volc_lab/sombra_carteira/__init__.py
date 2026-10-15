"""Motor shadow da carteira: a prova Senac generalizada para todas as campanhas
Google Ads de uma conta (W13, 15/10/2026).

Camadas (Clean Architecture pragmática, CLAUDE.md):

    dominio.py      reconciliação custo × receita e decisão; puro, sem I/O
    portas.py       contratos de leitura consumidos do W11 (custo) e do W12
                    (receita datada com câmbio versionado), por interface
    adaptadores.py  snapshot JSON (replay, testes) e PostgREST só-leitura
    aplicacao.py    gera um experimento conferido por sha256 por campanha e o
                    manifesto do lote; nunca executa nada
    __main__.py     CLI: gerar | replay

Nada aqui chama Google Ads, GTM, GA4, WordPress ou n8n, e nada grava no banco.
A recomendação é sombra: `executada` é sempre False e não há valor sugerido.
"""
