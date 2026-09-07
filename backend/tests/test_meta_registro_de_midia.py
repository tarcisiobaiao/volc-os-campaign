"""Provas do registro de mídia: idempotência, ambiguidade e zero criação.

O ato provado aqui é o SEGUNDO dos quatro que a lane separa — importar,
registrar, validar, criar. As provas cobram justamente que ele não vire nenhum
dos outros três por acidente.
"""
from __future__ import annotations

from typing import Any, Mapping

import httpx
import pytest

import imagens_meta
from app.trafego.meta.credenciais import SegredoEfemero
from app.trafego.meta_execucao import registro_de_midia as rm
from app.trafego.meta_execucao.registro_de_midia import (
    ESTADO_AMBIGUO,
    ESTADO_JA_REGISTRADO,
    ESTADO_RECUSADO,
    ESTADO_REGISTRADO,
    ErroDeRegistroDeMidia,
    PecaParaRegistrar,
    RegistradorDeMidiaMeta,
)


CONTA = "1234567890"
CONTA_REF = "metaacct_exemplo"
SEGREDO = SegredoEfemero("token-meta-falso-seguro")


def _peca(nome: str = "peca.jpg", *, conteudo: bytes | None = None) -> PecaParaRegistrar:
    return PecaParaRegistrar(
        master_ref="master-001",
        nome=nome,
        mime_type="image/jpeg",
        conteudo=conteudo if conteudo is not None else imagens_meta.jpeg(600, 600),
    )


class _Resposta:
    def __init__(self, corpo: Any, status: int = 200) -> None:
        self.status_code = status
        self._corpo = corpo

    def json(self) -> Any:
        return self._corpo


class _GraphFake:
    """Dublê que CONTA os POSTs — é a contagem que prova o não-reenvio."""

    def __init__(self, *, resposta: Any = None, status: int = 200, estourar: bool = False) -> None:
        self.posts: list[tuple[str, dict[str, str]]] = []
        self.corpos: list[Any] = []
        self._resposta = resposta if resposta is not None else {
            "images": {"peca.jpg": {"hash": "hashNovo_123456", "url": "https://x.fbcdn.net/a.jpg"}}}
        self._status = status
        self._estourar = estourar

    async def post(self, url: str, *, headers=None, files=None, **_: Any):
        self.posts.append((url, dict(headers or {})))
        self.corpos.append(files)
        if self._estourar:
            raise httpx.TimeoutException("sem resposta")
        return _Resposta(self._resposta, self._status)


class _LivroFake:
    def __init__(self, estado: str = "DESPACHAR", *, image_hash: str | None = None) -> None:
        self.estado = estado
        self.image_hash = image_hash
        self.reservas: list[dict[str, Any]] = []
        self.concluidos: list[dict[str, Any]] = []
        self.ambiguos: list[str] = []
        self.falhados: list[tuple[str, str]] = []
        self.ordem: list[str] = []

    async def reservar(self, *, account_ref, content_sha256, ator, master_ref):
        self.reservas.append({
            "account_ref": account_ref, "content_sha256": content_sha256,
            "ator": ator, "master_ref": master_ref,
        })
        self.ordem.append("reservar")
        if self.estado == "REGISTRADO":
            return {"estado": "REGISTRADO", "image_hash": self.image_hash}
        if self.estado == "AMBIGUO":
            return {"estado": "AMBIGUO"}
        return {"estado": "DESPACHAR", "reserva_ref": "reserva-1", "claim_token": "tok-1"}

    async def concluir(self, *, reserva_ref, image_hash, claim_token):
        self.ordem.append("concluir")
        self.concluidos.append({
            "reserva_ref": reserva_ref, "image_hash": image_hash, "claim_token": claim_token})

    async def marcar_ambiguo(self, *, reserva_ref, claim_token):
        self.ordem.append("ambiguo")
        self.ambiguos.append(reserva_ref)

    async def falhar(self, *, reserva_ref, codigo, claim_token):
        self.ordem.append("falhar")
        self.falhados.append((reserva_ref, codigo))


async def _registrar(graph: _GraphFake, livro: _LivroFake, pecas=None):
    return await RegistradorDeMidiaMeta(graph, livro).registrar_imagens(  # type: ignore[arg-type]
        conta_externa=CONTA,
        pecas=pecas if pecas is not None else [_peca()],
        segredo=SEGREDO,
        ator="operador-meta",
        account_ref=CONTA_REF,
    )


# ── O caminho feliz, e a ordem que ele obedece ──────────────────────────────


@pytest.mark.anyio
async def test_registro_grava_recibo_antes_do_post_e_id_antes_do_readback() -> None:
    graph, livro = _GraphFake(), _LivroFake()
    resultados = await _registrar(graph, livro)
    assert livro.ordem == ["reservar", "concluir"]
    assert len(graph.posts) == 1
    assert graph.posts[0][0].endswith(f"/v26.0/act_{CONTA}/adimages")
    assert resultados[0].estado == ESTADO_REGISTRADO
    assert resultados[0].image_hash == "hashNovo_123456"


@pytest.mark.anyio
async def test_asset_ref_devolvido_e_o_mesmo_que_a_leitura_produz() -> None:
    """Se divergisse, a peça recém-enviada apareceria duas vezes na biblioteca."""
    import hashlib
    esperado = "metaasset_" + hashlib.sha256(
        f"META_ADS:{CONTA}:image_asset:hashNovo_123456".encode("utf-8")).hexdigest()[:24]
    resultados = await _registrar(_GraphFake(), _LivroFake())
    assert resultados[0].asset_ref == esperado
    assert rm.referencia_opaca_de_imagem(CONTA, "hashNovo_123456") == esperado


# ── Idempotência e ambiguidade ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_bytes_ja_registrados_nao_geram_segundo_envio() -> None:
    """`A28`: replay por conta+hash devolve o que existe, não cria outro ativo."""
    graph = _GraphFake()
    livro = _LivroFake("REGISTRADO", image_hash="hashAntigo_98765")
    resultados = await _registrar(graph, livro)
    assert graph.posts == []
    assert resultados[0].estado == ESTADO_JA_REGISTRADO
    assert resultados[0].image_hash == "hashAntigo_98765"


@pytest.mark.anyio
async def test_reserva_ambigua_nao_reenvia() -> None:
    """Um envio sem conclusão registrada exige leitura, nunca retry."""
    graph = _GraphFake()
    resultados = await _registrar(graph, _LivroFake("AMBIGUO"))
    assert graph.posts == []
    assert resultados[0].estado == ESTADO_AMBIGUO
    assert resultados[0].codigo == "META_ASSET_REGISTRATION_AMBIGUOUS"


@pytest.mark.anyio
async def test_timeout_vira_ambiguo_e_nao_fracasso() -> None:
    """Silêncio da rede depois do POST não prova que nada nasceu."""
    graph, livro = _GraphFake(estourar=True), _LivroFake()
    resultados = await _registrar(graph, livro)
    assert len(graph.posts) == 1
    assert livro.ambiguos == ["reserva-1"]
    assert livro.concluidos == []
    assert resultados[0].estado == ESTADO_AMBIGUO
    assert "duplicaria" in (resultados[0].motivo or "")


@pytest.mark.anyio
async def test_recusa_explicita_da_meta_fecha_o_passo_como_falha() -> None:
    """Só a recusa explícita prova que nada foi criado."""
    graph = _GraphFake(status=400, resposta={"error": {"message": "nope"}})
    livro = _LivroFake()
    resultados = await _registrar(graph, livro)
    assert livro.falhados == [("reserva-1", "META_ASSET_UPLOAD_REJECTED")]
    assert livro.ambiguos == []
    assert resultados[0].estado == ESTADO_RECUSADO


@pytest.mark.anyio
async def test_200_sem_hash_identificavel_vira_ambiguo() -> None:
    """O caso mais perigoso: a peça existe e não sabemos o nome dela."""
    graph = _GraphFake(resposta={"images": {"a": {}, "b": {}}})
    livro = _LivroFake()
    resultados = await _registrar(graph, livro)
    assert livro.ambiguos == ["reserva-1"]
    assert resultados[0].estado == ESTADO_AMBIGUO
    assert resultados[0].codigo == "META_ASSET_REGISTRATION_UNIDENTIFIED"


@pytest.mark.anyio
async def test_resposta_com_uma_entrada_de_nome_diferente_ainda_resolve() -> None:
    """O provedor normaliza o nome do arquivo; uma entrada só não é ambígua."""
    graph = _GraphFake(resposta={"images": {"outro_nome.jpg": {"hash": "hashUnico_1234"}}})
    resultados = await _registrar(graph, _LivroFake())
    assert resultados[0].estado == ESTADO_REGISTRADO
    assert resultados[0].image_hash == "hashUnico_1234"


# ── Isolamento e chave de idempotência ──────────────────────────────────────


@pytest.mark.anyio
async def test_chave_de_idempotencia_e_conta_mais_bytes_nao_nome() -> None:
    """Nome é do operador e muda; os bytes são o que a Meta indexa."""
    livro = _LivroFake()
    bytes_iguais = imagens_meta.jpeg(600, 600)
    await _registrar(_GraphFake(), livro, pecas=[
        _peca("um.jpg", conteudo=bytes_iguais), _peca("outro.jpg", conteudo=bytes_iguais)])
    assert livro.reservas[0]["content_sha256"] == livro.reservas[1]["content_sha256"]
    assert livro.reservas[0]["account_ref"] == CONTA_REF


@pytest.mark.anyio
async def test_o_ator_vem_de_quem_chamou_e_entra_no_recibo() -> None:
    livro = _LivroFake()
    await _registrar(_GraphFake(), livro)
    assert livro.reservas[0]["ator"] == "operador-meta"


# ── O token nunca aparece onde não deve ─────────────────────────────────────


@pytest.mark.anyio
async def test_token_viaja_so_no_cabecalho_e_nunca_no_corpo() -> None:
    graph, livro = _GraphFake(), _LivroFake()
    await _registrar(graph, livro)
    url, headers = graph.posts[0]
    assert headers["Authorization"].startswith("Bearer ")
    assert "token" not in url and "access_token" not in url
    # O corpo multipart carrega os bytes e o nome — nada mais.
    assert "token-meta-falso-seguro" not in str(graph.corpos[0])
    # E o recibo durável também não vê o segredo.
    assert "token-meta-falso-seguro" not in str(livro.reservas)


@pytest.mark.anyio
async def test_o_repr_do_segredo_nao_revela_material() -> None:
    assert "token-meta-falso-seguro" not in repr(SEGREDO)
    assert "token-meta-falso-seguro" not in str(SEGREDO)


# ── Limites e formatos: o mais restritivo vence ─────────────────────────────


def test_formato_sem_prova_de_envio_e_recusado() -> None:
    """Ler um GIF da conta e ENVIAR um GIF são capacidades diferentes."""
    with pytest.raises(ErroDeRegistroDeMidia) as erro:
        PecaParaRegistrar(
            master_ref="m", nome="a.gif", mime_type="image/gif", conteudo=b"GIF89a")
    assert erro.value.codigo == "META_ASSET_UPLOAD_FORMAT_UNPROVEN"


def test_teto_de_bytes_usa_o_limite_mais_restritivo() -> None:
    with pytest.raises(ErroDeRegistroDeMidia) as erro:
        PecaParaRegistrar(
            master_ref="m", nome="a.jpg", mime_type="image/jpeg",
            conteudo=b"x" * (rm.TETO_DE_IMAGEM_BYTES + 1))
    assert erro.value.codigo == "META_ASSET_UPLOAD_TOO_LARGE"
    assert rm.TETO_DE_IMAGEM_BYTES == 12 * 1024 * 1024


def test_peca_vazia_e_recusada() -> None:
    with pytest.raises(ErroDeRegistroDeMidia) as erro:
        PecaParaRegistrar(master_ref="m", nome="a.jpg", mime_type="image/jpeg", conteudo=b"")
    assert erro.value.codigo == "META_ASSET_UPLOAD_EMPTY"


@pytest.mark.anyio
async def test_lote_vazio_e_lote_grande_demais_sao_recusados() -> None:
    with pytest.raises(ErroDeRegistroDeMidia) as erro:
        await _registrar(_GraphFake(), _LivroFake(), pecas=[])
    assert erro.value.codigo == "META_ASSET_UPLOAD_EMPTY_BATCH"
    with pytest.raises(ErroDeRegistroDeMidia) as erro:
        await _registrar(_GraphFake(), _LivroFake(), pecas=[_peca(f"p{i}.jpg") for i in range(11)])
    assert erro.value.codigo == "META_ASSET_UPLOAD_BATCH_TOO_LARGE"


# ── O ato não vira outro ato ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_registro_so_toca_adimages_e_nunca_campaigns_adsets_ads() -> None:
    """`A27`/`A45`: registrar mídia não é criar campanha."""
    graph, livro = _GraphFake(), _LivroFake()
    await _registrar(graph, livro, pecas=[_peca("a.jpg"), _peca("b.jpg")])
    caminhos = [url for url, _ in graph.posts]
    assert all(url.endswith("/adimages") for url in caminhos)
    for proibido in ("/campaigns", "/adsets", "/ads", "/adcreatives", "/advideos"):
        assert all(proibido not in url for url in caminhos)


@pytest.mark.anyio
async def test_uma_peca_ambigua_nao_contamina_as_outras() -> None:
    """Peça a peça: a ambiguidade fica contida em uma."""
    class _MetadeQueEstoura(_GraphFake):
        async def post(self, url: str, *, headers=None, files=None, **_: Any):
            self.posts.append((url, dict(headers or {})))
            if len(self.posts) == 1:
                raise httpx.TimeoutException("sem resposta")
            return _Resposta(
                {"images": {"b.jpg": {"hash": "hashSegundo_1234"}}})

    graph, livro = _MetadeQueEstoura(), _LivroFake()
    resultados = await _registrar(graph, livro, pecas=[
        _peca("a.jpg", conteudo=imagens_meta.jpeg(600, 600)),
        _peca("b.jpg", conteudo=imagens_meta.jpeg(800, 800)),
    ])
    assert resultados[0].estado == ESTADO_AMBIGUO
    assert resultados[1].estado == ESTADO_REGISTRADO
    assert len(graph.posts) == 2


def test_registrador_recusa_base_que_nao_seja_a_graph() -> None:
    with pytest.raises(ValueError):
        RegistradorDeMidiaMeta(
            _GraphFake(), _LivroFake(), base_url="https://exemplo.invalido")  # type: ignore[arg-type]


# ═════════════════════════════════════════════════════════════════════════════
# A rota: a confirmação, a autorização por conta e a fronteira do ato
# ═════════════════════════════════════════════════════════════════════════════

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.routers import meta_local, trafego_meta_ativos  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_admin  # noqa: E402


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(trafego_meta_ativos.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(
        sub="operador-meta", email="admin@volc", papel="ADMIN", origem="sessao")
    return TestClient(app, headers={"host": "localhost"})


def _pedido(**troca: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "account_ref": "metaacct_exemplo",
        "master_refs": ["master-1"],
        "confirmar_registro_na_conta": "metaacct_exemplo",
        "confirmar_quantidade": 1,
    }
    base.update(troca)
    return base


def test_capacidades_sem_conta_ficam_fechadas(monkeypatch) -> None:
    """Quem não sabe de qual conta fala não recebe a autorização de nenhuma."""
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setenv("META_UPLOAD_ASSET_ENABLED", "metaacct_liberada")
    corpo = _app().get("/api/trafego/meta/ativos/capacidades").json()
    assert corpo["registro_de_imagem"] == "BLOCKED_BY_SERVER_FLAG"
    assert corpo["cria_campanha"] == "NEVER_IN_THIS_ROUTE"


def test_capacidades_sao_por_conta(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setenv("META_UPLOAD_ASSET_ENABLED", "metaacct_liberada")
    cliente = _app()
    liberada = cliente.get(
        "/api/trafego/meta/ativos/capacidades",
        params={"account_ref": "metaacct_liberada"}).json()
    outra = cliente.get(
        "/api/trafego/meta/ativos/capacidades",
        params={"account_ref": "metaacct_outra"}).json()
    assert liberada["registro_de_imagem"] == "ENABLED"
    assert outra["registro_de_imagem"] == "BLOCKED_BY_SERVER_FLAG"
    assert outra["motivo"]


def test_video_e_declarado_bloqueado_e_nao_disponivel(monkeypatch) -> None:
    """`A29`: vídeo é capacidade diferente, com prova própria."""
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setenv("META_UPLOAD_ASSET_ENABLED", "metaacct_liberada")
    corpo = _app().get(
        "/api/trafego/meta/ativos/capacidades",
        params={"account_ref": "metaacct_liberada"}).json()
    assert corpo["registro_de_imagem"] == "ENABLED"
    assert corpo["registro_de_video"].startswith("BLOCKED_")


def test_conta_confirmada_diferente_da_conta_do_pedido_recusa(monkeypatch) -> None:
    """`A27`: a confirmação lista a conta, e o servidor confere."""
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setenv("META_UPLOAD_ASSET_ENABLED", "metaacct_exemplo")
    monkeypatch.setattr(
        trafego_meta_ativos, "_credencial_salva",
        lambda *_: pytest.fail("nao deveria ler token"))
    resposta = _app().post(
        "/api/trafego/meta/ativos/registrar",
        json=_pedido(confirmar_registro_na_conta="metaacct_outra"))
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_ASSET_CONFIRMATION_ACCOUNT_MISMATCH"


def test_quantidade_confirmada_diferente_recusa(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setenv("META_UPLOAD_ASSET_ENABLED", "metaacct_exemplo")
    monkeypatch.setattr(
        trafego_meta_ativos, "_credencial_salva",
        lambda *_: pytest.fail("nao deveria ler token"))
    resposta = _app().post(
        "/api/trafego/meta/ativos/registrar",
        json=_pedido(master_refs=["m1", "m2"], confirmar_quantidade=1))
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_ASSET_CONFIRMATION_COUNT_MISMATCH"


def test_conta_nao_liberada_recusa_antes_de_ler_token_ou_bytes(monkeypatch) -> None:
    """`A27`: nenhum efeito externo — nem leitura de credencial — sem autorização."""
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.delenv("META_UPLOAD_ASSET_ENABLED", raising=False)
    monkeypatch.setattr(
        trafego_meta_ativos, "_credencial_salva",
        lambda *_: pytest.fail("nao deveria ler token"))
    monkeypatch.setattr(
        trafego_meta_ativos, "_carregar_pecas",
        lambda *a, **k: pytest.fail("nao deveria ler bytes"))
    resposta = _app().post("/api/trafego/meta/ativos/registrar", json=_pedido())
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "META_ASSET_UPLOAD_BLOCKED"


def test_a_rota_nao_aceita_bytes_no_corpo(monkeypatch) -> None:
    """Aceitar bytes no JSON transformaria isto num proxy de upload."""
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    resposta = _app().post(
        "/api/trafego/meta/ativos/registrar",
        json=_pedido(conteudo_base64="ZmFrZQ=="))
    assert resposta.status_code == 422


def test_o_router_nao_tem_rota_de_criacao_ou_ativacao() -> None:
    """`A45`: a flag de upload não abre criar/ativar."""
    paths = {rota.path for rota in trafego_meta_ativos.router.routes}
    assert paths == {
        "/api/trafego/meta/ativos/capacidades", "/api/trafego/meta/ativos/registrar"}
    for proibido in ("campanha", "campaign", "adset", "criar", "ativar", "aprovar"):
        assert all(proibido not in path for path in paths)


def test_a_flag_de_upload_nao_abre_a_criacao_de_campanha(monkeypatch) -> None:
    """Duas autoridades separadas: liberar mídia não libera gasto."""
    from app.trafego.meta_execucao import capacidades as caps

    monkeypatch.setenv("META_UPLOAD_ASSET_ENABLED", "metaacct_exemplo")
    monkeypatch.delenv("META_CREATE_PAUSED_ENABLED", raising=False)
    monkeypatch.delenv("META_CREATE_LEDGER_WRITE_ENABLED", raising=False)
    assert caps.upload_de_ativo_liberado("metaacct_exemplo") is True
    assert caps.criacao_liberada("metaacct_exemplo") is False
    assert caps.FLAG_UPLOAD_DE_ATIVO not in caps.FLAGS_DE_CRIACAO
    assert caps.FLAG_UPLOAD_DE_ATIVO not in caps.FLAGS_DE_PROCESSO
