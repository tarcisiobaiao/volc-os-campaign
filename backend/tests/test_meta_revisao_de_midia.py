"""The real policy gate, owned approvals and the upload route as one boundary."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import imagens_meta
from app.criativo.politica import inspecao, recibo
from app.routers import trafego_meta_ativos as rota
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta_execucao import revisao_de_midia as review
from app.trafego.meta_execucao.registro_de_midia import PecaParaRegistrar, ErroDeRegistroDeMidia


class PixelFixture:
    nome = "fixture.ocr_and_logo"
    versao = "1"
    capacidades = inspecao.CAPACIDADES_EXIGIDAS

    def inspecionar(self, content, *, mime):
        assert content.startswith(b"\xff\xd8")
        return inspecao.LeituraDePixel()


class Repo:
    def __init__(self, peca):
        self.master = {"content_hash": "sha256:" + peca.content_sha256,
                       "versao": 2, "sintetico": True}
        self.approvals = [{"id": "approval-1", "decisao": "aprovado", "versao": 2,
                           "ator_id": "owner", "finalidade": "meta_ads", "revogada_em": None}]

    async def buscar_master_do_dono(self, ref, *, criado_por):
        return self.master if criado_por == "owner" else None

    async def aprovacoes_de(self, tipo, ref):
        return deepcopy(self.approvals)


@pytest.fixture
def setup(monkeypatch):
    # Local .env may enable paid Gemini. Hermetic tests must never inherit it.
    monkeypatch.setattr(review, "detector_meta_se_autorizado", lambda: None)
    monkeypatch.setattr(recibo, "_segredo", lambda: b"test-policy-secret")
    monkeypatch.setattr(inspecao, "_DETECTORES_DE_PIXEL", [PixelFixture()])
    monkeypatch.setenv("CRIATIVO_POLICY_GATE_STRICT", "1")
    peca = PecaParaRegistrar("master-1", "image", "image/jpeg", imagens_meta.jpeg(600, 600))
    return peca, Repo(peca)


async def _review(setup):
    peca, repo = setup
    return await review.revisar_pecas([peca], repo=repo, ator="owner", account_ref="metaacct_example", automatizada=True)


@pytest.mark.anyio
async def test_actual_gate_and_versioned_human_approval_allow_review(setup):
    rows = await _review(setup)
    assert rows[0]["utilizavel"] is True
    assert rows[0]["politica"]["decisao"] == "CLEAR"
    assert rows[0]["aprovacao_ref"] == "approval-1"
    review.exigir_revisoes(rows, {"master-1": setup[0].content_sha256})


@pytest.mark.anyio
@pytest.mark.parametrize("change", [
    {"versao": 1}, {"finalidade": "interno"}, {"revogada_em": "2026-09-08"},
    {"ator_id": "another-owner"}, {"decisao": "rejeitado"},
])
async def test_approval_must_be_current_same_version_owner_and_paid_use(setup, change):
    setup[1].approvals[0].update(change)
    row = (await _review(setup))[0]
    assert not row["utilizavel"]
    assert row["codigo"] == "META_ASSET_FINAL_APPROVAL_REQUIRED"


@pytest.mark.anyio
@pytest.mark.parametrize("legacy_flag", ["0", "1"])
async def test_no_pixel_detector_blocks_even_with_human_approval_and_legacy_relaxation(setup, monkeypatch, legacy_flag):
    monkeypatch.setattr(inspecao, "_DETECTORES_DE_PIXEL", [])
    monkeypatch.setenv("CRIATIVO_POLICY_GATE_STRICT", legacy_flag)
    row = (await _review(setup))[0]
    assert row["aprovacao_humana"]
    assert not row["utilizavel"]
    assert row["codigo"] == "META_ASSET_POLICY_UNAVAILABLE"


@pytest.mark.anyio
async def test_foreign_or_archived_or_changed_master_never_reaches_gate(setup):
    peca, repo = setup
    with pytest.raises(ErroDeRegistroDeMidia, match="pertence"):
        await review.revisar_pecas([peca], repo=repo, ator="stranger", account_ref="metaacct_example")
    repo.master["arquivado_em"] = "2026-09-08"
    with pytest.raises(ErroDeRegistroDeMidia, match="arquivada"):
        await _review(setup)
    repo.master.pop("arquivado_em")
    repo.master["content_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ErroDeRegistroDeMidia, match="mudou"):
        await _review(setup)


@pytest.mark.anyio
async def test_changed_browser_hash_or_missing_piece_rejected(setup):
    rows = await _review(setup)
    for hashes in ({}, {"master-1": "0" * 64}, {"master-1": setup[0].content_sha256, "other": "0" * 64}):
        with pytest.raises(ErroDeRegistroDeMidia):
            review.exigir_revisoes(rows, hashes)


@pytest.mark.anyio
async def test_imported_media_cannot_claim_generated_provenance(setup):
    setup[1].master["sintetico"] = False
    row = (await _review(setup))[0]
    assert row["codigo"] == "META_ASSET_POLICY_BLOCKED"


@pytest.mark.anyio
async def test_ocr_alone_does_not_claim_visual_brand_inspection(setup, monkeypatch):
    detector = PixelFixture()
    detector.capacidades = (inspecao.CAPACIDADE_TEXTO_NA_IMAGEM,)
    monkeypatch.setattr(inspecao, "_DETECTORES_DE_PIXEL", [detector])
    assert (await _review(setup))[0]["codigo"] == "META_ASSET_POLICY_UNAVAILABLE"


@pytest.mark.anyio
async def test_actual_pixel_brand_finding_blocks_approved_master(setup, monkeypatch):
    class Branded(PixelFixture):
        def inspecionar(self, content, *, mime):
            return inspecao.LeituraDePixel(texto="Banco do Brasil")
    monkeypatch.setattr(inspecao, "_DETECTORES_DE_PIXEL", [Branded()])
    result = (await _review(setup))[0]
    assert result["politica"]["decisao"] == "THIRD_PARTY_IDENTITY_UNVERIFIED"
    assert result["codigo"] == "META_ASSET_POLICY_BLOCKED"


@pytest.mark.anyio
async def test_opt_in_brand_detector_only_gets_owned_selected_image(setup, monkeypatch):
    calls = []
    local = PixelFixture()
    local.capacidades = (inspecao.CAPACIDADE_TEXTO_NA_IMAGEM,)
    class Brands(PixelFixture):
        capacidades = (inspecao.CAPACIDADE_MARCA_VISUAL,)
        def inspecionar(self, content, *, mime):
            calls.append((content, mime))
            return inspecao.LeituraDePixel()
    external = Brands()
    monkeypatch.setattr(inspecao, "_DETECTORES_DE_PIXEL", [local])
    monkeypatch.setattr(review, "detector_meta_se_autorizado", lambda: external)
    assert review.capacidades_de_inspecao(automatizada=True)["disponivel"] and not calls
    row = (await _review(setup))[0]
    assert row["utilizavel"]
    assert calls == [(setup[0].conteudo, setup[0].mime_type)]
    with pytest.raises(ErroDeRegistroDeMidia):
        await review.revisar_pecas([setup[0]], repo=setup[1], ator="stranger", account_ref="private")
    assert len(calls) == 1
    assert external not in inspecao.detectores_de_pixel_registrados()


def _client(monkeypatch, setup):
    monkeypatch.setattr(rota, "_exigir_host_local", lambda request: None)
    monkeypatch.setattr(rota, "_repositorio", lambda: setup[1])
    monkeypatch.setenv("META_UPLOAD_ASSET_ENABLED", "metaacct_example")
    async def pieces(refs, *, ator):
        return [setup[0]]
    monkeypatch.setattr(rota, "_carregar_pecas", pieces)
    app = FastAPI()
    app.include_router(rota.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(
        sub="owner", email="owner@example.test", papel="ADMIN", origem="sessao")
    return TestClient(app)


def _payload(setup):
    return {"account_ref": "metaacct_example", "master_refs": ["master-1"],
            "confirmar_registro_na_conta": "metaacct_example", "confirmar_quantidade": 1,
            "revisoes": [{"master_ref": "master-1", "content_sha256": setup[0].content_sha256}]}


def test_route_blocks_before_credentials_or_upload_when_approval_revoked(setup, monkeypatch):
    client = _client(monkeypatch, setup)
    setup[1].approvals[0]["revogada_em"] = "2026-09-08"
    async def forbidden(*args, **kwargs):
        pytest.fail("must not read token or call Meta")
    monkeypatch.setattr(rota, "credencial_operacional", forbidden)
    result = client.post("/api/trafego/meta/ativos/registrar", json=_payload(setup))
    assert result.status_code == 409
    assert result.json()["detail"]["codigo"] == "META_ASSET_FINAL_APPROVAL_REQUIRED"


def test_second_piece_rejected_before_first_piece_can_upload(setup, monkeypatch):
    client = _client(monkeypatch, setup)
    first = setup[0]
    second = PecaParaRegistrar("master-2", first.nome, first.mime_type, first.conteudo)
    async def pieces(refs, *, ator):
        return [first, second]
    async def approvals(tipo, ref):
        return setup[1].approvals if ref == "master-1" else []
    async def forbidden(*args, **kwargs):
        pytest.fail("no partial upload or credential access is allowed")
    monkeypatch.setattr(rota, "_carregar_pecas", pieces)
    monkeypatch.setattr(setup[1], "aprovacoes_de", approvals)
    monkeypatch.setattr(rota, "credencial_operacional", forbidden)
    body = _payload(setup)
    body["master_refs"].append("master-2")
    body["confirmar_quantidade"] = 2
    body["revisoes"].append({"master_ref": "master-2", "content_sha256": second.content_sha256})
    result = client.post("/api/trafego/meta/ativos/registrar", json=body)
    assert result.status_code == 409
    assert result.json()["detail"]["codigo"] == "META_ASSET_FINAL_APPROVAL_REQUIRED"


def test_review_route_is_read_only_and_returns_hash_bound_evidence(setup, monkeypatch):
    client = _client(monkeypatch, setup)
    result = client.post("/api/trafego/meta/ativos/revisar", json={
        "account_ref": "metaacct_example", "master_refs": ["master-1"]})
    assert result.status_code == 200
    assert result.json()["escopo"] == "FINAL_IMAGE_ONLY"
    assert result.json()["resultados"][0]["content_sha256"] == setup[0].content_sha256


def test_review_archived_master_keeps_domain_error_not_transient_503(setup, monkeypatch):
    client = _client(monkeypatch, setup)
    setup[1].master['arquivado_em'] = '2026-09-08'
    response = client.post('/api/trafego/meta/ativos/revisar', json={
        'account_ref': 'metaacct_example', 'master_refs': ['master-1']})
    assert response.status_code == 409
    assert response.json()['detail']['codigo'] == 'META_ASSET_MASTER_ARCHIVED'


def test_duplicate_refs_rejected_before_review(setup, monkeypatch):
    client = _client(monkeypatch, setup)
    response = client.post('/api/trafego/meta/ativos/revisar', json={
        'account_ref': 'metaacct_example', 'master_refs': ['master-1', 'master-1']})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_missing_detector_does_not_call_paid_inspection(setup, monkeypatch):
    monkeypatch.setattr(inspecao, '_DETECTORES_DE_PIXEL', [])
    def forbidden(*args, **kwargs):
        pytest.fail('Unavailable inspection must not spend on partial detection')
    monkeypatch.setattr(review.politica, 'avaliar', forbidden)
    assert (await _review(setup))[0]['codigo'] == 'META_ASSET_POLICY_UNAVAILABLE'


@pytest.mark.anyio
async def test_detector_resolved_once_per_review_batch(setup, monkeypatch):
    calls = []
    monkeypatch.setattr(review, 'detector_meta_se_autorizado', lambda: calls.append(True))
    await _review(setup)
    assert len(calls) == 1


def test_route_success_returns_asset_mapping_after_real_policy_gate(setup, monkeypatch):
    client = _client(monkeypatch, setup)
    calls = []
    async def credential(*args, **kwargs):
        return SimpleNamespace(token="not-real")
    async def account(*args):
        return "12345"
    class Registrar:
        def __init__(self, *args): pass
        async def registrar_imagens(self, **kwargs):
            calls.extend(kwargs["pecas"])
            return [SimpleNamespace(utilizavel=True, master_ref="master-1", estado="REGISTERED",
                                    asset_ref="metaasset_registered", motivo=None, codigo=None)]
    monkeypatch.setattr(rota, "credencial_operacional", credential)
    monkeypatch.setattr(rota, "_conta_externa_da", account)
    monkeypatch.setattr(rota, "_livro", lambda: None)
    monkeypatch.setattr(rota, "RegistradorDeMidiaMeta", Registrar)
    result = client.post("/api/trafego/meta/ativos/registrar", json=_payload(setup))
    assert result.status_code == 200
    assert calls == [setup[0]]
    assert result.json()["resultados"][0]["asset_ref"] == "metaasset_registered"
    assert result.json()["revisoes"][0]["politica"]["decisao"] == "HUMAN_REVIEW"
