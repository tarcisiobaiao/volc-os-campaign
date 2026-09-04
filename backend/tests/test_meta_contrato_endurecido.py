"""Provas do endurecimento do contrato Meta v26 desta rodada.

Cada teste aqui existe por causa de uma evidência oficial ou de um defeito
adjudicado, não por simetria de cobertura:

* `destination_type` não pertence a OUTCOME_TRAFFIC — a tabela oficial lista
  apenas UNDEFINED, MESSENGER, WHATSAPP e PHONE_CALL para esse objetivo.
  https://developers.facebook.com/docs/marketing-api/adset/destination_type/
* `targeting_automation.advantage_audience` assume 1 desde a v23.0 quando o Ad
  Set nasce sem o campo, então omitir liga o Advantage+ em silêncio.
  https://developers.facebook.com/docs/marketing-api/audiences/reference/targeting-expansion/advantage-audience/
* marcador de dependência em texto do operador trocaria o payload aprovado;
* recusa da Meta é FALHA provada, o resto é AMBÍGUO;
* texto do provedor não pode carregar segredo nem ativo opaco.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.compilador import (
    compilar_plano_pausado,
    resolver_dependencias,
)
from app.trafego.meta_execucao.contrato import (
    AutorizacaoMeta,
    ErroDeNascimentoMeta,
    PlanoMetaPausado,
    ReferenciasMetaResolvidas,
)
from app.trafego.meta_execucao.executor import (
    ErroRemotoMeta,
    ExecutorMetaPausado,
    _texto_seguro_do_provedor,
)
from app.trafego.meta_execucao.registro import PassoPreparadoMeta


TOKEN = "token-hermetico-nao-registrar"


def _plano(**mudancas: object) -> PlanoMetaPausado:
    base: dict[str, object] = dict(
        account_ref="metaacct_exemplo",
        campaign_name="Campanha endurecida",
        adset_name="Conjunto endurecido",
        creative_name="Criativo endurecido",
        ad_name="Anuncio endurecido",
        destination_url="https://example.com/oferta/",
        page_ref="metapage_exemplo",
        asset_ref="metaasset_exemplo",
        message="Mensagem do canario",
        headline="Titulo do canario",
        description="Descricao do canario",
        daily_budget_minor=1000,
        start_time=datetime(2027, 1, 2, 12, 0, tzinfo=timezone.utc),
        special_ad_categories=(),
        special_categories_confirmed=True,
        is_adset_budget_sharing_enabled=False,
    )
    base.update(mudancas)
    return PlanoMetaPausado(**base)  # type: ignore[arg-type]


def _refs() -> ReferenciasMetaResolvidas:
    return ReferenciasMetaResolvidas(
        account_id="1234567890", page_id="2222222222", image_hash="imagemHash_123456")


class _Registro:
    def __init__(self) -> None:
        self.eventos: list[tuple[str, str]] = []

    async def preparar_passo(
        self, *, plano_sha256: str, approval_id: str, ator: str,
        nome: str, payload_sha256: str,
    ) -> PassoPreparadoMeta:
        self.eventos.append(("preparar", nome))
        return PassoPreparadoMeta("passo_1", "DESPACHAR")

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
        approval_id="approval_endurecido",
        permitir_validate_only=True,
        permitir_criar_pausada=True,
    )


def test_adset_de_trafego_nao_envia_destination_type_invalido() -> None:
    conjunto = compilar_plano_pausado(_plano(), _refs()).operacoes[1]
    assert conjunto.payload["optimization_goal"] == "LANDING_PAGE_VIEWS"
    assert "destination_type" not in conjunto.payload


@pytest.mark.parametrize(("escolha", "esperado"), [(False, 0), (True, 1)])
def test_advantage_audience_viaja_sempre_explicito(escolha: bool, esperado: int) -> None:
    conjunto = compilar_plano_pausado(
        _plano(advantage_audience=escolha), _refs()).operacoes[1]
    automacao = conjunto.payload["targeting"]["targeting_automation"]
    assert automacao["advantage_audience"] == esperado


def test_advantage_audience_omitido_no_contrato_e_recusa_explicita() -> None:
    # A ausência não pode virar "a Meta decide": o padrão do contrato é 0.
    conjunto = compilar_plano_pausado(_plano(), _refs()).operacoes[1]
    assert conjunto.payload["targeting"]["targeting_automation"] == {
        "advantage_audience": 0}
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano(advantage_audience=None)
    assert erro.value.codigo == "META_ADVANTAGE_AUDIENCE_INVALID"


def test_advantage_audience_entra_no_hash_do_plano() -> None:
    recusado = compilar_plano_pausado(_plano(advantage_audience=False), _refs())
    aceito = compilar_plano_pausado(_plano(advantage_audience=True), _refs())
    assert recusado.plano_sha256 != aceito.plano_sha256


def test_texto_do_operador_nao_pode_imitar_marcador_de_dependencia() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        _plano(adset_name="$campaign.id")
    assert erro.value.codigo == "META_PLACEHOLDER_SYNTAX_RESERVED"


def test_resolucao_toca_apenas_caminhos_estruturais() -> None:
    payload = {
        "name": "Anuncio",
        "adset_id": "$adset.id",
        "creative": {"creative_id": "$creative:v1.id"},
        # Texto livre com a mesma sintaxe jamais pode ser substituído.
        "url_tags": "utm_campaign=x",
    }
    resolvido = resolver_dependencias(
        payload, {"adset": "2002", "creative:v1": "3003"})
    assert resolvido["adset_id"] == "2002"
    assert resolvido["creative"]["creative_id"] == "3003"
    assert resolvido["url_tags"] == "utm_campaign=x"


def test_payload_com_marcador_pendente_nao_sai_do_processo() -> None:
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        resolver_dependencias({"name": "$adset.id", "adset_id": "$adset.id"}, {"adset": "1"})
    assert erro.value.codigo == "META_UNRESOLVED_DEPENDENCY"


@pytest.mark.parametrize(
    ("status", "evento"),
    [(400, "falhar"), (500, "ambiguo")],
)
@pytest.mark.asyncio
async def test_apenas_recusa_da_meta_marca_passo_como_falho(
    status: int, evento: str,
) -> None:
    async def responder(request: httpx.Request) -> httpx.Response:
        if b"execution_options" in request.content:
            return httpx.Response(200, json={"success": True})
        return httpx.Response(status, json={"error": {
            "code": 100, "message": "recusa hermetica"}})

    compilado = compilar_plano_pausado(_plano(), _refs())
    registro = _Registro()
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        with pytest.raises(ErroRemotoMeta):
            await ExecutorMetaPausado(cliente, registro=registro).criar_pausada(
                compilado, SegredoEfemero(TOKEN), _autorizacao(compilado.plano_sha256))
    assert [nome for nome, _ in registro.eventos if nome in {"falhar", "ambiguo"}] == [evento]


@pytest.mark.asyncio
async def test_resposta_sem_id_deixa_o_passo_ambiguo() -> None:
    async def responder(request: httpx.Request) -> httpx.Response:
        if b"execution_options" in request.content:
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"nao_e_id": "?"})

    compilado = compilar_plano_pausado(_plano(), _refs())
    registro = _Registro()
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        with pytest.raises(ErroRemotoMeta):
            await ExecutorMetaPausado(cliente, registro=registro).criar_pausada(
                compilado, SegredoEfemero(TOKEN), _autorizacao(compilado.plano_sha256))
    assert ("ambiguo", "passo_1") in registro.eventos
    assert all(nome != "falhar" for nome, _ in registro.eventos)


@pytest.mark.parametrize("bruto", [
    "Bearer EAABsbCS1iHgBO7ZC8ZDZDdeadbeefdeadbeef",
    "access_token=EAABsbCS1iHgBO7ZC8ZDZDdeadbeef",
    "access token: EAABsbCS1iHgBO7ZC8ZDZDdeadbeef",
    "image_hash 8f2b1c9e4a7d6b3f0c5e8a1d4b7f2c9e6a3d0b5f",
])
def test_texto_do_provedor_nunca_carrega_segredo_nem_ativo_opaco(bruto: str) -> None:
    saida = _texto_seguro_do_provedor(bruto) or ""
    assert "EAABsbCS1iHgBO7ZC8ZDZDdeadbeef" not in saida
    assert "8f2b1c9e4a7d6b3f0c5e8a1d4b7f2c9e6a3d0b5f" not in saida
    assert "[redacted]" in saida


def test_manifesto_de_passos_espelha_o_plano_e_serve_a_migration() -> None:
    """O `steps_expected` da aprovação durável nasce do plano, não da mão.

    A migration candidata recusa preparar um passo fora do manifesto; se a
    futura rota de aprovação montasse a lista sozinha, ela poderia autorizar um
    conjunto diferente do que o operador conferiu.
    """
    from app.trafego.meta_execucao.contrato import VariacaoEstaticaMeta

    singular = compilar_plano_pausado(_plano(), _refs())
    assert singular.manifesto_de_passos == ("campaign", "adset", "creative", "ad")

    variacoes = tuple(
        VariacaoEstaticaMeta(
            variation_key=f"v{i}", creative_name=f"Criativo {i}", ad_name=f"Anuncio {i}",
            asset_ref="metaasset_exemplo", message=f"Mensagem {i}",
            headline=f"Titulo {i}", description=f"Descricao {i}",
        )
        for i in (1, 2)
    )
    lote = compilar_plano_pausado(_plano(variacoes_estaticas=variacoes), _refs())
    assert lote.manifesto_de_passos == (
        "campaign", "adset", "creative:v1", "ad:v1", "creative:v2", "ad:v2")
    # Sem repetição e dentro do limite que a migration aceita.
    assert len(set(lote.manifesto_de_passos)) == len(lote.manifesto_de_passos)
    assert 1 <= len(lote.manifesto_de_passos) <= 22


@pytest.mark.parametrize(
    ("lido", "enviado", "igual"),
    [
        ("https://example.com/oferta/", "https://example.com/oferta", True),
        ("https://EXAMPLE.com/oferta", "https://example.com/oferta/", True),
        ("https://example.com/oferta?x=1", "https://example.com/oferta?x=1", True),
        ("https://example.com/outra", "https://example.com/oferta", False),
        ("https://outro.com/oferta", "https://example.com/oferta", False),
        ("https://example.com/oferta?x=2", "https://example.com/oferta?x=1", False),
        ("", "https://example.com/oferta", False),
        (None, "https://example.com/oferta", False),
    ],
)
def test_destino_do_readback_tolera_normalizacao_sem_afrouxar(
    lido: object, enviado: str, igual: bool,
) -> None:
    """A Meta pode devolver a barra final normalizada; destino diferente, não."""
    from app.trafego.meta_execucao.executor import _mesmo_destino

    assert _mesmo_destino(lido, enviado) is igual
