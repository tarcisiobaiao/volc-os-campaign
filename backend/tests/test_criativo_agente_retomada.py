"""Retomada: o que o servidor precisa devolver para a revisão sobreviver ao reload.

O defeito que estes testes fecham não era de banco nem de tela isoladamente: as
decisões estavam gravadas, append-only e corretas, e mesmo assim recarregar a
página mostrava o lote inteiro como não aprovado. A leitura da operação
devolvia `operacao` e `runs` e mais nada, então a única memória da revisão era o
estado de sessão do React — que morre no F5.

O segundo defeito é mais caro e estava escondido atrás do primeiro: a aprovação
era conferida SÓ pelo caminho. Como o caminho endereça por `ref` e a ref
sobrevive ao refinamento, uma peça reescrita continuava "aprovada" e liberava o
botão que gasta. Aprovar é sobre CONTEÚDO, não sobre endereço.

Nada aqui chama modelo, provider, banco oficial ou API de anúncios.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.criativo.agente.persistencia import NaoEncontrado  # noqa: E402
from app.routers import criativos_agente  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_usuario  # noqa: E402

from test_criativo_studio_adaptador import saida  # noqa: E402


PROJECT_REF = "crproj_" + "a" * 24
RUN_REF = "crrun_" + "b" * 24
RUN_REF_2 = "crrun_" + "c" * 24
OWNER = "11111111-1111-4111-8111-111111111111"


def _hash(valor) -> str:
    return criativos_agente._hash_valor(valor)


def _decisao(caminho: str, decisao: str, *, snapshot, quando: str, run_ref: str = RUN_REF) -> dict:
    return {
        "decision_ref": "crdec_" + "d" * 24,
        "project_ref": PROJECT_REF,
        "run_ref": run_ref,
        "owner_id": OWNER,
        "decisao": decisao,
        "scope": "PECA",
        "path": caminho,
        "snapshot": snapshot,
        "snapshot_sha256": _hash(snapshot),
        "feedback": None,
        "created_at": quando,
    }


class RepoDeRetomada:
    """Um dublê do repositório que só sabe o que o banco realmente guarda.

    `listar_decisoes` devolve em ordem crescente de `created_at`, como o
    PostgREST devolve com `order=created_at.asc` — a ordem é o que faz a última
    decisão de cada caminho vencer, então inverter isto aqui esconderia o
    defeito em vez de prová-lo.
    """

    def __init__(self, *, runs: list[dict], decisoes: list[dict], dono: str = OWNER):
        self.runs = runs
        self.decisoes = decisoes
        self.dono = dono
        self.pontes: list[dict] = []

    def _confinar(self, owner_id: str) -> None:
        if owner_id != self.dono:
            raise NaoEncontrado(PROJECT_REF)

    async def obter_operacao(self, project_ref, owner_id):
        self._confinar(owner_id)
        return {
            "project_ref": PROJECT_REF,
            "owner_id": self.dono,
            "status": "READY_FOR_REVIEW",
            "latest_run_ref": self.runs[0]["run_ref"] if self.runs else None,
            "input": {
                "nome_da_operacao": "Operação teste",
                "contexto_do_publico": "Pessoa buscando entender o processo.",
                "objetivo_meta": "OUTCOME_TRAFFIC",
            },
        }

    async def listar_runs(self, project_ref, owner_id):
        self._confinar(owner_id)
        return self.runs

    async def listar_decisoes(self, project_ref, owner_id):
        self._confinar(owner_id)
        return sorted(self.decisoes, key=lambda d: d["created_at"])

    async def obter_run(self, run_ref, owner_id):
        self._confinar(owner_id)
        for r in self.runs:
            if r["run_ref"] == run_ref:
                return r
        raise NaoEncontrado(run_ref)

    async def listar_pontes(self, project_ref, owner_id):
        self._confinar(owner_id)
        return self.pontes

    async def ponte_por_peca(self, run_ref, creative_ref, owner_id):
        return None


def _cliente(repo, *, sub: str = OWNER) -> TestClient:
    app = FastAPI()
    app.include_router(criativos_agente.router)
    app.dependency_overrides[exigir_usuario] = lambda: Identidade(
        sub=sub, email="operador@example.com", papel="ADMIN", origem="sessao"
    )
    app.dependency_overrides[criativos_agente.obter_repositorio] = lambda: repo
    return TestClient(app)


def _run(run_ref: str, lote, *, quando: str) -> dict:
    return {
        "run_ref": run_ref,
        "project_ref": PROJECT_REF,
        "owner_id": OWNER,
        "status": "COMPLETED",
        "output": lote.model_dump(mode="json"),
        "created_at": quando,
    }


def _peca(lote, ref: str) -> dict:
    return next(p for p in lote.model_dump(mode="json")["pecas"] if p["ref"] == ref)


# ── a projeção que faltava ───────────────────────────────────────────────────


def test_ler_operacao_projeta_as_decisoes_persistidas():
    lote = saida()
    alvo = _peca(lote, "creative_variacao_1")
    repo = RepoDeRetomada(
        runs=[_run(RUN_REF, lote, quando="2026-09-07T12:00:00Z")],
        decisoes=[
            _decisao(
                "/pecas/creative_variacao_1",
                "APROVADO",
                snapshot=alvo,
                quando="2026-09-07T12:05:00Z",
            )
        ],
    )
    r = _cliente(repo).get(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}")
    assert r.status_code == 200, r.text
    corpo = r.json()

    assert [d["path"] for d in corpo["decisoes"]] == ["/pecas/creative_variacao_1"]
    assert corpo["decisoes"][0]["decisao"] == "APROVADO"
    # O snapshot inteiro NÃO volta: a run já carrega a peça, e repeti-la
    # dobraria a resposta sem acrescentar informação.
    assert "snapshot" not in corpo["decisoes"][0]
    assert corpo["aprovacoes_validas"] == {RUN_REF: ["/pecas/creative_variacao_1"]}


def test_reprovar_depois_de_aprovar_prevalece_na_retomada():
    lote = saida()
    alvo = _peca(lote, "creative_variacao_1")
    repo = RepoDeRetomada(
        runs=[_run(RUN_REF, lote, quando="2026-09-07T12:00:00Z")],
        decisoes=[
            _decisao(
                "/pecas/creative_variacao_1", "APROVADO", snapshot=alvo, quando="2026-09-07T12:05:00Z"
            ),
            _decisao(
                "/pecas/creative_variacao_1", "REPROVADO", snapshot=alvo, quando="2026-09-07T12:09:00Z"
            ),
        ],
    )
    corpo = _cliente(repo).get(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}").json()

    assert len(corpo["decisoes"]) == 1
    assert corpo["decisoes"][0]["decisao"] == "REPROVADO"
    assert corpo["aprovacoes_validas"] == {RUN_REF: []}


def test_conteudo_mudado_nao_herda_a_aprovacao_anterior():
    """O teste mais caro do arquivo: a ref sobrevive ao refinamento, o texto não.

    A run 2 mantém `creative_variacao_1` e troca o hook. A aprovação foi dada
    sobre o conteúdo da run 1. Se a conferência olhasse só o caminho, a peça
    reescrita apareceria aprovada e liberaria o clique que gasta.
    """
    lote1 = saida()
    aprovada = _peca(lote1, "creative_variacao_1")

    lote2 = saida()
    bruto = lote2.model_dump(mode="json")
    for p in bruto["pecas"]:
        if p["ref"] == "creative_variacao_1":
            p["hook"] = "Hook reescrito depois da aprovacao, que ninguem revisou"
    run2 = {
        "run_ref": RUN_REF_2,
        "project_ref": PROJECT_REF,
        "owner_id": OWNER,
        "status": "COMPLETED",
        "output": bruto,
        "created_at": "2026-09-07T13:00:00Z",
    }

    repo = RepoDeRetomada(
        runs=[run2, _run(RUN_REF, lote1, quando="2026-09-07T12:00:00Z")],
        decisoes=[
            _decisao(
                "/pecas/creative_variacao_1",
                "APROVADO",
                snapshot=aprovada,
                quando="2026-09-07T12:05:00Z",
            )
        ],
    )
    cliente = _cliente(repo)
    corpo = cliente.get(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}").json()

    # A run antiga continua aprovada; a nova, não.
    assert corpo["aprovacoes_validas"][RUN_REF] == ["/pecas/creative_variacao_1"]
    assert corpo["aprovacoes_validas"][RUN_REF_2] == []

    # E o plano da run nova RECUSA, antes de existir job ou chamada paga.
    plano = cliente.post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/geracoes/plano",
        json={
            "run_ref": RUN_REF_2,
            "selected_creative_refs": ["creative_variacao_1"],
            "format_ids": ["1x1"],
        },
    )
    assert plano.status_code == 200, plano.text
    assert plano.json()["pode_executar"] is False
    assert [b["codigo"] for b in plano.json()["bloqueios"]] == [
        "CRIATIVO_STUDIO_PECA_NAO_APROVADA"
    ]


def test_aprovacao_de_caminho_que_sumiu_do_lote_nao_conta():
    lote = saida()
    repo = RepoDeRetomada(
        runs=[_run(RUN_REF, lote, quando="2026-09-07T12:00:00Z")],
        decisoes=[
            _decisao(
                "/pecas/creative_que_nao_existe_mais",
                "APROVADO",
                snapshot={"ref": "creative_que_nao_existe_mais"},
                quando="2026-09-07T12:05:00Z",
            )
        ],
    )
    corpo = _cliente(repo).get(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}").json()
    assert corpo["aprovacoes_validas"] == {RUN_REF: []}


def test_run_nao_concluida_nao_aparece_em_aprovacoes_validas():
    lote = saida()
    alvo = _peca(lote, "creative_variacao_1")
    enfileirada = {
        "run_ref": RUN_REF_2,
        "project_ref": PROJECT_REF,
        "owner_id": OWNER,
        "status": "QUEUED",
        "output": None,
        "created_at": "2026-09-07T13:00:00Z",
    }
    repo = RepoDeRetomada(
        runs=[enfileirada, _run(RUN_REF, lote, quando="2026-09-07T12:00:00Z")],
        decisoes=[
            _decisao(
                "/pecas/creative_variacao_1", "APROVADO", snapshot=alvo, quando="2026-09-07T12:05:00Z"
            )
        ],
    )
    corpo = _cliente(repo).get(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}").json()
    assert RUN_REF_2 not in corpo["aprovacoes_validas"]
    assert corpo["aprovacoes_validas"][RUN_REF] == ["/pecas/creative_variacao_1"]


def test_operacao_de_outro_dono_nao_vaza_na_retomada():
    lote = saida()
    alvo = _peca(lote, "creative_variacao_1")
    repo = RepoDeRetomada(
        runs=[_run(RUN_REF, lote, quando="2026-09-07T12:00:00Z")],
        decisoes=[
            _decisao(
                "/pecas/creative_variacao_1", "APROVADO", snapshot=alvo, quando="2026-09-07T12:05:00Z"
            )
        ],
    )
    outro = "22222222-2222-4222-8222-222222222222"
    r = _cliente(repo, sub=outro).get(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}")
    assert r.status_code == 404
    assert r.json()["detail"]["codigo"] == "CRIATIVO_AGENTE_OPERACAO_INEXISTENTE"
