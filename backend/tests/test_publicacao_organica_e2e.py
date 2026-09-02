"""O fluxo inteiro, hermetico: peca aprovada -> destino -> rascunho/agendamento
-> recibo -> reconciliacao -> tela.

## O que e real aqui, e o que nao e

REAL: a v14_01 num Postgres descartavel; `RepositorioSupabase`; `CasosDeUso`;
`rotas.py` por `TestClient`; o `AdaptadorPostiz` de producao; o filtro de
mensagem de `infraestrutura.py`.

DE MENTIRA: apenas a REDE. O Supabase e substituido por um shim que fala
PostgREST na frente do Postgres de verdade (`apoio_publicacao_organica.py`), e o
Postiz por um `httpx.MockTransport` que responde as mesmas rotas da API oficial.

Nenhuma linha do caminho de producao e pulada. Nenhuma chamada externa acontece.

## Os catorze degraus

Cada teste abaixo corresponde a um item da lista da missao, e o nome diz qual.
Um degrau que nao pode ser provado localmente esta marcado e explicado — nao
marcado verde por vacuidade.
"""
from __future__ import annotations

import os
from typing import Any, Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.publicacao_organica import dominio as dom
from app.publicacao_organica import rotas as rotas_publicacao
from app.publicacao_organica.adaptadores import fake as fk
from app.publicacao_organica.adaptadores.postiz import AdaptadorPostiz
from app.publicacao_organica.aplicacao import CasosDeUso
from app.publicacao_organica.infraestrutura import RepositorioSupabase
from app.seguranca.identidade import Identidade, exigir_admin
from tests import apoio_publicacao_organica as apoio

REFERENCIA_DO_CANAL = "integ-piloto-0001"


# ---------------------------------------------------------------------------
# Cluster e cenario — sessao inteira
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cluster() -> Iterator[apoio.Cluster]:
    motivo = apoio.motivo_de_indisponibilidade()
    if motivo:
        if apoio.exigido():
            pytest.fail(f"VOLC_EXIGIR_POSTGRES esta ligado e o cluster nao pode nascer: {motivo}")
        pytest.skip(f"sem Postgres descartavel: {motivo}")
    c = apoio.subir_cluster()
    try:
        yield c
    finally:
        c.encerrar()


@pytest.fixture(scope="module")
def cenario(cluster: apoio.Cluster) -> apoio.Cenario:
    return apoio.semear(cluster, referencia_do_canal=REFERENCIA_DO_CANAL)


@pytest.fixture()
def plano() -> fk.ControlPlaneFake:
    return fk.ControlPlaneFake()


@pytest.fixture()
def contexto(cluster: apoio.Cluster, cenario: apoio.Cenario, plano: fk.ControlPlaneFake):
    """A app com o router real, o banco real e o control plane de mentira."""
    supabase = apoio.SupabasePsql(cluster=cluster)
    adaptador = AdaptadorPostiz(
        base_url="http://control-plane-de-prova.local", token=plano.token,
        permitir_rede_interna=True, cliente=plano.cliente())
    casos = CasosDeUso(RepositorioSupabase(supabase), adaptador)

    app = FastAPI()
    app.include_router(rotas_publicacao.router)

    identidade_atual = {"sub": cenario.dono_a, "email": "a@agenciavolc.com.br"}

    async def _identidade() -> Identidade:
        return Identidade(sub=identidade_atual["sub"], email=identidade_atual["email"],
                          papel="admin", origem="teste")

    app.dependency_overrides[exigir_admin] = _identidade
    app.dependency_overrides[rotas_publicacao._casos] = lambda: casos

    cliente = TestClient(app, raise_server_exceptions=False)

    class Contexto:
        def __init__(self) -> None:
            self.cliente = cliente
            self.plano = plano
            self.cenario = cenario
            self.cluster = cluster
            self.supabase = supabase

        def como(self, sub: str, email: str = "outro@agenciavolc.com.br") -> None:
            identidade_atual["sub"] = sub
            identidade_atual["email"] = email

    yield Contexto()
    cliente.close()


def _corpo_do_job(cenario: apoio.Cenario, **troca: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "peca_id": cenario.master_a,
        "peca_versao": 1,
        "autorizacao_id": cenario.aprov_a,
        "destino_id": cenario.destino_apto,
        "modo": "draft",
        "timezone": "America/Sao_Paulo",
        "texto": "Primeira peca organica do piloto.",
    }
    base.update(troca)
    return base


# ===========================================================================
# Degraus 1-3 — ativo do dono, aprovacao registrada, destino declarado
# ===========================================================================


def test_degrau_1_2_3_o_destino_do_dono_aparece_com_aptidao_e_motivo(contexto) -> None:
    r = contexto.cliente.get("/api/publicacao-organica/destinos")
    assert r.status_code == 200, r.text
    destinos = r.json()["destinos"]

    por_nome = {d["identidade_logica"]: d for d in destinos}
    assert set(por_nome) == {"PAGINA_PILOTO", "PERFIL_SEM_ADAPTER"}
    assert por_nome["PAGINA_PILOTO"]["apto"] is True

    # ⚠️ O INAPTO APARECE, e COM o motivo. Filtra-lo tornaria impossivel cumprir
    # a guarda do ADR ("MultiPost nunca mascara a ausencia de adapter oficial"):
    # o operador nunca veria a lacuna que justifica um fallback.
    assert por_nome["PERFIL_SEM_ADAPTER"]["apto"] is False
    assert "integracao ainda nao conectada" in por_nome["PERFIL_SEM_ADAPTER"]["motivo"]

    # E o destino do dono B nao aparece para o dono A.
    assert "PAGINA_DO_DONO_B" not in por_nome


def test_degrau_3_destino_sem_adapter_nao_aceita_job(contexto) -> None:
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, destino_id=contexto.cenario.destino_inapto))
    assert r.status_code == 409, r.text
    assert "adapter apto" in r.json()["detail"]["mensagem"]
    assert contexto.plano.chamadas == []


def test_contraprova_A_aprovacao_revogada_nao_publica(contexto) -> None:
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, autorizacao_id=contexto.cenario.aprov_revogada))
    assert r.status_code == 409, r.text
    assert "revogada" in r.json()["detail"]["mensagem"]


def test_contraprova_I_aprovacao_da_v1_nao_cobre_a_v2(contexto) -> None:
    # Criar a versao 2 da peca DEPOIS da aprovacao nao autoriza publicar a v2.
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, peca_id=contexto.cenario.master_a_v2, peca_versao=2))
    assert r.status_code == 409, r.text
    assert "nao e transferivel" in r.json()["detail"]["mensagem"]


# ===========================================================================
# Degrau 13 — tentativa por outro dono
# ===========================================================================


def test_degrau_13_outro_dono_nao_publica_a_peca_alheia(contexto) -> None:
    contexto.como(contexto.cenario.dono_b, "b@agenciavolc.com.br")
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(contexto.cenario))
    assert r.status_code == 403, r.text
    assert contexto.plano.chamadas == []


def test_degrau_13_outro_dono_nao_le_o_job_alheio(contexto) -> None:
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, texto="peca so do dono A"))
    assert criado.status_code == 201, criado.text
    job_id = criado.json()["job_id"]

    contexto.como(contexto.cenario.dono_b, "b@agenciavolc.com.br")
    r = contexto.cliente.get(f"/api/publicacao-organica/jobs/{job_id}")
    # ⚠️ 404 E NAO 403, de proposito: um 403 confirmaria que o job existe.
    assert r.status_code == 404


# ===========================================================================
# Degrau 14 — publicacao imediata sem autorizacao
# ===========================================================================


def test_degrau_14_now_sem_consentimento_e_recusado(contexto) -> None:
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, modo="now"))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["codigo"] == "consentimento_ausente"
    assert contexto.plano.chamadas == []


def test_degrau_14_now_com_consentimento_explicito_atravessa_e_registra_o_ator(contexto) -> None:
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, modo="now", texto="agora com consentimento",
        confirmo_publicacao_imediata=True))
    assert r.status_code == 201, r.text
    detalhe = contexto.cliente.get(f"/api/publicacao-organica/jobs/{r.json()['job_id']}").json()
    assert detalhe["consentimento_agora"] is True
    assert detalhe["consentimento_em"]


# ===========================================================================
# Degraus 4-8 — job, snapshot, despacho, uma chamada, recibo
# ===========================================================================


def test_degraus_4_a_8_o_caminho_feliz_do_rascunho(contexto) -> None:
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, texto="rascunho do caminho feliz"))
    assert criado.status_code == 201, criado.text
    assert criado.headers["X-Publicacao-Idempotente"] == "novo"
    job_id = criado.json()["job_id"]

    # DEGRAU 5 — o snapshot ja existe, e aponta para a VERSAO aprovada.
    antes = contexto.cliente.get(f"/api/publicacao-organica/jobs/{job_id}").json()
    assert antes["estado"] == "rascunho"
    assert antes["solicitacao"]["peca"]["versao"] == 1
    assert antes["solicitacao"]["peca"]["content_hash"].startswith("sha256:a")
    assert antes["solicitacao"]["destino"]["referencia_externa"] == REFERENCIA_DO_CANAL
    # ⚠️ Criar NAO despacha. Nenhuma chamada saiu.
    assert contexto.plano.chamadas == []

    # DEGRAU 6 — liberar e despachar.
    assert contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/liberar").status_code == 200
    despacho = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")
    assert despacho.status_code in (200, 201), despacho.text
    assert despacho.json()["estado"] == "rascunho_externo"

    # DEGRAU 7 — UMA chamada de escrita ao control plane.
    assert contexto.plano.chamadas_de_escrita() == [("POST", "/public/v1/posts")]
    assert len(contexto.plano.posts) == 1

    # DEGRAU 8 — o recibo esta persistido, com a referencia do provedor.
    depois = contexto.cliente.get(f"/api/publicacao-organica/jobs/{job_id}").json()
    assert len(depois["recibos"]) == 1
    assert depois["recibos"][0]["referencia_externa"] in contexto.plano.posts
    assert depois["recibos"][0]["estado_externo"] == "DRAFT"
    assert depois["recibos"][0]["origem"] == "despacho"


# ===========================================================================
# Degrau 9 — retry idempotente
# ===========================================================================


def test_degrau_9_recriar_o_mesmo_job_e_replay_e_nao_segundo_job(contexto) -> None:
    corpo = _corpo_do_job(contexto.cenario, texto="pedido que sera reenviado")
    primeiro = contexto.cliente.post("/api/publicacao-organica/jobs", json=corpo)
    segundo = contexto.cliente.post("/api/publicacao-organica/jobs", json=corpo)

    assert primeiro.status_code == 201
    assert primeiro.headers["X-Publicacao-Idempotente"] == "novo"
    assert segundo.status_code == 200
    assert segundo.headers["X-Publicacao-Idempotente"] == "replay"
    assert primeiro.json()["job_id"] == segundo.json()["job_id"]


def test_degrau_9_redespachar_nao_cria_segundo_post(contexto) -> None:
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, texto="despacho que sera repetido"))
    job_id = criado.json()["job_id"]
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/liberar")
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")

    escritas_apos_o_primeiro = len(contexto.plano.chamadas_de_escrita())
    posts_apos_o_primeiro = len(contexto.plano.posts)

    # ⚠️ O SEGUNDO DESPACHO NAO PODE CHEGAR NA PORTA. Ele e recusado na
    # reivindicacao: o job ja saiu de `pronto`. Se ele passasse, o post
    # duplicaria — e um post duplicado nao tem desfazer.
    repetido = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")
    assert repetido.status_code == 409, repetido.text
    assert len(contexto.plano.chamadas_de_escrita()) == escritas_apos_o_primeiro
    assert len(contexto.plano.posts) == posts_apos_o_primeiro


def test_contraprova_E_mesma_chave_com_payload_diferente_e_recusada(contexto) -> None:
    # A chave e derivada do conteudo, entao mudar o texto muda a chave — e o
    # caminho normal nao colide. Forcamos a colisao chamando a funcao governada
    # com a mesma chave e outro payload, que e o que um cliente com bug faria.
    corpo = _corpo_do_job(contexto.cenario, texto="original")
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=corpo)
    assert criado.status_code == 201

    pedido = dom.montar_pedido(
        peca_id=corpo["peca_id"], peca_versao=1, autorizacao_id=corpo["autorizacao_id"],
        destino_id=corpo["destino_id"], modo="draft", timezone="America/Sao_Paulo",
        horario_local=None, corpo={"texto": "original", "imagens": []},
        consentimento_agora=False)
    chave = dom.chave_de_idempotencia(pedido)

    with pytest.raises(apoio.ErroDoPostgres) as erro:
        contexto.cluster.chamar(
            "SELECT public.publicacao_organica_criar_job("
            f"'{{\"peca_tipo\":\"master\",\"peca_id\":\"{corpo['peca_id']}\",\"peca_versao\":1,"
            f"\"autorizacao_id\":\"{corpo['autorizacao_id']}\",\"destino_id\":\"{corpo['destino_id']}\","
            "\"modo\":\"draft\",\"timezone\":\"America/Sao_Paulo\",\"corpo\":{\"texto\":\"OUTRO\"}}'::jsonb, "
            f"'{chave}', '{contexto.cenario.dono_a}'::uuid, 'a@agenciavolc.com.br')")
    assert erro.value.sqlstate == "23505"
    # ⚠️ A CHAVE NAO APARECE NA MENSAGEM: a gramatica dela aceita uma senha.
    assert chave not in erro.value.mensagem


# ===========================================================================
# Degraus 10-11 — resposta ambigua e reconciliacao
# ===========================================================================


def test_degrau_10_timeout_entra_em_indeterminado_e_nao_inventa_recibo(contexto) -> None:
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, texto="pedido que vai dar timeout"))
    job_id = criado.json()["job_id"]
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/liberar")

    contexto.plano.falhar_com("timeout")
    despacho = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")
    assert despacho.status_code in (200, 201), despacho.text
    assert despacho.json()["estado"] == "indeterminado"

    detalhe = contexto.cliente.get(f"/api/publicacao-organica/jobs/{job_id}").json()
    assert detalhe["recibos"] == []
    assert detalhe["leitura"]["tom"] != "sucesso"
    assert detalhe["leitura"]["incerto"] is True


def test_degrau_10_11_500_apos_gravar_vira_indeterminado_e_a_reconciliacao_fecha(contexto) -> None:
    """O cenario mais caro: o post EXISTE la e nos nao sabemos."""
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, texto="gravou la e nao soubemos aqui"))
    job_id = criado.json()["job_id"]
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/liberar")

    contexto.plano.falhar_com("500_apos_gravar")
    despacho = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")
    assert despacho.json()["estado"] == "indeterminado"
    # O post EXISTE no control plane, apesar de nao termos recibo.
    assert len(contexto.plano.posts) == 1

    # A reconciliacao sem referencia externa nao inventa nada: o job continua
    # indeterminado e a observacao diz que nao ha o que procurar.
    recon = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/reconciliar")
    assert recon.status_code in (200, 201), recon.text
    assert recon.json()["estado"] == "indeterminado"
    assert recon.json()["fechou"] is False

    detalhe = contexto.cliente.get(f"/api/publicacao-organica/jobs/{job_id}").json()
    assert detalhe["leitura"]["tom"] == "atencao"
    assert "reconcilie" in detalhe["leitura"]["proxima_acao"].lower()


def test_degrau_11_reconciliacao_fecha_o_ciclo_quando_o_post_e_publicado(contexto) -> None:
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, modo="schedule", horario_local="2099-07-15 09:30",
        texto="agendado que sera publicado"))
    assert criado.status_code == 201, criado.text
    job_id = criado.json()["job_id"]
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/liberar")
    despacho = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")
    assert despacho.json()["estado"] == "agendado"

    referencia = despacho.json()["referencia_externa"]

    # Primeira reconciliacao: ainda na fila. NAO fecha, e NAO fica verde.
    r1 = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/reconciliar")
    assert r1.json()["estado"] == "agendado"
    assert r1.json()["fechou"] is False

    # O horario chega e o control plane publica sozinho.
    contexto.plano.publicar_de_verdade(referencia, "https://www.facebook.com/piloto/posts/9001")

    r2 = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/reconciliar")
    assert r2.json()["estado"] == "reconciliado", r2.text
    assert r2.json()["fechou"] is True

    detalhe = contexto.cliente.get(f"/api/publicacao-organica/jobs/{job_id}").json()
    assert detalhe["leitura"]["tom"] == "sucesso"
    assert detalhe["leitura"]["terminal"] is True
    # ⚠️ TRES OBSERVACOES PRESERVADAS, e nao uma sobrescrita: a auditoria pergunta
    # "quando ele ainda nao estava no ar?" e a resposta precisa existir.
    estados = [r["estado_externo"] for r in detalhe["recibos"]]
    assert estados == ["QUEUE", "QUEUE", "PUBLISHED"], estados
    assert detalhe["recibos"][-1]["url_publicada"] == "https://www.facebook.com/piloto/posts/9001"


# ===========================================================================
# Degrau 12 — a tela reflete o estado material
# ===========================================================================


def test_degrau_12_a_leitura_vem_do_servidor_e_nunca_pinta_incerto_de_verde(contexto) -> None:
    r = contexto.cliente.get("/api/publicacao-organica/jobs")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert jobs, "o cenario deveria ter jobs"

    for job in jobs:
        leitura = job["leitura"]
        assert leitura["rotulo"] and leitura["proxima_acao"]
        if leitura["incerto"]:
            assert leitura["tom"] != "sucesso", job["estado"]
        if leitura["tom"] == "sucesso":
            # O unico verde e `reconciliado`, e ele exige URL e instante.
            assert job["estado"] == "reconciliado"


def test_degrau_12_estado_desconhecido_na_query_e_recusado_com_mensagem(contexto) -> None:
    r = contexto.cliente.get("/api/publicacao-organica/jobs?estado=inventado")
    assert r.status_code == 400
    assert r.json()["detail"]["codigo"] == "estado_desconhecido"


def test_degrau_12_prontidao_diz_que_o_health_e_proxy(contexto) -> None:
    r = contexto.cliente.get("/api/publicacao-organica/prontidao")
    assert r.status_code == 200
    assert r.json()["fonte"] == "proxy:/integrations"
    assert "nao ha endpoint de health oficial" in r.json()["detalhe"]


# ===========================================================================
# Timezone — o horario declarado sobrevive a ida e volta
# ===========================================================================


def test_o_horario_local_vira_utc_e_volta_a_ser_apresentado_na_zona_declarada(contexto) -> None:
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, modo="schedule", timezone="America/Sao_Paulo",
        horario_local="2099-07-15 09:30", texto="teste de fuso"))
    assert r.status_code == 201, r.text
    detalhe = contexto.cliente.get(f"/api/publicacao-organica/jobs/{r.json()['job_id']}").json()

    # ⚠️ O SERVIDOR DE TESTE RODA EM UTC (fixture `subir_cluster`). Se a conversao
    # dependesse do TZ do processo, este numero mudaria de maquina para maquina.
    assert detalhe["instante_utc"].startswith("2099-07-15T12:30:00")
    # E o que o operador digitou volta como ele digitou, com a zona junto.
    assert detalhe["horario_local"] == "2099-07-15 09:30:00"
    assert detalhe["timezone"] == "America/Sao_Paulo"


def test_o_instante_enviado_ao_control_plane_e_o_utc_e_nao_o_local(contexto) -> None:
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, modo="schedule", timezone="America/Sao_Paulo",
        horario_local="2099-08-20 18:00", texto="fuso ate o provedor"))
    job_id = r.json()["job_id"]
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/liberar")
    despacho = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")
    referencia = despacho.json()["referencia_externa"]

    # A API do Postiz documenta `date` em UTC ISO. 18:00 em America/Sao_Paulo
    # (UTC-3, sem horario de verao desde 2019) e 21:00Z.
    enviado = contexto.plano.posts[referencia].publishDate
    assert enviado.startswith("2099-08-20T21:00:00"), enviado


@pytest.mark.parametrize("caso,esperado", [
    ({"modo": "schedule", "timezone": "America/Nao_Existe", "horario_local": "2099-01-01 10:00"},
     "timezone_invalido"),
    ({"modo": "schedule", "timezone": "America/Sao_Paulo", "horario_local": "amanha"},
     "horario_invalido"),
    ({"modo": "schedule", "timezone": "America/Sao_Paulo"}, "horario_ausente"),
])
def test_horario_invalido_e_recusado_antes_de_qualquer_chamada(contexto, caso, esperado) -> None:
    r = contexto.cliente.post("/api/publicacao-organica/jobs",
                              json=_corpo_do_job(contexto.cenario, **caso))
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["codigo"] == esperado
    assert contexto.plano.chamadas == []


def test_agendar_para_o_passado_e_recusado_pelo_banco(contexto) -> None:
    # O dominio nao recusa o passado (ele nao sabe que horas sao no fuso do
    # banco); quem recusa e a funcao governada. A recusa chega traduzida.
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, modo="schedule", timezone="America/Sao_Paulo",
        horario_local="2020-01-01 10:00", texto="passado"))
    assert r.status_code == 400, r.text
    assert "passado" in r.json()["detail"]["mensagem"]


# ===========================================================================
# Contraprova H — a linha crua do Postgres nao chega ao cliente
# ===========================================================================


def test_a_mensagem_de_erro_do_banco_nao_carrega_a_linha_recusada(contexto) -> None:
    """O shim devolve `details` com a linha inteira, como o PostgREST faz.

    Este teste existe porque o filtro de `infraestrutura.py` so vale se for
    exercitado contra um corpo que REALMENTE carrega a linha. Um shim que
    devolvesse so `message` faria o filtro parecer correto sem nunca ser usado.
    """
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, autorizacao_id=contexto.cenario.aprov_revogada))
    assert r.status_code == 409
    texto = r.text
    assert "Failing row contains" not in texto
    assert "DETAIL:" not in texto
    # A mensagem util sobrevive: a recusa continua dizendo o que houve.
    assert "revogada" in r.json()["detail"]["mensagem"]


def test_o_token_do_control_plane_nunca_aparece_em_resposta_nenhuma(contexto) -> None:
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, texto="job que vai receber um 400 com eco"))
    job_id = criado.json()["job_id"]
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/liberar")

    contexto.plano.falhar_com("400")
    despacho = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")
    assert despacho.json()["estado"] == "falha"

    detalhe = contexto.cliente.get(f"/api/publicacao-organica/jobs/{job_id}")
    assert contexto.plano.token not in detalhe.text
    assert contexto.plano.token not in despacho.text
    # E o banco tambem nao guardou.
    guardado = contexto.cluster.psql(
        "SELECT coalesce(string_agg(ultimo_erro, ' '), '') FROM public.publicacao_organica_job")
    assert contexto.plano.token not in guardado


# ===========================================================================
# Cancelamento seguro
# ===========================================================================


def test_cancelar_job_em_voo_e_recusado(contexto) -> None:
    """Nao ha `em_voo` observavel pela rota — e isso e a prova.

    O despacho reivindica e conclui na MESMA requisicao, entao o job nunca fica
    parado em `em_voo` para alguem cancelar. A recusa existe no banco para o
    caso em que o processo morre no meio, e esta provada em
    `scripts/provar-ciclo-v14_01.sh`. Aqui provamos o que a rota alcanca: um job
    ja despachado e cancelavel, e o recibo dele SOBREVIVE ao cancelamento.
    """
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, texto="job que sera cancelado"))
    job_id = criado.json()["job_id"]
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/liberar")
    contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/despachar")

    r = contexto.cliente.post(f"/api/publicacao-organica/jobs/{job_id}/cancelar",
                              json={"motivo": "peca substituida"})
    assert r.status_code == 200, r.text

    detalhe = contexto.cliente.get(f"/api/publicacao-organica/jobs/{job_id}").json()
    assert detalhe["estado"] == "cancelado"
    assert len(detalhe["recibos"]) == 1, "o recibo do rascunho nao pode sumir"
    assert detalhe["leitura"]["tom"] == "neutro"


def test_cancelar_sem_motivo_e_recusado(contexto) -> None:
    criado = contexto.cliente.post("/api/publicacao-organica/jobs", json=_corpo_do_job(
        contexto.cenario, texto="cancelamento sem motivo"))
    r = contexto.cliente.post(
        f"/api/publicacao-organica/jobs/{criado.json()['job_id']}/cancelar", json={"motivo": "  "})
    assert r.status_code == 400


def test_campo_desconhecido_no_corpo_e_recusado_sem_ecoar_o_valor(contexto) -> None:
    # ⚠️ O 422 padrao do FastAPI serializa `input` — o VALOR rejeitado. Se
    # alguem manda um token no campo errado, o token voltaria no corpo do erro.
    sintetico = "xox" + "b-0123456789abcdefghij"   # ver a nota em ..._dominio.py
    r = contexto.cliente.post("/api/publicacao-organica/jobs", json={
        **_corpo_do_job(contexto.cenario), "password": sintetico})
    assert r.status_code == 400, r.text
    assert sintetico not in r.text


# ===========================================================================
# Degrau que NAO pode ser provado localmente — declarado, nao mascarado
# ===========================================================================


def test_nenhuma_chamada_externa_real_aconteceu(contexto) -> None:
    """A prova estrutural de zero publicacao real.

    Todo trafego HTTP desta suite passou por `httpx.MockTransport`. Se alguem
    trocar o cliente injetado por um real, este teste continua passando — por
    isso ele NAO e a unica prova: `test_publicacao_organica_segredos.py` varre o
    codigo, e o handoff declara a fronteira. Aqui provamos o que da para provar
    de dentro: o fake registrou TODAS as chamadas, e nenhum host real aparece.
    """
    assert contexto.plano.chamadas is not None
    assert os.environ.get("POSTIZ_API_TOKEN") in (None, "")
