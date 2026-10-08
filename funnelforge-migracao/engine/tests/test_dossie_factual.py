"""DOSSIÊ FACTUAL PRÉ-REDAÇÃO — casos [1]..[11] da missão (herméticos).

A pesquisa é um dublê que devolve fatos + citações do "provedor"; o
verificador de URL é um dublê que responde por lista. Nada sai para a rede.
"""
from __future__ import annotations

import copy
import json
from datetime import date

import pytest

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.adapters.research_perplexity import pesquisar_funil_litellm as pesquisar_original
from funnelforge.domain.dossie import DossieDoFunil
from funnelforge.domain.models import RunState
from funnelforge.pipeline import pipeline as pl
from funnelforge.pipeline.dossie import (
    MAX_RODADAS_DE_COMPLEMENTO,
    RespostaDaPesquisa,
    aplicar_portao,
    compilar_dossie,
    hash_do_dossie,
    invalidar_paginas,
    paginas_afetadas,
)
from funnelforge.pipeline.jornada import contexto_de_jornada
from funnelforge.pipeline.validators.checks import run_validators
from tests.cenario_editorial import congelar_data, rodar_cenario, settings_do_cenario
from tests.test_jornada_senac import arquitetura

HOJE = date(2026, 10, 7)
PSG = "https://www.senac.br/psg"
SP = "https://www.sp.senac.br/programa-senac-de-gratuidade"
EAD = "https://www.ead.senac.br"
INSCR = "https://www.sp.senac.br/inscricao"
RO = "https://www.ro.senac.br/edital-de-selecao-no-02-2026"
CITADAS = [PSG, SP, EAD, INSCR, RO]


def _fato(afirmacao, fonte, paginas, requisitos=(), tipo="processo", valor="", unidade="",
          vigente="2008-07-21"):
    return {"afirmacao": afirmacao, "tipo": tipo, "valor": valor, "unidade": unidade,
            "fonte": fonte, "vigente_desde": vigente if valor else "",
            "evidencia": afirmacao[:60], "paginas": list(paginas),
            "requisitos": list(requisitos)}


RENDA = "renda.limite_per_capita"
FATOS_COMPLETOS = [
    _fato("O PSG oferece vagas gratuitas para famílias de baixa renda", PSG,
          ["senac_gratuito", "renda"], ["psg.quem_atende"], tipo="condicao"),
    _fato("Renda familiar per capita de até 2 salários mínimos", PSG, ["renda", "senac_gratuito"],
          [RENDA], tipo="numero", valor="2", unidade="salários mínimos"),
    _fato("O Senac EAD oferece cursos livres, técnicos e de graduação", EAD, ["curso"],
          ["curso.tipos_ofertados"], tipo="processo"),
    _fato("O Senac São Paulo publica as vagas do PSG no portal regional", SP, ["estado"],
          ["estado.canal_regional"], tipo="processo"),
    _fato("A inscrição gratuita é feita no site da regional", INSCR, ["inscricao"],
          ["inscricao.como_se_inscrever"], tipo="processo"),
    _fato("Na inscrição o candidato autodeclara a renda familiar", INSCR, ["inscricao"],
          ["inscricao.documentos"], tipo="condicao"),
    _fato("Em 2026 o limite equivale a R$ 3.242,00 por pessoa (edital do Senac-RO)", RO,
          ["renda"], ["renda.valor_vigente"], tipo="numero", valor="3.242,00", unidade="R$",
          vigente="2026-01-14"),
]


class _Verificador:
    def __init__(self, vivas=CITADAS):
        self.vivas, self.visitas = set(vivas), []

    def verify_url(self, url):
        self.visitas.append(url)
        return url in self.vivas

    def motivo(self, url):
        return "HTTP 404"


class _Deps:
    def __init__(self, verificador=None):
        self.url_verifier = verificador or _Verificador()


def _registrar_canais(state, page, deps):
    """Dublê de `registrar_canais_oficiais`: a 1ª fonte verificada do domínio senac.br."""
    fontes = state.facts[page.page_number].fontes_resolvidas
    state.official_links[page.page_number] = [u for u in fontes if ".senac.br" in u][:1]


class _Pesquisa:
    def __init__(self, *rodadas, citacoes=CITADAS):
        self.rodadas, self.citacoes, self.pedidos = list(rodadas), citacoes, []

    def __call__(self, assunto, spec, faltantes):
        self.pedidos.append(copy.deepcopy(faltantes))
        fatos = self.rodadas.pop(0) if self.rodadas else []
        return RespostaDaPesquisa(dados={"fatos": fatos}, citacoes=list(self.citacoes),
                                  modelo_pedido="gemini/gemini-3.8-flash",
                                  modelo_servido="gemini-3.8-flash", auth_mode="api_key",
                                  prompt_tokens=1000, completion_tokens=400, custo_usd=0.002,
                                  latencia_ms=900)


def _arq_com_requisito_de_renda():
    """A arquitetura SENAC como a fixture declara: o ativo da renda pede a regra
    (`renda.limite_per_capita`) e o valor vigente (`renda.valor_vigente`) por
    requisito, sem URL presumida."""
    return arquitetura()


def _estado(arq=None):
    return RunState(run_id="r1", plan=plano_do_funnel_architecture(arq or _arq_com_requisito_de_renda()))


def _compilar(state, pesquisa, verificador=None):
    return compilar_dossie(state, _Deps(verificador), pesquisa,
                           registrar_canais=_registrar_canais, hoje=HOJE)


def _n(state, duvida):
    return next(p.page_number for p in state.plan.pages if p.jornada.duvida_id == duvida)


# [1] ------------------------------------------------------------------------

def test_1_dossie_completo_libera_todas_as_paginas():
    state = _estado()
    dossie = _compilar(state, _Pesquisa(FATOS_COMPLETOS))
    assert [p.cobertura.ready_to_write for p in dossie.paginas] == [True] * 5, \
        [p.cobertura.blockers for p in dossie.paginas]
    assert dossie.schema_version == "dossie-factual-v1" and len(dossie.sha256) == 64
    renda = dossie.pagina(_n(state, "renda"))
    assert renda.cobertura.requisitos[0].coberto
    assert state.facts[_n(state, "renda")].fatos_verificados[0].valor == "2"
    assert aplicar_portao(state, dossie).prontas == [1, 2, 3, 4, 5]


# [2] ------------------------------------------------------------------------

def test_2_fato_obrigatorio_ausente_bloqueia_antes_do_redator():
    state = _estado()
    sem_limite = [f for f in FATOS_COMPLETOS if RENDA not in f["requisitos"]]
    dossie = _compilar(state, _Pesquisa(sem_limite, [], []))
    renda = dossie.pagina(_n(state, "renda"))
    assert not renda.cobertura.ready_to_write
    assert any("renda.limite_per_capita" in b for b in renda.cobertura.blockers)
    portao = aplicar_portao(state, dossie)
    assert _n(state, "renda") in portao.bloqueadas
    assert state.step_status[f"blocked_p{_n(state, 'renda')}"].status.value == "FAILED"


# [3] [4] [5] ---------------------------------------------------------------

def test_3_url_nao_citada_ou_que_nao_responde_nao_vira_fonte():
    state = _estado()
    inventada = _fato("Vaga garantida para todos", "https://www.senac.br/inventada", ["curso"])
    morta = _fato("Bolsa integral automática", "https://www.sp.senac.br/morta", ["curso"])
    pesquisa = _Pesquisa(FATOS_COMPLETOS + [inventada, morta],
                         citacoes=CITADAS + ["https://www.sp.senac.br/morta"])
    dossie = _compilar(state, pesquisa)
    status = {f.afirmacao: (f.status, f.motivo_do_status) for f in dossie.fatos}
    assert status["Vaga garantida para todos"][0] == "unverified"
    assert "não citada pelo grounding" in status["Vaga garantida para todos"][1]
    assert status["Bolsa integral automática"][0] == "unverified"
    assert "não respondeu" in status["Bolsa integral automática"][1]
    fontes_do_curso = state.facts[_n(state, "curso")].fontes
    assert "https://www.senac.br/inventada" not in fontes_do_curso
    assert "https://www.sp.senac.br/morta" not in fontes_do_curso


def test_4_numero_sem_data_de_vigencia_bloqueia():
    state = _estado()
    sem_data = [dict(f) for f in FATOS_COMPLETOS]
    for f in sem_data:
        if RENDA in f["requisitos"]:
            f["vigente_desde"] = ""
    dossie = _compilar(state, _Pesquisa(sem_data, [], []))
    fato = next(f for f in dossie.fatos if RENDA in f.requisitos)
    assert fato.status == "unverified" and "referência temporal" in fato.motivo_do_status
    assert not dossie.pagina(_n(state, "renda")).cobertura.ready_to_write


def test_5_conflito_entre_fontes_bloqueia_o_fato():
    state = _estado()
    divergente = _fato("Renda per capita de até 1,5 salário mínimo", SP, ["renda"],
                       ["renda.limite_per_capita"], tipo="numero", valor="1,5",
                       unidade="salários mínimos")
    dossie = _compilar(state, _Pesquisa(FATOS_COMPLETOS + [divergente], [], []))
    conflitantes = [f for f in dossie.fatos if f.status == "conflict"]
    assert len(conflitantes) == 2 and set(dossie.conflitos) == {f.fact_id for f in conflitantes}
    renda = dossie.pagina(_n(state, "renda"))
    assert any("conflito" in b for b in renda.cobertura.blockers)
    assert all(f.valor not in ("2", "1,5") for f in state.facts[_n(state, "renda")].fatos_verificados)


# [6] ------------------------------------------------------------------------

def test_6_no_maximo_duas_rodadas_de_complementacao_so_para_o_que_falta():
    state = _estado()
    sem_limite = [f for f in FATOS_COMPLETOS if RENDA not in f["requisitos"]]
    pesquisa = _Pesquisa(sem_limite, [], [], [], [])
    dossie = _compilar(state, pesquisa)
    assert len(pesquisa.pedidos) == 1 + MAX_RODADAS_DE_COMPLEMENTO == 3
    assert pesquisa.pedidos[0] is None
    assert [f["requisito"] for f in pesquisa.pedidos[1]] == ["renda.limite_per_capita"]
    assert len(dossie.pesquisa) == 3
    assert dossie.pesquisa[1].faltantes_pedidos == ["renda:renda.limite_per_capita"]


def test_6_complementacao_que_acha_o_fato_libera_e_para():
    state = _estado()
    sem_limite = [f for f in FATOS_COMPLETOS if RENDA not in f["requisitos"]]
    com_limite = [f for f in FATOS_COMPLETOS if RENDA in f["requisitos"]]
    pesquisa = _Pesquisa(sem_limite, com_limite)
    dossie = _compilar(state, pesquisa)
    assert len(pesquisa.pedidos) == 2
    assert dossie.pagina(_n(state, "renda")).cobertura.ready_to_write


# [7] [8] ------------------------------------------------------------------

def test_7_cada_pagina_recebe_so_o_proprio_pacote():
    state = _estado()
    dossie = _compilar(state, _Pesquisa(FATOS_COMPLETOS))
    state.dossie = dossie.model_dump(mode="json")
    curso = next(p for p in state.plan.pages if p.jornada.duvida_id == "curso")
    ctx = contexto_de_jornada(state.plan, curso, state.dossie)
    ids = {f["id"] for f in ctx["dossie"]["fatos"]}
    assert ids == set(dossie.pagina(curso.page_number).fatos_verificados)
    assert all("EAD" in f["afirmacao"] for f in ctx["dossie"]["fatos"])
    assert ctx["dossie"]["sha256"] == dossie.pagina(curso.page_number).sha256


def test_8_numero_sem_lastro_no_dossie_e_reprovado():
    state = _estado()
    _compilar(state, _Pesquisa(FATOS_COMPLETOS))
    facts = state.facts[_n(state, "renda")]
    conteudo = ("<!-- wp:paragraph -->\n<p>Famílias com renda de até 3 salários mínimos por "
                "pessoa têm 70% de desconto.</p>\n<!-- /wp:paragraph -->")
    issues = run_validators(["critical_fact_grounding"], conteudo, {"facts": facts})
    assert issues, "número inventado passou pelo portão factual"


# [9] [10] [11] -----------------------------------------------------------

def _settings_com_dossie(tmp_path):
    s = settings_do_cenario(tmp_path)
    from funnelforge.config.settings import StepConfig
    s.steps["dossie"] = StepConfig(model="gemini/gemini-3.8-flash", web_search=True,
                                   temperature=0.2)
    s.run.dossie_factual = True
    s.run.imagens_habilitadas = False
    return s


def _ligar_pesquisa(monkeypatch, pesquisa):
    from funnelforge.adapters import research_perplexity as rp
    monkeypatch.setattr(rp, "pesquisar_funil",
                        lambda llm, cfg, assunto, spec, faltantes=None: pesquisa(assunto, spec, faltantes))
    from funnelforge.pipeline import steps as st
    monkeypatch.setattr(st, "registrar_canais_oficiais", _registrar_canais)


def test_9_e_2_pipeline_congela_o_dossie_e_nao_chama_nada_para_pagina_bloqueada(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    sem_limite = [f for f in FATOS_COMPLETOS if RENDA not in f["requisitos"]]
    _ligar_pesquisa(monkeypatch, _Pesquisa(sem_limite, [], []))
    settings = _settings_com_dossie(tmp_path)
    arq = _arq_com_requisito_de_renda()
    state, deps, llm = rodar_cenario(tmp_path, arq, settings)
    n = _n(state, "renda")
    assert state.step_status[f"dossie_p{n}"].status.value == "FAILED"
    assert not any(k.endswith(f"_p{n}") and k.split("_p")[0] in
                   ("briefing", "write", "seo", "widget", "revisor", "judge", "image",
                    "screenshot", "build", "publish", "content_gate") for k in state.step_status)
    pasta = deps.runner.runs_dir / state.run_id
    assert all(f"_p{n}" not in json.loads(l).get("step", "") for l in
               (pasta / "log.jsonl").read_text().splitlines())
    dossie = DossieDoFunil.model_validate(state.dossie)
    assert hash_do_dossie(dossie) == state.dossie_sha256           # [9] intacto
    assert json.loads((pasta / "dossie_factual.json").read_text())["sha256"] == state.dossie_sha256
    assert state.step_status["dossie"].model_requested == "gemini/gemini-3.8-flash"
    outras = [p.page_number for p in state.plan.pages if p.page_number != n]
    assert all(k in state.drafts for k in outras)                  # as outras escreveram


def test_10_resume_reaproveita_o_mesmo_dossie_sem_pesquisar(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, _Pesquisa(FATOS_COMPLETOS))
    settings = _settings_com_dossie(tmp_path)
    state, deps, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(), settings)
    hash_antes = state.dossie_sha256
    _ligar_pesquisa(monkeypatch, lambda *a: pytest.fail("resume não pode pesquisar de novo"))
    retomado = pl.run_pipeline(None, deps, resume_state=RunState.from_json(state.to_json()))
    assert retomado.dossie_sha256 == hash_antes


def test_10_dossie_adulterado_no_estado_bloqueia_tudo(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, _Pesquisa(FATOS_COMPLETOS))
    settings = _settings_com_dossie(tmp_path)
    state, deps, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(), settings)
    adulterado = RunState.from_json(state.to_json())
    adulterado.dossie["fatos"][0]["valor"] = "99"
    for p in adulterado.plan.pages:
        for k in [k for k in adulterado.step_status if k.endswith(f"_p{p.page_number}")
                  and not k.startswith(("research_", "dossie_"))]:
            adulterado.step_status.pop(k)
    final = pl.run_pipeline(None, deps, resume_state=adulterado)
    assert all(final.step_status[f"dossie_p{p.page_number}"].status.value == "FAILED"
               for p in final.plan.pages)


def test_11_mudanca_factual_invalida_so_as_paginas_afetadas():
    state = _estado()
    antigo = _compilar(state, _Pesquisa(FATOS_COMPLETOS)).model_dump(mode="json")
    mudados = [dict(f) for f in FATOS_COMPLETOS]
    mudados[2]["afirmacao"] = "O Senac EAD oferece cursos livres, técnicos, graduação e pós"
    state2 = _estado()
    novo = _compilar(state2, _Pesquisa(mudados))
    afetadas = paginas_afetadas(antigo, novo)
    assert afetadas == [_n(state2, "curso")]
    from funnelforge.domain.models import PageDraft, StepResult, StepStatus
    for p in state2.plan.pages:
        state2.drafts[p.page_number] = PageDraft(page_number=p.page_number, page_type="x",
                                                 format="gutenberg", content="<p>x</p>")
        state2.step_status[f"write_p{p.page_number}"] = StepResult(
            step=f"write_p{p.page_number}", status=StepStatus.OK)
    invalidar_paginas(state2, afetadas)
    assert set(state2.drafts) == {1, 2, 3, 4, 5} - set(afetadas)
    assert f"write_p{afetadas[0]}" not in state2.step_status


def test_modelo_servido_diferente_do_pedido_bloqueia_o_funil_inteiro(tmp_path, monkeypatch):
    """Sem troca silenciosa: pediu gemini-3.8-flash e veio outro -> nada é escrito."""
    congelar_data(monkeypatch)

    class _Trocado(_Pesquisa):
        def __call__(self, assunto, spec, faltantes):
            resp = super().__call__(assunto, spec, faltantes)
            resp.modelo_servido = "gemini-2.5-flash"
            return resp

    _ligar_pesquisa(monkeypatch, _Trocado(FATOS_COMPLETOS))
    state, _, llm = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(),
                                  _settings_com_dossie(tmp_path))
    assert all(state.step_status[f"dossie_p{p.page_number}"].status.value == "FAILED"
               for p in state.plan.pages)
    motivo = state.step_status["dossie"].issues[0].message
    assert "gemini-2.5-flash" in motivo and "troca de modelo" in motivo
    assert state.step_status["dossie"].model_requested == "gemini/gemini-3.8-flash"
    assert state.drafts == {} and not state.dossie


def test_resposta_vazia_do_provedor_aborta_sem_complementar_e_guarda_o_custo(tmp_path, monkeypatch):
    """Canário real de 07/10: gemini-3.8-flash devolveu texto vazio 3 vezes e o
    motor tratou como "zero fatos", pagando duas complementações às cegas."""
    from funnelforge.adapters import research_perplexity as rp
    from funnelforge.ports.llm import LLMResult

    class _LLMVazio:
        chamadas = 0

        def complete(self, *a, **kw):
            _LLMVazio.chamadas += 1
            return LLMResult(text="", model_used="gemini-3.8-flash", prompt_tokens=2083,
                             cost_usd=0.0016, finish_reason="content_filter")

    from funnelforge.config.settings import StepConfig
    cfg = StepConfig(model="gemini/gemini-3.8-flash", web_search=True)
    resp = pesquisar_original(_LLMVazio(), cfg, "Senac", [], None)
    assert resp.defeito == "provedor devolveu texto vazio (finish_reason=content_filter)"

    congelar_data(monkeypatch)
    monkeypatch.setattr(rp, "pesquisar_funil",
                        lambda llm, c, assunto, spec, faltantes=None: pesquisar_original(
                            _LLMVazio(), c, assunto, spec, faltantes))
    _LLMVazio.chamadas = 0
    state, _, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(),
                                _settings_com_dossie(tmp_path))
    assert _LLMVazio.chamadas == 1                                   # nenhuma complementação
    dossie = state.step_status["dossie"]
    assert dossie.status.value == "FAILED" and dossie.cost_usd == pytest.approx(0.0016)
    assert "finish_reason=content_filter" in dossie.issues[0].message
    assert all(state.step_status[f"blocked_p{p.page_number}"].status.value == "FAILED"
               for p in state.plan.pages)



# ---------------------------------------------------------------------------
# contrato de evidência do ativo: necessidade por requisito, vínculo por fonte
# ---------------------------------------------------------------------------

MA = "https://ma.senac.br/wp-content/uploads/2026/03/EDITAL-PSG-No-56.2026.pdf"
PLANALTO = "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2008/decreto/d6633.htm"


def test_abrangencia_da_fonte_pelo_host():
    from funnelforge.pipeline.dossie import abrangencia_da_fonte as ab
    assert ab("https://www.senac.br/psg") == ("nacional", "")
    assert ab(PLANALTO) == ("nacional", "")
    assert ab(MA) == ("regional", "ma")
    assert ab("https://programasenacdegratuidade.mg.senac.br/faq.aspx") == ("regional", "mg")
    assert ab("https://www.sp.gov.br/x") == ("regional", "sp")
    assert ab("https://ead.senac.br") == ("outra", "")


def _so_renda(*fatos_extras, sem=("renda.limite_per_capita", "renda.valor_vigente")):
    base = [f for f in FATOS_COMPLETOS if not set(f["requisitos"]) & set(sem)]
    return base + list(fatos_extras)


REGRA_MA = _fato("Renda per capita de até 2 salários mínimos (edital Senac-MA nº 56/2026)", MA,
                 ["renda"], [RENDA], tipo="condicao", valor="até 2", unidade="salários mínimos")
REGRA_NACIONAL = _fato("Renda per capita de até 2 salários mínimos (Decreto 6.633/2008)",
                       PLANALTO, ["renda"], [RENDA], tipo="condicao", valor="2",
                       unidade="salários mínimos")
VALOR_RO = _fato("Em 2026 o limite equivale a R$ 3.242,00 por pessoa", RO, ["renda"],
                 ["renda.valor_vigente"], tipo="numero", valor="3.242,00", unidade="R$",
                 vigente="2026-01-14")


def _compilar_com(fatos, *rodadas, citacoes=None):
    citadas = CITADAS + [MA, PLANALTO]
    state = _estado()
    pesquisa = _Pesquisa(fatos, *rodadas, citacoes=citacoes or citadas)
    dossie = _compilar(state, pesquisa, _Verificador(vivas=citadas))
    return state, dossie, pesquisa


def test_edital_regional_nao_vira_fonte_universal_da_regra():
    state, dossie, pesquisa = _compilar_com(_so_renda(REGRA_MA, VALOR_RO), [], [])
    renda = dossie.pagina(_n(state, "renda"))
    assert not renda.cobertura.ready_to_write
    assert any("regra ('renda.limite_per_capita') sem fonte NACIONAL oficial" in b
               for b in renda.cobertura.blockers)
    # a complementação pede EXATAMENTE a prova nacional que falta
    pedido = pesquisa.pedidos[1]
    assert [f["requisito"] for f in pedido] == [RENDA]
    assert "fonte NACIONAL oficial" in pedido[0]["descricao"]


def test_fonte_nacional_prova_a_regra_e_edital_atual_prova_o_valor_vigente():
    state, dossie, _ = _compilar_com(_so_renda(REGRA_MA, REGRA_NACIONAL, VALOR_RO))
    renda = dossie.pagina(_n(state, "renda"))
    assert renda.cobertura.ready_to_write, renda.cobertura.blockers
    v = {x["papel"]: x for x in renda.cobertura.vinculos}
    assert v["regra"]["url"] == PLANALTO and v["regra"]["abrangencia"] == "nacional"
    assert v["valor_vigente"]["url"] == RO and v["valor_vigente"]["uf"] == "RO"
    assert v["valor_vigente"]["vigente_desde"] == "2026-01-14"
    assert v["valor_vigente"]["nivel"].startswith("edital oficial atual")


def test_valor_de_outro_ano_nao_vale_como_vigente():
    antigo = dict(VALOR_RO, vigente_desde="2025-01-10")
    state, dossie, _ = _compilar_com(_so_renda(REGRA_NACIONAL, antigo), [], [])
    blockers = dossie.pagina(_n(state, "renda")).cobertura.blockers
    assert any("valor_vigente ('renda.valor_vigente') sem valor em reais vigente em 2026" in b
               for b in blockers)


def test_fonte_regional_da_geografia_do_conteudo_prova_a_regra():
    arq = _arq_com_requisito_de_renda()
    arq["funnel_strategy"]["jornada"]["ufs"] = ["MA"]
    state = _estado(arq)
    citadas = CITADAS + [MA]
    dossie = _compilar(state, _Pesquisa(_so_renda(REGRA_MA, VALOR_RO), citacoes=citadas),
                       _Verificador(vivas=citadas))
    v = {x["papel"]: x for x in dossie.pagina(_n(state, "renda")).cobertura.vinculos}
    assert v["regra"]["url"] == MA
    assert v["regra"]["nivel"] == "fonte oficial regional da geografia do conteúdo"


def test_sem_rebind_arbitrario_fato_nao_verificado_ou_fonte_nao_oficial():
    blog = _fato("Renda de até 2 salários mínimos", "https://blog.exemplo.com.br/psg", ["renda"],
                 [RENDA], tipo="condicao", valor="2", unidade="salários mínimos")
    morta = dict(REGRA_NACIONAL)                             # citada, mas não responde
    state = _estado()
    citadas = CITADAS + ["https://blog.exemplo.com.br/psg", PLANALTO]
    dossie = _compilar(state, _Pesquisa(_so_renda(blog, morta, VALOR_RO), [], [],
                                        citacoes=citadas),
                       _Verificador(vivas=[u for u in citadas if u != PLANALTO]))
    renda = dossie.pagina(_n(state, "renda"))
    assert not [x for x in renda.cobertura.vinculos if x["papel"] == "regra"]
    assert not renda.cobertura.ready_to_write


def test_ativo_legado_com_url_continua_exigindo_a_url_verificada():
    arq = _arq_com_requisito_de_renda()
    for job in arq["writing_jobs"]:
        for a in job["writer_briefing"]["jornada"].get("ativos", []):
            a.pop("rule_source_fact_id"), a.pop("current_value_source_fact_id")
            a["fonte_da_regra"] = "https://www.senac.br/url-presumida"
    state = _estado(arq)
    dossie = _compilar(state, _Pesquisa(FATOS_COMPLETOS))
    assert any("fonte da regra fora das fontes verificadas" in b
               for b in dossie.pagina(_n(state, "renda")).cobertura.blockers)


def test_esqueleto_recusa_ativo_que_aponta_requisito_inexistente():
    from funnelforge.pipeline.jornada.esqueleto import revisar_esqueleto
    arq = _arq_com_requisito_de_renda()
    for job in arq["writing_jobs"]:
        for a in job["writer_briefing"]["jornada"].get("ativos", []):
            a["current_value_source_fact_id"] = "renda.inventado"
    rev = revisar_esqueleto(plano_do_funnel_architecture(arq))
    assert any(i.code == "ativo_requisito_inexistente" for i in rev.bloqueantes)


def test_prompt_mostra_a_abrangencia_e_o_vinculo_do_ativo():
    from funnelforge.prompts import render
    state, dossie, _ = _compilar_com(_so_renda(REGRA_NACIONAL, VALOR_RO))
    state.dossie = dossie.model_dump(mode="json")
    renda = next(p for p in state.plan.pages if p.jornada.duvida_id == "renda")
    ctx = contexto_de_jornada(state.plan, renda, state.dossie)
    texto = render("jornada_da_pagina", jornada=ctx)
    assert "(regional RO)" in texto and "vale para RO; não apresente como regra nacional" in texto
    assert "requisito renda.limite_per_capita do dossiê" in texto


def test_mesmo_valor_com_redacao_diferente_nao_e_conflito_e_dimensao_diferente_tambem_nao():
    from funnelforge.pipeline.dossie import marcar_conflitos
    from funnelforge.domain.dossie import FatoDoDossie

    def fato(i, valor, unidade):
        return FatoDoDossie(fact_id=f"f_{i:012x}", afirmacao="x", tipo="condicao", valor=valor,
                            unidade=unidade, source_url=PSG, status="verified",
                            requisitos=[RENDA])
    grupo = [fato(1, "até 2", "salários mínimos federais"),
             fato(2, "2", "salários mínimos federais por pessoa por mês"),
             fato(3, "02 (dois)", "salários mínimos"),
             fato(4, "3.242,00", "R$")]
    assert marcar_conflitos(grupo) == []
    divergente = fato(5, "1,5", "salários mínimos")
    assert len(marcar_conflitos(grupo + [divergente])) == 4      # só a dimensão "salários"
