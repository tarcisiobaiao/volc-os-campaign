"""A LP chega ao briefing antes da copy, e o juiz vê o que a página entrega.

Regressões do card 106 (09/10/2026):
- 1ª escrita sem `state.json`: briefing sem texto nem fatos da LP, 29 chamadas
  pagas, e a copy saiu com "Gás do Povo Calendário 2025", "Cadastro Grátis",
  "Entrega de Gás de Cozinha" e o callout "Calendário Atualizado".
- 2ª escrita, com LP: "Justiça Apura Fraude no Gás" e o sitelink "Consultar
  pelo CPF" (serviço que o guia não executa).
Sem rede e sem LLM.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from volc_ads.copy import encomendar as em
from volc_ads.copy import juiz_semantico as js

PROMESSA = {"estado": "presente", "titulo": "Gás do Povo",
            "subtitulo": "Entenda a ordem das etapas e escolha o que conferir antes de seguir para a retirada.",
            "ctas": ["Conferir quem entra nas regras", "Entender como validar a retirada"],
            "fonte": "state.json drafts[1] (lp_json)"}
TEXTO_LP = ("Para conferir sua situação no Gás do Povo, comece pelos critérios e pela seleção; "
            "depois, consulte o benefício, entenda a validação da recarga na revenda credenciada "
            "e verifique se há pendências cadastrais a corrigir. A leitura deste guia não produz "
            "um resultado individual.")


def _cockpit(texto=TEXTO_LP, promessa=PROMESSA):
    return SimpleNamespace(origem=SimpleNamespace(texto_da_lp=texto, promessa_da_lp=promessa, nicho="Gás do Povo"))


def test_sem_texto_da_lp_a_copy_nao_e_escrita():
    """O caso da 1ª escrita do card 106."""
    faltas = em.faltas_da_lp_no_briefing(_cockpit(texto=""))
    assert faltas and "texto da LP" in faltas[0]
    with pytest.raises(em.LpForaDoBriefing):
        em.exigir_lp_no_briefing(_cockpit(texto=""))


def test_promessa_ausente_diz_o_motivo():
    faltas = em.faltas_da_lp_no_briefing(_cockpit(promessa={"estado": "ausente",
                                                            "motivo_ausencia": "state.json fora do disco"}))
    assert faltas == ["promessa da LP (título, subtítulo e CTAs): state.json fora do disco"]


def test_com_a_lp_inteira_nada_falta():
    assert em.faltas_da_lp_no_briefing(_cockpit()) == []


def test_escrever_recusa_antes_de_criar_o_cliente(monkeypatch):
    """Nenhum token: a recusa vem antes de `criar()` e de qualquer chamada."""
    from volc_ads.copy import cliente as cli

    monkeypatch.setattr(cli, "criar", lambda **_: pytest.fail("criou cliente sem a LP no briefing"))
    with pytest.raises(em.LpForaDoBriefing):
        em.escrever(_cockpit(texto=""), keywords=["gás do povo"])


def test_o_juiz_ve_o_conteudo_que_a_pagina_entrega():
    bloco = js.bloco_promessa_da_lp(PROMESSA, TEXTO_LP)
    assert "CONTEÚDO ENTREGUE" in bloco and "revenda credenciada" in bloco
    # "Calendário Gás do Povo" passou porque o juiz não tinha como ver isto:
    assert "calend" not in bloco.lower()


def test_sem_conteudo_o_juiz_e_avisado_e_nao_presume():
    assert "NÃO RECEBIDO" in js.bloco_promessa_da_lp(PROMESSA, "")


def test_conteudo_longo_vai_em_trecho_declarado():
    bloco = js.bloco_promessa_da_lp(PROMESSA, "x " * 5000)
    assert f"trecho de {js.LIMITE_CONTEUDO_LP} de" in bloco


@pytest.mark.parametrize("defeito", ["Cadastro Grátis", "Consultar pelo CPF", "Entrega de Gás",
                                     "Calendário"])
def test_a_regra_destino_nomeia_os_defeitos_reais(defeito):
    """O julgamento continua sendo do juiz existente; a regra diz o que procurar."""
    assert defeito in js.SISTEMA
