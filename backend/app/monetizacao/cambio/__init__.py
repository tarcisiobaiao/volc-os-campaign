"""Câmbio versionado (W12, migration v23_01).

A regra de RESOLUÇÃO (qual taxa vale para um dia) mora num lugar só: a função
`public.cambio_resolver` da v23_01. Este pacote não a reimplementa; ele só
COLETA cotações de uma fonte pública e grava cada uma como versão imutável em
`exchange_rate_history` (par, data, taxa, fonte, as_of da fonte). Quem precisa
converter chama a função no banco e grava a cotação que ela devolveu.

    domain/          Cotacao e suas invariantes (sem I/O)
    application/     caso de uso de coleta e as portas
    infrastructure/  PTAX do Banco Central e o repositório PostgREST
"""
