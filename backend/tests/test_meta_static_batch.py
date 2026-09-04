from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta import dominio as meta_dom
from app.trafego.meta_execucao.ativos import ResolvedorAtivosMeta
from app.trafego.meta_execucao.compilador import compilar_plano_pausado
from app.trafego.meta_execucao.contrato import (
    AutorizacaoMeta,
    ErroDeNascimentoMeta,
    PlanoMetaPausado,
    ReferenciasMetaResolvidas,
    VariacaoEstaticaMeta,
)
from app.trafego.meta_execucao.executor import ExecutorMetaPausado
from app.trafego.meta_execucao.registro import PassoPreparadoMeta


TOKEN = "token-hermetico-nao-registrar"


def _variacao(indice: int, *, asset_ref: str | None = None) -> VariacaoEstaticaMeta:
    return VariacaoEstaticaMeta(
        variation_key=f"v{indice}",
        creative_name=f"Criativo {indice}",
        ad_name=f"Anuncio {indice}",
        asset_ref=asset_ref or f"metaasset_{indice}",
        message=f"Mensagem {indice}",
        headline=f"Titulo {indice}",
        description=f"Descricao {indice}",
    )


def _plano(*variacoes: VariacaoEstaticaMeta) -> PlanoMetaPausado:
    return PlanoMetaPausado(
        account_ref="metaacct_exemplo",
        campaign_name="Campanha lote pausada",
        adset_name="Conjunto lote pausado",
        creative_name="Criativo legado",
        ad_name="Anuncio legado",
        destination_url="https://example.com/conteudo/",
        page_ref="metapage_exemplo",
        asset_ref="metaasset_legado",
        message="Mensagem legada",
        headline="Titulo legado",
        description="Descricao legada",
        daily_budget_minor=1000,
        start_time=datetime(2027, 1, 2, 12, 0, tzinfo=timezone.utc),
        special_ad_categories=(),
        special_categories_confirmed=True,
        is_adset_budget_sharing_enabled=False,
        variacoes_estaticas=tuple(variacoes),
    )


def _refs(quantidade: int = 0) -> ReferenciasMetaResolvidas:
    return ReferenciasMetaResolvidas(
        account_id="1234567890",
        page_id="2222222222",
        image_hash="hash_legado_123",
        image_hashes_by_ref={
            f"metaasset_{indice}": f"hash_lote_{indice:03d}"
            for indice in range(1, quantidade + 1)
        },
    )


def _form(request: httpx.Request) -> dict[str, str]:
    return {
        chave: valores[-1]
        for chave, valores in parse_qs(
            request.content.decode("utf-8"), keep_blank_values=True
        ).items()
    }


class _Registro:
    def __init__(self) -> None:
        self.eventos: list[tuple[str, str]] = []

    async def preparar_passo(
        self, *, plano_sha256: str, approval_id: str, ator: str,
        nome: str, payload_sha256: str,
    ) -> PassoPreparadoMeta:
        self.eventos.append(("preparar", nome))
        return PassoPreparadoMeta(f"passo_{len(self.eventos)}", "DESPACHAR")

    async def fechar_passo(self, *, passo_ref: str, id_externo: str) -> None:
        self.eventos.append(("fechar", id_externo))

    async def marcar_ambiguo(self, *, passo_ref: str) -> None:
        self.eventos.append(("ambiguo", passo_ref))

    async def falhar_passo(self, *, passo_ref: str, codigo: str) -> None:
        self.eventos.append(("falhar", codigo))


def _autorizacao(hash_plano: str) -> AutorizacaoMeta:
    return AutorizacaoMeta(
        plano_sha256=hash_plano,
        ator="operador@example.com",
        approval_id="approval_batch_01",
        permitir_validate_only=True,
        permitir_criar_pausada=True,
    )


def test_lote_compila_chaves_tipos_dependencias_e_hashes_sem_quebrar_singular() -> None:
    singular = compilar_plano_pausado(_plano(), _refs())
    assert [op.chave for op in singular.operacoes] == [
        "campaign", "adset", "creative", "ad"]
    assert [op.tipo_objeto for op in singular.operacoes] == [
        "campaign", "adset", "creative", "ad"]

    lote = compilar_plano_pausado(_plano(_variacao(1), _variacao(2)), _refs(2))
    assert [op.chave for op in lote.operacoes] == [
        "campaign", "adset", "creative:v1", "ad:v1", "creative:v2", "ad:v2"]
    assert [op.tipo_objeto for op in lote.operacoes] == [
        "campaign", "adset", "creative", "ad", "creative", "ad"]
    assert lote.operacoes[3].depende_de == ("adset", "creative:v1")
    assert lote.operacoes[5].payload["creative"] == {"creative_id": "$creative:v2.id"}
    assert (
        lote.operacoes[2].payload["object_story_spec"]["link_data"]["image_hash"]
        == "hash_lote_001"
    )
    assert lote.plano_sha256 == compilar_plano_pausado(
        _plano(_variacao(1), _variacao(2)), _refs(2)).plano_sha256
    assert lote.plano_sha256 != compilar_plano_pausado(
        _plano(_variacao(2), _variacao(1)), _refs(2)).plano_sha256
    assert all(
        op.payload.get("status") == "PAUSED"
        for op in lote.operacoes if op.tipo_objeto in {"campaign", "adset", "ad"}
    )


def test_lote_recusa_limite_duplicata_e_referencia_nao_resolvida() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as limite:
        _plano(*(_variacao(i) for i in range(1, 12)))
    assert limite.value.codigo == "META_STATIC_BATCH_LIMIT_EXCEEDED"

    with pytest.raises(ErroDeNascimentoMeta) as duplicata:
        _plano(_variacao(1), replace(_variacao(2), ad_name="Anuncio 1"))
    assert duplicata.value.codigo == "META_STATIC_BATCH_DUPLICATE_NAME"

    with pytest.raises(ErroDeNascimentoMeta) as nao_resolvida:
        compilar_plano_pausado(_plano(_variacao(1), _variacao(2)), _refs(1))
    assert nao_resolvida.value.codigo == "META_ASSET_REFERENCE_UNRESOLVED"


@pytest.mark.asyncio
async def test_resolvedor_lote_le_inventario_uma_vez_e_resolve_refs_opacas() -> None:
    chamadas: list[str] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        if request.url.path.endswith("/me/adaccounts"):
            return httpx.Response(200, json={"data": [{
                "id": "act_1234567890", "name": "Conta", "currency": "BRL",
                "account_status": 1,
            }]})
        if request.url.path.endswith("/promote_pages"):
            return httpx.Response(200, json={"data": [{"id": "2222222222", "name": "Pagina"}]})
        if request.url.path.endswith("/adimages"):
            return httpx.Response(200, json={"data": [
                {"hash": "hash_lote_001", "name": "Um"},
                {"hash": "hash_lote_002", "name": "Dois"},
            ]})
        if request.url.path.endswith("/advideos"):
            return httpx.Response(200, json={"data": [
                {"id": "55443322", "name": "Video existente",
                 "picture": "https://scontent.example.fbcdn.net/thumb.jpg"},
            ]})
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        resolvedor = ResolvedorAtivosMeta(cliente)
        inventario = await resolvedor.inventariar(
            meta_dom.referencia_opaca_conta("1234567890"), SegredoEfemero(TOKEN))
        # Use the exact opaque handles derived by the domain implementation.
        asset_refs = tuple(item["referencia_opaca"] for item in inventario["imagens"])
        page_ref = inventario["paginas"][0]["referencia_opaca"]
        chamadas.clear()
        resolvidas = await resolvedor.resolver_lote(
            account_ref=inventario["account_ref"],
            page_ref=page_ref,
            asset_refs=asset_refs,
            segredo=SegredoEfemero(TOKEN),
        )
    assert set(resolvidas.image_hashes_by_ref) == set(asset_refs)
    assert set(resolvidas.image_hashes_by_ref.values()) == {
        "hash_lote_001", "hash_lote_002"}
    assert sum(path.endswith("/adimages") for path in chamadas) == 1


@pytest.mark.asyncio
async def test_validate_only_do_lote_valida_campaign_e_todos_criativos_sem_create() -> None:
    chamadas: list[tuple[str, str]] = []

    async def responder(request: httpx.Request) -> httpx.Response:
        dados = _form(request)
        chamadas.append((request.url.path.rsplit("/", 1)[-1], dados.get("name", "")))
        assert json.loads(dados["execution_options"]) == ["validate_only"]
        return httpx.Response(200, json={"success": True})

    compilado = compilar_plano_pausado(
        _plano(_variacao(1), _variacao(2), _variacao(3)), _refs(3))
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        resultado = await ExecutorMetaPausado(cliente).validar_raizes(
            compilado, SegredoEfemero(TOKEN), _autorizacao(compilado.plano_sha256))
    assert resultado.operacoes_validadas == (
        "campaign", "creative:v1", "creative:v2", "creative:v3")
    assert resultado.operacoes_dependentes_pendentes == (
        "adset", "ad:v1", "ad:v2", "ad:v3")
    assert [edge for edge, _ in chamadas] == [
        "campaigns", "adcreatives", "adcreatives", "adcreatives"]


@pytest.mark.asyncio
async def test_executor_lote_resolve_cada_criativo_e_readback_por_tipo() -> None:
    criados: dict[str, tuple[str, dict[str, str]]] = {}
    contadores = {"campaigns": 1000, "adsets": 2000, "adcreatives": 3000, "ads": 4000}

    async def responder(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            dados = _form(request)
            if "execution_options" in dados:
                return httpx.Response(200, json={"success": True})
            edge = request.url.path.rsplit("/", 1)[-1]
            contadores[edge] += 1
            identificador = str(contadores[edge])
            criados[identificador] = (edge, dados)
            return httpx.Response(200, json={"id": identificador})
        identificador = request.url.path.rsplit("/", 1)[-1]
        edge, dados = criados[identificador]
        base: dict[str, object] = {
            "id": identificador, "name": dados["name"], "account_id": "1234567890"}
        if edge == "campaigns":
            base.update({
                "objective": "OUTCOME_TRAFFIC", "buying_type": "AUCTION", "status": "PAUSED",
                "configured_status": "PAUSED", "effective_status": "PAUSED",
                "special_ad_categories": [], "is_adset_budget_sharing_enabled": False,
            })
        elif edge == "adsets":
            base.update({
                "campaign_id": dados["campaign_id"], "daily_budget": dados["daily_budget"],
                "billing_event": dados["billing_event"],
                "optimization_goal": dados["optimization_goal"],
                "bid_strategy": dados["bid_strategy"],
                "start_time": dados["start_time"],
                "targeting": json.loads(dados["targeting"]),
                "status": "PAUSED", "configured_status": "PAUSED", "effective_status": "PAUSED",
            })
        elif edge == "adcreatives":
            base.update({
                "status": "ACTIVE", "effective_status": "ACTIVE",
                "object_story_spec": json.loads(dados["object_story_spec"]),
            })
        else:
            base.update({
                "adset_id": dados["adset_id"],
                "creative": {"id": json.loads(dados["creative"])["creative_id"]},
                "status": "PAUSED", "configured_status": "PAUSED", "effective_status": "PAUSED",
            })
        return httpx.Response(200, json=base)

    compilado = compilar_plano_pausado(
        _plano(_variacao(1), _variacao(2)), _refs(2))
    registro = _Registro()
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        resultado = await ExecutorMetaPausado(cliente, registro=registro).criar_pausada(
            compilado, SegredoEfemero(TOKEN), _autorizacao(compilado.plano_sha256))
    assert set(resultado.referencias_opacas) == {
        "campaign", "adset", "creative:v1", "ad:v1", "creative:v2", "ad:v2"}
    anuncios = [dados for edge, dados in criados.values() if edge == "ads"]
    assert [json.loads(item["creative"])["creative_id"] for item in anuncios] == [
        "3001", "3002"]
    assert all(item["status"] == "PAUSED" for item in anuncios)
    assert [evento for evento in registro.eventos if evento[0] == "preparar"] == [
        ("preparar", "campaign"), ("preparar", "adset"),
        ("preparar", "creative:v1"), ("preparar", "ad:v1"),
        ("preparar", "creative:v2"), ("preparar", "ad:v2"),
    ]
