"""A TRAVA DAS NOTAS EXISTENCIAIS no revisor V2 (paridade com o juiz V1).

O juiz V1 (`steps._judge_page`) é fail-closed: mesmo com `approved=true`, nota
< 7 ou AUSENTE (conta como 0) em qualquer critério existencial reprova a
página. O revisor V2 pedia "notas" mas só as gravava — no canário o modelo
copiou o exemplo `{0, 0, 0}` do prompt, aprovou, e as páginas viraram recibo
"aprovado". Aqui:

- decisão final "aprovado" (rodada 1 sem patch OU fim do caminho "ajustar")
  com critério exigido ausente, não numérico, fora de 0-10 ou < 7 fecha em
  `revisao_humana` com `notas_existenciais_insuficientes:<criterio>=<valor>` e
  o draft intacto;
- o conjunto exigido é o MESMO do V1 (editorial: compliance, cta_discipline,
  useful_delivery, destination_relevance; fora dele, `_existential_criteria_for`);
- o exemplo de saída do prompt não tem número copiável;
- recibo, publish e a revisão avulsa herdam a trava.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from funnelforge.pipeline import revisao, revisao_avulsa, steps
from funnelforge.pipeline.revisao import conferir_recibo, executar_revisao
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM
from tests.test_revisor_decisao import (
    A_PROMESSA,
    CFG,
    P_PROMESSA,
    _ctx,
    _doc,
    _rodar,
)

EDITORIAIS = ("compliance", "cta_discipline", "useful_delivery", "destination_relevance")
CANARIO = {"useful_delivery": 0, "destination_relevance": 0, "compliance": 0}
BOAS = {"compliance": 9, "cta_discipline": 8, "useful_delivery": 8, "destination_relevance": 8}
MOTIVO = "notas_existenciais_insuficientes"

_SEM = object()


def _resp(decisao="aprovado", notas=_SEM, achados=(), patches=(), afirmacoes=()) -> str:
    dados = {"versao": "revisao-v1", "decisao": decisao, "achados": list(achados),
             "patches": list(patches), "afirmacoes_nao_verificadas": list(afirmacoes),
             "preservado": ["ângulo"]}
    if notas is not _SEM:
        dados["notas"] = notas
    return json.dumps(dados, ensure_ascii=False)


def _motivos_de_nota(r) -> list[str]:
    return [m for m in r.registro["motivos"] if m.startswith(MOTIVO + ":")]


def _intacto(r) -> None:
    assert r.documento == _doc()
    assert r.registro["sha256"] == r.registro["sha256_entrada"] == _doc().sha256()


# ---------------------------------------------------------------------------
# rodada 1 "aprovado" sem patch
# ---------------------------------------------------------------------------

def test_notas_zeradas_copiadas_do_exemplo_nao_aprovam(tmp_path):
    """O caso real do canário (p1/p3): {0,0,0} e "aprovado"."""
    r, _ = _rodar([_resp(notas=CANARIO)], tmp_path)
    assert r.decisao == "revisao_humana"
    motivos = _motivos_de_nota(r)
    assert f"{MOTIVO}:compliance=0" in motivos
    assert f"{MOTIVO}:useful_delivery=0" in motivos
    assert f"{MOTIVO}:destination_relevance=0" in motivos
    assert f"{MOTIVO}:cta_discipline=ausente" in motivos
    _intacto(r)
    assert r.telemetria.status.value == "FAILED"


def test_todas_as_notas_zero_nao_aprovam(tmp_path):
    r, _ = _rodar([_resp(notas={c: 0 for c in EDITORIAIS})], tmp_path)
    assert r.decisao == "revisao_humana"
    assert sorted(_motivos_de_nota(r)) == sorted(f"{MOTIVO}:{c}=0" for c in EDITORIAIS)
    _intacto(r)


@pytest.mark.parametrize("notas", [_SEM, {}, None, [], "8", [8, 8, 8, 8]],
                         ids=["sem_chave", "vazio", "null", "lista_vazia", "texto", "lista"])
def test_sem_notas_nao_aprova(tmp_path, notas):
    r, _ = _rodar([_resp(notas=notas)], tmp_path)
    assert r.decisao == "revisao_humana"
    assert sorted(_motivos_de_nota(r)) == sorted(f"{MOTIVO}:{c}=ausente" for c in EDITORIAIS)
    _intacto(r)


def test_uma_nota_seis_nao_aprova(tmp_path):
    r, _ = _rodar([_resp(notas=dict(BOAS, cta_discipline=6))], tmp_path)
    assert r.decisao == "revisao_humana"
    assert _motivos_de_nota(r) == [f"{MOTIVO}:cta_discipline=6"]
    _intacto(r)


def test_canario_com_notas_boas_mas_sem_cta_discipline_nao_aprova(tmp_path):
    """O exemplo antigo do prompt não pedia cta_discipline; o V1 editorial exige."""
    r, _ = _rodar([_resp(notas={"useful_delivery": 8, "destination_relevance": 8,
                                "compliance": 9})], tmp_path)
    assert r.decisao == "revisao_humana"
    assert _motivos_de_nota(r) == [f"{MOTIVO}:cta_discipline=ausente"]


@pytest.mark.parametrize("notas", [
    {c: 7 for c in EDITORIAIS},
    BOAS,
    {c: 10 for c in EDITORIAIS},
    dict(BOAS, compliance=7.0),          # inteiro escrito como decimal (o V1 aceita)
    dict(BOAS, extra_nao_exigido=0),
], ids=["tudo_7", "boas", "tudo_10", "decimal", "extra_nao_exigido_zero"])
def test_todas_as_notas_exigidas_ate_7_aprovam(tmp_path, notas):
    r, _ = _rodar([_resp(notas=notas)], tmp_path)
    assert r.decisao == "aprovado", r.registro["motivos"]
    _intacto(r)


@pytest.mark.parametrize("valor,escrito", [
    ("9", '"9"'), ("8", '"8"'), (11, "11"), (-1, "-1"), (10.5, "10.5"), (True, "true"),
    (None, "null"), ([9], "[9]"), ({"nota": 9}, '{"nota": 9}'), ("nove", '"nove"'),
], ids=["texto_9", "texto_8", "onze", "negativo", "acima_de_10", "booleano", "null",
        "lista", "objeto", "por_extenso"])
def test_nota_nao_numerica_ou_fora_de_0_a_10_nao_aprova(tmp_path, valor, escrito):
    r, _ = _rodar([_resp(notas=dict(BOAS, useful_delivery=valor))], tmp_path)
    assert r.decisao == "revisao_humana"
    assert _motivos_de_nota(r) == [f"{MOTIVO}:useful_delivery={escrito}"]
    _intacto(r)


def test_as_notas_avaliadas_ficam_no_registro_da_rodada(tmp_path):
    r, _ = _rodar([_resp(notas=dict(BOAS, cta_discipline=6))], tmp_path)
    avaliacao = r.registro["rodadas"][0]["notas_existenciais"]
    assert tuple(avaliacao["criterios"]) == EDITORIAIS
    assert avaliacao["minima"] == 7
    assert avaliacao["avaliadas"]["cta_discipline"] == 6
    assert avaliacao["avaliadas"]["compliance"] == 9
    assert avaliacao["insuficientes"] == [f"{MOTIVO}:cta_discipline=6"]
    r2, _ = _rodar([_resp(notas=BOAS)], tmp_path / "ok")
    assert r2.registro["rodadas"][0]["notas_existenciais"]["insuficientes"] == []


# ---------------------------------------------------------------------------
# o fim do caminho "ajustar" (as notas descrevem o texto ANTES do patch)
# ---------------------------------------------------------------------------

def test_ajustar_com_nota_baixa_vai_para_humano_com_draft_intacto(tmp_path):
    r, llm = _rodar([_resp("ajustar", dict(BOAS, compliance=4), [A_PROMESSA], [P_PROMESSA])],
                    tmp_path)
    assert r.decisao == "revisao_humana" and len(llm.calls) == 1
    assert f"{MOTIVO}:compliance=4" in r.registro["motivos"]
    _intacto(r)
    rod = r.registro["rodadas"][0]
    assert not rod.get("mantida")
    assert [p["achado"] for p in rod["patches_aplicados"]] == ["a1"]   # registrado p/ o humano


def test_ajustar_sem_notas_vai_para_humano(tmp_path):
    r, _ = _rodar([_resp("ajustar", _SEM, [A_PROMESSA], [P_PROMESSA])], tmp_path)
    assert r.decisao == "revisao_humana"
    assert f"{MOTIVO}:compliance=ausente" in r.registro["motivos"]
    _intacto(r)


def test_aprovado_com_patch_tratado_como_ajustar_tambem_confere_as_notas(tmp_path):
    r, _ = _rodar([_resp("aprovado", CANARIO, [A_PROMESSA], [P_PROMESSA])], tmp_path)
    assert r.decisao == "revisao_humana"
    assert f"{MOTIVO}:compliance=0" in r.registro["motivos"]
    _intacto(r)


def test_ajustar_com_notas_boas_continua_aprovando(tmp_path):
    r, _ = _rodar([_resp("ajustar", BOAS, [A_PROMESSA], [P_PROMESSA])], tmp_path)
    assert r.decisao == "aprovado", r.registro["motivos"]
    assert "depende do pedido" in r.documento.corpo


# ---------------------------------------------------------------------------
# o conjunto exigido é o do V1
# ---------------------------------------------------------------------------

def test_conjunto_editorial_e_o_do_v1_e_papel_desconhecido_nao_afrouxa():
    fn = revisao.criterios_existenciais
    for papel in ("SOLUTION", "PRESELL", "LP", "", None, "qualquer"):
        # sem a informação "editorial": nunca menos que o conjunto editorial
        assert set(EDITORIAIS) <= set(fn({"papel": papel})), papel
        assert tuple(fn({"papel": papel, "editorial": True})) == EDITORIAIS, papel
    assert tuple(fn({"papel": "SOLUTION", "editorial": False})) == (
        "compliance", "cta_discipline")
    assert tuple(fn({"papel": "PRESELL", "editorial": False})) == (
        "compliance", "cta_discipline")
    assert tuple(fn({"papel": "LP", "editorial": False})) == (
        "single_destination", "compliance", "cta_discipline")
    # sem papel e sem slug que o derive: LP (o conjunto mais amplo do papel)
    assert "single_destination" in fn({"papel": "", "slug": "", "editorial": False})


def test_regra_do_papel_vem_de_existential_criteria_for(monkeypatch):
    """Reuso, não cópia: mudar a função do V1 muda o conjunto do revisor."""
    monkeypatch.setattr(steps, "_existential_criteria_for",
                        lambda role: ("single_destination", "compliance"))
    fn = revisao.criterios_existenciais
    assert tuple(fn({"papel": "SOLUTION", "editorial": False})) == (
        "single_destination", "compliance")
    # no editorial, o V1 não subtrai nada pelo papel: o conjunto é o editorial
    assert tuple(fn({"papel": "SOLUTION", "editorial": True})) == EDITORIAIS


_TODAS_DO_JUIZ = ("useful_delivery", "destination_relevance", "cta_discipline",
                  "proof_and_authority", "compliance", "tone_e_e_a_t", "faq_resolution",
                  "single_destination", "authorship_signal")


def _v1_bloqueia(config_files, page, plano, scores) -> bool:
    from funnelforge.domain.models import RunState, StepStatus
    from tests.test_steps_prompt_routing import _deps
    verdict = json.dumps({"approved": True, "blocking": False, "scores": scores})
    deps = _deps(config_files, FakeLLM(responses=[verdict]))
    state = RunState(run_id="paridade", plan=plano)
    steps._judge_page(state, page, "Texto", deps)
    return state.step_status[f"judge_p{page.page_number}"].status is StepStatus.FAILED


@pytest.mark.parametrize("editorial", [True, False], ids=["editorial", "sem_editorial"])
@pytest.mark.parametrize("indice", [0, 1, 2], ids=["LP", "PRESELL", "SOLUTION"])
def test_paridade_com_o_juiz_v1(config_files, editorial, indice):
    """Para cada papel, com e sem contrato editorial: o juiz V1 reprova com 6 em
    CADA critério que o revisor exige, e aprova com só esses critérios ≥ 7."""
    from funnelforge.pipeline.routing import build_funnel_routes
    from tests.test_contextual_editorial import plan
    from tests.test_steps_prompt_routing import _deps
    plano = plan()
    if not editorial:
        for p in plano.pages:
            p.editorial = None
    build_funnel_routes(plano, _deps(config_files, FakeLLM(responses=[])).settings)
    page = plano.pages[indice]
    exigidos = revisao.criterios_existenciais(
        {"papel": steps.effective_role(page).value, "editorial": page.editorial is not None})
    assert exigidos
    assert not _v1_bloqueia(config_files, page, plano, {c: 9 for c in exigidos})
    for c in exigidos:
        scores = {k: 9 for k in _TODAS_DO_JUIZ}
        scores[c] = 6
        assert _v1_bloqueia(config_files, page, plano, scores), c


# ---------------------------------------------------------------------------
# o prompt
# ---------------------------------------------------------------------------

def _exemplo_de_notas(prompt: str) -> str:
    saida = prompt.split("<saida>", 1)[1]
    m = re.search(r'"notas":\s*\{[^}]*\}', saida)
    assert m, "o exemplo de saída não traz o objeto de notas"
    return m.group(0)


def test_prompt_pede_notas_sem_numero_copiavel_e_com_cta_discipline():
    prompt = revisao.montar_prompt_do_revisor(_doc(), _ctx())
    exemplo = _exemplo_de_notas(prompt)
    for c in EDITORIAIS:
        assert f'"{c}"' in exemplo, c
    assert "<0-10>" in exemplo
    assert not re.search(r"\d", exemplo.replace("<0-10>", "")), exemplo
    assert "0 a 10" in prompt
    assert '"useful_delivery": 0' not in prompt


def test_prompt_de_pagina_sem_contrato_editorial_pede_o_conjunto_do_papel():
    ctx = _ctx(pagina={"numero": 1, "slug": "guia", "papel": "LP", "h1": "Guia",
                       "editorial": False})
    exemplo = _exemplo_de_notas(revisao.montar_prompt_do_revisor(_doc(), ctx))
    assert '"single_destination"' in exemplo and '"cta_discipline"' in exemplo
    assert '"useful_delivery"' not in exemplo
    assert not re.search(r"\d", exemplo.replace("<0-10>", ""))


# ---------------------------------------------------------------------------
# recibo, publish e revisão avulsa herdam a trava
# ---------------------------------------------------------------------------

def test_no_fluxo_notas_do_canario_nao_geram_recibo_nem_publicam(tmp_path, monkeypatch):
    from tests.cenario_editorial import arquitetura_base
    from tests.cenario_revisor import chamadas_do_revisor, responder_fluxo, rodar_fluxo
    slug3 = "quem-tem-direito-tarifa-social-p1"
    responder = responder_fluxo(revisores={3: lambda _p: _resp(notas=CANARIO)})
    state, _deps, llm, wp = rodar_fluxo(tmp_path, monkeypatch, arquitetura_base(editorial=True),
                                        responder=responder)
    assert state.revisoes[3]["decisao"] == "revisao_humana"
    assert f"{MOTIVO}:compliance=0" in state.revisoes[3]["motivos"]
    assert 3 not in state.recibos
    problema = conferir_recibo(state, 3)
    assert problema is not None and problema.code == "recibo_ausente"
    assert slug3 not in wp.posts                             # nada publicado
    assert state.step_status["blocked_p3"].status.value == "FAILED"
    assert "como-pedir-tarifa-social-p2" in wp.posts  # as outras seguem
    # página com contrato editorial: o prompt pede o conjunto editorial
    exemplo = _exemplo_de_notas(chamadas_do_revisor(llm, 3)[0])
    assert '"cta_discipline"' in exemplo and '"useful_delivery"' in exemplo


def test_no_fluxo_sem_contrato_editorial_o_revisor_pede_o_conjunto_do_papel(
        tmp_path, monkeypatch):
    from tests.cenario_editorial import arquitetura_base
    from tests.cenario_revisor import chamadas_do_revisor, responder_fluxo, rodar_fluxo
    state, _deps, llm, wp = rodar_fluxo(tmp_path, monkeypatch, arquitetura_base(editorial=False),
                                        responder=responder_fluxo())
    solucao = _exemplo_de_notas(chamadas_do_revisor(llm, 3)[0])
    assert '"compliance"' in solucao and '"cta_discipline"' in solucao
    assert '"useful_delivery"' not in solucao and '"single_destination"' not in solucao
    lp = _exemplo_de_notas(chamadas_do_revisor(llm, 1)[0])
    assert '"single_destination"' in lp


def _revisar_avulso(tmp_path: Path, resposta: str) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conteudo = tmp_path / "post.html"
    conteudo.write_text(_doc().corpo, encoding="utf-8")
    briefing = tmp_path / "briefing.json"
    briefing.write_text(json.dumps({"versao": "briefing-v1"}), encoding="utf-8")
    runner = Runner(llm=FakeLLM(responses=[resposta]), max_retries=0,
                    runs_dir=tmp_path / "runs", sleep=lambda _s: None)
    saida = tmp_path / "saida"
    res = revisao_avulsa.revisar_arquivo(conteudo, briefing, None, saida, runner=runner,
                                         cfg=CFG, hoje=date(2026, 9, 30))
    res["registro"] = json.loads((saida / "revisao.json").read_text(encoding="utf-8"))
    return res


def test_revisao_avulsa_herda_a_trava(tmp_path):
    res = _revisar_avulso(tmp_path, _resp(notas=CANARIO))
    assert res["decisao"] == "revisao_humana"
    assert f"{MOTIVO}:cta_discipline=ausente" in res["registro"]["motivos"]
    # a avulsa não sabe se a página é editorial: vale o conjunto mais estrito
    ok = _revisar_avulso(tmp_path / "ok", _resp(notas=dict(BOAS, single_destination=8)))
    assert ok["decisao"] == "aprovado", ok["registro"]["motivos"]


def test_executar_revisao_sem_papel_usa_o_conjunto_mais_estrito(tmp_path):
    llm = FakeLLM(responses=[_resp(notas=CANARIO)])
    runner = Runner(llm=llm, max_retries=0, runs_dir=tmp_path / "runs", sleep=lambda _s: None)
    r = executar_revisao(_doc(), _ctx(pagina={"numero": 3}), runner=runner, cfg=CFG,
                         run_id="run-teste-20260930-120000", numero=3)
    assert r.decisao == "revisao_humana"
    assert f"{MOTIVO}:cta_discipline=ausente" in r.registro["motivos"]
    assert f"{MOTIVO}:single_destination=ausente" in r.registro["motivos"]
