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
DECRETO_SM = "https://planalto.gov.br/ccivil_03/_ato2023-2026/2025/decreto/d12797.htm"
MA = "https://ma.senac.br/wp-content/uploads/2026/03/EDITAL-PSG-No-56.2026.pdf"
PLANALTO = "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2008/decreto/d6633.htm"
CITADAS = [PSG, SP, EAD, INSCR, RO, DECRETO_SM]

#: O emissor que cada fonte de teste DECLARA — e que o documento falso traz no
#: cabeçalho, para a proveniência genérica comprová-lo.
EMISSORES = {
    PSG: ("Departamento Nacional do Senac", "instituicao_oficial", "nacional", "BR"),
    SP: ("Senac São Paulo", "instituicao_oficial", "subnacional", "BR-SP"),
    INSCR: ("Senac São Paulo", "instituicao_oficial", "subnacional", "BR-SP"),
    EAD: ("Senac EAD", "instituicao_oficial", "nacional", "BR"),
    RO: ("Senac Rondônia", "instituicao_oficial", "subnacional", "BR-RO"),
    DECRETO_SM: ("Presidência da República", "governo", "nacional", "BR"),
    MA: ("Senac Maranhão", "instituicao_oficial", "subnacional", "BR-MA"),
    PLANALTO: ("Presidência da República", "governo", "nacional", "BR"),
}


def _ler(url):
    if url not in EMISSORES:
        return {"ok": False, "motivo": "HTTP 404", "status": 404}
    return {"ok": True, "motivo": "", "status": 200, "sha256": "x", "titulo": "",
            "texto": f"{EMISSORES[url][0]}. Documento de teste."}


def _fato(afirmacao, fonte, paginas, requisitos=(), tipo="processo", valor="", unidade="",
          vigente="2008-07-21"):
    emissor, tipo_de_emissor, escopo, jurisdicao = EMISSORES.get(fonte, ("", "", "", ""))
    return {"afirmacao": afirmacao, "tipo": tipo, "valor": valor, "unidade": unidade,
            "fonte": fonte, "vigente_desde": vigente if valor else "",
            "evidencia": afirmacao[:60], "paginas": list(paginas),
            "requisitos": list(requisitos), "emissor": emissor,
            "tipo_de_emissor": tipo_de_emissor, "escopo": escopo, "jurisdicao": jurisdicao}


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
    _fato("O salário mínimo é de R$ 1.621,00 a partir de 1º de janeiro de 2026", DECRETO_SM,
          ["renda"], ["salario_minimo.vigente"], tipo="numero", valor="1.621,00", unidade="R$",
          vigente="2026-01-01"),
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


def _compilar(state, pesquisa, verificador=None, **kw):
    return compilar_dossie(state, _Deps(verificador), pesquisa,
                           registrar_canais=_registrar_canais, hoje=HOJE, ler_documento=_ler,
                           **kw)


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

def test_2_lacuna_na_promessa_central_vai_para_revisao_e_nao_bloqueia():
    state = _estado()
    sem_limite = [f for f in FATOS_COMPLETOS if RENDA not in f["requisitos"]]
    dossie = _compilar(state, _Pesquisa(sem_limite, [], []))
    cob = dossie.pagina(_n(state, "renda")).cobertura
    assert cob.estado == "review" and cob.ready_to_write and cob.requer_revisao
    req = next(r for r in cob.requisitos if r.requisito_id == RENDA)
    assert req.estado == "unsupported" and req.central and req.risco == "alto"
    assert any(d["requisito"] == RENDA and "omita" in d["instrucao"] for d in cob.degradacoes)
    n = _n(state, "renda")
    portao = aplicar_portao(state, dossie)
    assert n in portao.prontas and f"blocked_p{n}" not in state.step_status
    assert state.step_status[f"dossie_p{n}"].issues[0].code == "revisao_humana_por_evidencia"

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


def test_4_numero_sem_data_de_vigencia_nao_vira_fato_e_a_pagina_vai_para_revisao():
    state = _estado()
    sem_data = [dict(f) for f in FATOS_COMPLETOS]
    for f in sem_data:
        if RENDA in f["requisitos"]:
            f["vigente_desde"] = ""
    dossie = _compilar(state, _Pesquisa(sem_data, [], []))
    fato = next(f for f in dossie.fatos if RENDA in f.requisitos)
    assert fato.status == "unverified" and "referência temporal" in fato.motivo_do_status
    assert dossie.pagina(_n(state, "renda")).cobertura.estado == "review"

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
    assert [f["requisito"] for f in pesquisa.pedidos[1]] == [RENDA]
    assert len(dossie.pesquisa) == 3
    assert dossie.pesquisa[1].faltantes_pedidos == [f"renda:{RENDA}"]

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
    from funnelforge.pipeline import dossie as pd
    original = pd.CompiladorDeDossie.__init__

    def com_leitor(self, *a, ler_documento=None, **kw):
        original(self, *a, ler_documento=ler_documento or _ler, **kw)
    monkeypatch.setattr(pd.CompiladorDeDossie, "__init__", com_leitor)


def test_9_e_2_pipeline_lacuna_central_pesquisa_sob_demanda_escreve_e_nao_publica(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    sem_limite = [f for f in FATOS_COMPLETOS if RENDA not in f["requisitos"]]
    pesquisa = _Pesquisa(sem_limite, [])
    _ligar_pesquisa(monkeypatch, pesquisa)
    settings = _settings_com_dossie(tmp_path)
    state, deps, llm = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(), settings)
    n = _n(state, "renda")
    # a pesquisa global e UMA complementação sob demanda, só da lacuna da p2
    assert pesquisa.pedidos[0] is None and [f["requisito"] for f in pesquisa.pedidos[1]] == [RENDA]
    assert len(pesquisa.pedidos) == 2 and f"dossie_complemento_p{n}" in state.step_status
    # a página é escrita (degradada, para revisão) e as outras também
    assert all(p.page_number in state.drafts for p in state.plan.pages)
    assert state.step_status[f"dossie_p{n}"].status.value == "OK"
    # nenhuma página parada PELO DOSSIÊ (a revisão global do texto pronto é outra coisa)
    assert all(state.step_status[f"dossie_p{p.page_number}"].status.value == "OK"
               for p in state.plan.pages)
    pasta = deps.runner.runs_dir / state.run_id
    dossie = DossieDoFunil.model_validate(state.dossie)
    assert hash_do_dossie(dossie) == state.dossie_sha256           # [9] consolidado e íntegro
    assert json.loads((pasta / "dossie_factual.json").read_text())["sha256"] == state.dossie_sha256
    assert dossie.pagina(n).cobertura.estado == "review"
    prompt = (pasta / "prompts" / f"write_p{n}.txt").read_text()
    assert "O QUE NÃO PODE SER AFIRMADO" in prompt

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


def test_modelo_trocado_nao_entra_no_dossie_e_nao_bloqueia_o_funil(tmp_path, monkeypatch):
    """Sem troca silenciosa: pediu gemini-3.8-flash e veio outro -> nenhum fato
    da resposta entra; as páginas seguem degradadas/para revisão."""
    congelar_data(monkeypatch)

    class _Trocado(_Pesquisa):
        def __call__(self, assunto, spec, faltantes):
            resp = super().__call__(assunto, spec, faltantes)
            resp.modelo_servido = "gemini-2.5-flash"
            return resp

    _ligar_pesquisa(monkeypatch, _Trocado(FATOS_COMPLETOS))
    state, _, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(),
                                _settings_com_dossie(tmp_path))
    dossie = DossieDoFunil.model_validate(state.dossie)
    assert dossie.fatos == []
    assert all("troca de modelo" in t.defeito for t in dossie.pesquisa)
    # nenhuma página parada PELO DOSSIÊ (a revisão global do texto pronto é outra coisa)
    assert all(state.step_status[f"dossie_p{p.page_number}"].status.value == "OK"
               for p in state.plan.pages)
    estados = {p.cobertura.estado for p in dossie.paginas}
    assert estados <= {"review", "degraded"}
    req = next(r for p in dossie.paginas for r in p.cobertura.requisitos)
    assert req.estado == "unavailable"

def test_resposta_vazia_do_provedor_e_falha_de_pesquisa_que_nao_derruba_o_funil(tmp_path, monkeypatch):
    """Canário real de 07/10: gemini-3.8-flash devolveu texto vazio. Agora:
    defeito registrado com o custo, nenhum fato, página segue degradada."""
    from funnelforge.adapters import research_perplexity as rp
    from funnelforge.config.settings import StepConfig
    from funnelforge.ports.llm import LLMResult

    class _LLMVazio:
        chamadas = 0

        def complete(self, *a, **kw):
            _LLMVazio.chamadas += 1
            return LLMResult(text="", model_used="gemini-3.8-flash", prompt_tokens=2083,
                             cost_usd=0.0016, finish_reason="content_filter")

    cfg = StepConfig(model="gemini/gemini-3.8-flash", web_search=True)
    resp = pesquisar_original(_LLMVazio(), cfg, "Senac", [], None)
    assert resp.defeito == "provedor devolveu texto vazio (finish_reason=content_filter)"

    congelar_data(monkeypatch)
    _ligar_pesquisa(monkeypatch, lambda assunto, spec, faltantes: pesquisar_original(
        _LLMVazio(), cfg, assunto, spec, faltantes))
    _LLMVazio.chamadas = 0
    state, _, _ = rodar_cenario(tmp_path, _arq_com_requisito_de_renda(),
                                _settings_com_dossie(tmp_path))
    dossie = state.step_status["dossie"]
    assert dossie.status.value == "OK" and dossie.cost_usd >= 0.0016
    # nenhuma página parada PELO DOSSIÊ (a revisão global do texto pronto é outra coisa)
    assert all(state.step_status[f"dossie_p{p.page_number}"].status.value == "OK"
               for p in state.plan.pages)
    assert all(p.page_number in state.drafts for p in state.plan.pages)

# ---------------------------------------------------------------------------
# contrato de evidência do ativo: necessidade por requisito, vínculo por fonte
# ---------------------------------------------------------------------------

MA = "https://ma.senac.br/wp-content/uploads/2026/03/EDITAL-PSG-No-56.2026.pdf"
PLANALTO = "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2008/decreto/d6633.htm"


def test_host_nao_decide_autoridade_e_publicador_decide_independencia():
    from funnelforge.domain.dossie import FatoDoDossie
    from funnelforge.pipeline.dossie import escopo_do_fato, publicador
    sem_prov = FatoDoDossie(fact_id="f_" + "a" * 12, afirmacao="x", tipo="condicao",
                            source_url="https://www.gov.br/algo")
    assert escopo_do_fato(sem_prov) == ("desconhecido", "")        # gov.br não basta
    assert publicador("https://www.bcb.gov.br/x") == "bcb.gov.br"
    assert publicador("https://news.bbc.co.uk/a") == "bbc.co.uk"
    assert publicador("https://docs.python.org/3/") == "python.org"


def _so_renda(*fatos_extras, sem=(RENDA, "renda.valor_vigente", "salario_minimo.vigente")):
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
SM_2026 = _fato("O salário mínimo é de R$ 1.621,00 a partir de 1º de janeiro de 2026",
                DECRETO_SM, ["renda"], ["salario_minimo.vigente"], tipo="numero",
                valor="1.621,00", unidade="R$", vigente="2026-01-01")


def _compilar_com(fatos, *rodadas, citacoes=None, arq=None, vivas=None):
    citadas = citacoes or (CITADAS + [MA, PLANALTO])
    state = _estado(arq)
    pesquisa = _Pesquisa(fatos, *rodadas, citacoes=citadas)
    dossie = _compilar(state, pesquisa, _Verificador(vivas=vivas or citadas))
    return state, dossie, pesquisa


def _renda(state, dossie):
    return dossie.pagina(_n(state, "renda"))


def test_fonte_de_subdivisao_nao_prova_regra_do_pais_e_a_ferramenta_e_desativada():
    state, dossie, pesquisa = _compilar_com(_so_renda(REGRA_MA, VALOR_RO, SM_2026), [], [])
    cob = _renda(state, dossie).cobertura
    assert cob.ready_to_write                                    # a página segue
    assert any(d["tipo"] == "ativo" and "regra" in d["motivo"] for d in cob.desativados)
    assert not [v for v in cob.vinculos if v["papel"] == "regra"]
    # a complementação pede EXATAMENTE a prova de escopo nacional que falta
    pedido = pesquisa.pedidos[1]
    assert [f["requisito"] for f in pedido] == [RENDA]
    assert "não prova regra do país" in pedido[0]["descricao"]


def test_regra_do_pais_e_valor_derivado_ligam_a_ferramenta():
    state, dossie, _ = _compilar_com(_so_renda(REGRA_MA, REGRA_NACIONAL, VALOR_RO, SM_2026))
    cob = _renda(state, dossie).cobertura
    assert cob.estado == "ready", (cob.degradacoes, cob.desativados)
    v = {x["papel"]: x for x in cob.vinculos}
    assert v["regra"]["url"] == PLANALTO and v["regra"]["abrangencia"] == "nacional"
    assert v["valor_vigente"]["origem"] == "derivado" and v["valor_vigente"]["formula"] == "2 × 1621"


def _sem_derivacao():
    arq = _arq_com_requisito_de_renda()
    for job in arq["writing_jobs"]:
        j = job["writer_briefing"]["jornada"]
        if j["duvida_id"] == "renda":
            j["requisitos"] = [dict(r, derivacao=None) for r in j["requisitos"]
                               if r["id"] != "salario_minimo.vigente"]
    return arq


def test_sem_derivacao_publicacao_oficial_atual_de_subdivisao_prova_o_valor():
    state, dossie, _ = _compilar_com(_so_renda(REGRA_NACIONAL, VALOR_RO), arq=_sem_derivacao())
    v = {x["papel"]: x for x in _renda(state, dossie).cobertura.vinculos}
    assert v["valor_vigente"]["url"] == RO and v["valor_vigente"]["jurisdicao"] == "BR-RO"
    assert v["valor_vigente"]["nivel"].startswith("publicação oficial atual de subjurisdição")


def test_valor_de_outro_ano_nao_vale_como_vigente_e_so_desativa_a_ferramenta():
    antigo = dict(VALOR_RO, vigente_desde="2025-01-10")
    state, dossie, _ = _compilar_com(_so_renda(REGRA_NACIONAL, antigo), [], [],
                                     arq=_sem_derivacao())
    cob = _renda(state, dossie).cobertura
    assert cob.ready_to_write
    assert any("valor vigente em 2026" in d["motivo"] for d in cob.desativados)


def test_fonte_da_subdivisao_do_conteudo_prova_a_regra():
    arq = _arq_com_requisito_de_renda()
    arq["funnel_strategy"]["jornada"]["jurisdicao"] = ["BR-MA"]
    state, dossie, _ = _compilar_com(_so_renda(REGRA_MA, VALOR_RO, SM_2026), arq=arq)
    v = {x["papel"]: x for x in _renda(state, dossie).cobertura.vinculos}
    assert v["regra"]["url"] == MA and v["regra"]["jurisdicao"] == "BR-MA"


def test_sem_rebind_arbitrario_fato_nao_verificado_ou_emissor_nao_comprovado():
    blog = _fato("Renda de até 2 salários mínimos", "https://blog.exemplo.com.br/psg", ["renda"],
                 [RENDA], tipo="condicao", valor="2", unidade="salários mínimos")
    blog.update(emissor="Governo Federal", tipo_de_emissor="governo", escopo="nacional",
                jurisdicao="BR")                       # declarado, mas o documento não diz
    citadas = CITADAS + ["https://blog.exemplo.com.br/psg", PLANALTO]
    state, dossie, _ = _compilar_com(_so_renda(blog, REGRA_NACIONAL, VALOR_RO, SM_2026), [], [],
                                     citacoes=citadas,
                                     vivas=[u for u in citadas if u != PLANALTO])
    cob = _renda(state, dossie).cobertura
    assert not [x for x in cob.vinculos if x["papel"] == "regra"]
    assert any(d["tipo"] == "ativo" for d in cob.desativados)


def test_ativo_legado_com_url_nao_verificada_e_desativado_sem_bloquear():
    arq = _arq_com_requisito_de_renda()
    for job in arq["writing_jobs"]:
        for a in job["writer_briefing"]["jornada"].get("ativos", []):
            a.pop("rule_source_fact_id"), a.pop("current_value_source_fact_id")
            a["fonte_da_regra"] = "https://www.senac.br/url-presumida"
    state = _estado(arq)
    dossie = _compilar(state, _Pesquisa(FATOS_COMPLETOS))
    cob = dossie.pagina(_n(state, "renda")).cobertura
    assert cob.ready_to_write
    assert any("fonte da regra fora das fontes verificadas" in d["motivo"]
               for d in cob.desativados)


def test_esqueleto_recusa_ativo_que_aponta_requisito_inexistente():
    from funnelforge.pipeline.jornada.esqueleto import revisar_esqueleto
    arq = _arq_com_requisito_de_renda()
    for job in arq["writing_jobs"]:
        for a in job["writer_briefing"]["jornada"].get("ativos", []):
            a["current_value_source_fact_id"] = "renda.inventado"
    rev = revisar_esqueleto(plano_do_funnel_architecture(arq))
    assert any(i.code == "ativo_requisito_inexistente" for i in rev.bloqueantes)


def test_prompt_mostra_a_abrangencia_o_vinculo_e_o_que_nao_pode_ser_afirmado():
    from funnelforge.prompts import render
    state, dossie, _ = _compilar_com(_so_renda(REGRA_NACIONAL, VALOR_RO), arq=_sem_derivacao())
    state.dossie = dossie.model_dump(mode="json")
    renda = next(p for p in state.plan.pages if p.jornada.duvida_id == "renda")
    texto = render("jornada_da_pagina", jornada=contexto_de_jornada(state.plan, renda, state.dossie))
    assert "(subnacional BR-RO)" in texto
    assert "vale para BR-RO; não apresente como regra do país" in texto
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
