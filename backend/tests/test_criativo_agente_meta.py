from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.criativo.agente.contrato import (
    ElementoCongelado,
    EntradaNovaOperacao,
    PedidoDoAgente,
    SaidaDoAgente,
)
from app.criativo.agente.orquestrador import (
    AgenteCriativoMeta,
    RespostaDoModeloInvalida,
    ResultadoDoAgente,
)
from app.criativo.agente.prompts import montar_missao
from app.criativo.agente.validacao import SaidaCriativaInvalida, validar_saida
from app.routers import criativos_agente
from app.seguranca.identidade import Identidade, exigir_usuario


PROJECT_REF = "crproj_" + "a" * 24
RUN_REF = "crrun_" + "b" * 24
OWNER = "11111111-1111-1111-1111-111111111111"


def pedido(qtd: int = 3) -> PedidoDoAgente:
    return PedidoDoAgente(
        project_ref=PROJECT_REF,
        nome_da_operacao="Foco Genial",
        destination_ref="destino:aprovado",
        objetivo_meta="OUTCOME_TRAFFIC",
        contexto_do_publico="Pessoa buscando entender um processo antes de decidir.",
        fatos_da_oferta=[
            {
                "ref": "fact_lp_offer",
                "declaracao": "A página entrega conteúdo informativo e independente.",
                "origem": "LANDING_PAGE",
                "evidencia_ref": "destino:aprovado",
            }
        ],
        formatos_permitidos=["1x1", "4x5", "9x16"],
        quantidade_de_pecas=qtd,
    )


def saida(qtd: int = 3) -> dict:
    estados = [
        {
            "ref": f"state_momento_{i}",
            "nome": f"Momento {i}",
            "ja_sabe": "Reconhece o tema, mas não domina o processo.",
            "duvida": f"Dúvida material {i} sobre a oferta.",
            "tensao": f"Tensão material {i} antes de agir.",
            "proximo_movimento": "Ler a explicação independente.",
        }
        for i in range(1, qtd + 1)
    ]
    grupos = [
        {
            "ref": f"group_territorio_{i}",
            "nome": f"Território {i}",
            "estado_mental_refs": [f"state_momento_{i}"],
            "funcao": f"Resolver a tensão {i}.",
            "territorio": f"Território conceitual {i}.",
            "diferenca_material": f"Muda estado, hipótese e formato no eixo {i}.",
        }
        for i in range(1, qtd + 1)
    ]
    copies = [
        {
            "ref": f"copy_grupo_{i}",
            "group_ref": f"group_territorio_{i}",
            "texto_principal": f"Entenda o ponto {i} com informação clara.",
            "titulo": f"Entenda o ponto {i}",
            "descricao": "Conteúdo informativo e independente.",
            "cta_nativa": "LEARN_MORE",
            "narracao": None,
            "fato_refs": ["fact_lp_offer"],
        }
        for i in range(1, qtd + 1)
    ]
    formatos = ["1x1", "4x5", "9x16"]
    pecas = [
        {
            "ref": f"creative_variacao_{i}",
            "group_ref": f"group_territorio_{i}",
            "shared_copy_ref": f"copy_grupo_{i}",
            "estado_mental_ref": f"state_momento_{i}",
            "angulo": f"Ângulo estratégico {i}",
            "subangulo": f"Subângulo específico {i}",
            "hipotese": f"Hipótese falsificável {i}",
            "hook": f"Hook autossuficiente {i}",
            "mecanismo_de_interrupcao": f"Mecanismo {i}",
            "formato": formatos[(i - 1) % len(formatos)],
            "headline_interna": f"Entenda o ponto {i}",
            "complemento_interno": "Informação antes da decisão.",
            "cta_visual": "Saiba mais",
            "direcao_visual": f"Composição autossuficiente e legível para o território {i}.",
            "fato_refs": ["fact_lp_offer"],
            "rule_refs": ["META-CR-001", "META-CR-005"],
        }
        for i in range(1, qtd + 1)
    ]
    return {
        "schema_version": "1.0",
        "project_ref": PROJECT_REF,
        "fase_concluida": "NOVA_OPERACAO",
        "diagnostico": {
            "oferta_real": "Conteúdo informativo independente.",
            "promessa_maxima": "Explicar o processo sem prometer resultado.",
            "tensao_central": "Falta de clareza antes da decisão.",
            "desconhecidos": [],
            "fato_refs": ["fact_lp_offer"],
        },
        "jornada": estados,
        "grupos": grupos,
        "copies_compartilhadas": copies,
        "pecas": pecas,
        "recibo": {"valido": True, "codigos": ["MODELO_DISSE_QUE_SIM"]},
        "proximo_ato": "Revisar e aprovar grupos e peças.",
    }


class ModeloFake:
    name = "fake"
    model = "fake-contract-model"

    def __init__(self, respostas: list[dict]):
        self.respostas = respostas
        self.chamadas = 0

    async def complete(self, system: str, user: str) -> str:
        resposta = self.respostas[min(self.chamadas, len(self.respostas) - 1)]
        self.chamadas += 1
        return json.dumps(resposta, ensure_ascii=False)


def test_prompt_isola_dados_nao_confiaveis_e_inclui_schema():
    missao = json.loads(montar_missao(pedido()))
    assert "DADOS_NAO_CONFIAVEIS" in missao
    assert "SCHEMA_DE_SAIDA" in missao
    assert missao["DADOS_NAO_CONFIAVEIS"]["project_ref"] == PROJECT_REF


def test_lote_valido_recebe_recibo_do_codigo_nao_do_modelo():
    resultado = asyncio.run(AgenteCriativoMeta(ModeloFake([saida()])).executar(pedido()))
    assert resultado.saida.recibo.valido is True
    assert "MODELO_DISSE_QUE_SIM" not in resultado.saida.recibo.codigos
    assert "META_CREATIVE_BATCH_DIVERSITY_VALID" in resultado.saida.recibo.codigos


def test_resposta_invalida_e_retentada_uma_vez():
    ruim = saida(2)
    ruim["project_ref"] = PROJECT_REF
    modelo = ModeloFake([ruim, saida(3)])
    resultado = asyncio.run(AgenteCriativoMeta(modelo).executar(pedido(3)))
    assert resultado.tentativas == 2
    assert modelo.chamadas == 2


def test_duas_respostas_invalidas_falham_sem_lote_parcial():
    modelo = ModeloFake([saida(2), saida(2)])
    with pytest.raises(RespostaDoModeloInvalida):
        asyncio.run(AgenteCriativoMeta(modelo).executar(pedido(3)))
    assert modelo.chamadas == 2


def test_fato_inventado_e_recusado():
    bruto = saida()
    bruto["pecas"][0]["fato_refs"] = ["fact_inventado"]
    with pytest.raises(SaidaCriativaInvalida, match="fatos inexistentes"):
        validar_saida(pedido(), SaidaDoAgente.model_validate(bruto))


def test_variacao_cosmetica_e_recusada():
    bruto = saida()
    for campo in ("estado_mental_ref", "angulo", "hipotese", "mecanismo_de_interrupcao", "formato"):
        bruto["pecas"][1][campo] = bruto["pecas"][0][campo]
    bruto["pecas"][1]["headline_interna"] = "Só trocou a frase"
    with pytest.raises(SaidaCriativaInvalida, match="variações cosméticas"):
        validar_saida(pedido(), SaidaDoAgente.model_validate(bruto))


def test_metadado_operacional_na_arte_e_recusado():
    bruto = saida()
    bruto["pecas"][0]["headline_interna"] = "G1-C01 APROVADO"
    with pytest.raises(SaidaCriativaInvalida, match="metadado operacional"):
        validar_saida(pedido(), SaidaDoAgente.model_validate(bruto))


def test_termo_bloqueado_pelo_operador_e_recusado_deterministicamente():
    dados = pedido().model_dump(mode="python")
    dados["restricoes"] = [
        {
            "ref": "rule_sem_oficialidade",
            "texto": "A oferta é privada e não pode sugerir vínculo oficial.",
            "escopo": "PROJETO",
            "termos_bloqueados": ["oficial"],
        }
    ]
    req = PedidoDoAgente.model_validate(dados)
    bruto = saida()
    bruto["pecas"][0]["headline_interna"] = "Canal oficial"
    with pytest.raises(SaidaCriativaInvalida, match="termo bloqueado"):
        validar_saida(req, SaidaDoAgente.model_validate(bruto))


def test_elemento_aprovado_e_literalmente_congelado():
    base = pedido().model_copy(
        update={
            "elementos_congelados": [
                ElementoCongelado(
                    ref="frozen_titulo_grupo",
                    caminho="/grupos/group_territorio_1/nome",
                    valor=json.dumps("Território 1", ensure_ascii=False),
                    aprovado_em="2026-09-07T12:00:00Z",
                )
            ]
        }
    )
    bruto = saida()
    bruto["grupos"][0]["nome"] = "Outro nome"
    with pytest.raises(SaidaCriativaInvalida, match="foi alterado"):
        validar_saida(base, SaidaDoAgente.model_validate(bruto))


def test_caminho_por_indice_nao_e_aceito_como_congelamento():
    """A posição muda a cada geração; o congelamento tem de recusá-la.

    Antes, `/grupos/0/nome` resolvia por índice e o congelamento comparava
    "seja lá o que estiver na primeira posição agora" com o valor aprovado.
    Reordenar o lote trocava o objeto sem trocar o caminho.
    """
    base = pedido().model_copy(
        update={
            "elementos_congelados": [
                ElementoCongelado(
                    ref="frozen_por_indice",
                    caminho="/grupos/0/nome",
                    valor=json.dumps("Território 1", ensure_ascii=False),
                    aprovado_em="2026-09-07T12:00:00Z",
                )
            ]
        }
    )
    with pytest.raises(SaidaCriativaInvalida, match="ausente da saída"):
        validar_saida(base, SaidaDoAgente.model_validate(saida()))


def test_indice_negativo_nao_vira_ultimo_elemento():
    """`-1` passava no padrão do contrato e virava o ÚLTIMO item da lista."""
    from app.criativo.agente.caminhos import CaminhoInvalido, resolver

    documento = SaidaDoAgente.model_validate(saida()).model_dump(mode="json")
    with pytest.raises(CaminhoInvalido):
        resolver(documento, "/grupos/-1/nome")
    # e o endereçamento por ref continua funcionando
    assert resolver(documento, "/grupos/group_territorio_1/nome") == "Território 1"


def test_peca_nao_pode_usar_estado_mental_de_outro_grupo():
    """Existir na jornada não basta: o estado precisa ser do grupo da peça."""
    bruto = saida()
    # a peça do grupo 1 passa a apontar para o estado do grupo 2
    bruto["pecas"][0]["estado_mental_ref"] = "state_momento_2"
    with pytest.raises(SaidaCriativaInvalida, match="não pertence a group_territorio_1"):
        validar_saida(pedido(), SaidaDoAgente.model_validate(bruto))


class RepoFake:
    def __init__(self):
        self.eventos: list[str] = []
        self.operacao: dict = {}
        self.run: dict = {}

    async def criar_operacao(self, row):
        self.eventos.append("operacao")
        self.operacao = row
        return row

    async def criar_run(self, row):
        self.eventos.append("run_queued" if row.get("status") == "QUEUED" else "run_running")
        self.run = row
        return row

    async def reivindicar_run(self, run_ref, owner_id):
        if self.run.get("status") != "QUEUED":
            return None
        self.eventos.append("run_claimed")
        self.run["status"] = "RUNNING"
        return self.run

    async def reivindicar_run_abandonada(self, run_ref, owner_id, *, lease_s):
        return None

    async def devolver_run_para_fila(self, run_ref, owner_id):
        self.eventos.append("run_requeued")

    async def listar_operacoes(self, owner_id, *, limite=20, offset=0):
        return [self.operacao] if self.operacao else []

    async def concluir_run(self, run_ref, owner_id, **kwargs):
        self.eventos.append("run_completed")
        self.run.update({"run_ref": run_ref, "project_ref": self.operacao["project_ref"], "status": "COMPLETED", "output": kwargs["output"]})
        return self.run

    async def falhar_run(self, *args, **kwargs):
        self.eventos.append("run_failed")

    async def obter_operacao(self, project_ref, owner_id):
        return self.operacao

    async def obter_run(self, run_ref, owner_id):
        return self.run

    async def listar_runs(self, project_ref, owner_id):
        return [self.run]

    async def listar_decisoes(self, project_ref, owner_id):
        return []

    async def registrar_decisao(self, row):
        self.eventos.append("decisao")
        return row


class AgenteFake:
    async def executar(self, req):
        out = SaidaDoAgente.model_validate({**saida(req.quantidade_de_pecas), "project_ref": req.project_ref})
        return ResultadoDoAgente(out, "fake", 1, "1" * 64, "2" * 64)


def _app(repo: RepoFake) -> TestClient:
    app = FastAPI()
    app.include_router(criativos_agente.router)
    app.dependency_overrides[exigir_usuario] = lambda: Identidade(
        sub=OWNER, email="operador@example.com", papel="ADMIN", origem="sessao"
    )
    app.dependency_overrides[criativos_agente.obter_repositorio] = lambda: repo
    app.dependency_overrides[criativos_agente.obter_agente] = lambda: AgenteFake()
    return TestClient(app)


def test_api_grava_run_running_antes_de_chamar_modelo():
    repo = RepoFake()
    entrada = EntradaNovaOperacao(
        nome_da_operacao="Operação teste",
        destination_ref="destino:teste",
        objetivo_meta="OUTCOME_TRAFFIC",
        contexto_do_publico="Pessoa buscando entender o processo.",
        fatos_da_oferta=[
            {"ref": "fact_lp_offer", "declaracao": "Conteúdo informativo e independente.", "origem": "LANDING_PAGE"}
        ],
        quantidade_de_pecas=3,
    )
    cliente = _app(repo)
    resposta = cliente.post(
        "/api/criativos/meta/agente/operacoes", json=entrada.model_dump(mode="json")
    )
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()

    # O POST devolve identidade durável e NÃO chamou o modelo: nada de
    # `run_completed` aqui. É isso que permite recarregar a página sem perder a
    # operação e sem pagar duas vezes.
    assert repo.eventos == ["operacao", "run_queued"]
    assert corpo["project_ref"].startswith("crproj_")
    assert corpo["run_ref"].startswith("crrun_")
    assert corpo["status"] == "QUEUED"

    executada = cliente.post(
        f"/api/criativos/meta/agente/operacoes/{corpo['project_ref']}"
        f"/runs/{corpo['run_ref']}/executar"
    )
    assert executada.status_code == 200, executada.text
    assert repo.eventos == ["operacao", "run_queued", "run_claimed", "run_completed"]
    assert executada.json()["status"] == "COMPLETED"


def test_api_nao_exige_referencia_tecnica_de_destino():
    """O briefing humano não precisa conhecer uma chave interna sem resolver."""
    repo = RepoFake()
    entrada = EntradaNovaOperacao(
        nome_da_operacao="Operação sem destino vinculado",
        objetivo_meta="OUTCOME_TRAFFIC",
        contexto_do_publico="Pessoa buscando entender o processo.",
        fatos_da_oferta=[
            {
                "ref": "fact_operador_1",
                "declaracao": "Conteúdo informativo e independente.",
                "origem": "OPERADOR",
            }
        ],
    )
    resposta = _app(repo).post(
        "/api/criativos/meta/agente/operacoes",
        json=entrada.model_dump(mode="json"),
    )
    assert resposta.status_code == 201, resposta.text
    assert repo.operacao["input"]["destination_ref"] is None
    assert repo.run["input"]["destination_ref"] is None


def test_reexecutar_run_concluida_devolve_o_lote_sem_gerar_de_novo():
    """Recarregar a aba não pode pagar uma segunda geração."""
    repo = RepoFake()
    repo.operacao = {"project_ref": PROJECT_REF, "owner_id": OWNER, "input": {}}
    repo.run = {
        "run_ref": RUN_REF,
        "project_ref": PROJECT_REF,
        "status": "COMPLETED",
        "output": saida(),
    }
    resposta = _app(repo).post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/runs/{RUN_REF}/executar"
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["reexecutado"] is False
    # nenhum claim, nenhuma conclusão: o modelo não foi tocado
    assert repo.eventos == []


def test_run_em_execucao_recusa_segundo_disparo():
    repo = RepoFake()
    repo.operacao = {"project_ref": PROJECT_REF, "owner_id": OWNER, "input": {}}
    repo.run = {
        "run_ref": RUN_REF,
        "project_ref": PROJECT_REF,
        "status": "RUNNING",
        "output": None,
    }
    resposta = _app(repo).post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/runs/{RUN_REF}/executar"
    )
    assert resposta.status_code == 409
    assert resposta.json()["detail"]["codigo"] == "CRIATIVO_AGENTE_RUN_EM_EXECUCAO"


def test_listagem_de_operacoes_existe_e_e_confinada_ao_dono():
    repo = RepoFake()
    repo.operacao = {
        "project_ref": PROJECT_REF,
        "owner_id": OWNER,
        "status": "READY_FOR_REVIEW",
        "input": {"nome_da_operacao": "Operação teste"},
        "latest_run_ref": RUN_REF,
        "created_at": "2026-09-07T12:00:00Z",
        "updated_at": "2026-09-07T13:00:00Z",
    }
    resposta = _app(repo).get("/api/criativos/meta/agente/operacoes")
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["operacoes"][0]["project_ref"] == PROJECT_REF
    assert corpo["operacoes"][0]["nome_da_operacao"] == "Operação teste"
    # a listagem não carrega o lote inteiro
    assert "output" not in corpo["operacoes"][0]
    assert "input" not in corpo["operacoes"][0]


def test_falha_ao_gravar_recibo_nao_mascara_erro_original_do_modelo():
    class RepoComFalhaNoRecibo(RepoFake):
        async def falhar_run(self, *args, **kwargs):
            raise RuntimeError("banco indisponível ao gravar falha")

    class AgenteComSaidaInvalida:
        async def executar(self, req):
            raise RespostaDoModeloInvalida(["lote incompleto"])

    repo = RepoComFalhaNoRecibo()
    app = FastAPI()
    app.include_router(criativos_agente.router)
    app.dependency_overrides[exigir_usuario] = lambda: Identidade(
        sub=OWNER, email="operador@example.com", papel="ADMIN", origem="sessao"
    )
    app.dependency_overrides[criativos_agente.obter_repositorio] = lambda: repo
    app.dependency_overrides[criativos_agente.obter_agente] = lambda: AgenteComSaidaInvalida()

    cliente = TestClient(app)
    criada = cliente.post(
        "/api/criativos/meta/agente/operacoes",
        json={
            "nome_da_operacao": "Operação teste",
            "destination_ref": "destino:teste",
            "objetivo_meta": "OUTCOME_TRAFFIC",
            "contexto_do_publico": "Pessoa buscando entender o processo.",
            "fatos_da_oferta": [
                {
                    "ref": "fact_lp_offer",
                    "declaracao": "Conteúdo informativo e independente.",
                    "origem": "LANDING_PAGE",
                }
            ],
            "quantidade_de_pecas": 3,
        },
    )
    assert criada.status_code == 201, criada.text
    corpo = criada.json()
    repo.operacao["project_ref"] = corpo["project_ref"]

    resposta = cliente.post(
        f"/api/criativos/meta/agente/operacoes/{corpo['project_ref']}"
        f"/runs/{corpo['run_ref']}/executar"
    )

    assert resposta.status_code == 422
    assert resposta.json()["detail"]["codigo"] == "CRIATIVO_AGENTE_OUTPUT_INVALIDO"


def test_decisao_congela_snapshot_lido_no_servidor():
    repo = RepoFake()
    repo.operacao = {"project_ref": PROJECT_REF, "owner_id": OWNER, "input": {}}
    repo.run = {
        "run_ref": RUN_REF,
        "project_ref": PROJECT_REF,
        "status": "COMPLETED",
        "output": saida(),
    }
    resposta = _app(repo).post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/decisoes",
        json={
            "run_ref": RUN_REF,
            "decisao": "APROVADO",
            "escopo": "GRUPO",
            "caminho": "/grupos/group_territorio_1/nome",
        },
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["snapshot_sha256"]
    assert repo.eventos == ["decisao"]


def test_refinamento_carrega_o_lote_anterior_no_pedido():
    """Refinar sem o lote anterior é refazer do zero.

    O feedback do operador fala de peças que ele acabou de ler; se o pedido
    seguinte não as carrega, o modelo não tem a que se referir e a run devolve
    um lote novo que só coincide com o anterior nos pontos congelados.
    """
    repo = RepoFake()
    anterior = saida()
    repo.operacao = {
        "project_ref": PROJECT_REF,
        "owner_id": OWNER,
        "input": {
            "nome_da_operacao": "Operação teste",
            "destination_ref": "destino:teste",
            "objetivo_meta": "OUTCOME_TRAFFIC",
            "contexto_do_publico": "Pessoa buscando entender o processo.",
            "fatos_da_oferta": [
                {
                    "ref": "fact_lp_offer",
                    "declaracao": "Conteúdo informativo e independente.",
                    "origem": "LANDING_PAGE",
                }
            ],
            "quantidade_de_pecas": 3,
        },
    }
    repo.run = {
        "run_ref": RUN_REF,
        "project_ref": PROJECT_REF,
        "status": "COMPLETED",
        "output": anterior,
    }

    resposta = _app(repo).post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/runs",
        json={"fase": "REFACAO", "feedback": "Troque o hook da peça do frio.", "feedback_escopo": "PONTUAL"},
    )
    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["status"] == "QUEUED"

    gravado = repo.run["input"]
    assert gravado["saida_anterior"] is not None
    assert [p["ref"] for p in gravado["saida_anterior"]["pecas"]] == [
        p["ref"] for p in anterior["pecas"]
    ]
    assert gravado["feedback"] == "Troque o hook da peça do frio."


def test_primeira_run_nao_inventa_lote_anterior():
    """Sem run concluída, `saida_anterior` é ausência declarada, não objeto vazio."""
    repo = RepoFake()
    repo.operacao = {
        "project_ref": PROJECT_REF,
        "owner_id": OWNER,
        "input": {
            "nome_da_operacao": "Operação teste",
            "destination_ref": "destino:teste",
            "objetivo_meta": "OUTCOME_TRAFFIC",
            "contexto_do_publico": "Pessoa buscando entender o processo.",
            "fatos_da_oferta": [
                {
                    "ref": "fact_lp_offer",
                    "declaracao": "Conteúdo informativo e independente.",
                    "origem": "LANDING_PAGE",
                }
            ],
            "quantidade_de_pecas": 3,
        },
    }
    repo.run = {"run_ref": RUN_REF, "project_ref": PROJECT_REF, "status": "FAILED", "output": None}

    resposta = _app(repo).post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/runs",
        json={"fase": "MATRIZ"},
    )
    assert resposta.status_code == 201, resposta.text
    assert repo.run["input"]["saida_anterior"] is None


# ── procedência do modelo ────────────────────────────────────────────────────


class _ClienteFalso:
    """Só o que `_modelo_do_recibo` lê: o pedido e, talvez, o servido."""

    def __init__(self, model: str, modelo_servido: str | None = None):
        self.model = model
        self.modelo_servido = modelo_servido


def test_recibo_grava_um_nome_so_quando_o_servido_confere():
    from app.criativo.agente.orquestrador import _modelo_do_recibo

    assert _modelo_do_recibo(_ClienteFalso("gemini-3.8-flash", "gemini-3.8-flash")) == "gemini-3.8-flash"


def test_recibo_grava_um_nome_so_quando_o_provider_nao_informa():
    """Ausência não vira invenção: sem `modelVersion`, fica o que foi pedido."""
    from app.criativo.agente.orquestrador import _modelo_do_recibo

    assert _modelo_do_recibo(_ClienteFalso("gemini-3.8-flash", None)) == "gemini-3.8-flash"


def test_recibo_denuncia_rebaixamento_silencioso_do_provider():
    """O defeito que isto fecha: pedir 3.8 e ser servido por outro literal.

    Antes só o PEDIDO era gravado, então a procedência afirmava um modelo que
    talvez não tivesse respondido, e nada no banco desmentia. Gravar os dois é
    o que torna a divergência auditável depois — sem migration, porque a coluna
    `model` da v11_05 é `text` livre.
    """
    from app.criativo.agente.orquestrador import _modelo_do_recibo

    recibo = _modelo_do_recibo(_ClienteFalso("gemini-3.8-flash", "gemini-3.5-flash"))
    assert recibo == "gemini-3.8-flash→gemini-3.5-flash"
    assert "gemini-3.8-flash" in recibo and "gemini-3.5-flash" in recibo
