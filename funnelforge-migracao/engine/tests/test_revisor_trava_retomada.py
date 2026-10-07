"""A trava das notas existenciais, segunda rodada: o que os céticos acharam.

1. RETOMADA: uma página aprovada ANTES da trava (notas {0,0,0} ou sem notas)
   não pode continuar liberada por um recibo antigo. No `resume`, a aprovação
   anterior é reconferida pelas notas GRAVADAS (sem nova chamada ao modelo) e
   `conferir_recibo` recusa recibo do revisor que não traz a marca da trava.
2. Página sem a informação "editorial" (revisão avulsa, contexto montado à
   mão) ou com valor que não é bool: vale o conjunto MAIS ESTRITO (a união do
   editorial com o do papel), nunca um conjunto mais frouxo que o V1.
3. Página editorial: exatamente o conjunto do V1, sem subtrair nada pelo papel,
   e a lista é UMA só (constante de `steps`, usada pelo juiz V1 e pelo revisor).
4. Nota fracionária (7.5) é recusada, como o V1 (o `Verdict` não aceita).
5. Marcador `<0-10>` copiado do exemplo não derruba a resposta inteira: os
   achados ficam, a nota vira ausente e a página vai à pessoa.
6. Ajuste retido SÓ pela trava: os patches seguem no lote para a pessoa.
"""
from __future__ import annotations

import inspect
import json
from datetime import date
from pathlib import Path

import pytest

from funnelforge.pipeline import revisao, revisao_avulsa, steps
from funnelforge.pipeline.revisao import conferir_recibo, documento_de, gerar_recibo
from funnelforge.pipeline.runner import Runner
from tests.fakes import FakeLLM
from tests.test_revisor_decisao import A_CTA, A_PROMESSA, CFG, P_PROMESSA, _ctx, _doc, _rodar

EDITORIAIS = ("compliance", "cta_discipline", "useful_delivery", "destination_relevance")
CANARIO = {"useful_delivery": 0, "destination_relevance": 0, "compliance": 0}
BOAS = {"compliance": 9, "cta_discipline": 8, "useful_delivery": 8, "destination_relevance": 8}
MOTIVO = "notas_existenciais_insuficientes"
SLUG3 = "quem-tem-direito-tarifa-social-p1"


def _resp(decisao="aprovado", notas=None, achados=(), patches=()) -> str:
    dados = {"versao": "revisao-v1", "decisao": decisao, "achados": list(achados),
             "patches": list(patches), "afirmacoes_nao_verificadas": [],
             "preservado": ["ângulo"]}
    if notas is not None:
        dados["notas"] = notas
    return json.dumps(dados, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 1. retomada de run aprovado antes da trava
# ---------------------------------------------------------------------------

def _como_o_codigo_antigo_gravou(state, n: int) -> None:
    """Deixa a revisão e o recibo da página exatamente como o código de antes da
    trava gravava: registro sem `notas_existenciais` e recibo sem a marca."""
    for rod in state.revisoes[n]["rodadas"]:
        rod.pop("notas_existenciais", None)
    doc = documento_de(state.drafts[n], state.seo.get(n))
    state.recibos[n] = {"decisao": "aprovado", "origem": "revisor", "sha256": doc.sha256(),
                        "politica": "revisao-v1", "criado_em": "2026-09-30T13:10:00"}


def _run_de_antes_da_trava(tmp_path, monkeypatch, notas_p3):
    from tests.cenario_editorial import arquitetura_base
    from tests.cenario_revisor import responder_fluxo, rodar_fluxo
    with monkeypatch.context() as m:
        m.setattr(revisao, "_notas_que_impedem", lambda rod: [])      # o código antigo
        responder = responder_fluxo(revisores={3: lambda _p: _resp(notas=notas_p3)})
        state, deps, llm, wp = rodar_fluxo(tmp_path, m, arquitetura_base(editorial=True),
                                           responder=responder, publish=False)
    assert state.revisoes[3]["decisao"] == "aprovado" and 3 in state.recibos
    _como_o_codigo_antigo_gravou(state, 3)
    assert SLUG3 not in wp.posts
    return state, deps, llm, wp


def test_retomada_de_aprovacao_antiga_com_notas_zero_nao_publica(tmp_path, monkeypatch):
    from tests.cenario_editorial import congelar_data
    from tests.cenario_revisor import chamadas_do_revisor, retomar
    state, deps, llm, wp = _run_de_antes_da_trava(tmp_path, monkeypatch, CANARIO)
    antes = len(chamadas_do_revisor(llm, 3))
    congelar_data(monkeypatch)
    state = retomar(state, deps, publish=True)
    assert len(chamadas_do_revisor(llm, 3)) == antes          # sem rolar o dado de novo
    rev = state.revisoes[3]
    assert rev["decisao"] == "revisao_humana"
    assert f"{MOTIVO}:compliance=0" in rev["motivos"]
    assert f"{MOTIVO}:cta_discipline=ausente" in rev["motivos"]
    assert rev["reconferencia_da_trava"]["decisao_anterior"] == "aprovado"
    assert 3 not in state.recibos
    assert conferir_recibo(state, 3).code == "recibo_ausente"
    assert SLUG3 not in wp.posts
    assert state.step_status["revisor_p3"].status.value == "FAILED"
    assert "como-pedir-tarifa-social-p2" in wp.posts           # as outras seguem


def test_retomada_de_aprovacao_antiga_com_notas_boas_renova_o_recibo(tmp_path, monkeypatch):
    """Controle: aprovação antiga com notas que passam na trava continua valendo
    (o recibo ganha a marca, sem nova chamada) e a página publica."""
    from tests.cenario_editorial import congelar_data
    from tests.cenario_revisor import chamadas_do_revisor, retomar
    state, deps, llm, wp = _run_de_antes_da_trava(tmp_path, monkeypatch, BOAS)
    antes = len(chamadas_do_revisor(llm, 3))
    congelar_data(monkeypatch)
    state = retomar(state, deps, publish=True)
    assert len(chamadas_do_revisor(llm, 3)) == antes
    assert state.revisoes[3]["decisao"] == "aprovado"
    assert state.recibos[3]["trava_de_notas"] == revisao.VERSAO_DA_TRAVA
    assert conferir_recibo(state, 3) is None
    assert SLUG3 in wp.posts


def test_retomada_so_da_pagina_tambem_reconfere(tmp_path, monkeypatch):
    from tests.cenario_editorial import congelar_data
    from tests.cenario_revisor import retomar
    state, deps, _llm, wp = _run_de_antes_da_trava(tmp_path, monkeypatch, CANARIO)
    congelar_data(monkeypatch)
    state = retomar(state, deps, publish=True, only="p3")
    assert state.revisoes[3]["decisao"] == "revisao_humana"
    assert SLUG3 not in wp.posts


class _Estado:
    def __init__(self, recibo):
        from funnelforge.domain.models import PageDraft
        doc = _doc()
        self.drafts = {3: PageDraft(page_number=3, page_type="SOLUTION", format="gutenberg", content=doc.corpo, word_count=10)}
        self.seo = {3: {"seotitle": doc.seotitle, "metadescription": doc.metadescription}}
        self.recibos = {3: recibo(doc)} if recibo else {}
        self.revisoes = {}


def test_conferir_recibo_recusa_recibo_do_revisor_sem_a_marca_da_trava():
    antigo = _Estado(lambda d: {"decisao": "aprovado", "origem": "revisor",
                                "sha256": d.sha256(), "politica": "revisao-v1"})
    problema = conferir_recibo(antigo, 3)
    assert problema is not None and problema.code == "recibo_sem_trava_de_notas"
    # recibo novo do revisor (com a marca) e recibo humano continuam valendo
    novo = _Estado(lambda d: gerar_recibo(d, "revisor",
                                          trava_de_notas=revisao.VERSAO_DA_TRAVA))
    assert conferir_recibo(novo, 3) is None
    humano = _Estado(lambda d: gerar_recibo(d, "humano", quem="operador"))
    assert conferir_recibo(humano, 3) is None


# ---------------------------------------------------------------------------
# 2 e 3. o conjunto exigido
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pagina", [
    {"papel": "LP", "slug": "guia-x"},
    {"papel": "LP", "slug": "guia-x", "editorial": "false"},
    {"papel": "LP", "slug": "guia-x", "editorial": 0},
    {"papel": "LP", "slug": "guia-x", "editorial": None},
    {},
    {"numero": 1, "slug": "", "papel": "", "h1": ""},          # o que a avulsa monta
], ids=["sem_chave", "texto_false", "zero", "none", "vazia", "avulsa"])
def test_sem_informacao_editorial_vale_o_conjunto_mais_estrito(pagina):
    exigidos = set(revisao.criterios_existenciais(pagina))
    assert exigidos == set(EDITORIAIS) | {"single_destination"}, exigidos


def test_lp_avulsa_com_single_destination_zero_nao_aprova(tmp_path):
    notas = dict(BOAS, single_destination=0)
    ctx = _ctx(pagina={"numero": 1, "slug": "guia-x", "papel": "LP", "h1": "x"})
    r, _ = _rodar([_resp(notas=notas)], tmp_path, ctx=ctx)
    assert r.decisao == "revisao_humana"
    assert f"{MOTIVO}:single_destination=0" in r.registro["motivos"]


def test_solucao_sem_informacao_editorial_nao_exige_o_que_o_papel_dispensa():
    """A união não inventa critério: SOLUTION não tem single_destination nem no V1."""
    assert set(revisao.criterios_existenciais({"papel": "SOLUTION"})) == set(EDITORIAIS)


def test_pagina_editorial_usa_exatamente_o_conjunto_do_v1(monkeypatch):
    """O V1 editorial não subtrai nada pelo papel; o revisor também não."""
    monkeypatch.setattr(steps, "_existential_criteria_for", lambda role: ("compliance",))
    for papel in ("SOLUTION", "PRESELL", "LP"):
        assert tuple(revisao.criterios_existenciais(
            {"papel": papel, "editorial": True})) == steps.EDITORIAL_EXISTENTIAL_CRITERIA


def test_a_lista_editorial_e_uma_so(monkeypatch):
    assert steps.EDITORIAL_EXISTENTIAL_CRITERIA == EDITORIAIS
    assert not hasattr(revisao, "CRITERIOS_EXISTENCIAIS_EDITORIAIS")
    assert "EDITORIAL_EXISTENTIAL_CRITERIA" in inspect.getsource(steps._judge_page)
    literal = '"useful_delivery", "destination_relevance"'
    fonte_steps = inspect.getsource(steps)
    assert fonte_steps.count(literal) == 1                     # só na constante
    assert literal not in inspect.getsource(revisao)
    monkeypatch.setattr(steps, "EDITORIAL_EXISTENTIAL_CRITERIA", ("compliance", "x_novo"))
    assert revisao.criterios_existenciais({"papel": "SOLUTION", "editorial": True}) == (
        "compliance", "x_novo")


# ---------------------------------------------------------------------------
# 4. nota fracionária
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("valor", [7.5, 6.9999, 9.5])
def test_nota_fracionaria_nao_aprova(tmp_path, valor):
    r, _ = _rodar([_resp(notas=dict(BOAS, compliance=valor))], tmp_path)
    assert r.decisao == "revisao_humana"
    assert f"{MOTIVO}:compliance={valor}" in r.registro["motivos"]


def test_nota_inteira_escrita_como_decimal_aprova(tmp_path):
    """7.0 é inteiro: o V1 aceita (vira 7) e o revisor também."""
    r, _ = _rodar([_resp(notas=dict(BOAS, compliance=7.0))], tmp_path)
    assert r.decisao == "aprovado", r.registro["motivos"]


# ---------------------------------------------------------------------------
# 5. marcador copiado do exemplo
# ---------------------------------------------------------------------------

def test_marcador_copiado_preserva_os_achados_e_vai_para_humano(tmp_path):
    corpo = _resp(achados=[dict(A_PROMESSA, severidade="nota")], notas=BOAS)
    copiado = corpo.replace('"compliance": 9', '"compliance": <0-10>').replace(
        '"cta_discipline": 8', '"cta_discipline":<0-10>')
    assert "<0-10>" in copiado
    r, _ = _rodar([copiado], tmp_path)
    assert r.decisao == "revisao_humana"
    assert "json_ilegivel" not in r.registro["motivos"]
    assert f"{MOTIVO}:compliance=null" in r.registro["motivos"]
    assert f"{MOTIVO}:cta_discipline=null" in r.registro["motivos"]
    rod = r.registro["rodadas"][0]
    assert [a["id"] for a in rod["achados"]] == ["a1"]
    assert rod["marcador_de_nota_copiado"] is True


def test_marcador_so_e_trocado_no_lugar_de_valor(tmp_path):
    """Resposta ilegível por outro motivo continua json_ilegivel."""
    r, _ = _rodar(['{"decisao": "aprovado", "notas": {"compliance": <0-10>}, quebrado'],
                  tmp_path)
    assert r.decisao == "revisao_humana" and "json_ilegivel" in r.registro["motivos"]


# ---------------------------------------------------------------------------
# 6. ajuste retido só pela trava
# ---------------------------------------------------------------------------

def _revisar_avulso(tmp_path: Path, resposta: str) -> tuple[dict, dict, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    conteudo = tmp_path / "post.html"
    conteudo.write_text(_doc().corpo, encoding="utf-8")
    briefing = tmp_path / "briefing.json"
    briefing.write_text(json.dumps({"versao": "briefing-v1"}), encoding="utf-8")
    contexto = tmp_path / "contexto.json"
    contexto.write_text(json.dumps({"pagina": {"numero": 3, "slug": "x-p1",
                                               "papel": "SOLUTION"}}), encoding="utf-8")
    runner = Runner(llm=FakeLLM(responses=[resposta]), max_retries=0,
                    runs_dir=tmp_path / "runs", sleep=lambda _s: None)
    saida = tmp_path / "saida"
    revisao_avulsa.revisar_arquivo(conteudo, briefing, contexto, saida, runner=runner,
                                   cfg=CFG, hoje=date(2026, 9, 30))
    return (json.loads((saida / "revisao.json").read_text(encoding="utf-8")),
            json.loads((saida / "patches.json").read_text(encoding="utf-8")),
            (saida / "conteudo_revisado.html").read_text(encoding="utf-8"))


def test_ajuste_retido_so_pela_trava_leva_os_patches_para_a_pessoa(tmp_path):
    """Notas coerentes com o bloqueante (compliance 4 no texto de antes): vai à
    pessoa com o texto original, mas o patch corretivo segue no lote."""
    registro, lote, revisado = _revisar_avulso(
        tmp_path, _resp("ajustar", dict(BOAS, compliance=4), [A_PROMESSA], [P_PROMESSA]))
    assert registro["decisao"] == lote["decisao"] == "revisao_humana"
    assert f"{MOTIVO}:compliance=4" in registro["motivos"]
    assert revisado == _doc().corpo                                 # texto intacto
    rod = registro["rodadas"][0]
    assert rod["retida_pela_trava_de_notas"] is True and not rod.get("mantida")
    assert [(p["achado"], p["estado"]) for p in lote["patches"]] == [
        ("a1", "proposto_para_decisao_humana")]


def test_ajuste_retido_por_outro_motivo_nao_vira_proposta(tmp_path):
    """Se sobrou bloqueante sem patch, o lote não vira proposta de correção."""
    registro, lote, _ = _revisar_avulso(
        tmp_path, _resp("ajustar", dict(BOAS, compliance=4), [A_PROMESSA, A_CTA],
                        [P_PROMESSA]))
    assert registro["decisao"] == "revisao_humana"
    assert "bloqueante_nao_resolvido:a2" in registro["motivos"]
    assert not registro["rodadas"][0].get("retida_pela_trava_de_notas")
    assert lote["patches"] == []
