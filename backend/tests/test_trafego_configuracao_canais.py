"""Contrato GADS-CRIACAO-CANAIS-v1 — a configuração de cada canal na fronteira HTTP.

O que estes testes amarram:

  * a FORMA é julgada pelo dataclass do motor, e a recusa é 422 com o `loc`
    exato do campo (chave desconhecida, tipo errado, combinação impossível);
  * configuração de outro canal é 422 — nunca descartada em silêncio;
  * cada configuração CHEGA ao builder: Search/Display como opção de
    `preparar()`, Demand Gen/PMax dentro do brief (V25);
  * a correspondência por keyword escolhida na tela chega ao critério, só
    sobre keyword aprovada;
  * sem configuração, a impressão do plano é a de antes (selo idêntico);
  * o esquema publicado sai dos mesmos dataclasses.

Nenhum teste fala com o Google nem com o Supabase.
"""
from __future__ import annotations

import base64
import hashlib
import io
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.routers import trafego
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario
from app.trafego import configuracao_canais as cfgcan
from app.trafego import contrato_canais as ccan
from app.trafego import releitura_por_canal as rel
from app.trafego.veredito_de_releitura import EstadoDaReleitura
from volc_ads import pautador_ponte
from volc_ads.campanha import demand_gen_config as dgc
from volc_ads.campanha import display_config as dc
from volc_ads.campanha import pmax_config as pc
from volc_ads.campanha import search_config as sc
from volc_ads.campanha.brief import Copy
from volc_ads.campanha.criterio import Criterio

CID, MCC = "5478096539", "6016739364"
URL = "https://creditoup.com.br/r/guia-cursos-senac/"


# ── infraestrutura hermética ────────────────────────────────────────────────


@pytest.fixture
def cliente(monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(trafego.router)
    eu = Identidade(sub="u1", email="op@volc", papel="ADMIN", origem="sessao")
    app.dependency_overrides[exigir_usuario] = lambda: eu
    app.dependency_overrides[exigir_admin] = lambda: eu
    # A recusa de forma acontece ANTES do escopo e de qualquer rede.
    monkeypatch.setattr(trafego, "_no_escopo", lambda *_: pytest.fail(
        "a configuração inválida passou da validação de forma"))
    monkeypatch.setattr(trafego.cap, "servidor_oferece_demand_gen_validate_only", lambda: True)
    monkeypatch.setattr(trafego.cap, "servidor_oferece_pmax_validate_only", lambda: True)
    return TestClient(app)


class _OcrHermetico:
    nome = "ocr_hermetico_cfg"
    versao = "1"
    capacidades = ("texto_na_imagem", "marca_visual")

    def inspecionar(self, bytes_da_peca, *, mime):
        from app.criativo.politica import inspecao as insp

        return insp.LeituraDePixel()


@pytest.fixture
def com_inspecao_de_pixel(monkeypatch):
    from app.criativo.politica import inspecao as insp

    monkeypatch.setenv("CRIATIVO_URL_SECRET", "teste-hermetico-da-configuracao")
    insp.limpar_detectores_de_pixel()
    insp.registrar_detector_de_pixel(_OcrHermetico())
    yield
    insp.limpar_detectores_de_pixel()


def _png(w: int, h: int, semente: int) -> bytes:
    im = Image.new("RGB", (w, h), (semente * 40 % 255, 120, 200 - semente * 13 % 200))
    for x in range(w // 4, w // 2):
        im.putpixel((x, h // 2), (255, 255, 255))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


_DIM = {"imagem_marketing": (600, 314), "imagem_marketing_quadrada": (300, 300),
        "imagem_marketing_retrato": (480, 600), "logo_quadrado": (144, 144),
        "logo_paisagem": (512, 128)}


def _envelope(tipo: str, nome: str, semente: int) -> dict:
    dados = _png(*_DIM[tipo], semente)
    return {
        "tipo": tipo, "nome": nome,
        "dados_base64": base64.b64encode(dados).decode(),
        "conteudo_hash": "sha256:" + hashlib.sha256(dados).hexdigest(),
        "origem": "gerado",
        "procedencia": {"motor": "fixture", "versao_do_motor": "1",
                        "insumo": f"gerar {nome}", "quando": "2026-10-08T12:00:00+00:00"},
    }


def _search(**extra) -> dict:
    return {"opportunity_id": 1, "customer_id": CID, "login_customer_id": MCC,
            "canal": "SEARCH", **extra}


def _display(**extra) -> dict:
    return {"opportunity_id": 1, "customer_id": CID, "login_customer_id": MCC,
            "canal": "DISPLAY", "estrategia_lance": "MAXIMIZE_CONVERSIONS", **extra}


def _dg(**extra) -> dict:
    return {"opportunity_id": 1, "customer_id": CID, "login_customer_id": MCC,
            "canal": "DEMAND_GEN", "estrategia_lance": "MAXIMIZE_CONVERSIONS",
            "demand_gen": {"upgraded_targeting": False, "controles_de_canal": None,
                           "audiencias": [], "intencoes": [], "exclusoes_de_audiencia": []},
            "assets_demand_gen": [], **extra}


def _pmax(**extra) -> dict:
    return {"opportunity_id": 1, "customer_id": CID, "login_customer_id": MCC,
            "canal": "PERFORMANCE_MAX", "estrategia_lance": "MAXIMIZE_CONVERSIONS",
            "pmax": {"brand_guidelines_enabled": False}, "assets_pmax": [], **extra}


# ═══════════════════════════════════════════════════════════════════════════
# 422 — forma, chave desconhecida, canal errado
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("payload, loc", [
    (_search(configuracao_search={"lance": {"estrategia": "MANUAL_CPC", "teto": 1}}),
     ["body", "configuracao_search", "lance", "teto"]),
    (_display(configuracao_display={"exclusoes": {"placement": ["x.com"]}}),
     ["body", "configuracao_display", "exclusoes", "placement"]),
    (_dg(configuracao_demand_gen={"video": {"youtube_ids": ["M7lc1UVf-VE"], "cta": "LEARN_MORE"}}),
     ["body", "configuracao_demand_gen", "video", "cta"]),
    (_pmax(configuracao_pmax={"negativas_tipadas": [{"texto": "x", "match": "EXACT"}]}),
     ["body", "configuracao_pmax", "negativas_tipadas", 0, "match"]),
])
def test_chave_desconhecida_e_422_com_o_caminho_do_campo(cliente, payload, loc):
    r = cliente.post("/api/trafego/provar", json=payload)
    assert r.status_code == 422, r.text
    erro = r.json()["detail"][0]
    assert erro["loc"] == loc
    assert "desconhecido" in erro["msg"]
    assert erro["ctx"]["codigo"] == cfgcan.CONFIGURACAO_INVALIDA


@pytest.mark.parametrize("payload, loc", [
    (_search(configuracao_search={"rede": {"google_search": True, "parceiros": 0,
                                           "display_expansion": False}}),
     ["body", "configuracao_search", "rede", "parceiros"]),
    (_display(configuracao_display={"frequencia": [{"impressoes": "3"}]}),
     ["body", "configuracao_display", "frequencia", 0, "impressoes"]),
    (_dg(configuracao_demand_gen={"formato": "VIDEO_RESPONSIVO"}),
     ["body", "configuracao_demand_gen"]),
])
def test_tipo_errado_ou_combinacao_impossivel_e_422(cliente, payload, loc):
    r = cliente.post("/api/trafego/provar", json=payload)
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"] == loc


@pytest.mark.parametrize("payload", [
    _search(configuracao_display={}),
    _display(configuracao_search={"lance": {"estrategia": "MANUAL_CPC"}}),
    _dg(configuracao_pmax={}),
    _pmax(configuracao_demand_gen={}),
])
def test_configuracao_de_outro_canal_e_422(cliente, payload):
    r = cliente.post("/api/trafego/provar", json=payload)
    assert r.status_code == 422, r.text
    assert "configuração de" in r.text and "canal" in r.text


def test_subir_julga_a_mesma_forma(cliente, monkeypatch):
    monkeypatch.setattr(trafego.plat, "exigir_construtor", lambda *_: None)
    payload = _search(configuracao_search={"lanc": {}}, motivo="prova de forma da configuração",
                      plano_impressao="x", confirmar_criacao_pausada=True)
    r = cliente.post("/api/trafego/subir", json=payload)
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["loc"] == ["body", "configuracao_search", "lanc"]


def test_match_por_keyword_fora_de_search_e_422(cliente):
    r = cliente.post("/api/trafego/provar",
                     json=_display(match_por_keyword={"curso": "EXACT"}))
    assert r.status_code == 422
    assert "match_por_keyword" in r.text


def test_demand_gen_com_lance_na_configuracao_exige_a_mesma_estrategia(cliente):
    r = cliente.post("/api/trafego/provar", json=_dg(
        configuracao_demand_gen={"lance": {"estrategia": "TARGET_SPEND"}}))
    assert r.status_code == 422
    assert "estrategia_lance=TARGET_SPEND" in r.text


# ═══════════════════════════════════════════════════════════════════════════
# a configuração CHEGA ao builder
# ═══════════════════════════════════════════════════════════════════════════


class _SbFalso:
    def __init__(self):
        self.chamadas = []

    def preparar(self, cid, brief, **kw):
        self.chamadas.append((brief, kw))
        return "PREPARO"


def _pp_falso(escolhas: list):
    class PP:
        PonteIncompleta = pautador_ponte.PonteIncompleta
        Plano = pautador_ponte.Plano
        Aviso = pautador_ponte.Aviso
        Evidencia = pautador_ponte.Evidencia
        Criterio = pautador_ponte.Criterio
        de_lista = staticmethod(pautador_ponte.de_lista)
        deduplicar = staticmethod(pautador_ponte.deduplicar)

        @staticmethod
        def carregar(*_a, **_k):
            return SimpleNamespace(cluster=None, run={})

        @staticmethod
        def montar_cockpit(_linhas):
            return SimpleNamespace(bloqueios=(), avisos=(), origem=None)

        @staticmethod
        def Escolha(**kw):
            escolhas.append(kw)
            return SimpleNamespace(**kw)

        @staticmethod
        def montar_brief(cockpit, escolha, copy=None):
            positivas = [c for c in escolha.criterios if not c.negativa]
            brief = SimpleNamespace(criterios=positivas, url_final=URL)
            return pautador_ponte.Plano(brief=brief, grupos=(), avisos=())
    return PP


APROVADOS = [Criterio(texto=t, match_type="PHRASE", negativa=False, nivel="AD_GROUP",
                      grupo=None, origem="PAUTADOR")
             for t in ("cursos gratuitos senac", "cursos senac 2026")]


@pytest.fixture
def conjunto_aprovado(monkeypatch):
    monkeypatch.setattr(trafego.portao_pago, "criterios_do_cluster",
                        lambda _c: (SimpleNamespace(selected_keywords=()), list(APROVADOS)))
    monkeypatch.setattr(trafego.portao_pago, "keywords_por_grupo",
                        lambda _c: {"": tuple(c.texto for c in APROVADOS)})


def _montar(body, canal, pp, sb):
    return trafego._montar_e_preparar_plano(pp, sb, body, canal_resolvido=canal,
                                            cid=CID, mid=MCC, prefixo_nome="FORGE")


def test_search_repassa_a_configuracao_e_a_estrategia_efetiva(conjunto_aprovado):
    escolhas, sb = [], _SbFalso()
    body = trafego.ProvarEntrada(**_search(configuracao_search={
        "lance": {"estrategia": "TARGET_SPEND", "teto_cpc": 0.8},
        "rede": {"google_search": True, "parceiros": False, "display_expansion": False}}))
    _montar(body, "SEARCH", _pp_falso(escolhas), sb)
    _brief, kw = sb.chamadas[0]
    assert isinstance(kw["configuracao"], sc.ConfiguracaoSearch)
    assert kw["configuracao"].lance == sc.LanceSearch("TARGET_SPEND", teto_cpc=0.8)
    # o brief carrega a estratégia da configuração, não o default MANUAL_CPC
    assert escolhas[0]["estrategia_lance"] == "TARGET_SPEND"
    # a rede da configuração é a que o canário julga
    assert trafego._rede_do_corpo(body).search_partners is False


def test_sem_configuracao_o_preparo_e_o_de_antes(conjunto_aprovado):
    escolhas, sb = [], _SbFalso()
    body = trafego.ProvarEntrada(**_search())
    _montar(body, "SEARCH", _pp_falso(escolhas), sb)
    _brief, kw = sb.chamadas[0]
    assert "configuracao" not in kw, "sem configuração o kwarg nem é passado"
    assert escolhas[0]["estrategia_lance"] == "MANUAL_CPC"


def test_match_por_keyword_chega_ao_criterio(conjunto_aprovado):
    escolhas, sb = [], _SbFalso()
    body = trafego.ProvarEntrada(**_search(
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        match_por_keyword={"Cursos  Senac 2026": "EXACT", "cursos gratuitos senac": "PHRASE"}))
    plano = _montar(body, "SEARCH", _pp_falso(escolhas), sb)
    positivas = {c.texto: c.match_type for c in escolhas[0]["criterios"] if not c.negativa}
    assert positivas == {"cursos gratuitos senac": "PHRASE", "cursos senac 2026": "EXACT"}
    assert any(a.codigo == "MATCH_TYPE_ESCOLHIDO_NA_TELA" for a in plano.plano.avisos)


def test_match_por_keyword_fora_do_conjunto_e_recusado(conjunto_aprovado):
    body = trafego.ProvarEntrada(**_search(match_por_keyword={"concurso inss": "EXACT"}))
    with pytest.raises(cfgcan.ConfiguracaoRecusada) as e:
        _montar(body, "SEARCH", _pp_falso([]), _SbFalso())
    assert e.value.codigo == cfgcan.MATCH_FORA_DO_CONJUNTO


def test_display_repassa_a_configuracao(monkeypatch):
    sb = _SbFalso()
    monkeypatch.setattr(trafego, "_montar_plano_display", lambda *a, **k: (
        pautador_ponte.Plano(brief=SimpleNamespace(url_final=URL), grupos=(), avisos=()), None))
    body = trafego.ProvarEntrada(**_display(configuracao_display={
        "segmentacao": {"topicos": ["369"]},
        "anuncio": {"videos_youtube": ["jNQXAC9IVRw"]}}))
    preparado = _montar(body, "DISPLAY", _pp_falso([]), sb)
    _brief, kw = sb.chamadas[0]
    assert isinstance(kw["configuracao"], dc.ConfiguracaoDisplay)
    assert kw["configuracao"].segmentacao.topicos == ("369",)
    # vídeo por id atravessa sem o portão de bytes — e o plano DIZ isso
    assert any(a.codigo == "VIDEO_SEM_PORTAO_DE_POLITICA" for a in preparado.plano.avisos)


def test_display_cpc_manual_exige_cpc_explicito():
    body = trafego.ProvarEntrada(**_display(
        estrategia_lance="MANUAL_CPC",
        configuracao_display={"lance": {"estrategia": "MANUAL_CPC"}}))
    with pytest.raises(ValueError, match="cpc_inicial"):
        trafego._recusar_campos_nao_operados_display(body)
    ok = trafego.ProvarEntrada(**_display(
        estrategia_lance="MANUAL_CPC", cpc_inicial=0.4,
        configuracao_display={"lance": {"estrategia": "MANUAL_CPC"}}))
    trafego._recusar_campos_nao_operados_display(ok)
    assert trafego._cpc_manual_de_display(ok) == {"cpc_inicial": 0.4}


def _cockpit():
    return SimpleNamespace(bloqueios=(), avisos=(), origem=SimpleNamespace(
        url_final=URL, nicho="Cursos Senac", slug="guia-cursos-senac", pais="BR",
        idioma="pt", vertical="informativo"))


def _escolha():
    return SimpleNamespace(url_final=None, vertical=None, certificacoes=(),
                           prefixo_nome="FORGE", carimbo_nome="20261008_120000",
                           conversao="")


def test_demand_gen_video_chega_ao_brief_como_v25(com_inspecao_de_pixel):
    body = trafego.ProvarEntrada(**_dg(
        estrategia_lance="TARGET_CPC",
        copy={"headlines": ["Cursos Senac"], "long_headlines": ["Guia de cursos do Senac"],
              "descriptions": ["Veja modalidades."], "business_name": "Credito Up"},
        assets_demand_gen=[_envelope("logo_quadrado", "logo", 1)],
        configuracao_demand_gen={
            "formato": "VIDEO_RESPONSIVO",
            "lance": {"estrategia": "TARGET_CPC", "target_cpc": 0.6},
            "video": {"youtube_ids": ["M7lc1UVf-VE"], "call_to_action": "LEARN_MORE"},
            "automacoes": {"GENERATE_SHORTER_YOUTUBE_VIDEOS": "OPTED_IN"}}))
    plano, _supply = trafego._montar_plano_demand_gen(
        pautador_ponte, _cockpit(), _escolha(),
        Copy(headlines=["Cursos Senac"], long_headlines=["Guia de cursos do Senac"],
             descriptions=["Veja modalidades."], business_name="Credito Up"), body)
    cfg = plano.brief.demand_gen
    assert isinstance(cfg, dgc.ConfiguracaoDemandGenV25)
    assert cfg.formato == "VIDEO_RESPONSIVO" and cfg.lance.target_cpc == 0.6
    assert cfg.upgraded_targeting is False, "a base do objeto `demand_gen` foi preservada"
    assert plano.brief.estrategia_lance == "TARGET_CPC"
    # o lote do vídeo é só o logo — a régua do multi-asset não o recusa
    assert len(plano.brief.imagens_demand_gen.logo_quadrado) == 1


def _assets_pmax(sufixo: str, s0: int, logos: bool = True) -> list:
    tipos = ["imagem_marketing", "imagem_marketing_quadrada"]
    if logos:
        tipos += ["logo_quadrado"]
    return [_envelope(t, f"{t}{sufixo}", s0 + i) for i, t in enumerate(tipos)]


def _corpo_pmax(**cfg) -> trafego.ProvarEntrada:
    return trafego.ProvarEntrada(**_pmax(
        pmax={"brand_guidelines_enabled": True, "search_themes": ["cursos senac"]},
        assets_pmax=_assets_pmax("", 1),
        copy={"headlines": ["Cursos Senac 2026", "Guia de Cursos", "Veja Áreas"],
              "long_headlines": ["Guia informativo com áreas e modalidades do Senac"],
              "descriptions": ["Conheça as áreas.", "Guia com modalidades e inscrição."],
              "business_name": "Credito Up"},
        **cfg))


def _montar_pmax(body):
    return trafego._montar_plano_pmax(
        pautador_ponte, _cockpit(), _escolha(), None, body, cid=CID, mid=MCC,
        ler_mensuracao=lambda *_a, **_k: None)


def test_pmax_grupos_adicionais_passam_pelo_portao_e_entram_no_supply(com_inspecao_de_pixel):
    sem = _montar_pmax(_corpo_pmax())
    com = _montar_pmax(_corpo_pmax(configuracao_pmax={
        "path1": "cursos",
        "grupos_adicionais": [{
            "nome": "Senac livres", "url_final": URL + "?s=livres",
            "textos": {"headlines": ["Cursos Livres"], "long_headlines": ["Guia dos cursos livres"],
                       "descriptions": ["Veja áreas."]},
            # brand guidelines ON: logo é da campanha, o grupo não leva
            "imagens": _assets_pmax("_g2", 20, logos=False),
            "sinais": [{"tipo": "search_theme", "valor": "cursos livres"}]}]}))
    plano, supply = com
    cfg = plano.brief.pmax
    assert isinstance(cfg, pc.ConfiguracaoPMaxV25) and cfg.path1 == "cursos"
    grupo = cfg.grupos_adicionais[0]
    assert len(grupo.imagens.marketing) == 1 and len(grupo.imagens.marketing_quadrada) == 1
    assert grupo.imagens.logo == []
    assert supply != sem[1], "os recibos do grupo adicional entram no supply_sha256"


# ═══════════════════════════════════════════════════════════════════════════
# identidade do plano, ledger, mensuração
# ═══════════════════════════════════════════════════════════════════════════


def test_sem_configuracao_a_impressao_aprovavel_e_a_de_antes():
    body = trafego.ProvarEntrada(**_search(carimbo_nome="20261008_120000"))
    bruto = trafego._plano_aprovavel(body, cid=CID, mid=MCC)
    for campo in (*cfgcan.CAMPO_POR_CANAL.values(), "match_por_keyword"):
        assert campo not in bruto
    vazio = trafego.ProvarEntrada(**_search(carimbo_nome="20261008_120000", match_por_keyword={}))
    assert trafego._impressao_aprovavel(vazio, cid=CID, mid=MCC) == \
        trafego._impressao_aprovavel(body, cid=CID, mid=MCC)
    com = trafego.ProvarEntrada(**_search(configuracao_search={}))
    assert "configuracao_search" in trafego._plano_aprovavel(com, cid=CID, mid=MCC)
    assert trafego._impressao_aprovavel(com, cid=CID, mid=MCC) != \
        trafego._impressao_aprovavel(body, cid=CID, mid=MCC)


def test_ledger_canoniza_numero_da_configuracao_sem_float():
    a = trafego.ProvarEntrada(**_search(configuracao_search={
        "lance": {"estrategia": "TARGET_SPEND", "teto_cpc": 1.0}}))
    b = trafego.ProvarEntrada(**_search(configuracao_search={
        "lance": {"estrategia": "TARGET_SPEND", "teto_cpc": 1}}))
    pa = trafego.plano_do_ledger(a, cid=CID, mid=MCC)
    assert pa["configuracao_search"]["lance"]["teto_cpc"] == "1"
    assert pa == trafego.plano_do_ledger(b, cid=CID, mid=MCC)
    from app.trafego import lote

    lote._sem_float(pa)  # a guarda do ledger aceita o plano inteiro


def test_portao_de_mensuracao_julga_a_estrategia_efetiva():
    body = trafego.ProvarEntrada(**_search(configuracao_search={
        "lance": {"estrategia": "MAXIMIZE_CONVERSIONS"}}))
    assert trafego._estrategia_efetiva(body) == "MAXIMIZE_CONVERSIONS"
    assert trafego._estrategia_efetiva(trafego.ProvarEntrada(**_search())) == "MANUAL_CPC"


# ═══════════════════════════════════════════════════════════════════════════
# o esquema publicado
# ═══════════════════════════════════════════════════════════════════════════


def test_rota_de_esquema_publica_os_quatro_canais(cliente):
    r = cliente.get("/api/trafego/canais/esquema")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["versao"] == "GADS-CRIACAO-CANAIS-v1"
    assert set(corpo["canais"]) == {"SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX"}
    s = corpo["canais"]["SEARCH"]
    assert s["campo_http"] == "configuracao_search"
    assert s["esquema"]["$defs"]["LanceSearch"]["properties"]["estrategia"]["enum"] == list(sc.ESTRATEGIAS)
    pm = corpo["canais"]["PERFORMANCE_MAX"]["esquema"]
    item = pm["$defs"]["AssetGroupPMax"]["properties"]["imagens"]["items"]
    assert "dados_base64" in item["properties"], "imagens do grupo = envelope de assets_pmax"
    assert corpo["canais"]["DEMAND_GEN"]["esquema"]["properties"]["formato"]["enum"] == \
        list(dgc.FORMATOS)


# ═══════════════════════════════════════════════════════════════════════════
# releitura e travas de destino
# ═══════════════════════════════════════════════════════════════════════════


def _linha_campanha():
    return SimpleNamespace(campaign=SimpleNamespace(
        id=1, name="c", status=SimpleNamespace(name="PAUSED"),
        advertising_channel_type=SimpleNamespace(name="PERFORMANCE_MAX"),
        bidding_strategy_type=SimpleNamespace(name="MAXIMIZE_CONVERSIONS")))


def _ag(i):
    return SimpleNamespace(asset_group=SimpleNamespace(id=i, status=SimpleNamespace(name="PAUSED")))


def test_releitura_pmax_exige_os_n_asset_groups_do_plano():
    def buscar(n):
        return lambda q: [_linha_campanha()] if "FROM campaign" in q else [_ag(i) for i in range(n)]

    def ag(vereditos):
        return [v for v in vereditos if v.objeto == "asset_group"][0]

    so_um = rel.reler_na_conta(canal="PERFORMANCE_MAX", buscar=buscar(1), campaign_id="1",
                               esperado={"status": "PAUSED", rel.ESPERADO_ASSET_GROUPS: 2})
    assert ag(so_um).estado is EstadoDaReleitura.DIVERGENTE
    os_dois = rel.reler_na_conta(canal="PERFORMANCE_MAX", buscar=buscar(2), campaign_id="1",
                                 esperado={"status": "PAUSED", rel.ESPERADO_ASSET_GROUPS: 2})
    assert ag(os_dois).estado is EstadoDaReleitura.CONGRUENTE
    assert ag(os_dois).lido["ids"] == ["0", "1"]
    legado = rel.reler_na_conta(canal="PERFORMANCE_MAX", buscar=buscar(1), campaign_id="1",
                                esperado={"status": "PAUSED"})
    assert ag(legado).estado is EstadoDaReleitura.CONGRUENTE


def test_travas_de_destino_pmax_sem_page_feed_e_path_so_por_padrao():
    travas = ccan._TRAVAS_DE_DESTINO["PERFORMANCE_MAX"]
    assert not any("PAGE_FEED" in t for t in travas)
    assert any("path1/path2 por padrão" in t for t in travas)
