"""Portão hermético: canal sem builder nunca vira outro canal por acidente.

⚠️ Este arquivo mudou em 26/08/2026 e a mudança é de FATO, não de regra.
Display ganhou construtor próprio (`volc_ads/campanha/display.py`), então ele
saiu da lista dos recusados — e o portão continua exatamente tão fechado quanto
era para todo canal fora do registro do engine.

Um teste que carimbasse "DISPLAY é recusado" para sempre viraria o contrário do
que existe para fazer: ele passaria a proteger a AUSÊNCIA em vez do portão. O
que ele protege agora é a coerência: quem o engine deixa criar, o Hub oferece;
quem ele recusa, o Hub recusa com a lista do que existe — e a comparação é
feita contra o registro REAL, lido por árvore sintática.
"""
from __future__ import annotations

import ast
import asyncio
import base64
import copy
import hashlib
import pathlib
import struct
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.routers import trafego
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario
from app.trafego import plataforma as plat
from volc_ads import pautador_ponte
from volc_ads import subir as motor
from volc_ads.campanha.brief import Copy

RAIZ = pathlib.Path(__file__).resolve().parents[2]


class _Escolha:
    def __init__(self, **_: object) -> None:
        pass


class _PonteFalsa:
    class PonteIncompleta(RuntimeError):
        pass

    Escolha = _Escolha

    @staticmethod
    def carregar(*_: object, **__: object) -> object:
        pytest.fail("canal inválido tentou carregar a oportunidade")

    @staticmethod
    def montar_cockpit(_: object) -> object:
        return object()

    @staticmethod
    def montar_brief(*_: object, **__: object) -> object:
        return SimpleNamespace(brief=object(), avisos=(), grupos=())


def _isolar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        trafego,
        "_no_escopo",
        lambda *_: ("5478096539", "6016739364"),
    )
    monkeypatch.setattr(trafego, "_ponte", lambda: (_PonteFalsa, motor))
    monkeypatch.setattr(
        trafego.escopo,
        "conta_da_casa",
        lambda *_: pytest.fail("canal inválido consultou a conta Google"),
    )


def _payload_demand_gen_minimo(**troca: object) -> dict:
    base = {
        "opportunity_id": 1,
        "customer_id": "8017851692",
        "login_customer_id": "6016739364",
        "canal": "DEMAND_GEN",
        "estrategia_lance": "MAXIMIZE_CONVERSIONS",
        "demand_gen": {},
        "assets_demand_gen": [],
    }
    base.update(troca)
    return base


@pytest.mark.parametrize("canal", ["PMAX"])
def test_provar_recusa_canal_sem_builder_com_422(
    monkeypatch: pytest.MonkeyPatch,
    canal: str,
) -> None:
    _isolar(monkeypatch)

    body = trafego.ProvarEntrada(
        opportunity_id=1,
        customer_id="8017851692",
        login_customer_id="6016739364",
        canal=canal,
    )

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.provar(body))

    assert erro.value.status_code == 422
    assert "não possui builder provável" in str(erro.value.detail)


def test_provar_demand_gen_flag_off_recusa_antes_de_ponte_ou_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolar(monkeypatch)
    monkeypatch.delenv("VOLC_DEMAND_GEN_VALIDATE_ONLY", raising=False)
    monkeypatch.setattr(
        trafego,
        "_no_escopo",
        lambda *_: pytest.fail("flag fechada chegou até o portão de conta"),
    )
    monkeypatch.setattr(
        trafego,
        "_ponte",
        lambda: pytest.fail("flag fechada carregou engine/credencial"),
    )

    body = trafego.ProvarEntrada(**_payload_demand_gen_minimo())
    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.provar(body))
    assert erro.value.status_code == 403
    assert "nenhum validate_only foi chamado" in str(erro.value.detail)


def test_provar_demand_gen_flag_on_ainda_exige_capacidade_do_operador(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _isolar(monkeypatch)
    monkeypatch.setenv("VOLC_DEMAND_GEN_VALIDATE_ONLY", "on")
    monkeypatch.setattr(
        trafego,
        "_no_escopo",
        lambda *_: pytest.fail("operador sem capacidade chegou ao escopo"),
    )
    body = trafego.ProvarEntrada(**_payload_demand_gen_minimo())
    identidade = SimpleNamespace(papel="OPERATOR")
    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.provar(body, identidade=identidade))
    assert erro.value.status_code == 403
    assert "capacidade experimental" in str(erro.value.detail)


@pytest.mark.parametrize(
    ("troca", "campo"),
    [
        ({"cpc_inicial": 0.12}, "cpc_inicial"),
        ({"match_type": "PHRASE"}, "match_type"),
        ({"graduacao_em_conversoes": 30}, "graduacao_em_conversoes"),
        ({"meta_conversao_id": "customers/1/conversionActions/2"}, "meta_conversao_id"),
        ({"conversao": "Lead"}, "conversao"),
        ({"ai_max": True}, "ai_max"),
        ({"copy": {"long_headlines": ["Texto longo"]}}, "copy.long_headlines"),
        ({"copy": {"sitelinks": [{"texto": "Saiba mais"}]}}, "copy.sitelinks"),
        ({"copy": {"callouts": ["Sem taxa escondida"]}}, "copy.callouts"),
        (
            {"copy": {"snippet": {"header": "Serviços", "values": ["Consulta"]}}},
            "copy.snippet",
        ),
    ],
)
def test_provar_demand_gen_recusa_campo_nao_operado_antes_de_escopo_e_engine(
    monkeypatch: pytest.MonkeyPatch,
    troca: dict,
    campo: str,
) -> None:
    monkeypatch.setattr(
        trafego,
        "_no_escopo",
        lambda *_: pytest.fail(f"{campo} chegou ao escopo de conta"),
    )
    monkeypatch.setattr(
        trafego,
        "_ponte",
        lambda: pytest.fail(f"{campo} chegou ao engine/cliente"),
    )
    payload = _payload_demand_gen_minimo(**troca)

    with _cliente_da_fronteira() as cliente:
        resposta = cliente.post("/api/trafego/provar", json=payload)

    assert resposta.status_code == 422, resposta.text
    assert campo in resposta.text
    assert (
        "não os descarta em silêncio" in resposta.text
        or "campos Search" in resposta.text
    )


def test_plano_demand_gen_recusa_campos_search_em_vez_de_apaga_los() -> None:
    body = trafego.ProvarEntrada(
        opportunity_id=1,
        customer_id="8017851692",
        login_customer_id="6016739364",
        canal="DEMAND_GEN",
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        grupos=[trafego.GrupoEscolhido(tipo="busca", keywords=["não converter"])],
        demand_gen=trafego.ConfiguracaoDemandGenEntrada(),
        assets_demand_gen=[],
    )

    with pytest.raises(ValueError) as erro:
        trafego._montar_plano_demand_gen(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            None,
            body,
        )

    assert "não os descarta em silêncio" in str(erro.value)
    assert "grupos" in str(erro.value)


@pytest.mark.parametrize("campo", ["demand_gen", "assets_demand_gen"])
def test_search_relabelado_com_campo_demand_gen_recusa_antes_de_escopo(
    monkeypatch: pytest.MonkeyPatch,
    campo: str,
) -> None:
    payload = {
        "opportunity_id": 1,
        "customer_id": "8017851692",
        "login_customer_id": "6016739364",
        "canal": "SEARCH",
        "budget_diario": 10,
        "cpc_inicial": 0.12,
        "match_type": "PHRASE",
        campo: [] if campo == "assets_demand_gen" else {},
    }
    monkeypatch.setattr(
        trafego,
        "_no_escopo",
        lambda *_: pytest.fail(f"{campo} chegou ao escopo"),
    )
    monkeypatch.setattr(
        trafego,
        "_ponte",
        lambda: pytest.fail(f"{campo} chegou ao engine Search"),
    )

    with _cliente_da_fronteira() as cliente:
        resposta = cliente.post("/api/trafego/provar", json=payload)

    assert resposta.status_code == 422, resposta.text
    assert "canal=DEMAND_GEN" in resposta.text
    assert "Nada foi projetado para Search" in resposta.text


def test_search_com_null_demand_gen_preserva_ausencia() -> None:
    body = trafego.ProvarEntrada.model_validate({
        "opportunity_id": 1,
        "customer_id": "8017851692",
        "login_customer_id": "6016739364",
        "canal": "SEARCH",
        "budget_diario": 10,
        "cpc_inicial": 0.12,
        "match_type": "PHRASE",
        "demand_gen": None,
        "assets_demand_gen": None,
    })

    assert body.canal == "SEARCH"
    assert body.demand_gen is None
    assert body.assets_demand_gen is None


@pytest.mark.parametrize(
    ("troca", "mensagem"),
    [
        ({"estrategia_lance": "MANUAL_CPC"}, "MAXIMIZE_CONVERSIONS"),
        ({"demand_gen": None}, "demand_gen"),
        ({"assets_demand_gen": None}, "assets_demand_gen"),
        ({"cpc_inicial": 0.12}, "proíbe campos Search"),
        ({"match_type": "PHRASE"}, "proíbe campos Search"),
    ],
)
def test_modelo_demand_gen_discrimina_o_contrato_antes_da_rota(
    troca: dict,
    mensagem: str,
) -> None:
    payload = _payload_demand_gen_minimo(**troca)

    with pytest.raises(ValidationError) as erro:
        trafego.ProvarEntrada.model_validate(payload)

    assert mensagem in str(erro.value)


def _payload_http_demand_gen() -> dict:
    dados = b"imagem-hermetica"
    return {
        "opportunity_id": 1,
        "customer_id": "8017851692",
        "login_customer_id": "6016739364",
        "canal": "DEMAND_GEN",
        "estrategia_lance": "MAXIMIZE_CONVERSIONS",
        "copy": {
            "headlines": ["Entenda o benefício"],
            "descriptions": ["Veja regras, prazos e condições."],
            "business_name": "VOLC",
        },
        "demand_gen": {
            "upgraded_targeting": True,
            "controles_de_canal": {
                "estrategia": "ALL_CHANNELS",
                "selected_channels": None,
            },
            "audiencias": [],
            "intencoes": [],
            "exclusoes_de_audiencia": [],
        },
        "assets_demand_gen": [{
            "tipo": "imagem_marketing",
            "nome": "paisagem",
            "dados_base64": base64.b64encode(dados).decode(),
            "conteudo_hash": "sha256:" + hashlib.sha256(dados).hexdigest(),
            "origem": "gerado",
            "procedencia": {
                "motor": "fixture-hermetica",
                "versao_do_motor": "1",
                "insumo": "gerar paisagem",
                "quando": "2026-08-29T12:00:00+00:00",
            },
        }],
    }


def _cliente_da_fronteira() -> TestClient:
    app = FastAPI()
    app.include_router(trafego.router)
    identidade = Identidade(
        sub="u1", email="op@volc", papel="ADMIN", origem="sessao"
    )
    app.dependency_overrides[exigir_usuario] = lambda: identidade
    app.dependency_overrides[exigir_admin] = lambda: identidade
    return TestClient(app)


@pytest.mark.parametrize(
    ("caminho", "extra"),
    [
        ((), "campo_fantasma"),
        (("copy",), "headliness"),
        (("demand_gen",), "upgraded_targetting"),
        (("demand_gen", "controles_de_canal"), "selected_channel"),
        (("assets_demand_gen", 0), "dados_b64"),
        (("assets_demand_gen", 0, "procedencia"), "versao"),
    ],
)
def test_http_demand_gen_recusa_extra_aninhado_com_422_antes_do_engine(
    monkeypatch: pytest.MonkeyPatch,
    caminho: tuple,
    extra: str,
) -> None:
    payload = copy.deepcopy(_payload_http_demand_gen())
    alvo = payload
    for parte in caminho:
        alvo = alvo[parte]
    alvo[extra] = "não pode sumir"

    monkeypatch.setattr(
        trafego,
        "_no_escopo",
        lambda *_: pytest.fail(f"extra {extra} chegou ao escopo"),
    )
    monkeypatch.setattr(
        trafego,
        "_ponte",
        lambda: pytest.fail(f"extra {extra} chegou à ponte/cliente"),
    )
    with _cliente_da_fronteira() as cliente:
        resposta = cliente.post("/api/trafego/provar", json=payload)

    assert resposta.status_code == 422, resposta.text
    assert extra in resposta.text
    assert "extra_forbidden" in resposta.text


def test_search_preserva_tolerancia_ao_extra_legado() -> None:
    body = trafego.ProvarEntrada.model_validate({
        "opportunity_id": 1,
        "customer_id": "8017851692",
        "login_customer_id": "6016739364",
        "canal": "SEARCH",
        "campo_legado_desconhecido": "ignorado por compatibilidade",
    })

    assert body.canal == "SEARCH"
    assert not hasattr(body, "campo_legado_desconhecido")


def test_http_demand_gen_recusa_quantidade_antes_do_escopo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload_http_demand_gen()
    item = payload["assets_demand_gen"][0]
    payload["assets_demand_gen"] = [
        {**item, "nome": f"asset-{i}"}
        for i in range(trafego.TETO_QUANTIDADE_ASSETS_DEMAND_GEN + 1)
    ]
    monkeypatch.setattr(
        trafego,
        "_no_escopo",
        lambda *_: pytest.fail("lote grande chegou ao escopo"),
    )
    with _cliente_da_fronteira() as cliente:
        resposta = cliente.post("/api/trafego/provar", json=payload)

    assert resposta.status_code == 422, resposta.text
    assert "assets_demand_gen" in resposta.text
    assert "too_long" in resposta.text


def test_demand_gen_recusa_base64_codificado_acima_do_teto_na_validacao() -> None:
    payload = _payload_http_demand_gen()
    payload["assets_demand_gen"][0]["dados_base64"] = (
        "A" * (trafego.TETO_BASE64_ASSET_DEMAND_GEN + 1)
    )

    with pytest.raises(ValidationError) as erro:
        trafego.ProvarEntrada.model_validate(payload)

    detalhes = erro.value.errors()
    assert any(item["type"] == "string_too_long" for item in detalhes)
    assert any("dados_base64" in item["loc"] for item in detalhes)


def _asset_http(nome: str, dados: bytes) -> trafego.AssetDemandGenEntrada:
    return trafego.AssetDemandGenEntrada(
        tipo="imagem_marketing",
        nome=nome,
        dados_base64=base64.b64encode(dados).decode(),
        conteudo_hash="sha256:" + hashlib.sha256(dados).hexdigest(),
        origem="gerado",
        procedencia=trafego.ProcedenciaAssetDemandGenEntrada(
            motor="fixture-hermetica",
            insumo=f"gerar {nome}",
            quando="2026-08-29T12:00:00+00:00",
        ),
    )


def test_decodificacao_demand_gen_confere_base64_e_bytes_por_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _asset_http("a", b"12345678")
    monkeypatch.setattr(trafego, "TETO_BASE64_ASSET_DEMAND_GEN", 10_000)
    monkeypatch.setattr(trafego, "TETO_BYTES_LOTE_DEMAND_GEN", 10_000)

    monkeypatch.setattr(trafego, "TETO_BYTES_ASSET_DEMAND_GEN", 8)
    assert list(trafego._assets_decodificados_demand_gen([item]))[0][1] == b"12345678"

    monkeypatch.setattr(trafego, "TETO_BYTES_ASSET_DEMAND_GEN", 7)
    with pytest.raises(ValueError, match="teto por item"):
        list(trafego._assets_decodificados_demand_gen([item]))

    monkeypatch.setattr(trafego, "TETO_BYTES_ASSET_DEMAND_GEN", 100)
    monkeypatch.setattr(
        trafego, "TETO_BASE64_ASSET_DEMAND_GEN", len(item.dados_base64) - 1
    )
    with pytest.raises(ValueError, match="teto codificado"):
        list(trafego._assets_decodificados_demand_gen([item]))

    invalido = item.model_copy(update={"dados_base64": "não-é-base64%%%"})
    monkeypatch.setattr(trafego, "TETO_BASE64_ASSET_DEMAND_GEN", 10_000)
    with pytest.raises(ValueError, match="dados_base64 inválidos"):
        list(trafego._assets_decodificados_demand_gen([invalido]))

    vazio = item.model_copy(update={"dados_base64": ""})
    with pytest.raises(ValueError, match="conteúdo ausente"):
        list(trafego._assets_decodificados_demand_gen([vazio]))


def test_decodificacao_demand_gen_recusa_total_antes_de_entregar_o_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primeiro = _asset_http("primeiro", b"12345")
    segundo = _asset_http("segundo", b"67890")
    monkeypatch.setattr(trafego, "TETO_BASE64_ASSET_DEMAND_GEN", 10_000)
    monkeypatch.setattr(trafego, "TETO_BYTES_ASSET_DEMAND_GEN", 10_000)
    monkeypatch.setattr(trafego, "TETO_BYTES_LOTE_DEMAND_GEN", 9)

    gerador = iter(
        trafego._assets_decodificados_demand_gen([primeiro, segundo])
    )
    assert next(gerador)[0].nome == "primeiro"
    with pytest.raises(ValueError, match="teto total decodificado"):
        next(gerador)


def test_selected_channels_duplicado_na_forma_canonica_e_recusado() -> None:
    body = trafego.ProvarEntrada(
        opportunity_id=1,
        customer_id="8017851692",
        login_customer_id="6016739364",
        canal="DEMAND_GEN",
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        demand_gen={
            "upgraded_targeting": True,
            "controles_de_canal": {
                "estrategia": "selected_channels",
                "selected_channels": [" Discover ", "discover"],
            },
            "audiencias": [],
            "intencoes": [],
            "exclusoes_de_audiencia": [],
        },
        assets_demand_gen=[],
    )
    cockpit = SimpleNamespace(
        bloqueios=(),
        avisos=(),
        origem=SimpleNamespace(
            url_final="https://creditoup.com.br/r/saque-anual/",
            nicho="Saque Anual",
            slug="saque-anual",
            pais="BR",
            idioma="pt",
            vertical="informativo",
        ),
    )
    escolha = SimpleNamespace(
        url_final=None,
        vertical=None,
        certificacoes=(),
        prefixo_nome="FORGE",
        carimbo_nome="20260829_120000",
        conversao="",
    )

    with pytest.raises(ValueError, match="depois da canonização"):
        trafego._montar_plano_demand_gen(
            pautador_ponte, cockpit, escolha, Copy(), body
        )


def test_plano_http_demand_gen_nao_depende_de_keyword_e_preserva_superficies() -> None:
    def asset(tipo: str, nome: str, largura: int, altura: int) -> dict:
        dados = (
            b"\x89PNG\r\n\x1a\n"
            + struct.pack(">I", 13)
            + b"IHDR"
            + struct.pack(">II", largura, altura)
            + b"\x08\x06\x00\x00\x00"
            + nome.encode()
        )
        return {
            "tipo": tipo,
            "nome": nome,
            "dados_base64": base64.b64encode(dados).decode(),
            "conteudo_hash": "sha256:" + hashlib.sha256(dados).hexdigest(),
            "origem": "gerado",
            "procedencia": {
                "motor": "fixture-hermetica",
                "versao_do_motor": "1",
                "insumo": f"gerar {nome}",
                "quando": "2026-08-29T12:00:00+00:00",
            },
        }

    body = trafego.ProvarEntrada(
        opportunity_id=1,
        customer_id="8017851692",
        login_customer_id="6016739364",
        canal="DEMAND_GEN",
        estrategia_lance="MAXIMIZE_CONVERSIONS",
        copy={
            "headlines": ["Entenda o Saque Anual"],
            "descriptions": ["Veja regras, prazos e limites."],
            "business_name": "Credito Up",
        },
        demand_gen={
            "upgraded_targeting": True,
            "controles_de_canal": {
                "estrategia": "ALL_CHANNELS",
                "selected_channels": None,
            },
            "audiencias": [],
            "intencoes": [],
            "exclusoes_de_audiencia": [],
        },
        assets_demand_gen=[
            asset("imagem_marketing", "paisagem", 600, 314),
            asset("logo_quadrado", "logo", 144, 144),
        ],
    )
    cockpit = SimpleNamespace(
        bloqueios=(),
        avisos=(),
        origem=SimpleNamespace(
            url_final="https://creditoup.com.br/r/saque-anual/",
            nicho="Saque Anual",
            slug="saque-anual",
            pais="BR",
            idioma="pt",
            vertical="informativo",
        ),
    )
    escolha = SimpleNamespace(
        url_final=None,
        vertical=None,
        certificacoes=(),
        prefixo_nome="FORGE",
        carimbo_nome="20260829_120000",
        conversao="",
    )

    plano = trafego._montar_plano_demand_gen(
        pautador_ponte,
        cockpit,
        escolha,
        Copy(
            headlines=["Entenda o Saque Anual"],
            descriptions=["Veja regras, prazos e limites."],
            business_name="Credito Up",
        ),
        body,
    )

    assert plano.brief.keywords == []
    assert plano.brief.sub_intencoes == []
    assert plano.brief.demand_gen.audiencias == ()
    assert plano.brief.demand_gen.intencoes == ()
    assert plano.brief.demand_gen.exclusoes_de_audiencia == ()
    assert len(plano.brief.imagens_demand_gen.todas) == 2


def _payload_http_subir_demand_gen() -> dict:
    payload = copy.deepcopy(_payload_http_demand_gen())
    payload.update({
        "motivo": "prova hermetica de recusa operacional demand gen",
        "plano_impressao": "impressao-aprovada-fixture",
        "confirmar_criacao_pausada": True,
    })
    return payload


def _blindar_subir_demand_gen(monkeypatch: pytest.MonkeyPatch, caso: str) -> None:
    def falhar(destino: str):
        return lambda *_args, **_kwargs: pytest.fail(
            f"{caso} alcancou {destino} antes da recusa"
        )

    monkeypatch.setattr(
        trafego,
        "_no_escopo",
        falhar("_no_escopo"),
    )
    monkeypatch.setattr(
        trafego,
        "_ponte",
        falhar("a ponte"),
    )
    monkeypatch.setattr(
        trafego.escopo,
        "conta_da_casa",
        falhar("consulta de conta"),
    )
    for nome in (
        "impressao_do_plano",
        "exigir",
        "elegivel",
        "campanhas_com_marca",
        "campanhas_com_destino",
    ):
        monkeypatch.setattr(trafego.canario, nome, falhar(f"canario.{nome}"))
    for nome in ("resolver_construtor", "preparar", "subir"):
        monkeypatch.setattr(motor, nome, falhar(f"motor.{nome}"))


@pytest.mark.parametrize(
    ("troca", "remover", "esperado"),
    [
        ({"cpc_inicial": 0.12}, (), "cpc_inicial"),
        ({"match_type": "PHRASE"}, (), "match_type"),
        ({}, ("demand_gen",), "demand_gen"),
        ({}, ("assets_demand_gen",), "assets_demand_gen"),
        ({"demand_gen": None}, (), "demand_gen"),
        ({"assets_demand_gen": None}, (), "assets_demand_gen"),
        ({"assets_demand_gen": []}, (), "lista vazia"),
    ],
)
def test_http_subir_demand_gen_invalido_morre_na_validacao_antes_de_efeitos(
    monkeypatch: pytest.MonkeyPatch,
    troca: dict,
    remover: tuple[str, ...],
    esperado: str,
) -> None:
    payload = _payload_http_subir_demand_gen()
    payload.update(troca)
    for campo in remover:
        payload.pop(campo)
    _blindar_subir_demand_gen(monkeypatch, esperado)

    with _cliente_da_fronteira() as cliente:
        resposta = cliente.post("/api/trafego/subir", json=payload)

    assert resposta.status_code == 422, resposta.text
    assert esperado in resposta.text


def test_http_subir_demand_gen_valido_recusa_operacional_antes_de_efeitos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _blindar_subir_demand_gen(monkeypatch, "demand gen valido")

    with _cliente_da_fronteira() as cliente:
        resposta = cliente.post(
            "/api/trafego/subir",
            json=_payload_http_subir_demand_gen(),
        )

    assert resposta.status_code == 403, resposta.text
    assert "somente prova validate_only" in resposta.text
    assert "/subir" in resposta.text


@pytest.mark.parametrize("canal", ["DEMAND_GEN", "PERFORMANCE_MAX"])
def test_subir_recusa_canal_fora_do_canario_antes_da_escrita(
    monkeypatch: pytest.MonkeyPatch,
    canal: str,
) -> None:
    _isolar(monkeypatch)
    monkeypatch.setattr(
        motor,
        "subir",
        lambda *_args, **_kwargs: pytest.fail("o caminho de escrita foi alcançado"),
    )
    if canal == "DEMAND_GEN":
        monkeypatch.setattr(
            trafego.canario,
            "exigir",
            lambda **_kwargs: pytest.fail("Demand Gen alcançou o canário real"),
        )

    if canal == "DEMAND_GEN":
        body = trafego.SubirEntrada(**_payload_http_subir_demand_gen())
    else:
        body = trafego.SubirEntrada(
            opportunity_id=1,
            customer_id="5478096539",
            login_customer_id="6016739364",
            canal=canal,
            motivo="prova hermética do canal recusado",
            confirmar_criacao_pausada=True,
            carimbo_nome="20260828_120000",
        )

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(body))

    # Na prova, o manifesto explica a ausência de builder (422). Na única rota
    # que pode escrever, a política mais estreita vem antes: qualquer canal
    # diferente de Search está fora da autorização do canário (403).
    assert erro.value.status_code == 403
    if canal == "DEMAND_GEN":
        assert "somente prova validate_only" in str(erro.value.detail)
        assert "/subir" in str(erro.value.detail)
    else:
        assert "apenas SEARCH" in str(erro.value.detail)


# ═══════════════════════════════════════════════════════════════════════════
# COERÊNCIA — o que o engine cria e o que o Hub oferece
# ═══════════════════════════════════════════════════════════════════════════


def _canais_do_perfil_do_engine() -> set[str]:
    """Lê `volc_ads/campanha/perfil.py` por ÁRVORE SINTÁTICA.

    Por árvore e não por import, pelo mesmo motivo de
    `test_trafego_plataforma.py`: `perfil.py` referencia os construtores, que
    importam o SDK do Google. Uma prova de arquitetura não pode depender de a
    máquina ter a biblioteca instalada — teste que pula por falta de
    dependência é teste que não protege nada.

    O que se procura é `PerfilDeCanal(canal=…, construtor=…,
    permite_mutacao_real=True)`. Builder sozinho só autoriza prova; Demand Gen
    existe justamente para impedir que as duas portas voltem a ser sinônimas.
    """
    fonte = (RAIZ / "volc_ads" / "campanha" / "perfil.py").read_text(encoding="utf-8")
    criam: set[str] = set()
    for no in ast.walk(ast.parse(fonte)):
        if not (isinstance(no, ast.Call)
                and getattr(no.func, "id", "") == "PerfilDeCanal"):
            continue
        args = {k.arg: k.value for k in no.keywords}
        canal = args.get("canal")
        tem_construtor = args.get("construtor") is not None
        mutacao = args.get("permite_mutacao_real")
        permite_mutacao = (
            isinstance(mutacao, ast.Constant) and mutacao.value is True
        )
        if not tem_construtor or not permite_mutacao:
            continue
        if isinstance(canal, ast.Constant):
            criam.add(str(canal.value))
        elif isinstance(canal, ast.Attribute):
            # `search.CANAL` / `display.CANAL` — o canal declarado no módulo.
            criam.add(str(canal.value.id).upper())
    return criam


def test_o_manifesto_do_hub_bate_com_o_perfil_do_engine():
    """Duas verdades sobre o mesmo fato é o defeito; uma e uma projeção, não.

    Se o manifesto sobrar, a tela oferece o que não existe e o operador monta o
    pedido inteiro para receber um 422 no fim. Se faltar, ela esconde uma
    capacidade real. As duas direções derrubam este teste.
    """
    do_hub = {m.canal for m in plat._MANIFESTOS.values() if m.sabe_criar}
    do_engine = _canais_do_perfil_do_engine()

    assert do_engine, (
        "não achei nenhum `PerfilDeCanal(..., construtor=...)` em "
        "volc_ads/campanha/perfil.py — se ele mudou de forma, este teste "
        "precisa acompanhar ou deixa de proteger")
    assert do_hub == do_engine, (
        f"o Hub diz que {sorted(do_hub)} sabem criar e o perfil do engine "
        f"declara {sorted(do_engine)}")


def test_display_atravessa_o_portao_de_criacao_do_hub():
    """A contraprova das recusas acima: o portão deixa passar o que existe."""
    m = plat.exigir_construtor(plat.GOOGLE_ADS, "DISPLAY")

    assert m.sabe_criar
    assert "selo" in m.provas_obrigatorias
    canal, construtor = motor.resolver_construtor("display")
    assert canal == "DISPLAY" and construtor is not None


def test_a_recusa_continua_dizendo_o_que_existe_agora_que_sao_dois():
    """Uma recusa que ensina lista TUDO o que existe, não o primeiro que existiu."""
    with pytest.raises(ValueError) as erro:
        plat.exigir_construtor(plat.GOOGLE_ADS, "PERFORMANCE_MAX")
    mensagem = str(erro.value)
    assert "Search" in mensagem and "Display" in mensagem

    with pytest.raises(motor.CanalSemConstrutor) as erro2:
        motor.resolver_construtor("PERFORMANCE_MAX")
    assert "DISPLAY, SEARCH" in str(erro2.value)


def test_display_declara_a_ausencia_de_segmentacao_por_posicionamento():
    """A decisão de 26/08/2026 vira PROVA, não comentário.

    Duas fontes oficiais se contradizem sobre segmentação positiva por
    posicionamento, e a prova por `validate_only` na conta real não foi
    autorizada nesta rodada. A escolha foi não implementar — e uma escolha que
    só existe em texto de commit some na primeira releitura. Aqui ela é o que a
    tela mostra ao operador, e some junto com a implementação quando ela vier.
    """
    m = plat.manifesto(plat.GOOGLE_ADS, "DISPLAY")
    texto = " ".join(m.indisponibilidades).lower()

    assert "posicionamento" in texto
    assert "contradiz" in texto or "contradi" in texto
    assert "validate_only" in texto


def test_o_manifesto_de_display_nao_promete_o_que_a_fatia_nao_monta():
    """Campo do pedido é o que a tela desenha. Prometer segmentação aqui faria
    o operador preencher um formulário que o construtor descarta."""
    m = plat.manifesto(plat.GOOGLE_ADS, "DISPLAY")

    assert m.sabe_criar
    assert not [c for c in m.campos_do_pedido
                if "segment" in c or "publico" in c or "posicionamento" in c]
    assert "keywords" not in m.campos_do_pedido
