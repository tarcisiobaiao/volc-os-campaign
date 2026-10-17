"""Construtores de entrada compartilhados pelos testes de viabilidade (não é módulo de produto)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import (
    Cambio, EntradaViabilidade, Evidencia, JanelaObservada, MedidaContagem, MedidaMonetaria, PerdaMaxima, Taxa,
)

AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def entrada(cliques=634, custo="554.75", receita="7.77", moeda_receita="USD", taxa="5.25", cambio_ev=Evidencia.ESTIMATED,
            receita_ev=Evidencia.RECONCILED, moeda_rec_ev=Evidencia.ATTESTED, revshare="1", imposto=None, dias_maduros=16,
            perda=None, horizonte=None, custo_ev=Evidencia.OBSERVED, cliques_ev=Evidencia.OBSERVED, receita_none=False, custo_none=False):
    return EntradaViabilidade(
        candidato_id="cand-x", vertical="v", pais="BR", fonte_custo="google_ads", fonte_receita="joinads", as_of=AS_OF,
        janela=JanelaObservada(inicio="2026-09-26", fim="2026-10-11", dias_maduros=dias_maduros),
        cliques=MedidaContagem(valor=None if cliques is None else cliques, evidencia=cliques_ev if cliques is not None else Evidencia.ABSENT, disponivel_em=AS_OF),
        custo=MedidaMonetaria(valor=None if custo_none else Dinheiro.de_decimal(custo, "BRL"), evidencia=Evidencia.ABSENT if custo_none else custo_ev, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF),
        receita=MedidaMonetaria(valor=None if receita_none else Dinheiro.de_decimal(receita, moeda_receita), evidencia=Evidencia.ABSENT if receita_none else receita_ev, moeda_evidencia=moeda_rec_ev, disponivel_em=AS_OF),
        cambio=Cambio(taxa=None if taxa is None else Decimal(taxa), de="USD", para="BRL", proveniencia="literal_app" if taxa else "ausente", evidencia=cambio_ev if taxa else Evidencia.ABSENT),
        revshare=Taxa(valor=Decimal(revshare), evidencia=Evidencia.ATTESTED, proveniencia="tela"),
        imposto=Taxa(valor=None if imposto is None else Decimal(imposto), evidencia=Evidencia.UNKNOWN if imposto is None else Evidencia.ATTESTED, proveniencia="x"),
        perda_maxima=PerdaMaxima(valor=None if perda is None else Dinheiro.de_decimal(perda, "BRL"), horizonte_dias=horizonte, proveniencia="owner" if perda else "ausente"),
    )


