"""RED — evidência de custo/cliques projetada, receita velha, flags `invalid_*`.

Achado 3 da missão V2. Em todos os casos a economia é favorável (634 cliques, custo 554,75,
receita 800 BRL observada, moeda provada, 16 dias maduros): a V1 dá `already_profitable` com
confiança `high` olhando só a evidência da RECEITA.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from volc_dil.viability.contrato import Evidencia
from volc_dil.viability.gate import Confianca, Veredito, avaliar

from _entradas import AS_OF, entrada


def _favoravel(**kw):
    return entrada(receita="800", moeda_receita="BRL", taxa=None, moeda_rec_ev=Evidencia.OBSERVED, receita_ev=Evidencia.OBSERVED,
                   perda="300", horizonte=14, **kw)


def _nao_lucrativa_nem_alta(r, motivo: str) -> None:
    assert r.verdict is not Veredito.ALREADY_PROFITABLE, f"{motivo}: V1 devolve {r.verdict.value}"
    assert r.confidence_class is not Confianca.HIGH, f"{motivo}: V1 devolve confiança {r.confidence_class.value}"


def test_red03a_custo_projetado_nao_decide_lucro():
    """Achado 3a. Custo com evidência PROJECTED (nunca realizado), resto favorável.

    V1 está errada porque `realizada` e `_confianca` olham apenas `receita.evidencia`:
    custo projetado entra como se fosse fatura fechada e o veredito sai `already_profitable`
    com confiança `high`. A invariante de runtime também só confere a receita.

    V2 deve exigir custo E cliques realizados (observed/reconciled) para `already_profitable`
    e nunca atribuir `high` a uma economia com qualquer perna projetada/estimada.
    """
    _nao_lucrativa_nem_alta(avaliar(_favoravel(custo_ev=Evidencia.PROJECTED)), "custo projected")


def test_red03b_cliques_projetados_nao_decidem_lucro():
    """Achado 3b. Cliques com evidência PROJECTED. Mesma lacuna de 3a: `calcular_economia`
    só exige `cliques.valor`; a evidência da contagem não entra em nenhuma decisão da V1.
    V2 deve tratar cliques não realizados como economia não realizada."""
    _nao_lucrativa_nem_alta(avaliar(_favoravel(cliques_ev=Evidencia.PROJECTED)), "cliques projected")


def test_red03c_receita_observada_ha_mais_de_7_dias_nao_e_fresca(sobrescrever):
    """Achado 3c. Receita com `observado_em` = as_of − 10 dias (SLA de frescor: 7 dias).

    V1 não tem `observado_em` em `MedidaMonetaria`: o teste falha POR CONSTRUÇÃO na V1 (e isso
    já é o achado — não existe como saber a idade do fato). V2 deve levar `observado_em` nas
    medidas, aplicar `freshness_sla_dias=7` e, com receita velha, não decidir `already_profitable`
    nem `high`.
    """
    e = _favoravel()
    receita_velha = sobrescrever(e.receita, observado_em=AS_OF - timedelta(days=10))
    _nao_lucrativa_nem_alta(avaliar(replace(e, receita=receita_velha)), "receita observada há 10 dias")


def test_red03d_flag_invalid_na_entrada_nao_decide_lucro():
    """Achado 3d. `flags_qualidade=("invalid_receita_fora_do_grao",)` na entrada, resto favorável.

    V1 está errada porque `flags_qualidade` é carregado, ordenado, serializado e hasheado —
    e nunca lido pelo gate: uma flag `invalid_*` que o coletor emitiu de propósito não muda
    veredito nem confiança.

    V2 deve tratar qualquer flag `invalid_*` (na entrada ou na medida) como evidência inválida:
    sem `already_profitable`, sem `high`.
    """
    e = replace(_favoravel(), flags_qualidade=("invalid_receita_fora_do_grao",))
    r = avaliar(e)
    _nao_lucrativa_nem_alta(r, "flag invalid_* na entrada")
    assert any("invalid" in x for x in (*r.invalid_evidence, *r.missing_evidence, *(m.codigo for m in r.reasons)))


def test_red03e_flag_invalid_na_medida_nao_decide_lucro(sobrescrever):
    """Achado 3d (variante na medida). `receita.flags_qualidade=("invalid_moeda_mista",)`.
    V1 não tem `flags_qualidade` em `MedidaMonetaria` (falha por construção). V2 deve carregar
    e honrar flags por medida."""
    e = _favoravel()
    r = avaliar(replace(e, receita=sobrescrever(e.receita, flags_qualidade=("invalid_moeda_mista",))))
    _nao_lucrativa_nem_alta(r, "flag invalid_* na medida")
