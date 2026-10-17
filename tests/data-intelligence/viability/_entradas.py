"""Construtores de entrada compartilhados pelos testes de viabilidade (não é módulo de produto).

Reconciliado pelo integrador: construção nativa V2 (parâmetros versionados, Autorizacao) do subagente B
+ parâmetros de teste do subagente A (visitas, cobertura, observado_em, flags por medida, sla).
"""
from __future__ import annotations

import copy
import dataclasses
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
            autorizacao_perda=None, visitas=None, visitas_ev=Evidencia.OBSERVED, perda_moeda="BRL", janela=None,
            cobertura_ppm=1_000_000, dias_custo_sem_receita=0, observado_em=None, flags_medidas=None, sla_dias=None,
            freshness_sla_dias=7, flags_qualidade=()):
    """Defaults = V1 (+ cobertura de receita completa, exigida pelo V2 para veredito positivo).
    `visitas=None` → sem medida; `visitas=int` → MedidaContagem (0 é valor válido).
    `observado_em={"receita": dt}` / `flags_medidas={"receita": ("invalid_schema",)}` gravam campos nas medidas;
    `cobertura_ppm`/`dias_custo_sem_receita` vão na janela (ignorados se `janela` for passada);
    `sla_dias` sobrescreve `freshness_sla_dias` quando informado."""
    observado_em = observado_em or {}
    flags_medidas = flags_medidas or {}

    def medida(nome, m):
        extra = {}
        if nome in observado_em:
            extra["observado_em"] = observado_em[nome]
        if nome in flags_medidas:
            extra["flags_qualidade"] = tuple(flags_medidas[nome])
        return v2(m, **extra) if extra else m

    if janela is None:
        janela = JanelaObservada(inicio="2026-09-26", fim="2026-10-11", dias_maduros=dias_maduros,
                                 cobertura_receita_ppm=cobertura_ppm, dias_custo_sem_receita=dias_custo_sem_receita)
    tem_perda = perda is not None or horizonte is not None
    return EntradaViabilidade(
        candidato_id="cand-x", vertical="v", pais="BR", fonte_custo="google_ads", fonte_receita="joinads", as_of=AS_OF,
        janela=janela,
        cliques=medida("cliques", MedidaContagem(valor=None if cliques is None else cliques, evidencia=cliques_ev if cliques is not None else Evidencia.ABSENT, disponivel_em=AS_OF)),
        custo=medida("custo", MedidaMonetaria(valor=None if custo_none else Dinheiro.de_decimal(custo, "BRL"), evidencia=Evidencia.ABSENT if custo_none else custo_ev, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF)),
        receita=medida("receita", MedidaMonetaria(valor=None if receita_none else Dinheiro.de_decimal(receita, moeda_receita), evidencia=Evidencia.ABSENT if receita_none else receita_ev, moeda_evidencia=moeda_rec_ev, disponivel_em=AS_OF)),
        cambio=Cambio(taxa=None if taxa is None else Decimal(taxa), de="USD", para="BRL", proveniencia="literal_app" if taxa else "ausente", evidencia=cambio_ev if taxa else Evidencia.ABSENT,
                      effective_at=EFETIVO if taxa else None, disponivel_em=EFETIVO if taxa else None, versao="teste" if taxa else ""),
        revshare=Taxa(valor=Decimal(revshare), evidencia=Evidencia.ATTESTED, proveniencia="tela", effective_at=EFETIVO, disponivel_em=EFETIVO, versao="teste"),
        imposto=Taxa(valor=None if imposto is None else Decimal(imposto), evidencia=Evidencia.UNKNOWN if imposto is None else Evidencia.ATTESTED, proveniencia="x",
                     effective_at=None if imposto is None else EFETIVO, disponivel_em=None if imposto is None else EFETIVO, versao="" if imposto is None else "teste"),
        perda_maxima=PerdaMaxima(valor=None if perda is None else Dinheiro.de_decimal(perda, perda_moeda), horizonte_dias=horizonte,
                                 autorizacao=(autorizacao_perda or autorizacao()) if tem_perda else None),
        visitas=None if visitas is None else medida("visitas", MedidaContagem(valor=visitas, evidencia=visitas_ev, disponivel_em=AS_OF)),
        freshness_sla_dias=sla_dias if sla_dias is not None else freshness_sla_dias, flags_qualidade=tuple(flags_qualidade),
    )


def v2(obj, **campos):
    """Define campos do contrato V2 sem depender da versão do contrato: com o campo declarado usa
    `dataclasses.replace`; sem ele copia o objeto e grava o atributo (compatibilidade com testes do red team)."""
    nomes = {f.name for f in dataclasses.fields(obj)}
    if all(k in nomes for k in campos):
        return dataclasses.replace(obj, **campos)
    novo = copy.copy(obj)
    for k, v in campos.items():
        object.__setattr__(novo, k, v)
    return novo
