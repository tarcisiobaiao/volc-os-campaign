from __future__ import annotations
import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import meta_local
from app.seguranca.identidade import Identidade, exigir_admin
from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura, ErroDeLeituraMeta
from app.trafego.meta.configuracao_local import CredencialLocal, SegredoLocalNaoEncontrado
from app.trafego.meta.credenciais import ReferenciaDeCredencial, SegredoEfemero
from app.trafego.meta.persistencia import RepositorioMetaEmMemoria, linhas_de_insights
from app.trafego.meta.sincronizador import PedidoDeSync, sincronizar_conta

TOKEN = "token-sistema-meta-falso-123"


class RespostaFake:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body


class ClienteGraphFake:
    def __init__(self, roteiros: dict[str, list[dict[str, Any]]], *, token: str = TOKEN) -> None:
        self.roteiros = {k: list(v) for k, v in roteiros.items()}
        self.chamadas: list[dict[str, Any]] = []
        self.token = token

    async def get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> RespostaFake:
        assert headers == {"Authorization": f"Bearer {self.token}"}
        assert self.token not in url
        params = params or {}
        self.chamadas.append({"url": url, "params": dict(params), "headers": dict(headers or {})})
        if url.endswith("/me"):
            return RespostaFake(200, {"id": "900000000001", "name": "System User"})
        if url.endswith("/me/adaccounts"):
            return RespostaFake(200, self.roteiros["adaccounts"].pop(0))
        edge = url.rsplit("/", 1)[-1]
        body = self.roteiros[edge].pop(0)
        if body.get("__status"):
            return RespostaFake(body["__status"], body)
        return RespostaFake(200, body)


def pagina(data: list[dict[str, Any]], after: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"data": data}
    if after:
        body["paging"] = {"next": "https://graph.facebook.com/next", "cursors": {"after": after}}
    return body


def roteiros_hierarquia() -> dict[str, list[dict[str, Any]]]:
    return {
        "campaigns": [pagina([{"id": "1001", "name": "Campanha", "status": "PAUSED", "effective_status": "PAUSED", "objective": "OUTCOME_TRAFFIC"}], "c2"), pagina([{"id": "1002", "name": "Campanha 2", "status": "ACTIVE", "effective_status": "ACTIVE", "objective": "OUTCOME_TRAFFIC"}])],
        "adsets": [pagina([{"id": "2001", "campaign_id": "1001", "name": "Conjunto", "status": "PAUSED", "effective_status": "PAUSED", "optimization_goal": "LANDING_PAGE_VIEWS"}])],
        "ads": [pagina([{"id": "3001", "adset_id": "2001", "name": "Anuncio", "status": "PAUSED", "effective_status": "PAUSED", "creative": {"id": "4001"}}])],
        "adcreatives": [pagina([{"id": "4001", "name": "Criativo", "object_story_id": "story_1"}])],
    }


def test_conta_meta_opaca_estavel_e_resolve_sem_expor_id_cru() -> None:
    conta = dom.ContaMetaDescoberta(
        id_externo="act_123456789012",
        nome="Conta BRL",
        status="1",
        moeda="BRL",
        fuso="America/Sao_Paulo",
        business=dom.BusinessMeta(id_externo="555555", nome="VOLC"),
    )
    assert conta.id_externo == "123456789012"
    assert conta.referencia_opaca != conta.id_externo
    assert conta.referencia_opaca == dom.referencia_opaca_conta("123456789012")
    assert conta.publico()["referencia_opaca"] == conta.referencia_opaca
    assert "123456789012" not in str(conta.publico())


def test_referencia_desconhecida_e_recusada_por_releitura_interna() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake({"adaccounts": [pagina([{"id": "act_123456789012", "name": "Conta BRL", "currency": "BRL", "timezone_name": "America/Sao_Paulo"}])]})
        adaptador = AdaptadorMetaSomenteLeitura(cliente)  # type: ignore[arg-type]
        contas = await adaptador.descobrir_contas(SegredoEfemero(TOKEN))
        assert adaptador.resolver_referencia_opaca(contas, contas[0].referencia_opaca).id_externo == "123456789012"
        with pytest.raises(dom.ContratoMetaInvalido):
            adaptador.resolver_referencia_opaca(contas, "metaacct_desconhecida")
    asyncio.run(cenario())


class ResolvedorFake:
    def __init__(self, token: str) -> None:
        self.token = token
        self.repr_visto: str | None = None

    async def resolver(self, referencia: ReferenciaDeCredencial) -> SegredoEfemero:
        del referencia
        segredo = SegredoEfemero(self.token)
        self.repr_visto = repr(segredo)
        return segredo


def referencia_ok() -> ReferenciaDeCredencial:
    return ReferenciaDeCredencial(
        ativo_id="cred-meta-local",
        provider="1password",
        nome_logico="Meta system user",
        estado="referenced",
        verificacao_estado="verified",
        verificado_em=datetime.now(timezone.utc),
        valido_ate=date(2999, 1, 1),
    )


def test_keychain_falso_resolve_token_apenas_em_memoria_e_hierarquia_pagina() -> None:
    async def cenario() -> None:
        cliente = ClienteGraphFake(roteiros_hierarquia())
        adaptador = AdaptadorMetaSomenteLeitura(cliente, limite_por_pagina=1)
        repo = RepositorioMetaEmMemoria()
        resolvedor = ResolvedorFake(TOKEN)
        recibo = await sincronizar_conta(
            PedidoDeSync(conta_ativo_id="ativo-meta", conta_externa="123456789012", referencia=referencia_ok(), janela="preview"),
            adaptador=adaptador,
            resolvedor=resolvedor,
            repositorio=repo,
        )
        assert recibo.resultado == "ok"
        assert recibo.contagens == {"campaign": 2, "adset": 1, "ad": 1, "creative": 1}
        assert recibo.paginas_lidas == 5
        assert resolvedor.repr_visto == "SegredoEfemero(<oculto>)"
        assert all(TOKEN not in chamada["url"] for chamada in cliente.chamadas)
    asyncio.run(cenario())


def test_falha_na_pagina_2_nao_aplica_ausencia_nem_apaga_ultima_leitura_boa() -> None:
    async def cenario() -> None:
        repo = RepositorioMetaEmMemoria()
        bom = AdaptadorMetaSomenteLeitura(ClienteGraphFake(roteiros_hierarquia()), limite_por_pagina=1)  # type: ignore[arg-type]
        pedido = PedidoDeSync(conta_ativo_id="ativo-meta", conta_externa="123456789012", referencia=referencia_ok(), janela="preview-a")
        await sincronizar_conta(pedido, adaptador=bom, resolvedor=ResolvedorFake(TOKEN), repositorio=repo)
        assert len(repo.objetos) == 5
        ruim_roteiro = roteiros_hierarquia()
        ruim_roteiro["campaigns"] = [pagina([{"id": "1001", "name": "Campanha", "status": "PAUSED", "effective_status": "PAUSED", "objective": "OUTCOME_TRAFFIC"}], "c2"), {"__status": 500, "error": {"code": 2}}]
        ruim = AdaptadorMetaSomenteLeitura(ClienteGraphFake(ruim_roteiro), limite_por_pagina=1)  # type: ignore[arg-type]
        falho = await sincronizar_conta(
            PedidoDeSync(conta_ativo_id="ativo-meta", conta_externa="123456789012", referencia=referencia_ok(), janela="preview-b"),
            adaptador=ruim,
            resolvedor=ResolvedorFake(TOKEN),
            repositorio=repo,
        )
        assert falho.resultado == "falhou"
        assert len(repo.objetos) == 5
        assert repo.ausentes == set()
    asyncio.run(cenario())


def test_insights_preservam_null_e_actions_nao_sao_achatadas() -> None:
    insight = dom.InsightMeta(
        provider="META_ADS",
        conta_externa="123456789012",
        nivel="ad",
        objeto_externo="3001",
        periodo_inicio=date(2026, 9, 1),
        periodo_fim=date(2026, 9, 1),
        janela_atribuicao="7d_click",
        breakdown="none",
        observado_em=datetime.now(timezone.utc),
        spend=None,
        impressions=None,
        reach=10,
        frequency=None,
        clicks=None,
        inline_link_clicks=None,
        landing_page_views=None,
        cpm=None,
        cpc=None,
        ctr=None,
        actions=(dom.AcaoInsightMeta("lead", None, "7d_click", "ad", date(2026, 9, 1), date(2026, 9, 1)),),
    )
    linhas = linhas_de_insights([insight], conta_ativo_id="ativo-meta")
    fato = linhas["trafego_meta_insight_daily"][0]
    acao = linhas["trafego_meta_insight_action"][0]
    assert fato["spend"] is None
    assert fato["impressions"] is None
    assert acao["action_type"] == "lead"
    assert acao["value"] is None


def app_cliente(chaveiro: Any) -> TestClient:
    app = FastAPI()
    app.include_router(meta_local.router)
    quem = Identidade(sub="u-meta", email="admin@volc", papel="ADMIN", origem="sessao")
    app.dependency_overrides[exigir_admin] = lambda: quem
    return TestClient(app, headers={"host": "localhost"})


class ChaveiroFake:
    def __init__(self) -> None:
        self.valor = CredencialLocal.agora(TOKEN).serializar()

    def ler(self, conta: str) -> str:
        assert conta == "supabase-user:u-meta"
        return self.valor

    def salvar(self, conta: str, valor: str) -> None:
        self.valor = valor

    def remover(self, conta: str) -> bool:
        raise AssertionError("nao usado")


def test_rotas_preview_nao_devolvem_token_e_nao_tem_mutate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(meta_local.sys, "platform", "darwin")
    chaveiro = ChaveiroFake()
    monkeypatch.setattr(meta_local, "_chaveiro", lambda: chaveiro)

    async def contas(token: str) -> list[dom.ContaMetaDescoberta]:
        assert token == TOKEN
        return [dom.ContaMetaDescoberta(id_externo="123456789012", nome="Conta", status="1", moeda="BRL", fuso="America/Sao_Paulo")]

    async def preflight(token: str, referencia_opaca: str) -> dict[str, Any]:
        assert token == TOKEN
        assert referencia_opaca == dom.referencia_opaca_conta("123456789012")
        return {"ok": True, "referencia_opaca": referencia_opaca, "contagens": {"campaign": 1}, "capacidades_disponiveis": ["META_READ_INVENTORY"], "capacidades_ausentes": ["META_CREATE_PAUSED"], "frescor": "observado_agora", "erros": [], "proxima_acao": "preparar_sincronizacao"}

    monkeypatch.setattr(meta_local, "_descobrir_contas_com_token", contas)
    monkeypatch.setattr(meta_local, "_preflight_com_token", preflight)
    cliente = app_cliente(chaveiro)
    descoberta = cliente.get("/api/trafego/meta/local/contas")
    assert descoberta.status_code == 200
    ref = descoberta.json()["contas"][0]["referencia_opaca"]
    assert "123456789012" not in descoberta.text
    assert TOKEN not in descoberta.text
    prova = cliente.post("/api/trafego/meta/local/preflight", json={"referencia_opaca": ref})
    assert prova.status_code == 200
    assert TOKEN not in prova.text
    assert "123456789012" not in prova.text
    rotas = {(r.path, tuple(sorted(r.methods))) for r in meta_local.router.routes}
    assert not any("mutate" in path or "criar" in path or "ativar" in path for path, _ in rotas)


def test_sql_e_rollback_de_insights_sao_coerentes() -> None:
    sql = Path("supabase/migrations/v15_02_meta_ads_insights.sql").read_text()
    rollback = Path("supabase/migrations/v15_98_meta_ads_insights_rollback.sql").read_text()
    assert "CREATE TABLE public.trafego_meta_insight_daily" in sql
    assert "CREATE TABLE public.trafego_meta_insight_action" in sql
    assert "spend                  numeric" in sql
    assert "impressions            bigint" in sql
    daily_table = sql.lower().split("create table public.trafego_meta_insight_daily", 1)[1].split("create table public.trafego_meta_insight_action", 1)[0]
    assert "actions" not in daily_table
    assert "DROP TABLE IF EXISTS public.trafego_meta_insight_action" in rollback
    assert "DROP TABLE IF EXISTS public.trafego_meta_insight_daily" in rollback
