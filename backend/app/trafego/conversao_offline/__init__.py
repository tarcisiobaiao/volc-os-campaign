"""Conversão offline de volta ao Google, com o valor que nós medimos (W14, P07).

Monta, a partir de cliques capturados (`site_visits`) e da receita datada com
câmbio versionado (W12, v23_01), os eventos que a Data Manager API aceita em
`events:ingest`. Reusa a fronteira de `app.trafego.data_manager` (envelope,
validação item a item, dedup) e a trava de dois fatores de
`volc_ads.gads.modo` para o único caminho que manda de verdade.

    domain/          valor medido, identidade do evento, regras de pulo
    application/     portas (cliques, receita, câmbio, registro, transporte),
                     preparar o lote, validar no Google, envio real travado
    infrastructure/  transporte HTTP da Data Manager e registro PostgREST (v25_01)

O que este pacote NÃO faz: escolher meta de campanha, mudar a ação primária,
remover o valor fixo da conta ou ligar o envio real. Isso é do operador, e o
roteiro está em `docs/architecture/W14-PLANO-CONTA-GOOGLE-CONVERSOES.md`.
"""
