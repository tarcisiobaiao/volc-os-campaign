"""Construtores de entrada compartilhados pelos testes de viabilidade (não é módulo de produto)."""
from __future__ import annotations

import copy
import dataclasses
from datetime import datetime, timezone
from decimal import Decimal

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import (
    Cambio, EntradaViabilidade, Evidencia, JanelaObservada, MedidaContagem, MedidaMonetaria, PerdaMaxima, Taxa,
)

AS_OF = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def entrada(cliques=634, custo="554.75", receita="7.77", moeda_receita="USD", taxa="5.25", cambio_ev=Evidencia.ESTIMATED,
            receita_ev=Evidencia.RECONCILED, moeda_rec_ev=Evidencia.ATTESTED, revshare="1", imposto=None, dias_maduros=16,
            perda=None, horizonte=None, custo_ev=Evidencia.OBSERVED, cliques_ev=Evidencia.OBSERVED, receita_none=False, custo_none=False,
            visitas=None, visitas_ev=Evidencia.OBSERVED, perda_moeda="BRL",
            cobertura_ppm=1_000_000, dias_custo_sem_receita=0, observado_em=None, flags_medidas=None, sla_dias=None):
    """Defaults = V1 (+ cobertura de receita completa, que o V2 exige para veredito positivo).
    `visitas=None` → sem medida; `visitas=int` → MedidaContagem observada (0 é valor válido).
    `observado_em={"receita": dt}` e `flags_medidas={"receita": ("invalid_schema",)}` gravam campos V2 nas medidas;
    `cobertura_ppm`/`dias_custo_sem_receita` vão na janela; `sla_dias` em freshness_sla_dias (só quando informado)."""
    observado_em = observado_em or {}
    flags_medidas = flags_medidas or {}

    def medida(nome, m):
        extra = {}
        if nome in observado_em:
            extra["observado_em"] = observado_em[nome]
        if nome in flags_medidas:
            extra["flags_qualidade"] = tuple(flags_medidas[nome])
        return v2(m, **extra) if extra else m

    janela = v2(JanelaObservada(inicio="2026-09-26", fim="2026-10-11", dias_maduros=dias_maduros),
                cobertura_receita_ppm=cobertura_ppm, dias_custo_sem_receita=dias_custo_sem_receita)
    e = EntradaViabilidade(
        candidato_id="cand-x", vertical="v", pais="BR", fonte_custo="google_ads", fonte_receita="joinads", as_of=AS_OF,
        janela=janela,
        cliques=medida("cliques", MedidaContagem(valor=None if cliques is None else cliques, evidencia=cliques_ev if cliques is not None else Evidencia.ABSENT, disponivel_em=AS_OF)),
        custo=medida("custo", MedidaMonetaria(valor=None if custo_none else Dinheiro.de_decimal(custo, "BRL"), evidencia=Evidencia.ABSENT if custo_none else custo_ev, moeda_evidencia=Evidencia.OBSERVED, disponivel_em=AS_OF)),
        receita=medida("receita", MedidaMonetaria(valor=None if receita_none else Dinheiro.de_decimal(receita, moeda_receita), evidencia=Evidencia.ABSENT if receita_none else receita_ev, moeda_evidencia=moeda_rec_ev, disponivel_em=AS_OF)),
        cambio=Cambio(taxa=None if taxa is None else Decimal(taxa), de="USD", para="BRL", proveniencia="literal_app" if taxa else "ausente", evidencia=cambio_ev if taxa else Evidencia.ABSENT),
        revshare=Taxa(valor=Decimal(revshare), evidencia=Evidencia.ATTESTED, proveniencia="tela"),
        imposto=Taxa(valor=None if imposto is None else Decimal(imposto), evidencia=Evidencia.UNKNOWN if imposto is None else Evidencia.ATTESTED, proveniencia="x"),
        perda_maxima=PerdaMaxima(valor=None if perda is None else Dinheiro.de_decimal(perda, perda_moeda), horizonte_dias=horizonte, proveniencia="owner" if perda else "ausente"),
        visitas=None if visitas is None else medida("visitas", MedidaContagem(valor=visitas, evidencia=visitas_ev, disponivel_em=AS_OF)),
    )
    return e if sla_dias is None else v2(e, freshness_sla_dias=sla_dias)


def v2(obj, **campos):
    """Define campos do contrato V2 (observado_em, flags_qualidade, cobertura_receita_ppm, cambio da simulação...)
    sem depender da versão do contrato: com o campo declarado usa `dataclasses.replace`; sem ele (contrato V1)
    copia o objeto e grava o atributo, para que o kernel (que lê por `getattr`) enxergue o valor."""
    nomes = {f.name for f in dataclasses.fields(obj)}
    if all(k in nomes for k in campos):
        return dataclasses.replace(obj, **campos)
    novo = copy.copy(obj)
    for k, v in campos.items():
        object.__setattr__(novo, k, v)
    return novo
