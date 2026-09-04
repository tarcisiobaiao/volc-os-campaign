from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import meta_local
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta import dominio as dom
from app.trafego.meta.configuracao_local import CredencialLocal
from app.trafego.meta.persistencia import linhas_de_insights
from app.trafego.meta.read_model import (
    PersistenciaMetaBloqueada,
    RepositorioMetaReadModelSupabase,
    SnapshotMetaCanonico,
    montar_snapshot_canonico,
)

TOKEN = "token-meta-falso-operacional-123"


def leitura(conta: str = "123456789012") -> dom.LeituraDaHierarquia:
    return dom.LeituraDaHierarquia(
        conta_externa=conta,
        campanhas=(dom.ObjetoMeta("campaign", "1001", "Campanha", "PAUSED", "PAUSED", objetivo="OUTCOME_TRAFFIC"),),
        conjuntos=(dom.ObjetoMeta("adset", "2001", "Conjunto", "ACTIVE", "ACTIVE", parent_id_externo="1001", optimization_goal="LANDING_PAGE_VIEWS"),),
        anuncios=(dom.ObjetoMeta("ad", "3001", "Anuncio", "ACTIVE", "ACTIVE", parent_id_externo="2001", creative_id_externo="4001"),),
        criativos=(dom.ObjetoMeta("creative", "4001", "Criativo", None, None, object_story_id="story_1"),),
        paginas_lidas=4,
    )


def insight(conta: str = "123456789012") -> dom.InsightMeta:
    return dom.InsightMeta(
        provider="META_ADS",
        conta_externa=conta,
        nivel="ad",
        objeto_externo="3001",
        periodo_inicio=date(2026, 9, 4),
        periodo_fim=date(2026, 9, 4),
        janela_atribuicao="7d_click",
        breakdown="none",
        observado_em=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        spend=None,
        impressions=None,
        reach=10,
        actions=(dom.AcaoInsightMeta("lead", None, "7d_click", "ad", date(2026, 9, 4), date(2026, 9, 4)),),
    )


def test_snapshot_canonico_tem_hash_contagens_e_nao_expoe_ids_brutos() -> None:
    snap = montar_snapshot_canonico(
        conta=dom.ContaMetaDescoberta("123456789012", "Conta", "1", "BRL", "America/Sao_Paulo"),
        leitura=leitura(),
        insights=(insight(),),
        mensuracao={"pixels_ou_datasets": 12, "custom_conversions": 1},
        janela="2026-09-04",
        observado_em=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
    )
    publico = snap.recibo_sanitizado(escrita="bloqueada")
    assert publico["conta_opaca"].startswith("metaacct_")
    assert publico["contagens"] == {"campaign": 1, "adset": 1, "ad": 1, "creative": 1, "insight": 1}
    assert publico["paginas_lidas"] == 4
    assert publico["snapshot_hash"].startswith("meta_snapshot_")
    assert "123456789012" not in str(publico)
    assert "1001" not in str(publico)


class SupabaseFake:
    enabled = True

    def __init__(self) -> None:
        self.rpcs: list[tuple[str, dict[str, Any]]] = []
        self.tables: dict[str, list[dict[str, Any]]] = {}

    async def rpc(self, funcao: str, argumentos: dict[str, Any]) -> Any:
        self.rpcs.append((funcao, argumentos))
        return {"ok": True, "run_id": "00000000-0000-4000-8000-000000000001", "repetido": len(self.rpcs) > 1}

    async def select(self, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        return list(self.tables.get(table, []))


def test_repositorio_bloqueia_write_sem_flag_antes_de_rpc(monkeypatch) -> None:
    fake = SupabaseFake()
    repo = RepositorioMetaReadModelSupabase(fake)  # type: ignore[arg-type]
    snap = montar_snapshot_canonico(
        conta=dom.ContaMetaDescoberta("123456789012", "Conta", "1", "BRL", "America/Sao_Paulo"),
        leitura=leitura(),
        insights=(),
        mensuracao={},
        janela="preview",
        observado_em=datetime.now(timezone.utc),
    )
    monkeypatch.delenv("META_READ_MODEL_WRITE_ENABLED", raising=False)
    try:
        asyncio.run(repo.persistir_snapshot(snap))
    except PersistenciaMetaBloqueada as exc:
        assert exc.recibo["escrita"] == "bloqueada"
    else:  # pragma: no cover
        raise AssertionError("write deveria bloquear")
    assert fake.rpcs == []


def test_repositorio_chama_rpc_unica_com_payload_idempotente_e_isolado(monkeypatch) -> None:
    fake = SupabaseFake()
    repo = RepositorioMetaReadModelSupabase(fake)  # type: ignore[arg-type]
    monkeypatch.setenv("META_READ_MODEL_WRITE_ENABLED", "1")
    s1 = montar_snapshot_canonico(dom.ContaMetaDescoberta("111", "A", "1", "BRL", "UTC"), leitura("111"), (insight("111"),), {}, "d1", datetime.now(timezone.utc))
    s2 = montar_snapshot_canonico(dom.ContaMetaDescoberta("222", "B", "1", "BRL", "UTC"), leitura("222"), (), {}, "d1", datetime.now(timezone.utc))
    r1 = asyncio.run(repo.persistir_snapshot(s1))
    r1b = asyncio.run(repo.persistir_snapshot(s1))
    r2 = asyncio.run(repo.persistir_snapshot(s2))
    assert [name for name, _ in fake.rpcs] == ["trafego_meta_persistir_snapshot", "trafego_meta_persistir_snapshot", "trafego_meta_persistir_snapshot"]
    assert fake.rpcs[0][1]["p_snapshot"]["idempotency_key"] == fake.rpcs[1][1]["p_snapshot"]["idempotency_key"]
    assert fake.rpcs[0][1]["p_snapshot"]["idempotency_key"] != fake.rpcs[2][1]["p_snapshot"]["idempotency_key"]
    assert r1["escrita"] == "executada"
    assert r1b["repetido"] is True
    assert r2["conta_opaca"] != r1["conta_opaca"]


def test_linhas_de_insights_preservam_null_e_action_separada() -> None:
    linhas = linhas_de_insights([insight()], conta_ativo_id="meta_account_metaacct_x")
    fato = linhas["trafego_meta_insight_daily"][0]
    acao = linhas["trafego_meta_insight_action"][0]
    assert fato["spend"] is None
    assert fato["impressions"] is None
    assert acao["value"] is None
    assert "actions" not in fato


class ChaveiroFake:
    def ler(self, conta: str) -> str:
        return CredencialLocal.agora(TOKEN).serializar()


def cliente_app() -> TestClient:
    app = FastAPI()
    app.include_router(meta_local.router)
    app.dependency_overrides[exigir_admin] = lambda: Identidade(sub="u1", email="a@b", papel="ADMIN", origem="teste")
    return TestClient(app, headers={"host": "localhost"})


def test_endpoint_persistir_snapshot_fail_closed_sem_flag(monkeypatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    monkeypatch.setattr(meta_local, "_chaveiro", lambda: ChaveiroFake())
    monkeypatch.delenv("META_READ_MODEL_WRITE_ENABLED", raising=False)

    async def fake_preparar(token: str, referencia: str, *, janela: str = "preview") -> SnapshotMetaCanonico:
        assert janela == "preview"
        assert token == TOKEN
        assert referencia == "metaacct_abc"
        return montar_snapshot_canonico(dom.ContaMetaDescoberta("123456789012", "Conta", "1", "BRL", "UTC"), leitura(), (), {}, "preview", datetime.now(timezone.utc))

    fake_supa = SupabaseFake()
    monkeypatch.setattr(meta_local, "_preparar_snapshot_com_token", fake_preparar)
    monkeypatch.setattr(meta_local, "_repositorio_read_model", lambda: RepositorioMetaReadModelSupabase(fake_supa))
    resp = cliente_app().post("/api/trafego/meta/local/sincronizacao/persistir", json={"referencia_opaca": "metaacct_abc"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["escrita"] == "bloqueada"
    assert fake_supa.rpcs == []
    assert TOKEN not in resp.text


def test_router_nao_expoe_mutate() -> None:
    rotas = [(sorted(getattr(r, "methods", set())), r.path) for r in meta_local.router.routes]
    assert not any(any(m in {"PUT", "PATCH"} for m in metodos) for metodos, _ in rotas)
    assert not any("mutate" in path or "criar" in path or "ativar" in path for _, path in rotas)
