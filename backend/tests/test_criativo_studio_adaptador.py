"""A ponte entre estratégia aprovada e pedido de imagem.

O que estes testes impedem, em ordem de custo do defeito:

 1. gastar antes de conferir — teto, aprovação e formato são checados ANTES de
    existir qualquer briefing;
 2. `texto_principal` (a copy do anúncio) vazar para dentro dos pixels;
 3. um custo desconhecido virar "US$ 0,00" ao lado de um botão que gasta;
 4. linhagem perdida — sem ela ninguém responde de que peça veio a imagem.
"""

from __future__ import annotations

import os
import sys

# A raiz do repositório precisa estar no path porque `app.criativo.dominio`
# importa `volc_ads`, que mora fora de `backend/`. Sem isto o arquivo coleta
# só quando algum outro módulo de teste já inseriu a raiz antes — e passa a
# depender da ordem de coleção, que é exatamente o tipo de teste que some em
# silêncio quando alguém roda um arquivo sozinho.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from app.criativo.agente.contrato import SaidaDoAgente
from app.criativo.studio import MAX_RENDERS_POR_PEDIDO, PedidoDeGeracao
from app.criativo.studio.adaptador import montar_plano, pedido_de_job, texto_na_arte


PROJECT_REF = "crproj_" + "a" * 24
RUN_REF = "crrun_" + "b" * 24


def saida(qtd: int = 3) -> SaidaDoAgente:
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
            "funcao": "Apresentar a oferta com prova.",
            "territorio": f"Território material {i}.",
            "diferenca_material": f"Diferença material {i} contra os outros grupos.",
        }
        for i in range(1, qtd + 1)
    ]
    copies = [
        {
            "ref": f"copy_grupo_{i}",
            "group_ref": f"group_territorio_{i}",
            "texto_principal": f"COPY EXTERNA DO ANUNCIO {i} que nao pode entrar na arte.",
            "titulo": f"Titulo {i}",
            "descricao": f"Descricao {i}",
            "cta_nativa": "LEARN_MORE",
            "fato_refs": ["fact_lp_offer"],
        }
        for i in range(1, qtd + 1)
    ]
    pecas = [
        {
            "ref": f"creative_variacao_{i}",
            "group_ref": f"group_territorio_{i}",
            "shared_copy_ref": f"copy_grupo_{i}",
            "estado_mental_ref": f"state_momento_{i}",
            "angulo": f"Angulo {i}",
            "subangulo": f"Subangulo {i}",
            "hipotese": f"Hipotese material {i} sobre o publico.",
            "hook": f"Hook {i} que interrompe a rolagem",
            "mecanismo_de_interrupcao": f"Mecanismo {i}",
            "formato": "4x5",
            "headline_interna": f"Headline interna {i}",
            "complemento_interno": f"Complemento {i}",
            "cta_visual": "Ver como",
            "direcao_visual": f"Direcao visual material {i} para a composicao.",
            "fato_refs": ["fact_lp_offer"],
            "rule_refs": [],
        }
        for i in range(1, qtd + 1)
    ]
    return SaidaDoAgente.model_validate(
        {
            "project_ref": PROJECT_REF,
            "fase_concluida": "MATRIZ",
            "diagnostico": {
                "oferta_real": "Oferta real declarada.",
                "promessa_maxima": "Promessa maxima declarada.",
                "tensao_central": "Tensao central declarada.",
                "desconhecidos": [],
                "fato_refs": ["fact_lp_offer"],
            },
            "jornada": estados,
            "grupos": grupos,
            "copies_compartilhadas": copies,
            "pecas": pecas,
            "proximo_ato": "Revisar e aprovar o lote.",
        }
    )


def aprovados(*refs: str) -> frozenset[str]:
    return frozenset(f"/pecas/{r}" for r in refs)


def plano(pedido: PedidoDeGeracao, *, saida_=None, caminhos=None):
    return montar_plano(
        saida=saida_ or saida(),
        pedido=pedido,
        caminhos_aprovados=caminhos if caminhos is not None else aprovados("creative_variacao_1"),
        contexto_do_publico="Pessoa buscando entender o processo.",
        objetivo="OUTCOME_TRAFFIC",
    )


# ── N x M ────────────────────────────────────────────────────────────────────


def test_dois_conceitos_em_tres_formatos_dao_seis_saidas_e_nao_seis_ideias():
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1", "creative_variacao_2"],
            format_ids=["1x1", "4x5", "9x16"],
        ),
        caminhos=aprovados("creative_variacao_1", "creative_variacao_2"),
    )
    assert p.pode_executar
    assert p.conceitos == 2
    assert p.formatos == 3
    assert p.total_de_renders == 6
    assert len(p.briefings) == 6

    # Os seis briefings vêm de DOIS conceitos, cada um em três formatos. Nenhuma
    # ideia nova foi escrita: a direção visual repete por conceito.
    por_conceito: dict[str, set[str]] = {}
    for b in p.briefings:
        por_conceito.setdefault(b.linhagem.creative_ref, set()).add(b.formato_slot)
    assert por_conceito == {
        "creative_variacao_1": {"1x1", "4x5", "9x16"},
        "creative_variacao_2": {"1x1", "4x5", "9x16"},
    }
    direcoes = {b.direcao_visual for b in p.briefings if b.linhagem.creative_ref == "creative_variacao_1"}
    assert len(direcoes) == 1


# ── Os limites vêm antes dos efeitos ─────────────────────────────────────────


def test_o_teto_e_conferido_antes_de_existir_qualquer_briefing():
    # 12 conceitos é o teto de grupos do contrato estratégico; com 4 formatos
    # dá 48, que já passa do teto de renders sem precisar violar o outro.
    grande = saida(12)
    p = montar_plano(
        saida=grande,
        pedido=PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=[f"creative_variacao_{i}" for i in range(1, 13)],
            format_ids=["1x1", "4x5", "9x16", "1.91x1"],
        ),
        caminhos_aprovados=frozenset(f"/pecas/creative_variacao_{i}" for i in range(1, 13)),
        contexto_do_publico="Pessoa buscando entender o processo.",
        objetivo="OUTCOME_TRAFFIC",
    )
    assert p.total_de_renders == 48 > MAX_RENDERS_POR_PEDIDO
    assert not p.pode_executar
    # ⚠️ Zero briefings: a recusa acontece ANTES de haver o que despachar.
    assert p.briefings == []
    assert [b.codigo for b in p.bloqueios] == ["CRIATIVO_STUDIO_TETO_DE_RENDERS"]


def test_peca_sem_aprovacao_humana_nao_vira_render():
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_2"],
            format_ids=["1x1"],
        ),
        caminhos=aprovados("creative_variacao_1"),  # aprovou a OUTRA
    )
    assert not p.pode_executar
    assert p.briefings == []
    assert any(b.codigo == "CRIATIVO_STUDIO_PECA_NAO_APROVADA" for b in p.bloqueios)


def test_ref_de_outro_lote_e_recusada():
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_de_outra_run"],
            format_ids=["1x1"],
        ),
        caminhos=aprovados("creative_de_outra_run"),
    )
    assert not p.pode_executar
    assert any(b.codigo == "CRIATIVO_STUDIO_PECA_FORA_DO_LOTE" for b in p.bloqueios)


def test_formato_que_o_motor_nao_produz_e_recusado_com_nome():
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1"],
            format_ids=["21x9"],
        )
    )
    assert not p.pode_executar
    bloqueio = next(b for b in p.bloqueios if b.codigo == "CRIATIVO_STUDIO_FORMATO_INDISPONIVEL")
    assert "21x9" in bloqueio.mensagem


def test_pedido_com_refs_duplicadas_nem_e_construido():
    with pytest.raises(ValueError, match="duplicadas"):
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1", "creative_variacao_1"],
            format_ids=["1x1"],
        )


# ── A copy do anúncio não entra nos pixels ───────────────────────────────────


def test_o_texto_da_arte_nao_carrega_a_copy_da_campanha():
    s = saida()
    peca = s.pecas[0]
    arte = texto_na_arte(peca)

    assert arte == "Headline interna 1 · Complemento 1 · Ver como"
    # ⚠️ `texto_principal` é a copy que vai FORA da imagem, no anúncio.
    assert "COPY EXTERNA DO ANUNCIO" not in arte

    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1"],
            format_ids=["1x1"],
        )
    )
    for b in p.briefings:
        assert "COPY EXTERNA DO ANUNCIO" not in b.texto_na_arte
        assert "COPY EXTERNA DO ANUNCIO" not in b.direcao_visual


def test_metadado_operacional_nao_e_mandado_para_os_pixels():
    s = saida()
    quebrada = s.pecas[0].model_copy(update={"headline_interna": "APROVADO para o G1-C01"})
    s = s.model_copy(update={"pecas": [quebrada, *s.pecas[1:]]})
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1"],
            format_ids=["1x1"],
        ),
        saida_=s,
    )
    assert not p.pode_executar
    assert any(b.codigo == "CRIATIVO_STUDIO_METADADO_NA_ARTE" for b in p.bloqueios)


# ── Linhagem ─────────────────────────────────────────────────────────────────


def test_cada_briefing_carrega_a_linhagem_inteira():
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1"],
            format_ids=["1x1", "9x16"],
        )
    )
    for b in p.briefings:
        assert b.linhagem.creative_ref == "creative_variacao_1"
        assert b.linhagem.group_ref == "group_territorio_1"
        assert b.linhagem.copy_ref == "copy_grupo_1"
        assert b.linhagem.state_ref == "state_momento_1"
        assert b.linhagem.project_ref == PROJECT_REF
        assert b.linhagem.run_ref == RUN_REF
        assert b.linhagem.fato_refs == ["fact_lp_offer"]


# ── Custo ────────────────────────────────────────────────────────────────────


def test_custo_desconhecido_e_none_e_nunca_zero():
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1"],
            format_ids=["1x1"],
        )
    )
    # ⚠️ "US$ 0,00" ao lado de um botão que gasta é a frase mais cara que esta
    # tela poderia dizer. Ausência é `None`, e a tela desenha ausência.
    assert p.custo_estimado_usd is None or p.custo_estimado_usd > 0


# ── O job agrupa por conceito ────────────────────────────────────────────────


def test_um_job_cobre_um_conceito_com_todos_os_seus_formatos():
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1"],
            format_ids=["1x1", "4x5", "9x16"],
        )
    )
    pedido = pedido_de_job(p.briefings, nome_da_operacao="Operação teste")
    assert pedido["slots"] == ["1x1", "4x5", "9x16"]
    assert pedido["origem"] == "trafego"
    assert "Direcao visual material 1" in pedido["mensagem"]
    assert "Headline interna 1" in pedido["mensagem"]
    assert "COPY EXTERNA DO ANUNCIO" not in pedido["mensagem"]


def test_origem_do_assistente_respeita_o_check_sql_sem_perder_linhagem():
    from pathlib import Path
    import re

    sql = (Path(__file__).resolve().parents[2] / "supabase/migrations/v11_01_estudio_criativo.sql").read_text()
    check = re.search(r"constraint criativo_projeto_origem_valida\s+check \(origem in \((.*?)\)\)", sql, re.S)
    assert check is not None
    permitidas = re.findall(r"'([^']+)'", check.group(1))
    p = plano(PedidoDeGeracao(run_ref=RUN_REF, selected_creative_refs=["creative_variacao_1"], format_ids=["1x1"]))
    pedido = pedido_de_job(p.briefings, nome_da_operacao="Teste de contrato SQL")
    assert pedido["origem"] in permitidas
    assert pedido["creative_ref"] == "creative_variacao_1"
    assert pedido["run_ref"] == RUN_REF


def test_um_job_recusa_misturar_conceitos():
    p = plano(
        PedidoDeGeracao(
            run_ref=RUN_REF,
            selected_creative_refs=["creative_variacao_1", "creative_variacao_2"],
            format_ids=["1x1"],
        ),
        caminhos=aprovados("creative_variacao_1", "creative_variacao_2"),
    )
    with pytest.raises(ValueError, match="um único conceito"):
        pedido_de_job(p.briefings, nome_da_operacao="Operação teste")


# ── As rotas de geração ──────────────────────────────────────────────────────
#
# O plano é recalculado NO SERVIDOR. O que a tela mandou como total é ignorado:
# um teto conferido no browser não é um teto.

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.criativo.agente.caminhos import CaminhoInvalido  # noqa: E402
from app.criativo.agente.caminhos import resolver as resolver_caminho  # noqa: E402
from app.routers import criativos_agente  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_usuario  # noqa: E402


OWNER = "11111111-1111-1111-1111-111111111111"


class RepoDeGeracao:
    def __init__(self, *, aprovadas: list[str], saida_do_lote=None):
        self.saida = saida_do_lote or saida()
        self.aprovadas = aprovadas
        self.pontes: list[dict] = []

    async def obter_operacao(self, project_ref, owner_id):
        return {
            "project_ref": PROJECT_REF,
            "owner_id": OWNER,
            "input": {
                "nome_da_operacao": "Operação teste",
                "contexto_do_publico": "Pessoa buscando entender o processo.",
                "objetivo_meta": "OUTCOME_TRAFFIC",
            },
        }

    async def obter_run(self, run_ref, owner_id):
        return {
            "run_ref": RUN_REF,
            "project_ref": PROJECT_REF,
            "status": "COMPLETED",
            "output": self.saida.model_dump(mode="json"),
        }

    async def listar_decisoes(self, project_ref, owner_id):
        """Decisões como o banco as guarda: com o snapshot REAL e o hash dele.

        O dublê antes devolvia `snapshot: {}` e nenhum `snapshot_sha256`, o que
        aprovava por caminho e nunca por conteúdo — justamente a falha que o
        servidor passou a recusar. Resolver o caminho na saída deste lote é o
        que faz o teste exercitar a autoridade de verdade em vez de uma
        aprovação que o banco jamais produziria.
        """
        saida = self.saida.model_dump(mode="json")
        decisoes = []
        for ref in self.aprovadas:
            caminho = f"/pecas/{ref}"
            try:
                instantaneo = resolver_caminho(saida, caminho)
            except CaminhoInvalido:
                instantaneo = {}
            decisoes.append(
                {
                    "path": caminho,
                    "decisao": "APROVADO",
                    "decision_ref": "crdec_" + "c" * 24,
                    "run_ref": RUN_REF,
                    "scope": "PECA",
                    "snapshot": instantaneo,
                    "snapshot_sha256": criativos_agente._hash_valor(instantaneo),
                    "created_at": "2026-09-07T12:00:00Z",
                }
            )
        return decisoes

    async def listar_pontes(self, project_ref, owner_id):
        return self.pontes

    async def ponte_por_peca(self, run_ref, creative_ref, owner_id, *, geracao_ref=None):
        return next((p for p in self.pontes if p["creative_ref"] == creative_ref and p.get("geracao_ref", "original") == (geracao_ref or "original")), None)


def _app(repo) -> TestClient:
    app = FastAPI()
    app.include_router(criativos_agente.router)
    app.dependency_overrides[exigir_usuario] = lambda: Identidade(
        sub=OWNER, email="operador@example.com", papel="ADMIN", origem="sessao"
    )
    app.dependency_overrides[criativos_agente.obter_repositorio] = lambda: repo
    return TestClient(app)


def _plano(cliente, refs, formatos):
    return cliente.post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/geracoes/plano",
        json={"run_ref": RUN_REF, "selected_creative_refs": refs, "format_ids": formatos},
    )


def test_a_rota_de_plano_devolve_n_por_m_sem_gerar_nada():
    repo = RepoDeGeracao(aprovadas=["creative_variacao_1", "creative_variacao_2"])
    r = _plano(_app(repo), ["creative_variacao_1", "creative_variacao_2"], ["1x1", "4x5", "9x16"])
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["conceitos"] == 2
    assert corpo["formatos"] == 3
    assert corpo["total_de_renders"] == 6
    assert corpo["pode_executar"] is True
    assert corpo["bloqueios"] == []
    # nenhuma ponte foi criada: planejar não produz
    assert repo.pontes == []


def test_o_plano_recusa_peca_sem_aprovacao_humana():
    repo = RepoDeGeracao(aprovadas=[])  # nada aprovado
    r = _plano(_app(repo), ["creative_variacao_1"], ["1x1"])
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["pode_executar"] is False
    assert any(b["codigo"] == "CRIATIVO_STUDIO_PECA_NAO_APROVADA" for b in corpo["bloqueios"])
    assert corpo["briefings"] == []


def test_gerar_recusa_pedido_bloqueado_antes_de_tocar_no_motor():
    repo = RepoDeGeracao(aprovadas=[])
    r = _app(repo).post(
        f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/geracoes",
        json={"run_ref": RUN_REF, "selected_creative_refs": ["creative_variacao_1"], "format_ids": ["1x1"]},
    )
    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe["codigo"] == "CRIATIVO_STUDIO_PEDIDO_BLOQUEADO"
    # ⚠️ A recusa afirma que nada foi criado, e é verdade: nenhuma ponte existe.
    assert detalhe["nada_foi_criado"] is True
    assert repo.pontes == []


def test_run_nao_concluida_nao_vira_imagem():
    class RepoRunCorrendo(RepoDeGeracao):
        async def obter_run(self, run_ref, owner_id):
            return {"run_ref": RUN_REF, "project_ref": PROJECT_REF, "status": "RUNNING", "output": None}

    r = _plano(_app(RepoRunCorrendo(aprovadas=["creative_variacao_1"])), ["creative_variacao_1"], ["1x1"])
    assert r.status_code == 409
    assert r.json()["detail"]["codigo"] == "CRIATIVO_AGENTE_ALVO_INVALIDO"


def test_a_procedencia_e_listavel_e_nao_inventa_linha():
    repo = RepoDeGeracao(aprovadas=["creative_variacao_1"])
    repo.pontes = [
        {
            "ponte_ref": "crpj_" + "1" * 24,
            "creative_ref": "creative_variacao_1",
            "group_ref": "group_territorio_1",
            "run_ref": RUN_REF,
            "job_id": "00000000-0000-0000-0000-0000000000aa",
            "slots": ["1x1", "4x5"],
            "created_at": "2026-09-07T13:00:00Z",
        }
    ]
    r = _app(repo).get(f"/api/criativos/meta/agente/operacoes/{PROJECT_REF}/geracoes")
    assert r.status_code == 200, r.text
    geracoes = r.json()["geracoes"]
    assert len(geracoes) == 1
    assert geracoes[0]["creative_ref"] == "creative_variacao_1"
    assert geracoes[0]["slots"] == ["1x1", "4x5"]
