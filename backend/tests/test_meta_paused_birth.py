from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.compilador import compilar_plano_pausado
from app.trafego.meta_execucao.contrato import (
    AutorizacaoMeta,
    ErroDeNascimentoMeta,
    PlanoMetaPausado,
    ReferenciasMetaResolvidas,
)
from app.trafego.meta_execucao.executor import ErroRemotoMeta, ExecutorMetaPausado
from app.trafego.meta_execucao.registro import PassoPreparadoMeta


TOKEN = "token-super-secreto-que-nao-pode-vazar"


class RegistroEmMemoria:
    def __init__(self, retomados: dict[str, str] | None = None) -> None:
        self.retomados = retomados or {}
        self.eventos: list[tuple[str, str]] = []

    async def preparar_passo(
        self, *, plano_sha256: str, approval_id: str, ator: str, nome: str, payload_sha256: str,
    ) -> PassoPreparadoMeta:
        assert len(plano_sha256) == 64
        assert approval_id == "approval_meta_01"
        assert ator == "operador@example.com"
        assert len(payload_sha256) == 64
        self.eventos.append(("preparar", nome))
        if nome in self.retomados:
            return PassoPreparadoMeta(f"passo_{nome}", "CRIADO", self.retomados[nome])
        return PassoPreparadoMeta(f"passo_{nome}", "DESPACHAR")

    async def fechar_passo(self, *, passo_ref: str, id_externo: str) -> None:
        self.eventos.append(("fechar", passo_ref.removeprefix("passo_")))
        assert id_externo.isdigit()

    async def marcar_ambiguo(self, *, passo_ref: str) -> None:
        self.eventos.append(("ambiguo", passo_ref.removeprefix("passo_")))

    async def falhar_passo(self, *, passo_ref: str, codigo: str) -> None:
        self.eventos.append(("falhar", passo_ref.removeprefix("passo_")))
        assert codigo.startswith("META_")


def plano(**mudancas: object) -> PlanoMetaPausado:
    base = PlanoMetaPausado(
        account_ref="metaacct_exemplo",
        campaign_name="VOLC | Trafego | Canario pausado",
        adset_name="BR | LPV | Automatico",
        creative_name="Criativo estatico v1",
        ad_name="Anuncio estatico v1",
        destination_url="https://example.com/oferta/",
        page_ref="metapage_exemplo",
        asset_ref="metaasset_exemplo",
        message="Descubra as informacoes importantes antes de decidir.",
        headline="Entenda como funciona",
        description="Conteudo informativo e independente.",
        daily_budget_minor=1000,
        start_time=datetime(2027, 1, 2, 12, 0, tzinfo=timezone.utc),
        special_ad_categories=(),
        special_categories_confirmed=True,
    )
    return replace(base, **mudancas)


def referencias() -> ReferenciasMetaResolvidas:
    return ReferenciasMetaResolvidas(
        account_id="1234567890",
        page_id="2222222222",
        image_hash="imagemHash_123456",
    )


def compilado(**mudancas: object):
    return compilar_plano_pausado(plano(**mudancas), referencias())


def autorizacao(plano_sha256: str, **mudancas: object) -> AutorizacaoMeta:
    base = AutorizacaoMeta(
        plano_sha256=plano_sha256,
        ator="operador@example.com",
        approval_id="approval_meta_01",
        permitir_validate_only=True,
        permitir_criar_pausada=True,
    )
    return replace(base, **mudancas)


def formulario(request: httpx.Request) -> dict[str, str]:
    return {chave: valores[-1] for chave, valores in parse_qs(
        request.content.decode("utf-8"), keep_blank_values=True).items()}


def resposta_lida(nome: str, identificador: str) -> dict[str, object]:
    nomes = {
        "campaign": "VOLC | Trafego | Canario pausado",
        "adset": "BR | LPV | Automatico",
        "creative": "Criativo estatico v1",
        "ad": "Anuncio estatico v1",
    }
    comum: dict[str, object] = {
        "id": identificador,
        "account_id": "1234567890",
        "name": nomes[nome],
    }
    if nome == "campaign":
        comum.update({
            "objective": "OUTCOME_TRAFFIC",
            "status": "PAUSED",
            "configured_status": "PAUSED",
            "effective_status": "PAUSED",
            "special_ad_categories": [],
            "advantage_state_info": {"advantage_state": "DISABLED"},
        })
    elif nome == "adset":
        comum.update({
            "campaign_id": "1001",
            "daily_budget": "1000",
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "LANDING_PAGE_VIEWS",
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "destination_type": "WEBSITE",
            "status": "PAUSED",
            "configured_status": "PAUSED",
            "effective_status": "PAUSED",
        })
    elif nome == "creative":
        comum.update({"status": "ACTIVE", "effective_status": "ACTIVE"})
    else:
        comum.update({
            "campaign_id": "1001",
            "adset_id": "1002",
            "creative": {"id": "1003"},
            "status": "PAUSED",
            "configured_status": "PAUSED",
            "effective_status": "PAUSED",
        })
    return comum


def transport_sucesso(registro: list[tuple[str, str, dict[str, str]]]) -> httpx.MockTransport:
    ids = {"campaigns": "1001", "adsets": "1002", "adcreatives": "1003", "ads": "1004"}
    tipos = {"1001": "campaign", "1002": "adset", "1003": "creative", "1004": "ad"}

    async def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url)
        if request.method == "POST":
            dados = formulario(request)
            edge = request.url.path.rsplit("/", 1)[-1]
            registro.append(("POST", edge, dados))
            if "execution_options" in dados:
                assert json.loads(dados["execution_options"]) == ["validate_only"]
                return httpx.Response(200, json={"success": True})
            return httpx.Response(200, json={"id": ids[edge]})
        identificador = request.url.path.rsplit("/", 1)[-1]
        registro.append(("GET", tipos[identificador], {}))
        return httpx.Response(200, json=resposta_lida(tipos[identificador], identificador))

    return httpx.MockTransport(responder)


def test_compilador_produz_receita_estreita_pausada_e_sem_vazamento() -> None:
    saida = compilado()
    assert [op.nome for op in saida.operacoes] == ["campaign", "adset", "creative", "ad"]
    campanha, conjunto, criativo, anuncio = saida.operacoes
    assert campanha.payload["status"] == "PAUSED"
    assert "daily_budget" not in campanha.payload
    assert conjunto.payload["daily_budget"] == 1000
    assert conjunto.payload["status"] == "PAUSED"
    assert "publisher_platforms" not in conjunto.payload["targeting"]
    assert "promoted_object" not in conjunto.payload
    assert "status" not in criativo.payload
    assert anuncio.payload["status"] == "PAUSED"
    assert saida.plano_sha256 == compilado().plano_sha256
    publico = json.dumps(saida.publico(), ensure_ascii=False)
    assert "1234567890" not in publico
    assert "2222222222" not in publico
    assert "imagemHash_123456" not in publico
    assert "/act_<conta>/campaigns" in publico


@pytest.mark.parametrize(
    ("mudancas", "codigo"),
    [
        ({"objective": "OUTCOME_SALES"}, "META_RECIPE_NOT_PROVEN"),
        ({"daily_budget_minor": 10.5}, "META_BUDGET_INVALID"),
        ({"daily_budget_minor": True}, "META_BUDGET_INVALID"),
        ({"placements_mode": "MANUAL"}, "META_PLACEMENT_RECIPE_UNPROVEN"),
        ({"promoted_object": {"pixel_id": "1"}}, "META_MEASUREMENT_RECIPE_UNPROVEN"),
        ({"advantage_audience": True}, "META_ADVANTAGE_AUDIENCE_UNPROVEN"),
        ({"special_categories_confirmed": False}, "META_SPECIAL_CATEGORY_NOT_CONFIRMED"),
        ({"special_ad_categories": ("CREDIT",)}, "META_SPECIAL_CATEGORY_RECIPE_UNPROVEN"),
    ],
)
def test_contrato_recusa_receitas_nao_provadas(mudancas: dict[str, object], codigo: str) -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        plano(**mudancas)
    assert erro.value.codigo == codigo


def test_autorizacao_e_vinculada_a_hash_e_ato_exatos() -> None:
    saida = compilado()
    with pytest.raises(ErroDeNascimentoMeta) as divergente:
        autorizacao("0" * 64).exigir(plano_sha256=saida.plano_sha256, ato="create_paused")
    assert divergente.value.codigo == "META_APPROVED_PLAN_DIVERGED"
    with pytest.raises(ErroDeNascimentoMeta) as negada:
        autorizacao(saida.plano_sha256, permitir_criar_pausada=False).exigir(
            plano_sha256=saida.plano_sha256, ato="create_paused")
    assert negada.value.codigo == "META_ACTION_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_validate_only_valida_apenas_raizes_independentes_sem_criar() -> None:
    registros: list[tuple[str, str, dict[str, str]]] = []
    async with httpx.AsyncClient(transport=transport_sucesso(registros)) as cliente:
        saida = compilado()
        resultado = await ExecutorMetaPausado(cliente).validar_raizes(
            saida, SegredoEfemero(TOKEN), autorizacao(saida.plano_sha256))
    assert resultado.aceito is True
    assert resultado.cobertura == "INDEPENDENT_ROOTS_ONLY"
    assert resultado.operacoes_validadas == ("campaign", "creative")
    assert resultado.operacoes_dependentes_pendentes == ("adset", "ad")
    assert [(metodo, edge) for metodo, edge, _ in registros] == [
        ("POST", "campaigns"), ("POST", "adcreatives")]
    assert all("execution_options" in dados for _, _, dados in registros)


@pytest.mark.asyncio
async def test_saga_valida_cria_e_confere_cada_degrau_em_ordem() -> None:
    registros: list[tuple[str, str, dict[str, str]]] = []
    diario = RegistroEmMemoria()
    async with httpx.AsyncClient(transport=transport_sucesso(registros)) as cliente:
        saida = compilado()
        resultado = await ExecutorMetaPausado(cliente, registro=diario).criar_pausada(
            saida, SegredoEfemero(TOKEN), autorizacao(saida.plano_sha256))
    assert [(metodo, edge) for metodo, edge, _ in registros] == [
        ("POST", "campaigns"), ("POST", "campaigns"), ("GET", "campaign"),
        ("POST", "adsets"), ("POST", "adsets"), ("GET", "adset"),
        ("POST", "adcreatives"), ("POST", "adcreatives"), ("GET", "creative"),
        ("POST", "ads"), ("POST", "ads"), ("GET", "ad"),
    ]
    posts_reais = [dados for metodo, _, dados in registros if metodo == "POST" and "execution_options" not in dados]
    assert posts_reais[0]["status"] == "PAUSED"
    assert posts_reais[1]["status"] == "PAUSED"
    assert posts_reais[1]["campaign_id"] == "1001"
    assert "status" not in posts_reais[2]
    assert posts_reais[3]["status"] == "PAUSED"
    assert posts_reais[3]["adset_id"] == "1002"
    assert json.loads(posts_reais[3]["creative"])["creative_id"] == "1003"
    assert resultado.desfecho == "CREATED_PAUSED"
    assert resultado.retry_permitido is False
    assert diario.eventos == [
        ("preparar", "campaign"), ("fechar", "campaign"),
        ("preparar", "adset"), ("fechar", "adset"),
        ("preparar", "creative"), ("fechar", "creative"),
        ("preparar", "ad"), ("fechar", "ad"),
    ]
    assert set(resultado.referencias_opacas) == {"campaign", "adset", "creative", "ad"}
    serializado = json.dumps({
        "refs": resultado.referencias_opacas,
        "read_back": resultado.read_back,
    })
    for cru in ("1234567890", "1001", "1002", "1003", "1004", TOKEN):
        assert cru not in serializado


@pytest.mark.asyncio
async def test_timeout_na_criacao_e_ambiguo_e_nunca_autoriza_retry() -> None:
    chamadas = 0

    async def responder(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        if chamadas == 1:
            return httpx.Response(200, json={"success": True})
        raise httpx.ReadTimeout("tempo esgotado", request=request)

    diario = RegistroEmMemoria()
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        saida = compilado()
        with pytest.raises(ErroRemotoMeta) as erro:
            await ExecutorMetaPausado(cliente, registro=diario).criar_pausada(
                saida, SegredoEfemero(TOKEN), autorizacao(saida.plano_sha256))
    assert erro.value.codigo == "META_REMOTE_RESULT_AMBIGUOUS"
    assert erro.value.retryable is False
    assert chamadas == 2
    assert diario.eventos == [("preparar", "campaign"), ("ambiguo", "campaign")]


@pytest.mark.asyncio
async def test_read_back_ativo_interrompe_saga_antes_do_adset() -> None:
    chamadas: list[str] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.method)
        if request.method == "POST" and "execution_options" in formulario(request):
            return httpx.Response(200, json={"success": True})
        if request.method == "POST":
            return httpx.Response(200, json={"id": "1001"})
        dados = resposta_lida("campaign", "1001")
        dados["configured_status"] = "ACTIVE"
        dados["status"] = "ACTIVE"
        return httpx.Response(200, json=dados)

    diario = RegistroEmMemoria()
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        saida = compilado()
        with pytest.raises(ErroRemotoMeta) as erro:
            await ExecutorMetaPausado(cliente, registro=diario).criar_pausada(
                saida, SegredoEfemero(TOKEN), autorizacao(saida.plano_sha256))
    assert erro.value.codigo == "META_READBACK_DIVERGENT"
    assert erro.value.retryable is False
    assert erro.value.objetos_criados == ("campaign",)
    assert chamadas == ["POST", "POST", "GET"]


@pytest.mark.asyncio
async def test_criacao_sem_recibo_duravel_falha_antes_da_rede() -> None:
    chamadas = 0

    async def responder(request: httpx.Request) -> httpx.Response:
        nonlocal chamadas
        chamadas += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        saida = compilado()
        with pytest.raises(ErroDeNascimentoMeta) as erro:
            await ExecutorMetaPausado(cliente).criar_pausada(
                saida, SegredoEfemero(TOKEN), autorizacao(saida.plano_sha256))
    assert erro.value.codigo == "META_DURABLE_RECEIPT_UNAVAILABLE"
    assert chamadas == 0


@pytest.mark.asyncio
async def test_retomada_de_passo_criado_nao_repete_post_real() -> None:
    registros: list[tuple[str, str, dict[str, str]]] = []
    diario = RegistroEmMemoria({"campaign": "1001"})
    async with httpx.AsyncClient(transport=transport_sucesso(registros)) as cliente:
        saida = compilado()
        await ExecutorMetaPausado(cliente, registro=diario).criar_pausada(
            saida, SegredoEfemero(TOKEN), autorizacao(saida.plano_sha256))
    posts_campaign = [
        dados for metodo, edge, dados in registros
        if metodo == "POST" and edge == "campaigns"
    ]
    assert len(posts_campaign) == 1
    assert "execution_options" in posts_campaign[0]


def test_executor_recusa_host_e_versao_nao_fixados() -> None:
    cliente = httpx.AsyncClient()
    with pytest.raises(ValueError):
        ExecutorMetaPausado(cliente, base_url="https://example.com")
    with pytest.raises(ValueError):
        ExecutorMetaPausado(cliente, api_version="v25.0")
