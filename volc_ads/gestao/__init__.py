"""Gestão do dia a dia de campanhas que JÁ ESTÃO no ar (Google Ads API v25).

Nascer e gerir são dois ciclos, e este pacote é só o segundo. O nascimento
(`volc_ads.subir`) é atômico de propósito: campanha meio criada é pior que
campanha nenhuma. A gestão é o oposto: num lote de 40 negativas, uma recusada
por política não pode segurar as outras 39 — daí `partial_failure`, que só
este pacote usa.

  acoes.py   uma classe imutável por ação: valida local, monta a
             `MutateOperation` (função pura sobre `get_type`), diz como ler o
             "antes" e qual é o reverso.
  estado.py  lê o "antes" na conta (GAQL conferida pelo catálogo do servidor).
  lote.py    N ações num `MutateGoogleAdsRequest` com `partial_failure=True`,
             falha mapeada de volta à ação pelo índice da operação.
  ledger.py  a tradução para as linhas do ledger v10_02 (sem tocar no banco).
"""
