"""Lapidação da jornada (07/10/2026, 2ª rodada) — os casos obrigatórios.

[1] merge protegido arquiteto -> revisor        [10] Humanizer preserva fatos/links
[2] arquiteto -> revisor -> ponte -> motor      [11] texto natural não cria chamada
[3] aliases seguros normalizados                [12] layout x função editorial
[4] erro estrutural com campo e motivo          [13] print sem proveniência recusado
[6] saída oficial manda no roteador             [14] widget sem fonte recusado
[7] revisão global antes da publicação          [15] JSON-LD x conteúdo visível
[8] página reprovada fora da revisão global     [16] V1 intacto (ouro) — test_editorial_v2_flag_off_identico
[9] simulação nunca vira observação             [17] esqueleto reprovado = zero chamada — test_jornada_senac::c12
[5] entradas múltiplas — test_jornada_senac::test_pagina_com_entradas_multiplas_nao_assume_duvidas_resolvidas

Os módulos do BACKEND usados aqui são os reais (`page_factory`, `funnel_roles`,
`jornada_contrato`): puros, sem I/O, importados pelo caminho do repositório.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
from funnelforge.domain.medicao import LeituraDoFunil
from funnelforge.domain.models import (
    EvidenciaDaJornada,
    PageDraft,
    PageRole,
    RunState,
    StepResult,
    StepStatus,
    effective_role,
)
from funnelforge.pipeline import revisao as rv
from funnelforge.pipeline import steps as st
from funnelforge.pipeline.jornada import (
    politica_da_saida_oficial,
    revisar_esqueleto,
    revisar_funil_pronto,
)
from funnelforge.pipeline.metadados import metadados_da_pagina, validar_json_ld
from funnelforge.pipeline.pagespec import enforce_pagespec, pagespec_for
from funnelforge.pipeline.routing import bind_official_route, build_funnel_routes
from funnelforge.prompts import render
from tests.cenario_editorial import (
    congelar_data,
    montar_deps,
    prompts_do_run,
    responder_v1,
    responder_v2,
    rodar_cenario,
    settings_do_cenario,
)
from tests.test_jornada_senac import SLUG, arquitetura

_BACKEND = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from app.agents.funnel_pro.jornada_contrato import (  # noqa: E402
    normalizar_arquitetura,
    preservar_jornada,
)
from app.agents.funnel_pro.page_factory import (  # noqa: E402
    architect_pages_to_funnel_pages,
    page_factory,
)
from app.entities.funnel_roles import apply_roles_and_slugs  # noqa: E402

_SUFIXO = re.compile(r"-(?:pr|p\d+)$")


def _codigos(issues) -> set[str]:
    return {i.code for i in issues}


def saida_do_arquiteto() -> dict:
    """A fixture SENAC no formato que o ARQUITETO devolve (antes do
    page_factory e dos sufixos de slug)."""
    arq = arquitetura()
    tipos = {1: "LANDING PAGE", 2: "HUB"}
    pages = []
    for job in arq["writing_jobs"]:
        wb = job["writer_briefing"]
        ed = copy.deepcopy(wb["editorial"])
        for link in ed["links"]:
            link["target"] = _SUFIXO.sub("", link["target"])
        pages.append({
            "page_number": wb["page_num"], "page_type": tipos.get(wb["page_num"], "SOLUÇÃO"),
            "h1_title": wb["headline"], "slug": _SUFIXO.sub("", wb["current_url"]),
            "emotional_objective": wb["objective"], "main_content_structure": ["H2: Seção"],
            "hook_to_next_page": wb["cta_text"], "next_page_slug": "",
            "target_keywords": [k.strip() for k in wb["keywords"].split(",")],
            "editorial": ed, "jornada": copy.deepcopy(wb["jornada"]),
        })
    return {"funnel_strategy": copy.deepcopy(arq["funnel_strategy"]), "pages": pages}


def revisor_parcial(arq: dict) -> dict:
    """O revisor como o exemplo de saída dele induz: jornada RESUMIDA, sem
    coortes, evidências, monetização, valor, plano visual, ativos; condição
    terminal vazia; e nenhuma jornada no funil."""
    pages = []
    for p in copy.deepcopy(arq["pages"]):
        j = p["jornada"]
        p["jornada"] = {k: j[k] for k in ("duvida_id", "pergunta_principal",
                                          "resposta_imediata", "ja_resolvido",
                                          "proxima_duvida") if k in j}
        p["jornada"]["condicao_terminal"] = ""
        p["jornada"]["saida_oficial"] = {"esperada": j["saida_oficial"]["esperada"],
                                         "classificacao": j["saida_oficial"]["classificacao"]}
        pages.append(p)
    estrategia = {k: v for k, v in arq["funnel_strategy"].items() if k != "jornada"}
    return {"funnel_strategy": estrategia, "pages": pages}


def para_o_card(arq: dict) -> dict:
    """O que o backend grava em `funnel_architecture` (page_factory + sufixos)."""
    paginas, jobs = apply_roles_and_slugs(architect_pages_to_funnel_pages(arq),
                                          page_factory(arq)["writingJobs"])
    return {"funnel_strategy": arq["funnel_strategy"], "pages": paginas, "writing_jobs": jobs}


# ---------------------------------------------------------------------------
# [1] [2] arquiteto -> revisor -> ponte -> motor
# ---------------------------------------------------------------------------

def test_1_revisor_parcial_nao_apaga_a_jornada_do_arquiteto():
    arq = saida_do_arquiteto()
    mesclado, registro = preservar_jornada(arq, revisor_parcial(arq))
    for orig, nova in zip(arq["pages"], mesclado["pages"]):
        assert nova["jornada"] == orig["jornada"], orig["slug"]
    assert mesclado["funnel_strategy"]["jornada"] == arq["funnel_strategy"]["jornada"]
    campos = {r["campo"].split(".")[-1] for r in registro}
    assert {"monetizacao", "condicao_terminal", "valor", "plano_visual",
            "coortes_de_entrada", "hipotese_de_medicao"} <= campos
    assert any(r["campo"] == "funnel_strategy.jornada" for r in registro)


def test_1_mudanca_explicita_do_revisor_vale():
    arq = saida_do_arquiteto()
    rev = revisor_parcial(arq)
    rev["pages"][1]["jornada"]["resposta_imediata"] = "Renda até dois mínimos por pessoa."
    mesclado, _ = preservar_jornada(arq, rev)
    assert mesclado["pages"][1]["jornada"]["resposta_imediata"] == "Renda até dois mínimos por pessoa."
    assert mesclado["pages"][1]["jornada"]["ativos"] == arq["pages"][1]["jornada"]["ativos"]


def test_2_payload_real_atravessa_arquiteto_revisor_ponte_e_motor(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    arq = saida_do_arquiteto()
    mesclado, _ = preservar_jornada(arq, revisor_parcial(arq))
    normal, relatorio = normalizar_arquitetura(mesclado)
    assert relatorio["estado"] == "valida", relatorio["erros"]
    card = para_o_card(normal)
    plano = plano_do_funnel_architecture(copy.deepcopy(card))
    assert {p.slug for p in plano.pages} == set(SLUG.values())
    assert revisar_esqueleto(plano).bloqueantes == []
    settings = settings_do_cenario(tmp_path)
    state, _deps, _llm = rodar_cenario(tmp_path, card, settings)
    assert state.step_status["revisao_esqueleto"].status is StepStatus.OK
    assert state.drafts and state.revisao_global["versao"] == "revisao-global-v2"


# ---------------------------------------------------------------------------
# [3] [4] normalização segura e erro com campo + motivo
# ---------------------------------------------------------------------------

def test_3_aliases_e_variacoes_seguras_sao_normalizados():
    arq = saida_do_arquiteto()
    renda = arq["pages"][1]["jornada"]
    renda["coortes_de_entrada"] = ["Busca orgânica", "WhatsApp"]
    renda["entrada_direta"] = "Autocontida"
    renda["saida_oficial"]["classificacao"] = "Não aplicável"
    renda["valor"]["entregas"] = ["Cálculo", "Exemplo", "Resposta direta"]
    fj = arq["funnel_strategy"]["jornada"]
    fj["coortes"][0]["canal"] = "Google Ads Search"
    fj["coortes"][0]["profundidade"] = "Guiada"
    fj["evidencias"][0] = {"natureza": "Simulação", "afirmacao": "loop renda curso",
                           "fonte": "MiroFish", "confianca": "Média"}
    arq["pages"][0]["jornada"]["duvida_id"] = "Senac Gratuito"
    normal, rel = normalizar_arquitetura(arq)
    assert rel["estado"] == "valida", rel["erros"]
    j = normal["pages"][1]["jornada"]
    assert j["coortes_de_entrada"] == ["organic_search", "social"]
    assert j["entrada_direta"] == "autocontida"
    assert j["saida_oficial"]["classificacao"] == "nao_aplicavel"
    assert j["valor"]["entregas"] == ["calculo", "exemplo", "resposta_direta"]
    nfj = normal["funnel_strategy"]["jornada"]
    assert nfj["coortes"][0]["canal"] == "paid_search"
    assert nfj["evidencias"][0]["natureza"] == "simulacao"
    assert nfj["evidencias"][0]["fonte"] == "simulacao:mirofish"
    assert normal["pages"][0]["jornada"]["duvida_id"] == "senac_gratuito"
    assert rel["normalizacoes"]
    plano = plano_do_funnel_architecture(para_o_card(normal))
    assert plano.jornada.evidencias[0].fonte == "simulacao:mirofish"


def test_4_erro_estrutural_chega_ao_operador_com_campo_e_motivo():
    arq = saida_do_arquiteto()
    arq["funnel_strategy"]["jornada"]["coortes"][0]["canal"] = "tiktok_ads"
    arq["pages"][2]["jornada"]["proxima_duvida"] = "bolsa_integral"
    _, rel = normalizar_arquitetura(arq)
    assert rel["estado"] == "invalida"
    campos = {e["campo"] for e in rel["erros"]}
    assert "funnel_strategy.jornada.coortes[0].canal" in campos
    assert any("bolsa_integral" in e["motivo"] for e in rel["erros"])
    # o motor também recusa na carga, nomeando o campo — nunca "sem jornada"
    card = para_o_card(arq)
    with pytest.raises(ValueError, match=r"jornada inválida \(coortes\.0\.canal"):
        plano_do_funnel_architecture(card)


def test_4_campo_descritivo_cosmetico_nao_derruba_o_card():
    arq = saida_do_arquiteto()
    arq["funnel_strategy"]["jornada"]["evidencias"][1]["confianca"] = "quase certa"
    normal, rel = normalizar_arquitetura(arq)
    assert rel["estado"] == "valida"
    assert any("confianca" in a["campo"] for a in rel["avisos"])
    assert "confianca" not in normal["funnel_strategy"]["jornada"]["evidencias"][1]


# ---------------------------------------------------------------------------
# [6] a saída oficial manda no roteador
# ---------------------------------------------------------------------------

def _plano(arq=None):
    return plano_do_funnel_architecture(copy.deepcopy(arq or arquitetura()))


def _pagina(plano, duvida):
    return next(p for p in plano.pages if p.jornada.duvida_id == duvida)


def test_6_saida_oficial_boa_prematura_e_nao_aplicavel_controlam_a_rota(tmp_path):
    settings = settings_do_cenario(tmp_path)
    arq = arquitetura()
    for job in arq["writing_jobs"]:
        j = job["writer_briefing"]["jornada"]
        if j["duvida_id"] == "inscricao":
            j["saida_oficial"] = {"esperada": False, "classificacao": "nao_aplicavel"}
    plano = _plano(arq)
    build_funnel_routes(plano, settings)
    oficial = ["https://www.senac.br/oficial"]

    estado = _pagina(plano, "estado")
    agir = estado.model_copy(deep=True)           # boa no estágio de agir -> primeiro
    agir.jornada.proxima_duvida = ""
    bind_official_route(agir, oficial, role=PageRole.SOLUTION, is_terminal=False,
                        politica=politica_da_saida_oficial(agir))
    assert agir.routes[0].kind == "external_official"
    assert agir.routes[0].placement == "hero"

    # boa, mas ainda com dúvida interna aberta: a saída continua obrigatória e
    # visível, DEPOIS do CTA da próxima dúvida (não empurra o leitor para fora)
    assert estado.jornada.proxima_duvida
    pol = politica_da_saida_oficial(estado)
    assert pol.exige and pol.classe == "boa" and not pol.primeiro
    bind_official_route(estado, oficial, role=PageRole.SOLUTION, is_terminal=False,
                        politica=pol)
    assert estado.routes[0].kind == "funnel"
    assert estado.routes[-1].kind == "external_official"
    assert estado.routes[-1].placement == "footer"

    curso = _pagina(plano, "curso")               # prematura -> depois da próxima dúvida
    bind_official_route(curso, oficial, role=PageRole.SOLUTION, is_terminal=False,
                        politica=politica_da_saida_oficial(curso))
    assert [r.kind for r in curso.routes] == ["funnel", "external_official"]
    assert curso.routes[-1].placement == "footer"

    inscricao = _pagina(plano, "inscricao")      # não aplicável -> sem rota, sem exigência
    pol = politica_da_saida_oficial(inscricao)
    bind_official_route(inscricao, oficial, role=PageRole.SOLUTION, is_terminal=True,
                        terminal_official=True, politica=pol)
    assert not any(r.kind == "external_official" for r in inscricao.routes)
    spec = pagespec_for(settings, PageRole.SOLUTION, contextual=True, page_count=5,
                        exige_oficial=pol.exige)
    assert enforce_pagespec(inscricao.routes, spec, slug=inscricao.slug, h1_by_slug={}) == []


def test_6_saida_boa_sem_fonte_comprovada_falha_fechado(tmp_path):
    settings = settings_do_cenario(tmp_path)
    plano = _plano()
    build_funnel_routes(plano, settings)
    estado = _pagina(plano, "estado")
    pol = politica_da_saida_oficial(estado)
    bind_official_route(estado, [], role=PageRole.SOLUTION, is_terminal=False, politica=pol)
    spec = pagespec_for(settings, PageRole.SOLUTION, contextual=True, page_count=5,
                        exige_oficial=pol.exige)
    assert "target_missing" in _codigos(enforce_pagespec(
        estado.routes, spec, slug=estado.slug, h1_by_slug={}))


# ---------------------------------------------------------------------------
# [7] [8] revisão global antes da publicação, só páginas aprovadas
# ---------------------------------------------------------------------------

def test_7_revisao_global_roda_antes_de_qualquer_publicacao(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    vistos: list[bool] = []
    monkeypatch.setattr(st, "step_publish",
                        lambda state, page, deps: vistos.append(bool(state.revisao_global)))
    settings = settings_do_cenario(tmp_path)
    llm, deps = montar_deps(tmp_path, settings, responder_v1)
    deps.publisher = object()
    from funnelforge.pipeline.pipeline import run_pipeline
    state = run_pipeline(None, deps, publish=True, timestamp="20261007-120000",
                         plan=_plano())
    assert vistos and all(vistos), "publicou antes da revisão global"
    ordem = list(state.step_status)
    assert "revisao_global" in ordem


def _estado_aprovado(tmp_path):
    settings = settings_do_cenario(tmp_path)
    plano = _plano()
    build_funnel_routes(plano, settings)
    state = RunState(run_id="r", plan=plano)
    for p in plano.pages:
        state.drafts[p.page_number] = PageDraft(
            page_number=p.page_number, page_type=p.page_type, format="gutenberg",
            content=f"<p>{p.jornada.resposta_imediata}</p>")
        state.step_status[f"content_gate_p{p.page_number}"] = StepResult(
            step=f"content_gate_p{p.page_number}", status=StepStatus.OK)
    return state, settings


def test_8_pagina_reprovada_nao_entra_na_revisao_do_funil_pronto(tmp_path):
    state, settings = _estado_aprovado(tmp_path)
    curso = _pagina(state.plan, "curso")
    state.step_status[f"content_gate_p{curso.page_number}"] = StepResult(
        step=f"content_gate_p{curso.page_number}", status=StepStatus.FAILED)
    rev = revisar_funil_pronto(state, settings)
    assert curso.page_number not in rev["paginas_revisadas"]
    assert curso.page_number in rev["paginas_fora_da_revisao"]
    assert all(a["pagina"] != curso.page_number for a in rev["achados"])
    # órfã por causa de outra página que falhou é aviso, nunca bloqueio
    assert all(a["severidade"] == "aviso" for a in rev["achados"] if a["regra"] == "pagina_orfa")


# ---------------------------------------------------------------------------
# [9] simulação nunca vira observação — os dois contratos, a mesma guarda
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fonte", ["MiroFish", " SIMULAÇÃO: mirofish ", "simulacao:x",
                                   "mirofish-creditoup", "Hipótese do arquiteto"])
def test_9_simulacao_nunca_entra_como_observacao_real(fonte):
    with pytest.raises(ValidationError):
        EvidenciaDaJornada(natureza="observacao_real", afirmacao="x", fonte=fonte,
                           coletado_em=date(2026, 10, 1), referencia="rel-1")
    with pytest.raises(ValidationError):
        LeituraDoFunil(natureza="Observação real", sinal="loop_revisita", escopo="funil",
                       valor=0.3, amostra=100, fonte=fonte, referencia="rel-1",
                       janela={"inicio": "2026-09-01", "fim": "2026-09-30"})
    arq = saida_do_arquiteto()
    arq["funnel_strategy"]["jornada"]["evidencias"] = [{
        "natureza": "observado", "afirmacao": "x", "fonte": fonte,
        "coletado_em": "2026-10-01", "referencia": "rel-1"}]
    _, rel = normalizar_arquitetura(arq)
    assert rel["estado"] == "invalida"


def test_9_observacao_real_exige_fonte_data_e_identificador():
    with pytest.raises(ValidationError):
        EvidenciaDaJornada(natureza="observacao_real", afirmacao="x", fonte="ga4:propriedade")
    ok = EvidenciaDaJornada(natureza="observacao_real", afirmacao="x", fonte="ga4:propriedade",
                            coletado_em=date(2026, 10, 1), referencia="relatorio-123")
    assert ok.natureza == "observacao_real"
    with pytest.raises(ValidationError):
        LeituraDoFunil(natureza="observacao_real", sinal="abandono", escopo="funil", valor=0.4,
                       amostra=10, fonte="ga4:propriedade",
                       janela={"inicio": "2026-09-01", "fim": "2026-09-30"})


# ---------------------------------------------------------------------------
# [10] [11] Humanizer: preserva fatos, sem chamada extra
# ---------------------------------------------------------------------------

def _doc() -> rv.Documento:
    corpo = ("<!-- wp:paragraph -->\n<p>Neste artigo vamos entender tudo. A renda por pessoa "
             "precisa ficar abaixo de 2 salários mínimos.</p>\n<!-- /wp:paragraph -->\n\n"
             "<!-- wp:paragraph -->\n<p>Veja o <a href=\"https://www.senac.br/psg\">regulamento"
             "</a>, um marco crucial.</p>\n<!-- /wp:paragraph -->")
    return rv.Documento(formato="gutenberg", corpo=corpo)


def _achado(trecho: str, sev: str = "ajuste") -> dict:
    return rv.validar_achados([{"id": "n1", "severidade": sev, "categoria": "naturalidade",
                                "campo": "corpo", "trecho": trecho, "motivo": "abertura genérica",
                                "evidencia": {"tipo": "escrita", "ref": "padrao:abertura_generica"}}],
                              _doc(), rv.Referencias())[0]


def test_10_naturalidade_ajusta_forma_e_preserva_numero_e_link():
    doc = _doc()
    trecho = "Neste artigo vamos entender tudo. A renda por pessoa precisa ficar abaixo de 2 salários mínimos."
    achado = _achado(trecho)
    assert achado["severidade"] == "ajuste" and not achado["invalido"]
    regras = rv.RegrasDePatch(numeros_permitidos={"2"})
    ok, aplicados, _ = rv.aplicar_patches(doc, [{"achado": "n1", "campo": "corpo", "antes": trecho,
        "depois": "A renda por pessoa precisa ficar abaixo de 2 salários mínimos."}],
        {"n1": achado}, regras)
    assert aplicados and "Neste artigo" not in ok.corpo and "2 salários" in ok.corpo
    _, _, recusados = rv.aplicar_patches(doc, [{"achado": "n1", "campo": "corpo", "antes": trecho,
        "depois": "A renda por pessoa precisa ficar abaixo do teto."}], {"n1": achado}, regras)
    assert recusados[0]["motivo"] == "naturalidade_perderia_numero"
    trecho_link = "Veja o <a href=\"https://www.senac.br/psg\">regulamento</a>, um marco crucial."
    achado2 = _achado(trecho_link)
    _, _, recusados = rv.aplicar_patches(doc, [{"achado": "n1", "campo": "corpo",
        "antes": trecho_link, "depois": "Veja o regulamento."}], {"n1": achado2}, regras)
    # o link nunca muda: a proteção de região existente ou a régua de
    # naturalidade recusam — o texto com link fica intacto
    assert recusados[0]["motivo"] in ("regiao_protegida", "naturalidade_nao_toca_link")
    assert rv._checar_naturalidade(trecho_link, "Veja o regulamento.") == "naturalidade_nao_toca_link"


def test_10_naturalidade_nunca_bloqueia():
    achado = _achado("Neste artigo vamos entender tudo.", sev="bloqueante")
    assert achado["severidade"] == "ajuste"


def test_10_doutrina_esta_no_redator_e_no_revisor_v2_e_fora_do_v1():
    v2 = render("reader_contract_v2", briefing_texto="b")
    assert "<escrita_natural>" in v2 and "Preserve sempre: fatos, fontes" in v2
    assert "<escrita_natural>" not in render("reader_contract", editorial={})


def test_11_texto_natural_nao_cria_chamada_extra(tmp_path, monkeypatch):
    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=True)
    state, deps, _ = rodar_cenario(tmp_path, arquitetura(), settings, responder=responder_v2)
    log = (deps.runner.runs_dir / state.run_id / "log.jsonl").read_text(encoding="utf-8")
    passos = [json.loads(l)["step"] for l in log.splitlines() if '"attempt"' in l]
    assert not any("human" in p or "natural" in p for p in passos)
    revisoes = [p for p in passos if p.startswith("revisor_p")]
    assert len(revisoes) == len(set(revisoes)), "mais de uma revisão por página"
    assert any("<escrita_natural>" in t for k, t in
               prompts_do_run(deps.runner.runs_dir, state.run_id).items() if k.startswith("write_p"))


# ---------------------------------------------------------------------------
# [12] layout corresponde à função editorial
# ---------------------------------------------------------------------------

def test_12_bloco_tem_de_servir_a_uma_entrega_declarada():
    arq = arquitetura()
    for job in arq["writing_jobs"]:
        j = job["writer_briefing"]["jornada"]
        if j["duvida_id"] == "inscricao":
            j["plano_visual"] = [
                {"secao": "Comparar", "intencao": "comparar", "padrao": "table", "funcao": "x"},
                {"secao": "Docs", "intencao": "checklist", "padrao": "table", "funcao": "x"},
                {"secao": "Ferramenta", "intencao": "ferramenta", "padrao": "html", "funcao": "x"},
                {"secao": "Passos", "intencao": "passo_a_passo", "padrao": "list", "funcao": ""}]
    rev = revisar_esqueleto(_plano(arq))
    codigos = _codigos(rev.bloqueantes)
    assert {"bloco_incompativel_com_a_funcao", "ferramenta_sem_ativo",
            "bloco_sem_funcao_editorial"} <= codigos
    # bloco sem entrega declarada é oportunidade editorial: aviso, não bloqueio
    assert "bloco_sem_entrega_correspondente" not in codigos
    assert "bloco_sem_entrega_correspondente" in _codigos(rev.avisos)
    assert revisar_esqueleto(_plano()).bloqueantes == []


def test_12_pagina_sem_valor_ou_duplicada_nao_vai_a_redacao():
    arq = arquitetura()
    jobs = {j["writer_briefing"]["jornada"]["duvida_id"]: j["writer_briefing"]["jornada"]
            for j in arq["writing_jobs"]}
    del jobs["curso"]["valor"]
    jobs["inscricao"]["valor"]["informacao_nova"] = jobs["estado"]["valor"]["informacao_nova"]
    codigos = _codigos(revisar_esqueleto(_plano(arq)).bloqueantes)
    assert {"valor_nao_declarado", "fusao_necessaria"} <= codigos


# ---------------------------------------------------------------------------
# [13] print sem proveniência
# ---------------------------------------------------------------------------

class _Publicador:
    def __init__(self):
        self.enviados = []

    def upload_media(self, data, filename, mime, alt=""):
        self.enviados.append(filename)
        return {"source_url": "https://site.exemplo.com.br/wp-content/print.webp"}


def test_13_print_sem_proveniencia_e_recusado(tmp_path):
    arquivo = tmp_path / "p3-oficial.webp"
    arquivo.write_bytes(b"webp")
    url = "https://www.senac.br/psg"
    bom = st.proveniencia_do_print(url, arquivo, st.ResearchFacts(), titulo="PSG", crop="desktop")
    assert st.print_sem_proveniencia(bom) == []
    assert "capturada em" in bom["legenda"] and "pertence ao site de origem" in bom["legenda"]
    sem = {"url": url, "path": str(arquivo)}
    assert {"capturado_em", "sha256", "legenda", "trecho_ou_titulo"} <= set(
        st.print_sem_proveniencia(sem))
    adulterado = {**bom, "sha256": "0" * 64}
    state = RunState(run_id="r")
    state.screenshots[3] = [sem, adulterado]
    pub = _Publicador()
    deps = type("D", (), {"publisher": pub})()
    pagina = type("P", (), {"page_number": 3})()
    html = f'<!-- wp:paragraph -->\n<p><a href="{url}">PSG</a></p>\n<!-- /wp:paragraph -->'
    assert st._embed_official_screenshots(state, pagina, deps, html) == html
    assert pub.enviados == []
    state.screenshots[3] = [bom]
    saida = st._embed_official_screenshots(state, pagina, deps, html)
    assert pub.enviados and "capturada em" in saida


# ---------------------------------------------------------------------------
# [14] widget sem fonte factual
# ---------------------------------------------------------------------------

def test_14_ativo_sem_fonte_factual_nao_gera_widget_nem_chamada(tmp_path):
    settings = settings_do_cenario(tmp_path)
    llm, deps = montar_deps(tmp_path, settings, responder_v1)
    plano = _plano()
    curso = _pagina(plano, "curso")
    curso.engajamento = "comparativo"
    curso.jornada.ativos = [type(_pagina(plano, "renda").jornada.ativos[0])(
        pergunta="Qual modalidade cabe na minha rotina?", entradas=["horas livres"],
        logica="compara carga horária", resultado="modalidade sugerida",
        fonte_da_regra="https://www.fonte-sem-lastro.example/regra",
        fallback_sem_js="tabela", acessibilidade="label", evento_de_medicao="ev")]
    state = RunState(run_id="r", plan=plano)
    state.drafts[curso.page_number] = PageDraft(page_number=curso.page_number,
                                                page_type="SOLUTION", format="gutenberg",
                                                content="<p>texto</p>")
    st.step_widget(state, curso, deps)
    res = state.step_status[f"widget_p{curso.page_number}"]
    assert res.status is StepStatus.SKIPPED
    assert "ativo_sem_fonte_factual" in _codigos(res.issues)
    assert llm.calls == []


# ---------------------------------------------------------------------------
# [15] JSON-LD corresponde ao conteúdo visível
# ---------------------------------------------------------------------------

def test_15_json_ld_so_com_o_que_o_texto_mostra(tmp_path):
    settings = settings_do_cenario(tmp_path)
    plano = _plano()
    inscricao = _pagina(plano, "inscricao")
    conteudo = ("<p>A inscrição é feita na regional.</p>"
                "<ol><li>Separe o documento de identidade.</li><li>Abra o site da regional.</li></ol>"
                "<details><summary>Precisa pagar?</summary><p>Não, a vaga do PSG é gratuita.</p></details>")
    state = RunState(run_id="r", plan=plano)
    state.drafts[inscricao.page_number] = PageDraft(page_number=inscricao.page_number,
                                                    page_type="SOLUTION", format="gutenberg",
                                                    content=conteudo)
    state.seo[inscricao.page_number] = {"seotitle": "Inscrição no Senac passo a passo",
                                        "metadescription": "Passos e documentos."}
    meta = metadados_da_pagina(state, inscricao, settings, hoje=date(2026, 10, 7),
                               robots="noindex,follow")
    tipos = {b["@type"] for b in meta.json_ld}
    assert {"Article", "BreadcrumbList", "FAQPage", "HowTo"} <= tipos
    faq = next(b for b in meta.json_ld if b["@type"] == "FAQPage")
    assert faq["mainEntity"][0]["name"] == "Precisa pagar?"
    assert meta.canonical_estado == "previsto" and meta.publicado_em is None
    article = next(b for b in meta.json_ld if b["@type"] == "Article")
    assert article["author"]["@type"] == "Organization"
    # pergunta que não está visível é recusada
    invisivel = {**faq, "mainEntity": [{"@type": "Question", "name": "Dá dinheiro?",
                                        "acceptedAnswer": {"@type": "Answer", "text": "Sim."}}]}
    assert validar_json_ld(invisivel, "A inscrição é feita na regional.", settings)
    # sem details e sem passo_a_passo declarado: nada de FAQPage/HowTo
    estado = _pagina(plano, "estado")
    state.drafts[estado.page_number] = PageDraft(page_number=estado.page_number,
                                                 page_type="SOLUTION", format="gutenberg",
                                                 content="<ol><li>a</li><li>b</li></ol>")
    tipos2 = {b["@type"] for b in metadados_da_pagina(
        state, estado, settings, hoje=date(2026, 10, 7), robots="noindex,follow").json_ld}
    assert "FAQPage" not in tipos2 and "HowTo" not in tipos2


def test_lp_e_roteada_por_progresso_mesmo_vinda_do_card(tmp_path):
    plano = plano_do_funnel_architecture(para_o_card(saida_do_arquiteto()))
    build_funnel_routes(plano, settings_do_cenario(tmp_path))
    lp = next(p for p in plano.pages if effective_role(p) is PageRole.LP)
    assert lp.routes[0].target == SLUG["renda"]


def test_print_de_destino_que_a_pagina_nao_linka_nao_entra(tmp_path):
    arquivo = tmp_path / "p4-oficial.webp"
    arquivo.write_bytes(b"webp")
    linkado, solto = "https://www.gov.br/aneel/fale", "https://www.ba.gov.br/noticia"
    state = RunState(run_id="r")
    state.screenshots[4] = [
        st.proveniencia_do_print(u, arquivo, st.ResearchFacts(), titulo="t", crop="mobile")
        for u in (linkado, solto)]
    pub = _Publicador()
    deps = type("D", (), {"publisher": pub})()
    pagina = type("P", (), {"page_number": 4})()
    html = (f'<!-- wp:paragraph -->\n<p><a href="{linkado}">ANEEL</a></p>\n'
            '<!-- /wp:paragraph -->')
    saida = st._embed_official_screenshots(state, pagina, deps, html)
    assert len(pub.enviados) == 1 and saida.count("<!-- wp:image") == 1
