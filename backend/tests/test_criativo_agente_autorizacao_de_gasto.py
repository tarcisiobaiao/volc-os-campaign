"""O consentimento explícito que precede qualquer render pago.

O plano já era recalculado no servidor, mas plano responde "o que aconteceria",
não "alguém autorizou que acontecesse". Sem esta porta, qualquer POST bem
formado — uma aba antiga, um script, um botão que mudou de significado depois
que a tela foi desenhada — despachava chamadas pagas sem ninguém ter lido um
número.

Estes testes provam as quatro recusas e o caminho feliz com um motor e um
executor DUBLÊS. Nenhum provider é chamado, nenhuma imagem é gerada, nenhum
centavo é gasto: o dublê levanta se alguém tentar sair para a rede.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.routers import criativos_agente  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_usuario  # noqa: E402

from test_criativo_studio_adaptador import PROJECT_REF, RUN_REF, RepoDeGeracao  # noqa: E402


OWNER = "11111111-1111-4111-8111-111111111111"
MODELO = "gemini:gemini-3.1-flash-image"

#: 0.039 por imagem é o preço de REFERÊNCIA publicado pelo motor. Duas imagens
#: dão 0.078 — o número que a autorização precisa cobrir.
CUSTO_DE_DUAS = 0.078


class MotorDublê:
    nome = MODELO
    configurado = True


class ExecutorDublê:
    """Conta o que foi despachado. Se for chamado numa recusa, o teste falha."""

    def __init__(self) -> None:
        self.criados: list[dict] = []
        self.disparados: list[str] = []

    async def criar_job_de_imagem(self, pedido, owner_id):
        job = {"id": f"job-{len(self.criados) + 1}"}
        self.criados.append({"pedido": pedido, "owner_id": owner_id})
        return job, True

    def disparar(self, job_id: str) -> None:
        self.disparados.append(job_id)


class RepoQueGrava(RepoDeGeracao):
    async def registrar_ponte(self, row):
        self.pontes.append(row)
        return row


@pytest.fixture
def cenario(monkeypatch):
    """Motor e executor dublês instalados no lugar dos de produção.

    A rota importa `obter_motor`/`obter_executor` de dentro da função, então o
    monkeypatch precisa acertar o MÓDULO de origem — trocar um atributo já
    importado não teria efeito nenhum aqui.
    """
    from app.routers import criativos as rotas_criativos

    executor = ExecutorDublê()
    monkeypatch.setattr(rotas_criativos, "obter_motor", lambda: MotorDublê())
    monkeypatch.setattr(rotas_criativos, "obter_executor", lambda *a, **k: executor)
    monkeypatch.setattr(rotas_criativos, "obter_repo", lambda *a, **k: object())
    monkeypatch.setattr(rotas_criativos, "obter_assinador", lambda *a, **k: object())

    repo = RepoQueGrava(aprovadas=["creative_variacao_1", "creative_variacao_2"])
    app = FastAPI()
    app.include_router(criativos_agente.router)
    app.dependency_overrides[exigir_usuario] = lambda: Identidade(
        sub=OWNER, email="operador@example.com", papel="ADMIN", origem="sessao"
    )
    app.dependency_overrides[criativos_agente.obter_repositorio] = lambda: repo
    return TestClient(app), executor, repo


def _gerar(cliente, autorizacao, *, refs=None, formatos=None):
    corpo = {
        "run_ref": RUN_REF,
        "selected_creative_refs": refs or ["creative_variacao_1", "creative_variacao_2"],
        "format_ids": formatos or ["1x1"],
    }
    if autorizacao is not None:
        corpo["autorizacao"] = autorizacao
    return cliente.post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/geracoes", json=corpo
    )


def _ok(total: int = 2, teto: float | None = 1.0) -> dict:
    return {"modelo": MODELO, "total_de_renders": total, "teto_custo_usd": teto}


# ── o plano precisa dizer com o quê ──────────────────────────────────────────


def test_o_plano_nomeia_o_modelo_e_marca_o_custo_como_estimativa(cenario):
    cliente, _executor, _repo = cenario
    r = cliente.post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/geracoes/plano",
        json={
            "run_ref": RUN_REF,
            "selected_creative_refs": ["creative_variacao_1", "creative_variacao_2"],
            "format_ids": ["1x1"],
        },
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["modelo_de_imagem"] == MODELO
    assert corpo["motor_configurado"] is True
    assert corpo["total_de_renders"] == 2
    # "estimativa" precisa viajar junto do número: o provider cobra por token e
    # nunca devolve dólar, então a tela não pode apresentar isto como fatura.
    assert corpo["custo_e_estimado"] is True
    assert corpo["custo_estimado_usd"] == pytest.approx(CUSTO_DE_DUAS)


# ── as quatro recusas ────────────────────────────────────────────────────────


def test_sem_autorizacao_nao_despacha_nada(cenario):
    cliente, executor, repo = cenario
    r = _gerar(cliente, None)
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["codigo"] == "CRIATIVO_STUDIO_SEM_AUTORIZACAO_DE_GASTO"
    assert detalhe["nada_foi_criado"] is True
    # A recusa CARREGA o que precisa ser confirmado, para a tela não ter que
    # adivinhar nem refazer a conta por conta própria.
    assert detalhe["modelo_de_imagem"] == MODELO
    assert detalhe["total_de_renders"] == 2
    assert executor.criados == [] and executor.disparados == []
    assert repo.pontes == []


def test_modelo_divergente_recusa(cenario):
    cliente, executor, _repo = cenario
    r = _gerar(cliente, {**_ok(), "modelo": "openai:gpt-image-2"})
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CRIATIVO_STUDIO_MODELO_DIVERGENTE"
    assert executor.criados == []


def test_total_divergente_recusa(cenario):
    """A seleção mudou entre a tela e o clique: o consentimento não cobre isto."""
    cliente, executor, _repo = cenario
    r = _gerar(cliente, _ok(total=1))
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["codigo"] == "CRIATIVO_STUDIO_TOTAL_DIVERGENTE"
    assert detalhe["autorizado"] == 1 and detalhe["total_de_renders"] == 2
    assert executor.criados == []


def test_teto_de_custo_abaixo_da_estimativa_recusa(cenario):
    cliente, executor, _repo = cenario
    r = _gerar(cliente, _ok(teto=0.01))
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["codigo"] == "CRIATIVO_STUDIO_TETO_DE_CUSTO"
    assert detalhe["custo_e_estimado"] is True
    assert executor.criados == []


# ── o caminho autorizado ─────────────────────────────────────────────────────


def test_autorizacao_conferida_despacha_um_job_por_conceito(cenario):
    cliente, executor, repo = cenario
    r = _gerar(cliente, _ok())
    assert r.status_code == 201, r.text
    corpo = r.json()

    assert corpo["total_de_renders"] == 2
    assert {g["creative_ref"] for g in corpo["geracoes"]} == {
        "creative_variacao_1",
        "creative_variacao_2",
    }
    # Um job por CONCEITO, com os formatos dele dentro — é o que faz falha em
    # 9x16 não jogar fora o 1x1 pronto.
    assert len(executor.criados) == 2
    assert executor.disparados == ["job-1", "job-2"]
    # E a procedência foi gravada com a linhagem, não só com o id do job.
    assert len(repo.pontes) == 2
    assert all(p["group_ref"] and p["copy_ref"] and p["state_ref"] for p in repo.pontes)


def test_teto_ausente_e_permitido_e_a_contagem_continua_valendo(cenario):
    """Custo desconhecido não pode travar o produto — a contagem ainda limita.

    O teto em dólar é opcional de propósito: ele confere uma ESTIMATIVA. O
    limite que o servidor impõe com exatidão é o número de chamadas, e esse
    continua sendo conferido mesmo sem teto financeiro.
    """
    cliente, executor, _repo = cenario
    r = _gerar(cliente, _ok(teto=None))
    assert r.status_code == 201, r.text
    assert len(executor.criados) == 2


def test_reenviar_o_mesmo_pedido_autorizado_nao_paga_de_novo(cenario):
    cliente, executor, _repo = cenario
    assert _gerar(cliente, _ok()).status_code == 201
    segunda = _gerar(cliente, _ok())
    assert segunda.status_code == 201

    # A ponte é única por (run_ref, creative_ref) e responde ANTES do executor.
    assert len(executor.criados) == 2
    assert all(g["criado_agora"] is False for g in segunda.json()["geracoes"])
