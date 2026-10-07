"""CONTRATO DO BRIEFING-V1 (etapa B4, item 5) — o que o código recusa.

O briefing é o plano persuasivo de UMA página, escrito por LLM. O código não
julga se ele é bom; confere o que é objetivamente verificável:

- toda afirmação persuasiva declara de onde veio (`fato` com ref, `hipotese`
  com evidência, `briefing_do_arquiteto` com ref);
- a intenção real da busca é SEMPRE hipótese;
- benefício só com fato citado (existente, citável) e com o limite que o
  acompanha; número no benefício só se estiver no fato citado, e fato
  `contexto` nunca sustenta número;
- próximo passo só para destino que existe nas rotas ou nos canais oficiais,
  e o que o leitor encontra lá vem do contrato do destino ou de um fato.

O que é heurística (rótulo genérico, tom "calmo" sem pedido, número fora dos
fatos fora dos benefícios, URL fora do inventário) vira AVISO para inspeção,
não recusa — diretriz 2 do operador (30/09, item 8).
"""
from __future__ import annotations

import copy
import json

import pytest

from funnelforge.domain.models import (
    ContextoDeLeitura, EditorialIntent, FunnelPlan, Page, PageRole, ResearchFacts,
    Route, RunState, TermoDeBusca, TermosDeBusca, Tensao, VerifiedFact,
)
from funnelforge.pipeline.briefing import (
    briefing_para_o_redator, normalizar_briefing, referencias_do_briefing,
)
from funnelforge.pipeline.inventario import montar_inventario
from funnelforge.pipeline.validators.briefing_contract import validar_briefing
from funnelforge.pipeline.validators.checks import run_validators

OFICIAL = "https://servicos.exemplo.gov.br/tarifa-social/consulta"
TOM = "Direto e acolhedor, sem jargao"
AVATAR = "Familia de baixa renda que paga conta de luz alta"
TENSAO = "Acha que precisa pagar alguem para pedir"


def _estado(*, termos: bool = True) -> tuple[RunState, Page]:
    facts = ResearchFacts(
        fontes=[OFICIAL], fontes_resolvidas=[OFICIAL],
        dados_validados=[
            {"fato": "O pedido e feito na propria distribuidora.", "fonte": OFICIAL,
             "tipo": "processo"},
            {"fato": "A inscricao no cadastro social e condicao.", "fonte": OFICIAL,
             "tipo": "condicao"},
            {"fato": "O programa tem 27 escritorios regionais.", "fonte": OFICIAL,
             "tipo": "contexto"},
            {"fato": "Contagem de agencias contraditoria na fonte.", "fonte": OFICIAL,
             "tipo": "contexto", "citavel": False},
        ],
        fatos_verificados=[VerifiedFact(
            valor="65%", unidade="de desconto na faixa de consumo mais baixa",
            tipo="numero", fonte_primaria=OFICIAL, dispositivo="Lei de exemplo, art. 1",
            vigente_desde="2010-01-20", verificado_em="2026-09-29")],
    )
    pagina = Page(
        page_number=3, page_type="SOLUTION", slug="quem-tem-direito-p1",
        h1_title="Quem tem direito a tarifa social", role=PageRole.SOLUTION, ordinal=1,
        emotional_objective="Leitor quer confirmar se a familia se encaixa",
        main_content_structure=["Quem tem direito", "Casos que ficam de fora"],
        target_keywords=["quem tem direito tarifa social"],
        routes=[Route(placement="inline", kind="funnel", target="como-pedir-p2",
                      anchor="Como pedir", reason="Depois de confirmar o direito")],
    )
    destino = Page(
        page_number=4, page_type="SOLUTION", slug="como-pedir-p2", h1_title="Como pedir",
        role=PageRole.SOLUTION, ordinal=2,
        editorial=EditorialIntent(reader_question="Como pedir?",
                                  useful_delivery="Passo a passo do pedido na distribuidora",
                                  cta_label="Ver como pedir"))
    plano = FunnelPlan(
        pages=[pagina, destino], tone_voice=TOM, avatar_summary=AVATAR,
        contexto_de_leitura=ContextoDeLeitura(
            perguntas_paa=["Quem tem direito a tarifa social?"],
            tensao=Tensao(frase=TENSAO, evidencia="validacao:7/10")),
        contexto_de_busca=(TermosDeBusca(
            estado="presente", janela={"inicio": "2026-09-21", "fim": "2026-09-30"},
            coletado_em="2026-09-30T08:20:00-03:00", fonte="search_term_view",
            termos=[TermoDeBusca(termo="tarifa social quem tem direito",
                                 impressoes=120, cliques=9)]) if termos else None),
    )
    state = RunState(run_id="r", plan=plano, facts={3: facts},
                     official_links={3: [OFICIAL]})
    return state, pagina


def _ref(**kw):
    state, pagina = _estado(**kw)
    return referencias_do_briefing(state, pagina, montar_inventario(state, pagina))


BRIEFING_VALIDO = {
    "intencao": {
        "pergunta_do_leitor": {"texto": "A minha familia pode ter o desconto?",
                               "base": "briefing_do_arquiteto", "ref": ["arquiteto:objetivo"]},
        "intencao_real_da_busca": {
            "texto": "Confirmar se se encaixa antes de ir a distribuidora",
            "base": "hipotese", "evidencia": ["termo:tarifa social quem tem direito", "paa:1"]},
    },
    "leitor": {
        "conhecimento_previo": {"texto": "Sabe que existe desconto, nao conhece a regra",
                                "base": "hipotese", "evidencia": ["arquiteto:avatar_summary"]},
        "desejo_ou_problema": {"texto": "Pagar menos na conta de luz",
                               "base": "briefing_do_arquiteto", "ref": ["arquiteto:avatar_summary"]},
        "objecoes": [{
            "objecao": {"texto": "Acha que precisa pagar alguem para pedir",
                        "base": "hipotese", "evidencia": ["tensao"]},
            "resposta": {"texto": "O pedido e feito na propria distribuidora",
                         "base": "fato", "ref": ["f1"]},
        }],
    },
    "promessa_da_pagina": {"texto": "Mostrar quem tem direito e o que a regra exige",
                           "cumprida_em": "secao Quem tem direito",
                           "base": "briefing_do_arquiteto", "ref": ["arquiteto:estrutura"]},
    "entrega_concreta": {"formato": "checklist",
                         "itens": [{"texto": "As condicoes que a regra exige",
                                    "base": "fato", "ref": ["f2"]}]},
    "beneficios": [{"texto": "Desconto de ate 65% na faixa de consumo mais baixa",
                    "fatos": ["n1"], "limite": "vale so para a faixa de consumo mais baixa"}],
    "proximos_passos": [{
        "tipo": "funnel", "destino": "como-pedir-p2", "rotulo": "Ver como pedir o desconto",
        "intencao_do_leitor": {"texto": "Pedir o desconto depois de confirmar o direito",
                               "base": "hipotese", "evidencia": ["paa:1"]},
        "o_que_encontra": {"texto": "O passo a passo do pedido na distribuidora",
                           "base": "briefing_do_arquiteto", "ref": ["destino:como-pedir-p2"]},
        "motivo": "Quem confirmou o direito quer pedir",
    }],
    "limites": [{"texto": "Nao prometer que o desconto e automatico",
                 "base": "fato", "ref": ["f1"]}],
    "hipoteses": [{"id": "h1", "sobre": "leitor", "texto": "O leitor teme pagar intermediario",
                   "como_confirmar": "termos com 'taxa' ou 'pagar'"}],
    "tom": {"registro": "jornalismo de servico", "intensidade": "direta",
            "justificativa": "Leitor quer confirmar o direito rapido", "base": "hipotese",
            "evidencia": ["termo:tarifa social quem tem direito"]},
}


def _codigos(dados, **kw) -> list[str]:
    erros, _avisos = validar_briefing(dados, _ref(**kw))
    return [i.code for i in erros]


def _com(**mudancas) -> dict:
    dados = copy.deepcopy(BRIEFING_VALIDO)
    for caminho, valor in mudancas.items():
        alvo = dados
        partes = caminho.split("__")
        for p in partes[:-1]:
            alvo = alvo[int(p)] if p.isdigit() else alvo[p]
        ultimo = partes[-1]
        if ultimo.isdigit():
            alvo[int(ultimo)] = valor
        else:
            alvo[ultimo] = valor
    return dados


def test_briefing_valido_passa_sem_erro():
    assert _codigos(BRIEFING_VALIDO) == []


# --- os quatro casos pedidos pela etapa --------------------------------------

def test_beneficio_sem_fato_e_recusado():
    assert "beneficio_sem_fato" in _codigos(_com(beneficios__0__fatos=[]))


def test_intencao_como_fato_e_recusada():
    dados = _com(intencao__intencao_real_da_busca={
        "texto": "Quer o desconto", "base": "fato", "ref": ["n1"]})
    assert "intencao_nao_e_fato" in _codigos(dados)


def test_destino_fora_das_rotas_e_recusado():
    assert "destino_fora_das_rotas" in _codigos(_com(proximos_passos__0__destino="outra-p9"))
    # canal externo só se for canal oficial desta página
    externo = _com(proximos_passos__0__tipo="external_official",
                   proximos_passos__0__destino="https://portal-qualquer.com.br/x",
                   proximos_passos__0__o_que_encontra={
                       "texto": "x", "base": "fato", "ref": ["n1"]})
    assert "destino_fora_das_rotas" in _codigos(externo)
    oficial = _com(proximos_passos__0__tipo="external_official",
                   proximos_passos__0__destino=OFICIAL,
                   proximos_passos__0__o_que_encontra={
                       "texto": "A consulta no site oficial", "base": "briefing_do_arquiteto",
                       "ref": [f"destino:{OFICIAL}"]})
    assert _codigos(oficial) == []


def test_hipotese_e_preservada_como_hipotese_ate_o_redator():
    state, pagina = _estado()
    inventario = montar_inventario(state, pagina)
    briefing = normalizar_briefing(copy.deepcopy(BRIEFING_VALIDO), state, pagina, inventario)
    assert briefing["intencao"]["intencao_real_da_busca"]["base"] == "hipotese"
    texto = briefing_para_o_redator(briefing)
    linha = next(l for l in texto.splitlines()
                 if "Confirmar se se encaixa antes de ir a distribuidora" in l)
    assert "hipótese" in linha.lower() and "não afirme" in linha.lower()
    assert "HIPÓTESES" in texto and "O leitor teme pagar intermediario" in texto
    # a hipótese não aparece como fato em lugar nenhum
    assert "[fato" not in linha


# --- o resto do contrato ------------------------------------------------------

@pytest.mark.parametrize("mudanca, codigo", [
    ({"beneficios__0__limite": ""}, "beneficio_sem_limite"),
    ({"beneficios__0__texto": "Desconto de ate 80% na conta"}, "numero_fora_dos_fatos"),
    ({"beneficios__0__fatos": ["f3"],
      "beneficios__0__texto": "Atendimento em 27 escritorios"}, "numero_sem_fato_compativel"),
    ({"beneficios__0__fatos": ["n9"]}, "ref_inexistente"),
    ({"beneficios__0__fatos": ["f4"]}, "fato_nao_citavel"),
    ({"leitor__conhecimento_previo__evidencia": []}, "hipotese_sem_evidencia"),
    ({"leitor__conhecimento_previo__evidencia": ["termo:termo que ninguem digitou"]},
     "evidencia_inexistente"),
    ({"leitor__desejo_ou_problema__base": "fato"}, "base_invalida"),
    ({"promessa_da_pagina__cumprida_em": ""}, "promessa_sem_lugar"),
    ({"entrega_concreta__formato": "tabela_bonita"}, "entrega_formato_invalido"),
    ({"entrega_concreta__itens": []}, "entrega_vazia"),
    ({"proximos_passos__0__rotulo": ""}, "rotulo_ausente"),
    ({"proximos_passos__0__o_que_encontra": {
        "texto": "algo", "base": "briefing_do_arquiteto", "ref": ["destino:outra-p9"]}},
     "o_que_encontra_sem_lastro"),
    ({"leitor__objecoes__0__resposta": {"texto": "", "base": "hipotese",
                                        "evidencia": ["tensao"]}}, "objecao_sem_resposta"),
    ({"tom__justificativa": ""}, "tom_sem_justificativa"),
    ({"proximos_passos": []}, "proximo_passo_ausente"),
])
def test_contrato_recusa(mudanca, codigo):
    assert codigo in _codigos(_com(**mudanca))


def test_sem_termos_coletados_nao_ha_evidencia_de_termo():
    """Com termos AUSENTES, citar um termo como evidência é inventar dado."""
    assert "evidencia_inexistente" in _codigos(BRIEFING_VALIDO, termos=False)


def test_termo_inventado_recebe_mensagem_que_declara_a_ausencia():
    """Canário p5 (30/09): a retentativa precisa saber POR QUE o termo não vale —
    sem termos observados não há `termo:` a citar; com termos, só o literal da lista."""
    sem = [i.message for i in validar_briefing(BRIEFING_VALIDO, _ref(termos=False))[0]
           if i.code == "evidencia_inexistente"]
    assert sem and all("nenhum termo de busca observado" in m for m in sem)
    inventado = _com(**{"leitor__conhecimento_previo__evidencia": ["termo:portal senac"]})
    com = [i.message for i in validar_briefing(inventado, _ref())[0]
           if i.code == "evidencia_inexistente"]
    assert com and "não está entre os termos observados" in com[0]


def test_destino_com_base_fato_diz_qual_base_usar():
    """Canário p5 (30/09, 4ª ocorrência): `o_que_encontra` com base "fato" e
    ref "destino:<URL>". A retentativa precisa ouvir que destino vai com base
    "briefing_do_arquiteto" e que base "fato" pede id de fato."""
    dados = _com(proximos_passos__0__o_que_encontra={
        "texto": "O passo a passo do pedido", "base": "fato", "ref": ["destino:como-pedir-p2"]})
    msgs = [i.message for i in validar_briefing(dados, _ref())[0] if i.code == "ref_inexistente"]
    assert msgs and "briefing_do_arquiteto" in msgs[0]


def test_json_invalido_e_campos_ausentes():
    ref = _ref()
    issues = run_validators(["briefing_contract"], "isto nao e json", {"briefing_ref": ref})
    assert [i.code for i in issues] == ["briefing_json_invalido"]
    faltando = copy.deepcopy(BRIEFING_VALIDO)
    del faltando["promessa_da_pagina"]
    assert "campo_ausente" in _codigos(faltando)
    # fora do passo do briefing o validador não tem régua e não opina
    assert run_validators(["briefing_contract"], "{}", {}) == []


def test_heuristicas_viram_aviso_e_nao_recusa():
    dados = _com(proximos_passos__0__rotulo="Saiba mais",
                 tom__intensidade="calma",
                 promessa_da_pagina__texto="Mostrar as 3 regras de 2027")
    erros, avisos = validar_briefing(dados, _ref())
    assert erros == []
    codigos = {a.code for a in avisos}
    assert {"aviso_rotulo_generico", "aviso_tom_calmo_sem_pedido",
            "aviso_numero_fora_dos_fatos"} <= codigos


def test_objecoes_vazias_sao_aviso():
    erros, avisos = validar_briefing(_com(leitor__objecoes=[]), _ref())
    assert erros == []
    assert "aviso_sem_objecoes" in {a.code for a in avisos}


def test_normalizacao_poe_o_que_e_do_codigo_por_cima_do_que_o_modelo_disse():
    """`termos_observados`, `briefing_do_arquiteto`, a leitura e a página são
    DADOS que o código já tem: o modelo não os escreve, e se escrever, perde."""
    state, pagina = _estado()
    inventario = montar_inventario(state, pagina)
    dados = copy.deepcopy(BRIEFING_VALIDO)
    dados["intencao"]["termos_observados"] = {"estado": "presente", "amostra": ["inventado"]}
    dados["briefing_do_arquiteto"] = {"tone_voice": "outro tom"}
    briefing = normalizar_briefing(dados, state, pagina, inventario)
    assert briefing["versao"] == "briefing-v1"
    assert briefing["pagina"] == {"numero": 3, "slug": "quem-tem-direito-p1",
                                  "papel": "SOLUTION", "h1": "Quem tem direito a tarifa social"}
    assert briefing["intencao"]["termos_observados"]["amostra"] == [
        "tarifa social quem tem direito"]
    arquiteto = briefing["briefing_do_arquiteto"]
    assert arquiteto["tone_voice"] == TOM and arquiteto["avatar_summary"] == AVATAR
    assert arquiteto["tensao"]["frase"] == TENSAO
    assert briefing["leitura"]["perguntas_paa"] == ["Quem tem direito a tarifa social?"]
    texto = briefing_para_o_redator(briefing)
    for valor in (TOM, AVATAR, TENSAO):
        assert valor in texto


def test_briefing_para_o_redator_diz_ausencia_de_termos_sem_inventar():
    state, pagina = _estado(termos=False)
    inventario = montar_inventario(state, pagina)
    dados = copy.deepcopy(BRIEFING_VALIDO)
    dados["intencao"]["intencao_real_da_busca"]["evidencia"] = ["paa:1"]
    dados["tom"]["evidencia"] = ["paa:1"]
    briefing = normalizar_briefing(dados, state, pagina, inventario)
    texto = briefing_para_o_redator(briefing)
    assert "NÃO COLETADOS" in texto
    assert "não presuma termos" in texto.lower()
    assert json.dumps(briefing, ensure_ascii=False)  # serializável para o artefato


def test_exemplo_de_o_que_encontra_traz_so_a_referencia_pura():
    """Validação real do p5 (30/09): o modelo copiou para o ref a dica de esquema
    'destino:<URL> com base briefing_do_arquiteto'. O exemplo JSON mostra só o valor
    puro; a explicação fica fora da string, e o contrato segue exigindo o destino exato."""
    import re

    from funnelforge.prompts import render

    prompt = render("briefing", pagina={"numero": 3, "slug": "x-p1", "papel": "SOLUTION",
                                        "papel_rotulo": "guia", "h1": "X", "objetivo": "o",
                                        "estrutura": ["a"], "keywords": "k"},
                    editorial={}, arquiteto={"tone_voice": "t", "avatar_summary": "a"},
                    inventario_texto="FATOS: nenhum", destinos=[], refs_arquiteto=[])
    linha = next(l for l in prompt.splitlines() if '"o_que_encontra": {' in l)
    refs = json.loads(re.search(r'"ref": (\[[^\]]*\])', linha).group(1))
    assert refs == ["destino:<destino>"]
    assert not any("com base" in r for r in refs)

    destino = BRIEFING_VALIDO["proximos_passos"][0]["destino"]

    def encontra(base, ref):
        return _codigos(_com(proximos_passos__0__o_que_encontra={
            "texto": "O passo a passo do pedido", "base": base, "ref": [ref]}))

    assert not encontra("briefing_do_arquiteto", f"destino:{destino}")
    assert "o_que_encontra_sem_lastro" in encontra(
        "briefing_do_arquiteto", f"destino:{destino} com base briefing_do_arquiteto")
    assert "o_que_encontra_sem_lastro" in encontra("briefing_do_arquiteto", "destino:outra-p9")
    assert not encontra("fato", "f1")
    assert "ref_inexistente" in encontra("fato", f"destino:{destino}")
    assert "ref_inexistente" in encontra("fato", "n99")
