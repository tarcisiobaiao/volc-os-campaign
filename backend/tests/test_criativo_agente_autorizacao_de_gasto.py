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
    qualidade = "referencia"
    configurado = True
    #: O preço agora vem do MOTOR e não de uma constante do Gemini importada
    #: direto. O dublê declara o mesmo 0.039 de referência para que as
    #: asserções de custo continuem medindo a conta, e não o import.
    preco_referencia_usd_por_imagem = 0.039


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


#: Segredo do selo. `segredo_de_assinatura()` deriva dele quando não há um
#: `CRIATIVO_URL_SECRET` próprio; declarar aqui torna o selo determinístico no
#: teste sem tocar em nenhum segredo real.
SEGREDO_DE_TESTE = "segredo-de-teste-para-selar-plano"


@pytest.fixture
def cenario(monkeypatch):
    """Motor e executor dublês instalados no lugar dos de produção.

    A rota importa `obter_motor`/`obter_executor` de dentro da função, então o
    monkeypatch precisa acertar o MÓDULO de origem — trocar um atributo já
    importado não teria efeito nenhum aqui.
    """
    from app.routers import criativos as rotas_criativos

    monkeypatch.setenv("CRIATIVO_URL_SECRET", SEGREDO_DE_TESTE)
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


def _planejar(cliente, *, refs=None, formatos=None):
    return cliente.post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/geracoes/plano",
        json={
            "run_ref": RUN_REF,
            "selected_creative_refs": refs
            or ["creative_variacao_1", "creative_variacao_2"],
            "format_ids": formatos or ["1x1"],
        },
    )


def _selo(cliente, *, refs=None, formatos=None) -> str:
    """O selo REAL emitido pelo plano para esta seleção.

    Os testes pegam o selo do próprio servidor, e não de um literal, porque é
    exatamente isso que o produto faz: a tela confere o plano, recebe o selo e o
    devolve. Um selo fabricado no teste provaria o formato e não o vínculo.
    """
    resposta = _planejar(cliente, refs=refs, formatos=formatos)
    assert resposta.status_code == 200, resposta.text
    selo = resposta.json()["selo_do_plano"]
    assert selo, "o plano executável precisa emitir selo"
    return selo


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


def _ok(
    cliente=None,
    total: int = 2,
    teto: float | None = 1.0,
    *,
    selo: str = "",
    refs=None,
    formatos=None,
) -> dict:
    return {
        "modelo": MODELO,
        "total_de_renders": total,
        "teto_custo_usd": teto,
        "selo_do_plano": selo or _selo(cliente, refs=refs, formatos=formatos),
    }


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
    r = _gerar(cliente, {**_ok(cliente), "modelo": "openai:gpt-image-2"})
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CRIATIVO_STUDIO_MODELO_DIVERGENTE"
    assert executor.criados == []


def test_total_divergente_recusa(cenario):
    """A seleção mudou entre a tela e o clique: o consentimento não cobre isto."""
    cliente, executor, _repo = cenario
    r = _gerar(cliente, _ok(cliente, total=1))
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["codigo"] == "CRIATIVO_STUDIO_TOTAL_DIVERGENTE"
    assert detalhe["autorizado"] == 1 and detalhe["total_de_renders"] == 2
    assert executor.criados == []


def test_teto_de_custo_abaixo_da_estimativa_recusa(cenario):
    cliente, executor, _repo = cenario
    r = _gerar(cliente, _ok(cliente, teto=0.01))
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["codigo"] == "CRIATIVO_STUDIO_TETO_DE_CUSTO"
    assert detalhe["custo_e_estimado"] is True
    assert executor.criados == []


# ── o caminho autorizado ─────────────────────────────────────────────────────


def test_autorizacao_conferida_despacha_um_job_por_conceito(cenario):
    cliente, executor, repo = cenario
    r = _gerar(cliente, _ok(cliente))
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
    r = _gerar(cliente, _ok(cliente, teto=None))
    assert r.status_code == 201, r.text
    assert len(executor.criados) == 2


def test_reenviar_o_mesmo_pedido_autorizado_nao_paga_de_novo(cenario):
    cliente, executor, _repo = cenario
    assert _gerar(cliente, _ok(cliente)).status_code == 201
    segunda = _gerar(cliente, _ok(cliente))
    assert segunda.status_code == 201

    # A ponte é única por (run_ref, creative_ref) e responde ANTES do executor.
    assert len(executor.criados) == 2
    assert all(g["criado_agora"] is False for g in segunda.json()["geracoes"])


# ═══════════════════════════════════════════════════════════════════════════
# O SELO — o consentimento vale para UM conteúdo de plano, e por um prazo
# ═══════════════════════════════════════════════════════════════════════════


def test_o_plano_executavel_emite_selo_e_o_bloqueado_nao(cenario, monkeypatch):
    """Emitir selo para um plano bloqueado convidaria o cliente a tentar mesmo assim."""
    cliente, _executor, repo = cenario
    assert _planejar(cliente).json()["selo_do_plano"]

    repo.aprovadas = []
    corpo = _planejar(cliente).json()
    assert corpo["pode_executar"] is False
    assert corpo["selo_do_plano"] is None


def test_autorizacao_de_OUTRA_selecao_e_recusada_mesmo_com_modelo_e_total_iguais(cenario):
    """A recusa que os três campos antigos não conseguiam dar.

    O operador confere {variação 1} × {1x1} = 1 render. Um POST manda
    {variação 2} × {1x1} = 1 render com a MESMA autorização: mesmo modelo, mesmo
    total, mesmo teto. Antes do selo isso passava, e o lote produzido não era o
    lote que a pessoa leu.
    """
    cliente, executor, repo = cenario
    selo_da_primeira = _selo(cliente, refs=["creative_variacao_1"])

    r = _gerar(
        cliente,
        {
            "modelo": MODELO,
            "total_de_renders": 1,
            "teto_custo_usd": 1.0,
            "selo_do_plano": selo_da_primeira,
        },
        refs=["creative_variacao_2"],
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["codigo"] == "CRIATIVO_STUDIO_PLANO_DIVERGENTE"
    assert executor.criados == [] and repo.pontes == []


def test_autorizacao_de_OUTROS_FORMATOS_e_recusada(cenario):
    cliente, executor, _repo = cenario
    selo = _selo(cliente, refs=["creative_variacao_1"], formatos=["1x1"])
    r = _gerar(
        cliente,
        {
            "modelo": MODELO,
            "total_de_renders": 1,
            "teto_custo_usd": 1.0,
            "selo_do_plano": selo,
        },
        refs=["creative_variacao_1"],
        formatos=["4x5"],
    )
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CRIATIVO_STUDIO_PLANO_DIVERGENTE"
    assert executor.criados == []


def test_selo_forjado_e_recusado_como_vencido(cenario):
    cliente, executor, _repo = cenario
    r = _gerar(cliente, _ok(cliente, selo="nao.eh.um.selo.valido"))
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CRIATIVO_STUDIO_AUTORIZACAO_VENCIDA"
    assert executor.criados == []


def test_selo_expirado_e_recusado_e_nada_e_criado(cenario, monkeypatch):
    """Uma aba aberta há horas não autoriza: o preço e o motor podem ter mudado.

    O relógio é adiantado em vez de o selo nascer vencido, porque `emitir_selo`
    se recusa a emitir um selo já morto (`max(1, ttl_s)`) — e essa recusa é uma
    guarda de produção que não deve ser afrouxada para caber num teste.
    """
    import time as _time

    from app.criativo.studio import autorizacao as mod

    cliente, executor, _repo = cenario
    selo = _selo(cliente)

    depois = _time.time() + mod.TTL_PADRAO_S + 60
    monkeypatch.setattr(mod.time, "time", lambda: depois)

    r = _gerar(cliente, _ok(cliente, selo=selo))
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CRIATIVO_STUDIO_AUTORIZACAO_VENCIDA"
    assert executor.criados == []


def test_selo_de_outro_segredo_nao_vale(cenario):
    """Sem isso, qualquer um que saiba o algoritmo emitiria a própria autorização."""
    from app.criativo.studio.autorizacao import assinatura_do_plano, emitir_selo

    cliente, executor, _repo = cenario
    intruso = emitir_selo(
        assinatura_do_plano(
            run_ref=RUN_REF,
            creative_refs=["creative_variacao_1", "creative_variacao_2"],
            format_ids=["1x1"],
            modelo=MODELO,
            qualidade="referencia",
            total_de_renders=2,
            custo_estimado_usd=CUSTO_DE_DUAS,
            anexo_sha256=None,
            modo_de_composicao=None,
        ),
        segredo="outro-segredo-completamente-diferente",
    )
    r = _gerar(cliente, _ok(cliente, selo=intruso))
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CRIATIVO_STUDIO_AUTORIZACAO_VENCIDA"
    assert executor.criados == []


def test_reordenar_a_selecao_nao_invalida_o_selo(cenario):
    """`[A, B]` e `[B, A]` são a mesma escolha. Recusar seria confundir por nada."""
    cliente, executor, _repo = cenario
    selo = _selo(cliente, refs=["creative_variacao_1", "creative_variacao_2"])
    r = _gerar(
        cliente,
        {
            "modelo": MODELO,
            "total_de_renders": 2,
            "teto_custo_usd": 1.0,
            "selo_do_plano": selo,
        },
        refs=["creative_variacao_2", "creative_variacao_1"],
    )
    assert r.status_code == 201, r.text
    assert len(executor.criados) == 2


# ═══════════════════════════════════════════════════════════════════════════
# CUSTO SEM ESTIMATIVA — o caso que o gpt-image-2 transforma em regra
# ═══════════════════════════════════════════════════════════════════════════


class MotorSemPreco:
    """O contrato do `gpt-image-2`: cobra por token, não publica dólar por imagem."""

    nome = "openai:gpt-image-2"
    qualidade = "medium"
    configurado = True
    preco_referencia_usd_por_imagem = None


@pytest.fixture
def cenario_sem_preco(monkeypatch, cenario):
    from app.routers import criativos as rotas_criativos

    monkeypatch.setattr(rotas_criativos, "obter_motor", lambda: MotorSemPreco())
    return cenario


def test_motor_sem_preco_publica_estimativa_nula_e_nunca_zero(cenario_sem_preco):
    cliente, _executor, _repo = cenario_sem_preco
    corpo = _planejar(cliente).json()
    assert corpo["modelo_de_imagem"] == "openai:gpt-image-2"
    assert corpo["qualidade_de_imagem"] == "medium"
    assert corpo["custo_estimado_usd"] is None
    assert corpo["custo_tem_estimativa"] is False


def test_o_preco_do_gemini_nao_contamina_o_plano_de_outro_provider(cenario_sem_preco):
    """O defeito era importar a constante do Gemini sem olhar o motor que ia rodar."""
    cliente, _executor, _repo = cenario_sem_preco
    assert _planejar(cliente).json()["custo_estimado_usd"] != pytest.approx(CUSTO_DE_DUAS)


def test_sem_estimativa_e_sem_consentimento_explicito_o_pedido_e_recusado(
    cenario_sem_preco,
):
    """Antes, um teto declarado sem estimativa era ignorado em silêncio."""
    cliente, executor, repo = cenario_sem_preco
    r = _gerar(
        cliente,
        {
            "modelo": "openai:gpt-image-2",
            "total_de_renders": 2,
            "teto_custo_usd": 0.50,
            "selo_do_plano": _selo(cliente),
        },
    )
    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe["codigo"] == "CRIATIVO_STUDIO_SEM_ESTIMATIVA_DE_CUSTO"
    assert detalhe["custo_estimado_usd"] is None
    assert detalhe["limite_efetivo"] == "quantidade_de_imagens"
    assert detalhe["nada_foi_criado"] is True
    assert executor.criados == [] and repo.pontes == []


def test_com_consentimento_explicito_o_lote_sem_estimativa_roda(cenario_sem_preco):
    cliente, executor, _repo = cenario_sem_preco
    r = _gerar(
        cliente,
        {
            "modelo": "openai:gpt-image-2",
            "total_de_renders": 2,
            "teto_custo_usd": None,
            "aceito_sem_estimativa": True,
            "selo_do_plano": _selo(cliente),
        },
    )
    assert r.status_code == 201, r.text
    assert len(executor.criados) == 2


# ═══════════════════════════════════════════════════════════════════════════
# MOTOR ANÔNIMO — "não sei qual motor vai rodar" não é "autorizado"
# ═══════════════════════════════════════════════════════════════════════════


class MotorSemNome:
    nome = None
    qualidade = None
    configurado = True
    preco_referencia_usd_por_imagem = 0.039


def test_motor_que_nao_se_nomeia_nao_recebe_autorizacao(cenario, monkeypatch):
    cliente, executor, _repo = cenario
    selo = _selo(cliente)

    from app.routers import criativos as rotas_criativos

    monkeypatch.setattr(rotas_criativos, "obter_motor", lambda: MotorSemNome())
    r = _gerar(
        cliente,
        {
            "modelo": MODELO,
            "total_de_renders": 2,
            "teto_custo_usd": 1.0,
            "selo_do_plano": selo,
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CRIATIVO_STUDIO_MODELO_DIVERGENTE"
    assert executor.criados == []
