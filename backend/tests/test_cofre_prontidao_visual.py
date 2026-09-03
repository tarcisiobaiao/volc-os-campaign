"""A rota `GET /api/cofre/ativos/{id}/prontidao-visual`, pelo HTTP.

Ela é leitura composta, como o `handoff`: nenhuma escrita, nenhuma chamada ao
broker, nenhum navegador. O que este arquivo prova é que a composição continua
honesta ao atravessar a fronteira HTTP — inclusive quando o Cofre cai, quando o
broker não existe e quando nada foi executado.
"""
from __future__ import annotations

import json
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

for _chave in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
    os.environ[_chave] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.asset_vault import rotas  # noqa: E402
from app.asset_vault.aplicacao import CasosDeUso, CofreIndisponivel  # noqa: E402
from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario  # noqa: E402
from app.visual_proof import infraestrutura as infra  # noqa: E402

ADMIN = Identidade(sub="sub-a", email="dono@volc.test", papel="ADMIN", origem="sessao")
OUTRO = Identidade(sub="sub-b", email="outro@volc.test", papel="ADMIN", origem="sessao")

DETALHE_COMPLETO = {
    "ativo_id": "asset:facebook-page:piloto", "nome": "Página piloto",
    "kind": "facebook_page", "plataforma": "Facebook", "estado": "active",
    "url_publica": "https://exemplo.com.br/pagina", "projeto": "Piloto",
    "vertical": "Notícias",
    "credencial": [{"provider": "1password", "nome_logico": "FB_PAGE_ADMIN",
                    "estado": "referenced", "verificacao_estado": "verified",
                    "verificado_em": "2026-09-01"}],
    "relacoes": [{"tipo": "authenticates_through",
                  "destino_id": "asset:browser-profile:piloto",
                  "destino_rotulo": "Perfil piloto"}],
}


class RepoFalso:
    def __init__(self, detalhe=None, engines=None, erro=None):
        self._detalhe = detalhe
        self._engines = engines if engines is not None else []
        self._erro = erro

    @property
    def configurado(self):
        return True

    async def listar(self, **_f):
        return {"gavetas": [], "ativos": []}

    async def detalhar(self, ativo_id):
        if self._erro:
            raise self._erro
        return self._detalhe

    async def engines(self):
        if self._erro:
            raise self._erro
        return self._engines

    async def postura_credencial(self, ativo_id):
        return []

    async def executar(self, funcao, argumentos):
        raise AssertionError("prontidão é leitura: não pode executar nada")


def montar(repo, *, quem=ADMIN, leitor=None, broker_configurado=False) -> TestClient:
    app = FastAPI()
    app.include_router(rotas.router)
    app.dependency_overrides[rotas.obter_casos] = lambda: CasosDeUso(repo)
    if quem is not None:
        # `quem=None` deixa a dependência REAL de identidade no caminho — é
        # assim que se prova que a rota está atrás do portão, e não apenas que
        # ela funciona quando o portão foi substituído por um duplê.
        app.dependency_overrides[exigir_usuario] = lambda: quem
        app.dependency_overrides[exigir_admin] = lambda: quem
    app.dependency_overrides[rotas.obter_leitor_de_prova_visual] = (
        lambda: leitor or infra.LeitorSemPersistencia())
    app.dependency_overrides[rotas.obter_broker_configurado] = lambda: broker_configurado
    return TestClient(app, raise_server_exceptions=False)


def test_prontidao_completa_sem_broker_diz_o_que_falta():
    cliente = montar(RepoFalso(detalhe=DETALHE_COMPLETO))
    resposta = cliente.get("/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["pronto_para_receber_peca"] is True
    assert corpo["pronto_para_publicar"] is True
    assert corpo["pronto_para_qa"] is False
    assert corpo["broker"]["estado"] == "nao_configurado"
    assert [b["codigo"] for b in corpo["bloqueios"]] == ["broker_indisponivel"]
    assert corpo["qa_visual"]["estado"] == "nao_persistido"
    assert "P03-T11" in corpo["proxima_acao"]


def test_prontidao_de_ativo_sem_perfil_separa_receber_de_publicar():
    detalhe = {**DETALHE_COMPLETO, "relacoes": []}
    cliente = montar(RepoFalso(detalhe=detalhe), broker_configurado=True)
    corpo = cliente.get(
        "/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual").json()
    assert corpo["pronto_para_receber_peca"] is True
    assert corpo["pronto_para_publicar"] is False
    assert corpo["perfil_de_navegador"]["presente"] is False
    assert "P03-T07" in corpo["proxima_acao"]


def test_prontidao_nunca_devolve_localizador():
    """O `handoff` já omite o endereço; a prontidão herda a omissão."""
    cliente = montar(RepoFalso(detalhe=DETALHE_COMPLETO), broker_configurado=True)
    texto = cliente.get(
        "/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual").text
    assert "op://" not in texto and "localizador" not in texto


def test_ativo_inexistente_e_404_e_nao_prontidao_vazia():
    cliente = montar(RepoFalso(detalhe=None))
    resposta = cliente.get("/api/cofre/ativos/asset:facebook-page:sumiu/prontidao-visual")
    assert resposta.status_code == 404


def test_cofre_indisponivel_e_503_e_nao_prontidao_negativa():
    """A distinção que o Cofre inteiro existe para preservar.

    Um 200 com `pronto_para_publicar: false` sobre um banco fora do ar diria
    "seu ativo não está pronto" — quando o fato é "não sabemos".
    """
    cliente = montar(RepoFalso(erro=CofreIndisponivel("banco fora do ar")))
    resposta = cliente.get("/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual")
    assert resposta.status_code == 503
    assert resposta.json()["detail"]["codigo"] == "cofre_indisponivel"


def test_rota_exige_admin():
    cliente = montar(RepoFalso(detalhe=DETALHE_COMPLETO), quem=None)
    app = cliente.app
    app.dependency_overrides.pop(exigir_admin, None)
    app.dependency_overrides.pop(exigir_usuario, None)
    resposta = cliente.get("/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual")
    assert resposta.status_code in (401, 403, 503)


def test_prontidao_mostra_job_do_dono_e_nada_do_outro():
    from app.visual_proof import aplicacao as vp
    from app.visual_proof import dominio as vdom

    repo_visual = infra.RepositorioEmMemoria()
    controle = vp.ControleDeProvaVisual(
        repositorio=repo_visual,
        broker=_BrokerQueCaptura(),
        resolvedor_de_dns=lambda host: ["93.184.216.34"],
    )
    perfil = vdom.BrowserProfileReference(
        ativo_id="asset:browser-profile:piloto", perfil_logico="PERFIL_PILOTO_01",
        owner_sub=ADMIN.sub, provider="1password",
        credencial_nome_logico="ADSPOWER_API_KEY")
    job = controle.criar(vp.PedidoDeProvaVisual(
        ativo_id="asset:facebook-page:piloto", owner_sub=ADMIN.sub,
        url_esperada="https://exemplo.com.br/pagina", dominio_esperado="exemplo.com.br",
        perfil=perfil, chave_idempotencia="vpj-rota-2026-09-02-01"))
    controle.executar(job.job_id, solicitante=ADMIN.sub)

    leitor = infra.LeitorEmMemoria(repo_visual)
    do_dono = montar(RepoFalso(detalhe=DETALHE_COMPLETO), leitor=leitor,
                     broker_configurado=True).get(
        "/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual").json()
    assert do_dono["qa_visual"]["estado"] == "em_execucao"
    assert do_dono["qa_visual"]["artefato"]["sha256"] == "b" * 64

    do_outro = montar(RepoFalso(detalhe=DETALHE_COMPLETO), quem=OUTRO, leitor=leitor,
                      broker_configurado=True).get(
        "/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual").json()
    assert do_outro["qa_visual"]["estado"] == "nao_executado"
    assert do_outro["qa_visual"]["job"] is None


class _BrokerQueCaptura:
    configurado = True

    def executar(self, pedido, *, consumidor):
        from app.visual_proof import dominio as vdom
        return vdom.AdsPowerBrokerReceipt(
            recibo_id="rcp_rota", pedido_id=pedido.pedido_id,
            chave_idempotencia=pedido.chave_idempotencia, operacao=pedido.operacao,
            perfil_logico=pedido.perfil.perfil_logico, owner_sub=pedido.owner_sub,
            ativo_id=pedido.ativo_id, estado="executado", motivo_codigo="ok",
            motivo="ok", iniciado_em="2026-09-02T12:00:00+00:00",
            concluido_em="2026-09-02T12:00:03+00:00", duracao_ms=3000,
            adspower_code=0, url_final=pedido.url_alvo, status_http=200,
            artefato=vdom.VisualProofArtifact(
                referencia="vpartifact://PERFIL_PILOTO_01/rcp_rota/captura.png",
                sha256="b" * 64, bytes_=1234, mime="image/png",
                criado_em="2026-09-02T12:00:03+00:00"),
            console_resumo={"erros": 0}, rede_resumo={"falhas": 0})


def test_json_da_prontidao_e_serializavel_e_estavel():
    cliente = montar(RepoFalso(detalhe=DETALHE_COMPLETO), broker_configurado=True)
    corpo = cliente.get(
        "/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual").json()
    assert json.loads(json.dumps(corpo)) == corpo
    for campo in ("pagina", "referencia_de_credencial", "perfil_de_navegador",
                  "broker", "qa_visual", "pronto_para_receber_peca",
                  "pronto_para_publicar", "pronto_para_qa", "bloqueios", "proxima_acao"):
        assert campo in corpo, campo


@pytest.mark.parametrize("estado_do_ativo,esperado", [("retired", False), ("active", True)])
def test_ativo_aposentado_nao_recebe_peca(estado_do_ativo, esperado):
    detalhe = {**DETALHE_COMPLETO, "estado": estado_do_ativo}
    cliente = montar(RepoFalso(detalhe=detalhe), broker_configurado=True)
    corpo = cliente.get(
        "/api/cofre/ativos/asset:facebook-page:piloto/prontidao-visual").json()
    assert corpo["pronto_para_receber_peca"] is esperado
