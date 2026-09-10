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

import imagens_meta

from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao.compilador import (
    compilar_plano_pausado,
    resolver_dependencias,
)
from app.trafego.meta_execucao.contrato import (
    DESTINO_SHOP_CONTA_NAO_ELEGIVEL,
    AutorizacaoMeta,
    ErroDeNascimentoMeta,
    ManifestoSupplyMeta,
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
    manifesto = ManifestoSupplyMeta(
        asset_ref="metaasset_exemplo", content_sha256="a" * 64,
        item_sha256="a" * 64, supply_sha256="b" * 64,
        policy_receipt_ref="metapolicy_" + "c" * 24,
        policy_state="AUTHORIZED", policy_expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        lifecycle="READY_FOR_PAID_MEDIA", provider_image_hash="imagemHash_123456",
        mime_type="image/png", width=1080, height=1080,
    )
    return ReferenciasMetaResolvidas(
        account_id="1234567890", page_id="2222222222", image_hash="imagemHash_123456",
        page_permission_proven=True, placement_identity_mode="FACEBOOK_ONLY_PAGE_PROVEN",
        shop_redirect_proof=DESTINO_SHOP_CONTA_NAO_ELEGIVEL,
        asset_supply_manifests={"metaasset_exemplo": manifesto})


class _Registro:
    """Dublê mínimo do ledger — e mínimo NÃO quer dizer mais permissivo.

    ⚠️ Ele carrega o token de reivindicação e sabe gravar read-back porque o
    servidor passou a exigir as duas coisas: o executor recusa despachar com um
    ledger que não sabe registrar o que leu. Um dublê menos capaz que o único
    ledger do runtime faria os testes provarem um contrato que não existe.
    """

    def __init__(self) -> None:
        self.eventos: list[tuple[str, str]] = []

    async def preparar_passo(
        self, *, plano_sha256: str, approval_id: str, ator: str,
        nome: str, payload_sha256: str,
    ) -> PassoPreparadoMeta:
        self.eventos.append(("preparar", nome))
        return PassoPreparadoMeta("passo_1", "DESPACHAR", claim_token="claim_1")

    async def fechar_passo(
        self, *, passo_ref: str, id_externo: str, claim_token: str,
    ) -> str | None:
        assert claim_token, "fechar exige a reivindicacao vigente"
        self.eventos.append(("fechar", id_externo))
        return f"{claim_token}-girado"

    async def marcar_ambiguo(self, *, passo_ref: str, claim_token: str) -> None:
        self.eventos.append(("ambiguo", passo_ref))

    async def falhar_passo(
        self, *, passo_ref: str, codigo: str, claim_token: str,
    ) -> None:
        assert claim_token, "falhar exige a reivindicacao vigente"
        self.eventos.append(("falhar", codigo))

    async def registrar_readback(
        self, *, passo_ref: str, evidencia: dict, codigo: str | None = None,
        claim_token: str | None = None,
    ) -> None:
        # A evidência positiva e a divergente são fatos opostos; confundi-las
        # aqui deixaria passar uma correção que grava a errada.
        assert evidencia["matched"] is (codigo is None)
        self.eventos.append(("readback", passo_ref))


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


def test_recibo_de_politica_expirado_nao_compila() -> None:
    manifesto = ManifestoSupplyMeta(
        asset_ref="metaasset_exemplo", content_sha256="a" * 64,
        item_sha256="a" * 64, supply_sha256="b" * 64,
        policy_receipt_ref="metapolicy_" + "c" * 24,
        policy_state="AUTHORIZED",
        policy_expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        lifecycle="READY_FOR_PAID_MEDIA", provider_image_hash="imagemHash_123456",
        mime_type="image/png",
    )
    refs = ReferenciasMetaResolvidas(
        account_id="1234567890", page_id="2222222222",
        image_hash="imagemHash_123456", page_permission_proven=True,
        placement_identity_mode="FACEBOOK_ONLY_PAGE_PROVEN",
        shop_redirect_proof=DESTINO_SHOP_CONTA_NAO_ELEGIVEL,
        asset_supply_manifests={"metaasset_exemplo": manifesto},
    )
    with pytest.raises(ErroDeNascimentoMeta) as erro:
        compilar_plano_pausado(_plano(), refs)
    assert erro.value.codigo == "META_ASSET_POLICY_RECEIPT_EXPIRED"


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


@pytest.mark.asyncio
async def test_criacao_nunca_volta_como_repetivel_apos_despacho() -> None:
    """5xx numa CRIAÇÃO pode ter criado o objeto; repetir duplicaria a campanha."""
    async def responder(request: httpx.Request) -> httpx.Response:
        if b"execution_options" in request.content:
            return httpx.Response(200, json={"success": True})
        return httpx.Response(503, json={"error": {"code": 2, "message": "instabilidade"}})

    compilado = compilar_plano_pausado(_plano(), _refs())
    registro = _Registro()
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        with pytest.raises(ErroRemotoMeta) as erro:
            await ExecutorMetaPausado(cliente, registro=registro).criar_pausada(
                compilado, SegredoEfemero(TOKEN), _autorizacao(compilado.plano_sha256))
    assert erro.value.retryable is False
    assert erro.value.criacao_descartada is False
    assert ("ambiguo", "passo_1") in registro.eventos


@pytest.mark.asyncio
async def test_4xx_sem_erro_reconhecivel_da_meta_fica_ambiguo() -> None:
    """Um 400 de gateway, com corpo que não é erro Meta, não prova descarte."""
    async def responder(request: httpx.Request) -> httpx.Response:
        if b"execution_options" in request.content:
            return httpx.Response(200, json={"success": True})
        return httpx.Response(400, text="<html>Bad Request</html>")

    compilado = compilar_plano_pausado(_plano(), _refs())
    registro = _Registro()
    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        with pytest.raises(ErroRemotoMeta) as erro:
            await ExecutorMetaPausado(cliente, registro=registro).criar_pausada(
                compilado, SegredoEfemero(TOKEN), _autorizacao(compilado.plano_sha256))
    assert erro.value.criacao_descartada is False
    assert ("ambiguo", "passo_1") in registro.eventos
    assert all(nome != "falhar" for nome, _ in registro.eventos)


def test_sanitizacao_preserva_o_nome_do_campo_que_o_operador_precisa_corrigir() -> None:
    bruto = (
        "Invalid parameter: is_adset_budget_sharing_enabled must be true or false; "
        "token EAABsbCS1iHgBO7ZC8ZDZDdeadbeefdeadbeef"
    )
    saida = _texto_seguro_do_provedor(bruto) or ""
    assert "is_adset_budget_sharing_enabled" in saida
    assert "EAABsbCS1iHgBO7ZC8ZDZDdeadbeefdeadbeef" not in saida


@pytest.mark.parametrize(
    ("lido", "enviado", "igual"),
    [
        ("https://example.com:8443/a", "https://example.com/a", False),
        ("https://example.com:443/a", "https://example.com/a", True),
        ("https://example.com/a#um", "https://example.com/a#dois", False),
    ],
)
def test_destino_considera_porta_e_fragmento(lido: str, enviado: str, igual: bool) -> None:
    from app.trafego.meta_execucao.executor import _mesmo_destino

    assert _mesmo_destino(lido, enviado) is igual


@pytest.mark.asyncio
async def test_inventario_de_video_indisponivel_nao_derruba_a_receita_estatica() -> None:
    """Um token sem leitura de vídeo não pode impedir uma campanha de imagens."""
    from app.trafego.meta.credenciais import SegredoEfemero as Segredo
    from app.trafego.meta import dominio as meta_dom
    from app.trafego.meta_execucao.ativos import ResolvedorAtivosMeta
    from app.trafego.meta_execucao.contrato import DeclaracaoPoliticaAtivoMeta

    async def responder(request: httpx.Request) -> httpx.Response:
        caminho = request.url.path
        if caminho.endswith("/me/adaccounts"):
            return httpx.Response(200, json={"data": [{
                "id": "act_1234567890", "name": "Conta", "currency": "BRL",
                "account_status": 1}]})
        if caminho.endswith("/promote_pages"):
            return httpx.Response(200, json={"data": [{"id": "2222222222", "name": "Pagina"}]})
        if caminho.endswith("/adimages"):
            return httpx.Response(200, json={"data": [{
                "hash": "hash_um", "name": "Um",
                "url": "https://preview.example.fbcdn.net/hash_um.png",
            }]})
        if caminho.endswith("/advideos"):
            return httpx.Response(403, json={"error": {"code": 200, "message": "sem permissao"}})
        if request.url.host.endswith(".fbcdn.net"):
            # ⚠️ Imagem DE VERDADE: a fixture antiga não decodificava e o
            # caminho feliz media a ausência do gate, não o gate.
            return httpx.Response(200, content=imagens_meta.png(1080, 1080), headers={
                "content-type": "image/png"})
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as cliente:
        resolvedor = ResolvedorAtivosMeta(cliente)
        inventario = await resolvedor.inventariar(
            meta_dom.referencia_opaca_conta("1234567890"), Segredo(TOKEN))
        # A leitura de imagens segue inteira e a compilação continua possível.
        assert len(inventario["imagens"]) == 1
        assert inventario["videos"] == []
        assert inventario["videos_indisponiveis"] == "META_ASSET_READ_FAILED"
        asset_ref = inventario["imagens"][0]["referencia_opaca"]
        resolvidas = await resolvedor.resolver_lote(
            ator="operador@example.com",
            account_ref=inventario["account_ref"],
            page_ref=inventario["paginas"][0]["referencia_opaca"],
            asset_refs=(asset_ref,),
            segredo=Segredo(TOKEN),
            declaracoes={asset_ref: DeclaracaoPoliticaAtivoMeta(
                direitos_confirmados=True,
                identidade_de_terceiro_liberada=True,
                confirmada_em=datetime.now(timezone.utc),
            )},
        )
    assert resolvidas.image_hash == "hash_um"


# ---------------------------------------------------------------------------
# T01 — CAMPOS E PAYLOAD
# ---------------------------------------------------------------------------
# As provas desta seção nasceram de F14 e F15 do pacote
# `docs/specs/traffic-operational-closure-v2/`.


def test_mascara_de_creative_nao_pede_effective_status() -> None:
    """O catálogo oficial v26 de AdCreative não declara `effective_status`.

    Duas fontes independentes, lidas em 07/09/2026:

    * o SDK gerado na tag 26.0.0 enumera `status`, `destination_spec`,
      `object_story_spec`, `asset_feed_spec` e `degrees_of_freedom_spec`, e
      NÃO enumera `effective_status`;
    * a referência pública documenta `status` com
      `ACTIVE, IN_PROCESS, WITH_ISSUES, DELETED` e não documenta
      `effective_status`.

    Um campo inválido no `fields` faz a Graph recusar a leitura INTEIRA. Como o
    read-back acontece DEPOIS de o objeto nascer, o preço do campo a mais não
    seria uma leitura vazia: seria um objeto criado cuja conferência falha.

    ⚠️ Este teste NÃO afirma que a Meta recusaria a máscara antiga — nenhuma
    conta foi chamada. Ele fixa a decisão de não pedir o que o catálogo não tem.
    """
    from app.trafego.meta_execucao.executor import CAMPOS_DE_LEITURA

    assert "effective_status" not in CAMPOS_DE_LEITURA["creative"].split(",")
    assert "destination_spec" in CAMPOS_DE_LEITURA["creative"].split(",")
    # `status` continua: é o estado de BIBLIOTECA do criativo, e é por ele que
    # um criativo inutilizável é recusado.
    assert "status" in CAMPOS_DE_LEITURA["creative"].split(",")
    # Os objetos veiculáveis continuam pedindo o campo — para eles ele existe.
    for veiculavel in ("campaign", "adset", "ad"):
        assert "effective_status" in CAMPOS_DE_LEITURA[veiculavel].split(",")


def test_creative_nunca_e_exigido_pausado_e_estados_de_biblioteca_decidem() -> None:
    """O AdCreative não é pausável; o que o recusa é o estado de biblioteca."""
    validar = ExecutorMetaPausado._validar_read_back
    payload = {"name": "Criativo endurecido"}
    comuns = dict(
        payload=payload, identificador="777", ids={}, conta_externa="1234567890")

    # ACTIVE é o estado normal de um criativo recém-criado — e passa.
    validar("creative", {
        "id": "777", "account_id": "act_1234567890",
        "name": "Criativo endurecido", "status": "ACTIVE"}, **comuns)

    # Sem `effective_status` na resposta, porque não foi pedido. Continua passando.
    validar("creative", {
        "id": "777", "account_id": "1234567890",
        "name": "Criativo endurecido", "status": "IN_PROCESS"}, **comuns)

    # O que recusa é o estado de biblioteca inutilizável.
    for ruim in ("DELETED", "WITH_ISSUES"):
        with pytest.raises(ErroRemotoMeta) as erro:
            validar("creative", {
                "id": "777", "account_id": "1234567890",
                "name": "Criativo endurecido", "status": ruim}, **comuns)
        assert erro.value.codigo == "META_READBACK_DIVERGENT"
        assert "status" in str(erro.value)


def test_payload_form_urlencoded_preserva_booleano_lista_e_objeto() -> None:
    """A paridade que importa é a do que SAI no fio, não a do dict em memória.

    `_form` é o serializador canônico: booleano vira `true`/`false` JSON (nunca
    `True` do Python), lista e objeto viram JSON compacto, e escalar vira texto.
    Comparar apenas os objetos pré-serialização deixaria passar exatamente o
    erro que a Meta veria — `is_adset_budget_sharing_enabled=True` chegando como
    a string `"True"`, que não é um booleano JSON.
    """
    import json as _json

    from app.trafego.meta_execucao.executor import _form

    plano = compilar_plano_pausado(_plano(), _refs())
    campanha = next(op for op in plano.operacoes if op.tipo_objeto == "campaign")
    conjunto = next(op for op in plano.operacoes if op.tipo_objeto == "adset")

    fio_campanha = _form(campanha.payload)
    # Booleano: JSON, minúsculo, jamais o repr do Python.
    assert fio_campanha["is_adset_budget_sharing_enabled"] == "false"
    assert "True" not in fio_campanha.values() and "False" not in fio_campanha.values()
    # Lista vazia continua sendo uma lista, não string vazia nem ausência.
    assert fio_campanha["special_ad_categories"] == "[]"
    assert fio_campanha["status"] == "PAUSED"
    assert fio_campanha["objective"] == "OUTCOME_TRAFFIC"

    fio_conjunto = _form(conjunto.payload)
    # Objeto aninhado: JSON compacto, e a escolha do Advantage+ sobrevive
    # explícita no fio como 0/1 — a omissão é que ligaria o recurso.
    alvo = _json.loads(fio_conjunto["targeting"])
    assert alvo["targeting_automation"]["advantage_audience"] == 0
    assert alvo["publisher_platforms"] == ["facebook"]
    assert alvo["geo_locations"]["countries"] == ["BR"]
    # Inteiro vira texto, e continua sendo o mesmo número.
    assert fio_conjunto["daily_budget"] == "1000"
    # `destination_type` não pertence a esta receita e não pode aparecer no fio.
    assert "destination_type" not in fio_conjunto


def test_todo_valor_do_payload_compilado_sobrevive_ao_serializador() -> None:
    """Nenhuma chave do payload aprovado some ao virar form-urlencoded."""
    from app.trafego.meta_execucao.executor import _form

    for operacao in compilar_plano_pausado(_plano(), _refs()).operacoes:
        fio = _form(operacao.payload)
        assert set(fio) == set(operacao.payload), operacao.chave
        assert all(isinstance(valor, str) for valor in fio.values()), operacao.chave
