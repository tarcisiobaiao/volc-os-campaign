"""S2 · integração operacional do editorial v2 (30/09/2026), itens 2, 3 e 7.

- **item 2:** a rota de disparo aceita `editorial_v2`, GRAVA na linha do run e
  o transmite ao perfil que o motor lê. Desligado, o disparo é o de sempre;
- **item 3:** `contexto_de_busca` e `contexto_de_anuncio` sempre chegam à
  arquitetura do run, em estado do contrato. Sem campanha: `ausente` COM motivo;
- **item 7:** a publicação avulsa lê o card em `pautador_entity_opportunities`
  (a tabela que tem `entity_id` e `funnel_architecture`), não na antiga;
- **ponta a ponta:** o worker de verdade escreve o perfil e a arquitetura, o
  processo do motor é disparado com o ambiente de verdade, e o código do MOTOR
  (venv dele) lê `run.editorial_v2 = True` e os dois contextos no inventário.

O Supabase é FALSO e imita a projeção do PostgREST (coluna não pedida não
volta). Nada fala com rede: o leitor do Google Ads é um dublê.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
from pydantic import ValidationError

from app.redator import contexto as ctx
from app.routers import publicacao
from app.seguranca import cifrar, gerar_chave

SENHA = "abcd EFGH ijkl MNOP qrst UVWX"

ARQUITETURA = {
    "funnel_strategy": {"avatar_summary": "Quem busca curso gratuito", "tone_voice": "direto",
                        "total_pages": 2},
    "pages": [{"position": 1, "page_title": "Cursos Senac"},
              {"position": 2, "page_title": "Por onde começar"}],
    "writing_jobs": [
        {"job_id": "write_p1", "writer_briefing": {
            "page_num": 1, "headline": "Cursos Senac", "current_url": "cursos-senac",
            "keywords": "cursos senac", "cta_text": "Ver cursos gratuitos",
            "cta_link": "/por-onde-comecar"}},
        {"job_id": "write_p2", "writer_briefing": {
            "page_num": 2, "headline": "Por onde começar", "current_url": "por-onde-comecar",
            "keywords": ["senac por estado"], "cta_text": "Ver como achar a turma",
            "cta_link": "/inicio"}},
    ],
}

CAMPANHA = {"campaign_id": "24278665189", "customer_id": "123-456-7890",
            "canal": "SEARCH", "presenca": "presente", "nome": "Senac Search"}

LINHAS_TERMOS = [
    {"search_term_view": {"search_term": "cursos senac gratuitos"}, "segments": {"date": "2026-09-20"},
     "metrics": {"impressions": "120", "clicks": "14", "cost_micros": "5000000"}},
    {"search_term_view": {"search_term": "senac inscrição"}, "segments": {"date": "2026-09-21"},
     "metrics": {"impressions": "80", "clicks": "6"}},
]
LINHAS_RSA = [
    {"ad_group_ad": {"status": "ENABLED", "ad": {"id": "1", "responsive_search_ad": {
        "headlines": [{"text": "Cursos Senac Gratuitos"}, {"text": "Veja Como Se Inscrever"}],
        "descriptions": [{"text": "Entenda quem tem direito e onde consultar as turmas."}]}}}},
    {"ad_group_ad": {"status": "PAUSED", "ad": {"id": "2", "responsive_search_ad": {
        "headlines": [{"text": "Texto pausado não conta"}]}}}},
]


def _leitor(consultas: List[str]):
    """Dublê de `(customer_id, gaql) -> linhas`: responde por tipo de GAQL."""
    def consultar(customer_id: str, gaql: str):
        consultas.append(gaql)
        assert gaql.lstrip().upper().startswith("SELECT")
        assert customer_id == "1234567890"
        return LINHAS_TERMOS if "search_term_view" in gaql else LINHAS_RSA
    return consultar


class _SupaFalso:
    enabled = True

    def __init__(self, *, card: Dict[str, Any], campanhas: List[Dict[str, Any]] | None = None,
                 run_linha: Dict[str, Any] | None = None, insert_falha: bool = False) -> None:
        self.card = card
        self.campanhas = campanhas or []
        self.run_linha = run_linha
        self.insert_falha = insert_falha
        self.selects: List[tuple] = []
        self.inserts: List[tuple] = []
        self.patches: List[tuple] = []

    @staticmethod
    def _projetar(linha: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        campos = params.get("select")
        if campos and campos != "*":
            pedidos = {c.strip() for c in campos.split(",")}
            return {k: v for k, v in linha.items() if k in pedidos}
        return dict(linha)

    async def select(self, tabela: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.selects.append((tabela, dict(params)))
        if tabela == "pautador_entity_opportunities":
            return [self._projetar(self.card, params)]
        if tabela == "pautador_opportunities":
            # A tabela ANTIGA: existe, mas não tem `entity_id` nem `funnel_architecture`.
            return [{"id": self.card["id"], "keyword": "cursos senac", "status": "funnel"}]
        if tabela == publicacao.TABELA:
            return [{"project_id": 9, "wp_url": "https://creditoup.com.br/",
                     "wp_username": "redator-volc", "wp_app_password_enc": cifrar(SENHA),
                     "post_type": "rec", "lp_post_type": "r", "conexao_ok": True}]
        if tabela == publicacao.TABELA_RUNS:
            if "status" in params:            # "já tem run andando?"
                return []
            return [self.run_linha] if self.run_linha else []
        if tabela == "pautador_entities":
            return [{"id": 501, "canonical_name": "Senac", "aliases": ["senac cursos"],
                     "official_source": "Senac"}]
        if tabela == ctx.VIEW_CAMPANHAS:
            return [self._projetar(c, params) for c in self.campanhas]
        return []

    async def insert(self, tabela: str, linhas: List[Dict[str, Any]]):
        self.inserts.append((tabela, linhas))
        if self.insert_falha:
            req = httpx.Request("POST", "http://x/rest/v1/pautador_funnel_runs")
            raise httpx.HTTPStatusError(
                "400", request=req, response=httpx.Response(400, request=req))
        return [{"id": 77, **linhas[0]}]

    async def patch(self, tabela: str, match: Dict[str, Any], valores: Dict[str, Any]):
        self.patches.append((tabela, match, valores))
        return []


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setenv("VOLC_SEGREDO_KEY", gerar_chave())


def _card(**over) -> Dict[str, Any]:
    card = {"id": 42, "status": "funnel", "entity_id": 501, "funnel_architecture": ARQUITETURA}
    card.update(over)
    return card


def _disparar(monkeypatch, supa: _SupaFalso, *, leitor=None, pasta_termos=None,
              **corpo) -> Dict[str, Any]:
    from app.redator import worker as w

    recebido: Dict[str, Any] = {}

    def executar_falso(**kwargs):
        recebido.update(kwargs)
        return asyncio.sleep(0)

    monkeypatch.setattr(publicacao, "_supa", lambda: supa)
    monkeypatch.setattr(w, "executar", executar_falso)
    monkeypatch.setattr(ctx, "leitor_google_ads", lambda: leitor)
    if pasta_termos is None:
        monkeypatch.delenv(ctx.ENV_PASTA_TERMOS, raising=False)
    else:
        monkeypatch.setenv(ctx.ENV_PASTA_TERMOS, str(pasta_termos))

    async def _rodar():
        saida = await publicacao.disparar_redator(
            publicacao.DispararEntrada(opportunity_id=42, project_id=9, **corpo))
        await asyncio.sleep(0)
        return saida

    recebido["_saida"] = asyncio.run(_rodar())
    return recebido


def _linha_inserida(supa: _SupaFalso) -> Dict[str, Any]:
    tabela, linhas = supa.inserts[0]
    assert tabela == publicacao.TABELA_RUNS
    return linhas[0]


# ── item 2 · a flag ─────────────────────────────────────────────────────────

def test_desligado_o_disparo_e_o_de_sempre(monkeypatch, com_chave):
    supa = _SupaFalso(card=_card())
    recebido = _disparar(monkeypatch, supa)
    assert "editorial_v2" not in _linha_inserida(supa)
    assert "editorial_v2" not in recebido["perfil"]
    assert recebido["_saida"].run.editorial_v2 is False


def test_ligado_grava_na_linha_e_chega_ao_perfil_do_motor(monkeypatch, com_chave):
    supa = _SupaFalso(card=_card())
    recebido = _disparar(monkeypatch, supa, editorial_v2=True)
    assert _linha_inserida(supa)["editorial_v2"] is True
    assert recebido["perfil"]["editorial_v2"] is True
    assert recebido["_saida"].run.editorial_v2 is True


def test_texto_true_nao_liga_o_fluxo():
    with pytest.raises(ValidationError):
        publicacao.DispararEntrada(opportunity_id=42, project_id=9, editorial_v2="true")


def test_banco_sem_a_coluna_recusa_v2_com_409_e_o_motivo(monkeypatch, com_chave):
    supa = _SupaFalso(card=_card(), insert_falha=True)
    with pytest.raises(publicacao.HTTPException) as exc:
        _disparar(monkeypatch, supa, editorial_v2=True)
    assert exc.value.status_code == 409
    assert "06_run_editorial_v2.sql" in exc.value.detail


def test_banco_sem_a_coluna_nao_muda_o_erro_do_disparo_de_sempre(monkeypatch, com_chave):
    supa = _SupaFalso(card=_card(), insert_falha=True)
    with pytest.raises(httpx.HTTPStatusError):
        _disparar(monkeypatch, supa)


def test_lista_de_runs_expoe_a_flag():
    assert publicacao._run_para_saida({"id": 1, "opportunity_id": 2, "project_id": 3,
                                       "editorial_v2": True}).editorial_v2 is True
    assert publicacao._run_para_saida({"id": 1, "opportunity_id": 2,
                                       "project_id": 3}).editorial_v2 is False


# ── item 3 · contextos ──────────────────────────────────────────────────────

def test_sem_campanha_os_dois_contextos_vao_ausentes_com_motivo(monkeypatch, com_chave):
    consultas: List[str] = []
    supa = _SupaFalso(card=_card())
    recebido = _disparar(monkeypatch, supa, leitor=_leitor(consultas))
    arq = recebido["arquitetura"]
    assert arq["contexto_de_busca"]["estado"] == "ausente"
    assert arq["contexto_de_busca"]["termos"] == []
    assert "campanha Search" in arq["contexto_de_busca"]["motivo_ausencia"]
    assert arq["contexto_de_anuncio"]["estado"] == "ausente"
    assert arq["contexto_de_anuncio"]["motivo_ausencia"]
    assert consultas == []                      # funil novo não chama o Google
    # o resto da arquitetura do card viaja intacto, e o card não é mutado
    assert arq["funnel_strategy"] == ARQUITETURA["funnel_strategy"]
    assert "contexto_de_busca" not in ARQUITETURA


def test_com_campanha_termos_e_rsa_ativa_chegam_presentes(monkeypatch, com_chave):
    consultas: List[str] = []
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    recebido = _disparar(monkeypatch, supa, leitor=_leitor(consultas))
    busca = recebido["arquitetura"]["contexto_de_busca"]
    anuncio = recebido["arquitetura"]["contexto_de_anuncio"]
    assert busca["estado"] == "presente" and busca["fonte"] == "search_term_view"
    assert [t["termo"] for t in busca["termos"]] == ["cursos senac gratuitos", "senac inscrição"]
    assert anuncio["estado"] == "presente"
    assert anuncio["titulos"] == ["Cursos Senac Gratuitos", "Veja Como Se Inscrever"]
    assert "Texto pausado não conta" not in anuncio["titulos"]
    assert len(consultas) == 2


def test_campanha_sem_leitor_e_ausencia_dita(monkeypatch, com_chave):
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    arq = _disparar(monkeypatch, supa, leitor=None)["arquitetura"]
    for chave in ("contexto_de_busca", "contexto_de_anuncio"):
        assert arq[chave]["estado"] == "ausente"
        assert "leitor do Google Ads" in arq[chave]["motivo_ausencia"]


def test_leitor_que_explode_vira_ausente_sem_derrubar_o_disparo(monkeypatch, com_chave):
    def explode(_cid, _gaql):
        raise RuntimeError("token=segredo")
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    arq = _disparar(monkeypatch, supa, leitor=explode)["arquitetura"]
    assert arq["contexto_de_busca"]["estado"] == "ausente"
    assert arq["contexto_de_anuncio"]["estado"] == "ausente"
    assert "segredo" not in json.dumps(arq)     # só a classe do erro, nunca a mensagem


def test_duas_campanhas_search_e_ambiguidade_dita():
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA, {**CAMPANHA, "campaign_id": "999"}])
    r = asyncio.run(ctx.contextos_do_funil(supa, 42, fabricar_leitor=lambda: None))
    assert "2 campanhas Search" in r["contexto_de_busca"]["motivo_ausencia"]


def test_export_do_integrador_vence_e_leva_o_sha256(tmp_path):
    (tmp_path / "24278665189.json").write_text(json.dumps(LINHAS_TERMOS), encoding="utf-8")
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    from datetime import date
    r = asyncio.run(ctx.contextos_do_funil(supa, 42, fabricar_leitor=lambda: None,
                                           pasta_termos=str(tmp_path), hoje=date(2026, 9, 30)))
    assert r["contexto_de_busca"]["estado"] == "presente"
    assert r["contexto_de_busca"]["fonte"].startswith("arquivo:")
    assert r["contexto_de_anuncio"]["estado"] == "ausente"


def test_ausencia_de_agora_nao_apaga_o_que_o_card_ja_trazia():
    do_card = {"estado": "presente", "titulos": ["T"], "descricoes": [], "fonte": "x"}
    arq = ctx.anexar_contextos({"pages": [{}], "contexto_de_anuncio": do_card},
                               {"contexto_de_anuncio": ctx.anuncio_ausente("sem campanha"),
                                "contexto_de_busca": ctx.busca_ausente("sem campanha")})
    assert arq["contexto_de_anuncio"] == do_card
    assert arq["contexto_de_busca"]["estado"] == "ausente"


# ── S4 · revisão adversarial: o contexto nunca derruba o disparo, e o export
#    que não cobre a janela não vira "0 termos" ───────────────────────────────
#
# Os contextos são lidos DEPOIS do INSERT do run. Uma exceção ali devolvia 500
# e deixava a linha `queued` para sempre — e o card passava a responder "Já
# existe uma execução na fila" a todo disparo seguinte. E um export do
# integrador sem nenhuma linha na janela de hoje saía `vazio_confirmado`
# ("consulta feita: 0 termos") e ainda vencia a API: ausência virando dado.

_LINHA_FORA_DO_FORMATO = [{"segments": {"date": "2026-09-20"}, "search_term_view": "cursos senac"}]
_LINHA_DE_JULHO = [{"search_term_view": {"search_term": "cursos senac gratuitos"},
                    "segments": {"date": "2026-07-10"},
                    "metrics": {"impressions": "900", "clicks": "80"}}]


def test_export_fora_do_formato_nao_derruba_o_disparo_nem_prende_o_card(
        monkeypatch, com_chave, tmp_path):
    (tmp_path / "24278665189.json").write_text(json.dumps(_LINHA_FORA_DO_FORMATO),
                                               encoding="utf-8")
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    recebido = _disparar(monkeypatch, supa, leitor=None, pasta_termos=tmp_path)
    assert recebido["_saida"].run.status == "queued"          # o disparo seguiu
    assert not any(v.get("status") == "failed" for _t, _m, v in supa.patches)
    busca = recebido["arquitetura"]["contexto_de_busca"]
    assert busca["estado"] == "ausente"
    assert "AttributeError" in busca["motivo_ausencia"]


def test_export_sem_linha_na_janela_nao_vira_vazio_confirmado(tmp_path):
    from datetime import date
    (tmp_path / "24278665189.json").write_text(json.dumps(_LINHA_DE_JULHO), encoding="utf-8")
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    sem_api = asyncio.run(ctx.contextos_do_funil(
        supa, 42, fabricar_leitor=lambda: None, pasta_termos=str(tmp_path),
        hoje=date(2026, 9, 30)))["contexto_de_busca"]
    assert sem_api["estado"] == "ausente"
    assert "janela" in sem_api["motivo_ausencia"] and "24278665189.json" in sem_api["motivo_ausencia"]
    # com a API disponível, o export que não cobre a janela não a mascara
    consultas: List[str] = []
    com_api = asyncio.run(ctx.contextos_do_funil(
        supa, 42, fabricar_leitor=lambda: _leitor(consultas), pasta_termos=str(tmp_path),
        hoje=date(2026, 9, 30)))["contexto_de_busca"]
    assert com_api["estado"] == "presente" and com_api["fonte"] == "search_term_view"


def test_export_com_termos_na_janela_continua_vencendo(tmp_path):
    from datetime import date
    (tmp_path / "24278665189.json").write_text(json.dumps(LINHAS_TERMOS), encoding="utf-8")
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    r = asyncio.run(ctx.contextos_do_funil(
        supa, 42, fabricar_leitor=lambda: _leitor([]), pasta_termos=str(tmp_path),
        hoje=date(2026, 9, 30)))["contexto_de_busca"]
    assert r["estado"] == "presente" and r["fonte"].startswith("arquivo:")


def test_contextos_nunca_levantam(monkeypatch):
    def quebra(*_a, **_k):
        raise KeyError("token=segredo")
    monkeypatch.setattr(ctx, "_ler_google", quebra)
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    r = asyncio.run(ctx.contextos_do_funil(supa, 42, fabricar_leitor=lambda: _leitor([]),
                                           pasta_termos=""))
    for chave in ("contexto_de_busca", "contexto_de_anuncio"):
        assert r[chave]["estado"] == "ausente"
        assert "KeyError" in r[chave]["motivo_ausencia"]
    assert "segredo" not in json.dumps(r)


# ── item 7 · a tabela certa na publicação avulsa ────────────────────────────

def test_publicacao_avulsa_le_o_card_na_tabela_entity_first(monkeypatch, com_chave, tmp_path):
    from app.redator import worker as w

    supa = _SupaFalso(card=_card(), run_linha={
        "id": 5, "opportunity_id": 42, "project_id": 9, "status": "done",
        "run_id": "cursos-senac-20260930", "paginas_publicadas": [], "editorial_v2": True})
    recebido: Dict[str, Any] = {}

    async def publicar_falso(**kwargs):
        recebido.update(kwargs)
        return {"ok": True, "publicada": {"status_wp": "draft"}}

    monkeypatch.setattr(publicacao, "_supa", lambda: supa)
    monkeypatch.setattr(publicacao, "_pasta_do_run", lambda run: tmp_path)
    monkeypatch.setattr(w, "_ler_estado", lambda _d: {
        "step_status": {}, "drafts": {"2": {"content": "<p>x</p>"}}})
    monkeypatch.setattr(w, "publicar_pagina", publicar_falso)

    saida = asyncio.run(publicacao.publicar_pagina_do_run(5, 2))
    assert saida.ok is True
    tabelas = [t for t, _ in supa.selects]
    assert "pautador_opportunities" not in tabelas
    pedido = next(p for t, p in supa.selects if t == "pautador_entity_opportunities")
    assert {"entity_id", "funnel_architecture"} <= set(pedido["select"].split(","))
    perfil = recebido["perfil"]
    # a entidade foi lida (antes nunca era) e os termos do CARD chegaram
    assert perfil["tema"]["official_preference"] == ["Senac"]
    assert "cursos senac" in perfil["tema"]["termos"]
    # o run nasceu v2 e é retomado v2
    assert perfil["editorial_v2"] is True


# ── ponta a ponta · rota → worker → processo do motor → código do motor ─────

_MOTOR = Path(__file__).resolve().parents[2] / "funnelforge-migracao" / "engine"
_PY_MOTOR = _MOTOR / ".venv" / "bin" / "python"

_SHIM = '''#!{python}
"""Faz o papel do `funnelforge run-volc`: lê o que o worker entregou com o
código do MOTOR e para antes de qualquer LLM ou rede."""
import json, os, sys, tempfile
from pathlib import Path
from funnelforge.adapters.briefing_volc import carregar_arquitetura, plano_do_funnel_architecture
from funnelforge.config.perfil import aplicar_perfil
from funnelforge.config.settings import load_settings
from funnelforge.domain.models import RunState
from funnelforge.pipeline.inventario import montar_inventario
from funnelforge.pipeline.pipeline import editorial_v2_do_run

args = sys.argv[1:]
assert args[0] == "run-volc", args
arq, perfil = Path(args[1]), Path(args[args.index("--perfil") + 1])
vazio = Path(tempfile.mkdtemp()) / ".env"
vazio.write_text("", encoding="utf-8")
settings = aplicar_perfil(load_settings(vazio, Path("config.yaml")),
                          json.loads(perfil.read_text(encoding="utf-8")))
plano = plano_do_funnel_architecture(carregar_arquitetura(arq))
estado = RunState(run_id="s2", plan=plano)
inv = montar_inventario(estado, plano.pages[0])
Path(os.environ["S2_SAIDA"]).write_text(json.dumps({{
    "argv": args,
    "modo_perfil": oct(perfil.stat().st_mode & 0o777),
    "settings_editorial_v2": settings.run.editorial_v2,
    "editorial_v2_do_run": editorial_v2_do_run(estado, settings),
    "plano_busca": plano.contexto_de_busca.estado if plano.contexto_de_busca else None,
    "plano_anuncio": plano.contexto_de_anuncio.estado if plano.contexto_de_anuncio else None,
    "inv_termos": inv.termos_de_busca.model_dump(),
    "inv_anuncio": inv.anuncio.model_dump(),
}}), encoding="utf-8")
'''


@pytest.mark.skipif(not _PY_MOTOR.exists(), reason="venv do motor ausente neste checkout")
@pytest.mark.parametrize("ligado", [True, False])
def test_ponta_a_ponta_a_flag_e_os_contextos_chegam_ao_motor(monkeypatch, com_chave, tmp_path,
                                                             ligado):
    from app.redator import worker as w

    executar_de_verdade = w.executar          # `_disparar` troca o do módulo
    shim = tmp_path / "funnelforge"
    shim.write_text(_SHIM.format(python=_PY_MOTOR), encoding="utf-8")
    shim.chmod(0o700)
    saida_motor = tmp_path / "motor.json"
    monkeypatch.setenv("S2_SAIDA", str(saida_motor))
    monkeypatch.setattr(w, "_executavel", lambda: shim)

    # 1 · a rota, com Supabase falso e campanha vinculada (leitor dublê)
    consultas: List[str] = []
    supa = _SupaFalso(card=_card(), campanhas=[CAMPANHA])
    recebido = _disparar(monkeypatch, supa, leitor=_leitor(consultas),
                         **({"editorial_v2": True} if ligado else {}))

    # 2 · o worker DE VERDADE: grava perfil/arquitetura e dispara o processo
    asyncio.run(executar_de_verdade(supa=supa, run_row_id=77, arquitetura=recebido["arquitetura"],
                           perfil=recebido["perfil"], publicar=True))
    status = [v.get("status") for _t, _m, v in supa.patches if v.get("status")]
    assert status[-1] == "done", supa.patches[-1]

    # 3 · o que o CÓDIGO DO MOTOR leu
    m = json.loads(saida_motor.read_text(encoding="utf-8"))
    assert m["argv"][-1] == "--publish"          # sobe como rascunho (draft) — ver config.yaml
    assert m["modo_perfil"] == "0o600"           # a senha decifrada não fica legível
    assert m["settings_editorial_v2"] is ligado
    assert m["editorial_v2_do_run"] is ligado
    assert m["plano_busca"] == "presente" and m["plano_anuncio"] == "presente"
    assert m["inv_termos"]["estado"] == "presente"
    assert m["inv_termos"]["amostra"][:1] == ["cursos senac gratuitos"]
    assert m["inv_anuncio"]["estado"] == "presente"
    assert "Cursos Senac Gratuitos" in m["inv_anuncio"]["titulos"]
    # e a senha decifrada sumiu do disco
    assert not any(Path(a).exists() for a in m["argv"] if a.endswith("perfil.json"))
