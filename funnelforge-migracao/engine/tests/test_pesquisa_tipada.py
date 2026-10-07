"""PESQUISA TIPADA (etapa B4, item 2) — correção de defeito, vale para todo run.

O defeito (verificação adversarial V10): o tipo do fato era DEDUZIDO do campo de
origem lá na ponte (`dados_validados` -> "afirmacao", `fatos_verificados` ->
"numero"), e o `VerifiedFact` do motor descartava qualquer `tipo` que a
pesquisa mandasse (pydantic `extra=ignore`). Resultado no run Senac: 3 de 7
fatos perdidos na copy e uma referência legal tratada como número.

Aqui o tipo nasce NA PESQUISA, com vocabulário fechado, é guardado pelo motor e
é conferido por código: tipo fora da lista reprova a pesquisa e a retentativa
estrutural leva a correção para a próxima chamada.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from funnelforge.adapters.research_perplexity import PerplexityResearch, _research_prompt
from funnelforge.config.settings import RunConfig, Secrets, Settings, SiteConfig, StepConfig
from funnelforge.domain.models import (
    TIPOS_DE_FATO, Page, ResearchFacts, RunState, StepStatus, VerifiedFact,
)
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.pipeline import Deps
from funnelforge.pipeline.runner import Runner
from funnelforge.pipeline.validators.checks import research_facts_contract
from tests.fakes import FakeLLM

FONTE = "https://www.exemplo.gov.br/regra/consulta"
HOJE = date.today()


def _fato(**extra) -> dict:
    base = {"valor": "2", "unidade": "salarios minimos per capita como limite de renda",
            "fonte_primaria": FONTE, "dispositivo": "Decreto de exemplo, art. 3",
            "vigente_desde": "2008-11-05", "verificado_em": HOJE.isoformat()}
    return {**base, **extra}


# ---------------------------------------------------------------------------
# o vocabulário é o do contrato entre as trilhas, e o modelo o guarda
# ---------------------------------------------------------------------------

def test_vocabulario_fechado_e_o_do_contrato():
    assert TIPOS_DE_FATO == ("numero", "prazo", "data", "mudanca", "condicao",
                             "orgao", "fonte_legal", "processo", "contexto")


def test_verified_fact_guarda_tipo_escopo_e_citavel_canonizados():
    f = VerifiedFact(**_fato(tipo=" Condição ", escopo="regional: sp", citavel="sim"))
    assert (f.tipo, f.escopo, f.citavel) == ("condicao", "regional:SP", True)
    dump = f.model_dump()
    assert dump["tipo"] == "condicao" and dump["escopo"] == "regional:SP"
    assert VerifiedFact(**_fato(tipo="Fonte legal")).tipo == "fonte_legal"
    assert VerifiedFact(**_fato(citavel="não")).citavel is False


def test_fato_antigo_sem_tipo_continua_carregando():
    """state.json anterior à reforma: nenhum dos três campos existe."""
    antigo = ResearchFacts(**{"fontes": [FONTE], "fatos_verificados": [_fato()]})
    fato = antigo.fatos_verificados[0]
    assert (fato.tipo, fato.escopo, fato.citavel) == (None, None, None)
    # e sobrevive à ida e volta pelo JSON do checkpoint
    de_volta = ResearchFacts.model_validate_json(antigo.model_dump_json())
    assert de_volta.fatos_verificados[0].tipo is None


def test_dados_validados_tem_tipo_canonizado_sem_perder_o_resto():
    facts = ResearchFacts(dados_validados=[
        {"fato": "O Senac tem 27 departamentos regionais.", "fonte": FONTE,
         "tipo": "Contexto", "escopo": "Nacional", "citavel": "true"},
        {"fato": "Sem tipo, como nos runs antigos.", "fonte": FONTE},
    ])
    assert facts.dados_validados[0]["tipo"] == "contexto"
    assert facts.dados_validados[0]["escopo"] == "nacional"
    assert facts.dados_validados[0]["citavel"] is True
    assert "tipo" not in facts.dados_validados[1]


# ---------------------------------------------------------------------------
# o validador determinístico
# ---------------------------------------------------------------------------

def _contrato(facts: ResearchFacts) -> list:
    return research_facts_contract("", {"parsed": facts, "today": HOJE, "max_age_days": 45})


def test_contrato_recusa_tipo_fora_do_vocabulario_nos_dois_campos():
    facts = ResearchFacts(
        fontes=[FONTE],
        fatos_verificados=[VerifiedFact(**_fato(tipo="percentual"))],
        dados_validados=[{"fato": "x", "fonte": FONTE, "tipo": "afirmacao"}],
    )
    codigos = [i.code for i in _contrato(facts)]
    assert codigos.count("fato_tipo_invalido") == 2
    mensagens = " ".join(i.message for i in _contrato(facts))
    assert "percentual" in mensagens and "afirmacao" in mensagens
    assert "numero" in mensagens  # a correção diz qual é a lista válida


def test_contrato_aceita_tipo_valido_e_tipo_ausente():
    for tipo in TIPOS_DE_FATO:
        facts = ResearchFacts(fontes=[FONTE], fatos_verificados=[VerifiedFact(**_fato(tipo=tipo))],
                              dados_validados=[{"fato": "x", "fonte": FONTE, "tipo": tipo}])
        assert not _contrato(facts), tipo
    sem_tipo = ResearchFacts(fontes=[FONTE], fatos_verificados=[VerifiedFact(**_fato())],
                             dados_validados=[{"fato": "x", "fonte": FONTE}])
    assert not _contrato(sem_tipo)


def test_contrato_recusa_escopo_fora_do_formato():
    for ruim in ("estadual", "regional", "regional:XX", "municipal:SP"):
        facts = ResearchFacts(fontes=[FONTE],
                              fatos_verificados=[VerifiedFact(**_fato(escopo=ruim))])
        assert [i.code for i in _contrato(facts)] == ["fato_escopo_invalido"], ruim
    for bom in ("nacional", "unidade", "regional:SP", "regional:rs"):
        facts = ResearchFacts(fontes=[FONTE],
                              fatos_verificados=[VerifiedFact(**_fato(escopo=bom))])
        assert not _contrato(facts), bom


# ---------------------------------------------------------------------------
# a retentativa estrutural leva a correção
# ---------------------------------------------------------------------------

class _PesquisaQueErraOTipoUmaVez:
    """Primeira resposta com tipo fora da lista; a segunda, corrigida."""

    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    def research(self, topic, structure, fontes_reprovadas=None, correcoes=None):
        self.chamadas.append({"fontes_reprovadas": list(fontes_reprovadas or []),
                              "correcoes": list(correcoes or [])})
        tipo = "percentual" if len(self.chamadas) == 1 else "condicao"
        return ResearchFacts(fontes=[FONTE],
                             fatos_verificados=[VerifiedFact(**_fato(tipo=tipo))])


class _Verificador:
    def verify_url(self, url: str) -> bool:
        return url == FONTE


def _deps(tmp_path: Path, pesquisa) -> Deps:
    settings = Settings(secrets=Secrets(), run=RunConfig(research_max_attempts=3),
                        site=SiteConfig(domain="https://site.exemplo.com.br"),
                        steps={"research": StepConfig(model="gemini/x")})
    runner = Runner(llm=FakeLLM(responses=[]), max_retries=0, runs_dir=tmp_path / "runs")
    return Deps(llm=FakeLLM(responses=[]), research=pesquisa, image_gen=None,
                image_proc=None, publisher=None, loader=None, settings=settings,
                runner=runner, url_verifier=_Verificador())


def test_tipo_invalido_reprova_e_a_retentativa_leva_a_correcao(tmp_path: Path):
    pesquisa = _PesquisaQueErraOTipoUmaVez()
    state = RunState(run_id="r")
    page = Page(page_number=1, page_type="LANDING PAGE", h1_title="Tema", slug="tema")
    st.step_research(state, page, _deps(tmp_path, pesquisa))

    res = state.step_status["research_p1"]
    assert res.status is StepStatus.OK, res.issues
    assert res.attempts == 2
    assert pesquisa.chamadas[0]["correcoes"] == []
    correcao = " ".join(pesquisa.chamadas[1]["correcoes"])
    assert "percentual" in correcao and "condicao" in correcao
    assert state.facts[1].fatos_verificados[0].tipo == "condicao"


def test_adaptador_nao_transforma_tipo_invalido_em_pesquisa_vazia():
    """Com `Literal` no modelo, um tipo torto derrubava o parse, a pesquisa
    virava `sparse` e o gate dizia 'sem fontes' — o motivo real sumia. O tipo
    torto chega intacto ao validador, que o recusa com o nome certo."""
    resposta = json.dumps({"resumo": "r", "dados_validados": [],
                           "fatos_verificados": [_fato(tipo="percentual")],
                           "passo_a_passo": [], "fontes": [FONTE]})
    facts = PerplexityResearch(FakeLLM(responses=[resposta]),
                               StepConfig(model="gemini/x")).research("Tema", "H2")
    assert facts.sparse is False
    assert facts.fatos_verificados[0].tipo == "percentual"


# ---------------------------------------------------------------------------
# o prompt: tipo pedido, vigência separada de data histórica
# ---------------------------------------------------------------------------

def test_prompt_pede_tipo_fechado_escopo_e_citavel():
    prompt = _research_prompt("Tema", "- H2")
    for tipo in TIPOS_DE_FATO:
        assert f"- {tipo}:" in prompt, tipo
    assert '"tipo"' in prompt and '"escopo"' in prompt and '"citavel"' in prompt
    assert "regional:UF" in prompt
    assert "contexto: fato descritivo" in prompt
    assert "nunca sustenta numero, prazo ou condicao" in prompt


def test_prompt_troca_ano_corrente_por_vigencia_e_data_historica():
    prompt = _research_prompt("Tema", "- H2")
    assert "SEMPRE o ano corrente" not in prompt
    assert "ano corrente" not in prompt.lower()
    low = prompt.lower()
    assert "vigencia" in low and "data historica" in low
    assert "vigente_desde" in prompt


def test_prompt_traz_as_correcoes_da_tentativa_anterior():
    sem = _research_prompt("Tema", "- H2")
    com = _research_prompt("Tema", "- H2", correcoes=["fatos_verificados[1]: tipo 'percentual'"])
    assert "TENTATIVA ANTERIOR RECUSADA" not in sem
    assert "TENTATIVA ANTERIOR RECUSADA" in com
    assert "tipo 'percentual'" in com


def test_fato_com_vigencia_passada_continua_valido():
    """Um decreto de 2008 em vigor é fato VIGENTE com data histórica — não é
    'ano passado'. O contrato só recusa vigência no futuro e verificação velha."""
    facts = ResearchFacts(fontes=[FONTE], fatos_verificados=[VerifiedFact(**_fato(
        vigente_desde="1946-01-10", tipo="fonte_legal"))])
    assert not _contrato(facts)
    velho = ResearchFacts(fontes=[FONTE], fatos_verificados=[VerifiedFact(**_fato(
        verificado_em=(HOJE - timedelta(days=90)).isoformat()))])
    assert [i.code for i in _contrato(velho)] == ["stale_fact"]


# ---------------------------------------------------------------------------
# `citavel: false` não é decorativo: o fato sai da base do redator e do portão
# ---------------------------------------------------------------------------

def _facts_com_citavel(citavel) -> ResearchFacts:
    return ResearchFacts(
        fontes=[FONTE], fontes_resolvidas=[FONTE],
        dados_validados=[{"fato": "A mesma pagina traz 617 e 689 unidades.", "fonte": FONTE,
                          "tipo": "contexto", "citavel": citavel}],
        fatos_verificados=[VerifiedFact(**_fato(valor="689", unidade="unidades operativas",
                                                tipo="numero", citavel=citavel))],
    )


def test_fato_nao_citavel_sai_da_base_do_redator():
    from funnelforge.pipeline.base_factual import base_para_o_redator

    citavel = base_para_o_redator(_facts_com_citavel(True))
    assert "689 unidades operativas" in citavel
    assert "617 e 689" in citavel
    nao_citavel = base_para_o_redator(_facts_com_citavel(False))
    assert "689 unidades operativas" not in nao_citavel
    assert "617 e 689" not in nao_citavel
    assert "FATOS VERIFICADOS: NENHUM." in nao_citavel
    assert "não citáve" in nao_citavel.lower()      # a retirada é dita, não silenciosa


def test_portao_nao_ancora_numero_em_fato_nao_citavel():
    from funnelforge.pipeline.validators.checks import critical_fact_grounding

    texto = f'<p>O desconto e de 30% na faixa mais baixa (<a href="{FONTE}">fonte</a>).</p>'
    for citavel, deve_passar in ((True, True), (None, True), (False, False)):
        facts = ResearchFacts(
            fontes=[FONTE], fontes_resolvidas=[FONTE],
            fatos_verificados=[VerifiedFact(**_fato(valor="30", unidade="% de desconto",
                                                    tipo="numero", citavel=citavel))])
        issues = critical_fact_grounding(texto, {"facts": facts})
        assert (not issues) is deve_passar, (citavel, issues)
