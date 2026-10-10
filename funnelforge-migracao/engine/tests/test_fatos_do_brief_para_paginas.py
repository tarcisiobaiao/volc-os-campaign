"""Fato verificado da pesquisa antecipada que nenhuma página possui chega a todas.

Run real 10/10/2026: "80 kWh com desconto integral" e a página de Tarifa Social
da Cemig estavam verificados, presos a ids do PAA (`q_…`), e nenhuma página os
recebia — a LP não pôde citar o benefício e a p4 não viu o canal da Cemig.
"""
from types import SimpleNamespace as NS

from funnelforge.domain.dossie import FatoDoDossie
from funnelforge.pipeline.dossie import _fatos_para_a_pagina


def _fato(n, paginas):
    return FatoDoDossie(fact_id=f"f_{n:012x}", afirmacao="a", tipo="condicao",
                        source_url="https://www.gov.br/x", paginas=paginas, status="verified")


def test_fato_so_do_brief_vai_para_todas_as_paginas():
    lp = NS(jornada=NS(duvida_id="tarifa_social"))
    p4 = NS(jornada=NS(duvida_id="distribuidoras"))
    do_brief = _fato(1, ["q_6c29c9a62edd"])
    da_lp = _fato(2, ["tarifa_social"])
    de_outra = _fato(3, ["quem_tem_direito"])
    misto = _fato(4, ["q_6c29c9a62edd", "quem_tem_direito"])
    fatos = [do_brief, da_lp, de_outra, misto]
    assert _fatos_para_a_pagina(fatos, lp) == [do_brief, da_lp]
    assert _fatos_para_a_pagina(fatos, p4) == [do_brief]


def test_id_de_pagina_parecido_nao_vira_fato_global():
    p = NS(jornada=NS(duvida_id="x"))
    assert _fatos_para_a_pagina([_fato(5, ["q_renda"])], p) == []


def test_fato_do_brief_nao_verificado_nao_se_espalha():
    p = NS(jornada=NS(duvida_id="x"))
    nao_verificado = _fato(6, ["q_6c29c9a62edd"]).model_copy(update={"status": "unverified"})
    assert _fatos_para_a_pagina([nao_verificado], p) == []


def test_requisito_declarado_por_duas_paginas_compartilha_o_fato():
    """Run de 10/10: o alcance do desconto era requisito da p6 e da p7; o fato
    marcado só para a p6 deixava a p7 'sem lastro'."""
    req = NS(id="cobranca.alcance_tsee")
    p6 = NS(jornada=NS(duvida_id="quanto_paga", requisitos=[req]))
    p7 = NS(jornada=NS(duvida_id="desconto_social", requisitos=[req]))
    outra = NS(jornada=NS(duvida_id="distribuidoras", requisitos=[NS(id="canal")]))
    fato = _fato(7, ["quanto_paga"]).model_copy(update={"requisitos": ["cobranca.alcance_tsee"]})
    nao_verificado = fato.model_copy(update={"fact_id": "f_00000000000a", "status": "unavailable"})
    assert _fatos_para_a_pagina([fato, nao_verificado], p7) == [fato]
    assert _fatos_para_a_pagina([fato], p6) == [fato]
    assert _fatos_para_a_pagina([fato], outra) == []
