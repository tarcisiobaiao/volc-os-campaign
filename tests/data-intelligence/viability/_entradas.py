"""Construtores de entrada compartilhados pelos testes de viabilidade (não é módulo de produto)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import (
    Autorizacao, Cambio, EntradaViabilidade, Evidencia, JanelaObservada, MedidaContagem, MedidaMonetaria, PerdaMaxima, Taxa,
)

AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
EFETIVO = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)  # vigência/disponibilidade dos parâmetros versionados


def autorizacao(expires_at=None, issuer="owner:teste", effective_at=EFETIVO, disponivel_em=EFETIVO, authorization_id="AUTH-T-0001", version="1"):
    return Autorizacao.emitir(authorization_id=authorization_id, version=version, issuer=issuer, effective_at=effective_at, expires_at=expires_at, disponivel_em=disponivel_em)


def entrada(cliques=634, custo="554.75", receita="7.77", moeda_receita="USD", taxa="5.25", cambio_ev=Evidencia.ESTIMATED,
            receita_ev=Evidencia.RECONCILED, moeda_rec_ev=Evidencia.ATTESTED, revshare="1", imposto=None, dias_maduros=16,
            perda=None, horizonte=None, custo_ev=Evidencia.OBSERVED, cliques_ev=Evidencia.OBSERVED, receita_none=False, custo_none=False,
            autorizacao_perda=None, visitas=None, janela=None, freshness_sla_dias=7, flags_qualidade=()):
    return EntradaViabilidade(
        candidato_id="cand-x", vertical="v", pais="BR", fonte_custo="google_ads", fonte_receita="joinads", as_of=AS_OF,
        janela=janela or JanelaObservada(inicio="2026-09-26", fim="2026-10-11", dias_maduros=dias_maduros),
        cliques=MedidaContagem(valor=None if cliques is None else cliques, evidencia=cliques_ev if cliques is not None else Evidencia.ABSENT, disponivel_em=AS_OF),
        custo=MedidaMonetaria(valor=None if custo_none else Dinheiro.de_decimal(custo, "BRL"), evidencia=Evidencia.ABSENT if custo_none else custo_ev, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF),
        receita=MedidaMonetaria(valor=None if receita_none else Dinheiro.de_decimal(receita, moeda_receita), evidencia=Evidencia.ABSENT if receita_none else receita_ev, moeda_evidencia=moeda_rec_ev, disponivel_em=AS_OF),
        cambio=Cambio(taxa=None if taxa is None else Decimal(taxa), de="USD", para="BRL", proveniencia="literal_app" if taxa else "ausente", evidencia=cambio_ev if taxa else Evidencia.ABSENT,
                      effective_at=EFETIVO if taxa else None, disponivel_em=EFETIVO if taxa else None, versao="teste" if taxa else ""),
        revshare=Taxa(valor=Decimal(revshare), evidencia=Evidencia.ATTESTED, proveniencia="tela", effective_at=EFETIVO, disponivel_em=EFETIVO, versao="teste"),
        imposto=Taxa(valor=None if imposto is None else Decimal(imposto), evidencia=Evidencia.UNKNOWN if imposto is None else Evidencia.ATTESTED, proveniencia="x",
                     effective_at=None if imposto is None else EFETIVO, disponivel_em=None if imposto is None else EFETIVO, versao="" if imposto is None else "teste"),
        perda_maxima=PerdaMaxima(valor=None if perda is None else Dinheiro.de_decimal(perda, "BRL"), horizonte_dias=horizonte,
                                 autorizacao=(autorizacao_perda or autorizacao()) if (perda is not None or horizonte is not None) else None),
        visitas=None if visitas is None else MedidaContagem(valor=visitas, evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF),
        freshness_sla_dias=freshness_sla_dias, flags_qualidade=tuple(flags_qualidade),
    )
