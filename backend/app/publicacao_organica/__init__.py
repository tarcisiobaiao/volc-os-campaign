"""Publicacao organica — a porta VOLC para o control plane externo (P12-T09).

Camadas, na ordem em que uma requisicao as atravessa:

    rotas.py           HTTP: codigo, corpo cru validado a mao, portao de dono
    aplicacao.py       orquestracao: criar -> liberar -> reivindicar ->
                       despachar -> concluir -> reconciliar
    dominio.py         regras sem banco nem rede: vocabulario, chave de
                       idempotencia, sanitizacao, leitura de estado
    infraestrutura.py  Supabase por funcao governada; nenhuma escrita direta
    portas.py          o contrato do control plane, e o que a API oficial NAO tem
    adaptadores/       postiz.py (real) e fake.py (HTTP hermetico para E2E)
"""
from app.publicacao_organica import dominio, portas  # noqa: F401

__all__ = ["dominio", "portas"]
