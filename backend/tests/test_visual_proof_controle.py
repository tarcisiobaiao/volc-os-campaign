"""O plano de controle: ciclo do job, idempotência, lease, dono e prontidão.

Sem rede e sem duplê HTTP — aqui o broker é uma porta implementada por um
objeto de teste. O E2E com sockets está em `test_adspower_broker_hermetico.py`;
este arquivo cobre as decisões que acontecem ANTES e DEPOIS do broker, que são
as que a tela consome.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.visual_proof import aplicacao as app
from app.visual_proof import dominio as dom
from app.visual_proof import infraestrutura as infra

DONO_A = "sub-a"
DONO_B = "sub-b"
URL = "https://exemplo.com.br/post/123"
DOMINIO = "exemplo.com.br"

DNS = {"exemplo.com.br": ["93.184.216.34"], "blog.exemplo.com.br": ["93.184.216.35"]}


def _dns(host: str) -> list[str]:
    try:
        return DNS[host]
    except KeyError:
        raise dom.NomeNaoResolvido(host) from None


def _perfil(owner: str = DONO_A) -> dom.BrowserProfileReference:
    return dom.BrowserProfileReference(
        ativo_id="asset:browser-profile:piloto", perfil_logico="PERFIL_PILOTO_01",
        owner_sub=owner, provider="1password", credencial_nome_logico="ADSPOWER_API_KEY")


def _pedido(**kwargs) -> app.PedidoDeProvaVisual:
    corpo = dict(
        ativo_id="asset:facebook-page:piloto", owner_sub=DONO_A, url_esperada=URL,
        dominio_esperado=DOMINIO, perfil=_perfil(),
        chave_idempotencia="vpj-piloto-2026-09-02-01")
    corpo.update(kwargs)
    return app.PedidoDeProvaVisual(**corpo)


class BrokerDeTeste:
    """Implementa a porta. Cada modo é um fato diferente sobre o executor."""

    def __init__(self, *, modo: str = "feliz", configurado: bool = True):
        self.modo = modo
        self._configurado = configurado
        self.pedidos: list[dom.AdsPowerBrokerRequest] = []

    @property
    def configurado(self) -> bool:
        return self._configurado

    def executar(self, pedido, *, consumidor):
        self.pedidos.append(pedido)
        if self.modo == "indisponivel":
            raise app.BrokerIndisponivel("broker fora do ar")
        base = dict(
            recibo_id=f"rcp_{len(self.pedidos):04d}", pedido_id=pedido.pedido_id,
            chave_idempotencia=pedido.chave_idempotencia, operacao=pedido.operacao,
            perfil_logico=pedido.perfil.perfil_logico, owner_sub=pedido.owner_sub,
            ativo_id=pedido.ativo_id, iniciado_em="2026-09-02T12:00:00+00:00",
            concluido_em="2026-09-02T12:00:05+00:00", duracao_ms=5000)
        if self.modo == "timeout":
            return dom.AdsPowerBrokerReceipt(
                estado="falhou", motivo_codigo="timeout",
                motivo="a Local API não respondeu a tempo.", **base)
        if self.modo == "recusado":
            return dom.AdsPowerBrokerReceipt(
                estado="recusado", motivo_codigo="nao_autorizado",
                motivo="perfil fora da allowlist", **base)
        url_final = URL if self.modo != "url_divergente" else "https://exemplo.com.br/404"
        return dom.AdsPowerBrokerReceipt(
            estado="executado", motivo_codigo="ok", motivo="captura concluída",
            adspower_code=0, url_final=url_final, status_http=200,
            artefato=dom.VisualProofArtifact(
                referencia="vpartifact://PERFIL_PILOTO_01/rcp/captura.png",
                sha256="a" * 64, bytes_=48_000, mime="image/png",
                criado_em="2026-09-02T12:00:05+00:00"),
            console_resumo={"erros": 0, "avisos": 1, "total": 1},
            rede_resumo={"requisicoes": 12, "falhas": 0}, **base)


def _controle(broker=None, repositorio=None) -> app.ControleDeProvaVisual:
    return app.ControleDeProvaVisual(
        repositorio=repositorio or infra.RepositorioEmMemoria(),
        broker=broker or BrokerDeTeste(), resolvedor_de_dns=_dns)


# ─────────────────────────────────────────────────────────────────────────────
# Ciclo
# ─────────────────────────────────────────────────────────────────────────────


def test_job_novo_nasce_autorizado_depois_de_validado():
    job = _controle().criar(_pedido())
    assert job.estado == "authorized"
    assert job.url_esperada == URL
    assert job.tentativas == 0


def test_url_fora_do_dominio_nem_cria_job():
    with pytest.raises(dom.UrlRecusada):
        _controle().criar(_pedido(url_esperada="https://outro.example/post"))


def test_dono_do_job_precisa_ser_o_dono_do_perfil():
    with pytest.raises(dom.PayloadRecusado):
        _controle().criar(_pedido(perfil=_perfil(owner=DONO_B)))


def test_chave_de_idempotencia_sorteada_e_recusada_pela_gramatica():
    with pytest.raises(dom.PayloadRecusado):
        _controle().criar(_pedido(chave_idempotencia="curta"))


def test_execucao_feliz_para_em_captured_e_nunca_em_approved():
    """A prova central do plano de controle.

    Uma captura limpa NÃO aprova: ela deixa o job em `captured`, esperando
    gente. `approved` só existe depois de `aprovar()` com revisor nomeado.
    """
    controle = _controle()
    job = controle.criar(_pedido())
    executado = controle.executar(job.job_id, solicitante=DONO_A)
    assert executado.estado == "captured"
    assert executado.veredito == "eligible_for_human_review"
    assert executado.veredito != "approved"
    assert executado.artefato and executado.artefato.sha256 == "a" * 64

    aprovado = controle.aprovar(job.job_id, solicitante=DONO_A, revisor="tarcisio",
                                nota="conferi a página publicada")
    assert aprovado.estado == "approved" and aprovado.veredito == "approved"
    assert aprovado.revisao_humana["revisor"] == "tarcisio"


def test_url_final_divergente_vira_correcao():
    controle = _controle(broker=BrokerDeTeste(modo="url_divergente"))
    job = controle.criar(_pedido())
    executado = controle.executar(job.job_id, solicitante=DONO_A)
    assert executado.estado == "needs_correction"
    assert executado.veredito == "needs_correction"


@pytest.mark.parametrize("modo,esperado", [
    ("timeout", "indeterminate"),
    ("recusado", "indeterminate"),
    ("indisponivel", "indeterminate"),
])
def test_falha_do_executor_e_indeterminada_nunca_reprovacao(modo, esperado):
    controle = _controle(broker=BrokerDeTeste(modo=modo))
    job = controle.criar(_pedido())
    executado = controle.executar(job.job_id, solicitante=DONO_A)
    assert executado.estado == esperado
    assert executado.veredito == "indeterminate"
    assert executado.estado != "needs_correction"


def test_broker_nao_configurado_e_indeterminado_e_nao_erro_de_pagina():
    controle = _controle(broker=BrokerDeTeste(configurado=False))
    job = controle.criar(_pedido())
    executado = controle.executar(job.job_id, solicitante=DONO_A)
    assert executado.estado == "indeterminate"
    assert any("executor" in j for j in executado.justificativas)


def test_job_terminal_nao_reexecuta():
    controle = _controle()
    job = controle.criar(_pedido())
    controle.executar(job.job_id, solicitante=DONO_A)
    controle.aprovar(job.job_id, solicitante=DONO_A, revisor="t", nota="ok")
    de_novo = controle.executar(job.job_id, solicitante=DONO_A)
    assert de_novo.estado == "approved" and de_novo.tentativas == 1


def test_reprovacao_humana_tambem_exige_revisor():
    controle = _controle()
    job = controle.criar(_pedido())
    controle.executar(job.job_id, solicitante=DONO_A)
    with pytest.raises(dom.TransicaoInvalida):
        controle.pedir_correcao(job.job_id, solicitante=DONO_A, revisor="", nota="x")
    corrigido = controle.pedir_correcao(job.job_id, solicitante=DONO_A,
                                        revisor="tarcisio", nota="clipping no topo")
    assert corrigido.estado == "needs_correction"


# ─────────────────────────────────────────────────────────────────────────────
# Idempotência, lease e dono
# ─────────────────────────────────────────────────────────────────────────────


def test_mesma_chave_com_mesma_entrada_devolve_o_mesmo_job():
    controle = _controle()
    primeiro = controle.criar(_pedido())
    segundo = controle.criar(_pedido())
    assert primeiro.job_id == segundo.job_id


def test_mesma_chave_com_entrada_diferente_e_recusada():
    controle = _controle()
    controle.criar(_pedido())
    with pytest.raises(app.ConflitoDeIdempotencia):
        controle.criar(_pedido(url_esperada="https://blog.exemplo.com.br/outro"))


def test_dois_consumidores_nao_executam_o_mesmo_job(monkeypatch):
    class BrokerLento(BrokerDeTeste):
        def executar(self, pedido, *, consumidor):
            time.sleep(0.4)
            return super().executar(pedido, consumidor=consumidor)

    broker = BrokerLento()
    controle = _controle(broker=broker)
    job = controle.criar(_pedido())
    erros: list[Exception] = []

    def rodar(nome: str) -> None:
        try:
            controle.executar(job.job_id, solicitante=DONO_A, consumidor=nome)
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    primeira = threading.Thread(target=rodar, args=("a",))
    primeira.start()
    time.sleep(0.1)
    rodar("b")
    primeira.join(timeout=10)

    assert len(erros) == 1 and isinstance(erros[0], app.JobEmExecucao)
    assert len(broker.pedidos) == 1


def test_dono_b_nao_le_nem_aprova_job_do_dono_a():
    controle = _controle()
    job = controle.criar(_pedido())
    controle.executar(job.job_id, solicitante=DONO_A)
    with pytest.raises(app.AcessoNegado):
        controle.ler(job.job_id, solicitante=DONO_B)
    with pytest.raises(app.AcessoNegado):
        controle.aprovar(job.job_id, solicitante=DONO_B, revisor="b", nota="x")


def test_job_de_outro_dono_responde_igual_a_job_inexistente():
    """A mensagem não pode distinguir os dois casos: distinguir é um oráculo."""
    controle = _controle()
    job = controle.criar(_pedido())
    with pytest.raises(app.AcessoNegado) as de_outro:
        controle.ler(job.job_id, solicitante=DONO_B)
    with pytest.raises(app.AcessoNegado) as inexistente:
        controle.ler("vpj_nao_existe", solicitante=DONO_B)
    assert str(de_outro.value) == str(inexistente.value)


def test_ultimo_job_do_ativo_e_por_dono():
    repo = infra.RepositorioEmMemoria()
    controle = _controle(repositorio=repo)
    controle.criar(_pedido())
    controle.criar(_pedido(chave_idempotencia="vpj-piloto-2026-09-02-02",
                           url_esperada="https://blog.exemplo.com.br/x",
                           dominio_esperado=DOMINIO))
    assert controle.ultimo_do_ativo("asset:facebook-page:piloto",
                                    solicitante=DONO_A) is not None
    assert controle.ultimo_do_ativo("asset:facebook-page:piloto",
                                    solicitante=DONO_B) is None


def test_lease_vencido_pode_ser_reivindicado():
    """Um worker que morre no meio não pode travar o job para sempre."""
    relogio = {"t": 0.0}
    repo = infra.RepositorioEmMemoria(relogio=lambda: relogio["t"])
    controle = app.ControleDeProvaVisual(
        repositorio=repo, broker=BrokerDeTeste(), resolvedor_de_dns=_dns, lease_s=10)
    job = controle.criar(_pedido())
    repo.reivindicar(job.job_id, "worker-morto", 10)
    with pytest.raises(app.JobEmExecucao):
        repo.reivindicar(job.job_id, "worker-vivo", 10)
    relogio["t"] = 11.0
    repo.reivindicar(job.job_id, "worker-vivo", 10)


# ─────────────────────────────────────────────────────────────────────────────
# Recibo vindo do broker
# ─────────────────────────────────────────────────────────────────────────────


def test_recibo_com_campo_proibido_e_recusado_inteiro():
    for proibido in ("localizador", "user_id", "cookie", "api_key"):
        with pytest.raises(app.BrokerIndisponivel) as erro:
            infra.recibo_de_dicionario({"recibo_id": "r", proibido: "x"})
        assert proibido in str(erro.value)


def test_broker_http_sem_configuracao_falha_fechado():
    broker = infra.BrokerHttp(ambiente={})
    assert broker.configurado is False
    with pytest.raises(app.BrokerIndisponivel):
        broker.executar(
            dom.AdsPowerBrokerRequest(
                pedido_id="p", chave_idempotencia="k" * 10, operacao="estado_do_perfil",
                perfil=_perfil(), owner_sub=DONO_A, ativo_id="asset:x:y"),
            consumidor="teste")


def test_broker_http_exige_endereco_e_token():
    assert infra.BrokerHttp(ambiente={infra.VAR_ENDERECO: "http://127.0.0.1:9"}).configurado is False
    assert infra.BrokerHttp(ambiente={infra.VAR_TOKEN: "t"}).configurado is False
    assert infra.BrokerHttp(ambiente={
        infra.VAR_ENDERECO: "http://127.0.0.1:9", infra.VAR_TOKEN: "t"}).configurado is True


# ─────────────────────────────────────────────────────────────────────────────
# Prontidão
# ─────────────────────────────────────────────────────────────────────────────


HANDOFF_COMPLETO = {
    "destino": {"ativo_id": "asset:facebook-page:piloto", "nome": "Página piloto",
                "kind": "facebook_page", "estado": "active",
                "url_publica": "https://exemplo.com.br/pagina"},
    "referencia_de_acesso": [{"provider": "1password", "nome_logico": "FB_PAGE_ADMIN",
                              "estado": "referenced", "verificacao_estado": "verified",
                              "verificado_em": "2026-09-01"}],
    "perfis_de_navegador": [{"tipo": "authenticates_through",
                             "destino_id": "asset:browser-profile:piloto",
                             "destino_rotulo": "Perfil piloto"}],
    "bloqueios": [],
}

SEM_PERSISTENCIA = ("ausente", "não existe persistência de VisualProofJob")
COM_PERSISTENCIA = ("disponivel", "repositório em memória")


def test_prontidao_sem_pagina_bloqueia_tudo():
    p = app.montar_prontidao(
        handoff={"destino": {}, "referencia_de_acesso": [], "perfis_de_navegador": [],
                 "bloqueios": []},
        broker_configurado=False, persistencia=SEM_PERSISTENCIA)
    assert p["pronto_para_receber_peca"] is False
    assert p["pronto_para_publicar"] is False
    assert p["bloqueios"][0]["codigo"] == "pagina_ausente"
    assert "P03-T02" in p["proxima_acao"]


def test_prontidao_distingue_receber_peca_de_publicar():
    """Página cadastrada e sem perfil: pode receber peça, não pode publicar."""
    handoff = {**HANDOFF_COMPLETO, "perfis_de_navegador": []}
    p = app.montar_prontidao(handoff=handoff, broker_configurado=True,
                             persistencia=SEM_PERSISTENCIA)
    assert p["pronto_para_receber_peca"] is True
    assert p["pronto_para_publicar"] is False
    assert [b["codigo"] for b in p["bloqueios"]] == ["perfil_ausente"]


def test_prontidao_sem_broker_bloqueia_qa_mas_nao_publicacao():
    p = app.montar_prontidao(handoff=HANDOFF_COMPLETO, broker_configurado=False,
                             persistencia=SEM_PERSISTENCIA)
    assert p["pronto_para_publicar"] is True
    assert p["pronto_para_qa"] is False
    assert [b["codigo"] for b in p["bloqueios"]] == ["broker_indisponivel"]


def test_prontidao_diz_nao_persistido_quando_nao_ha_onde_guardar():
    """`nao_persistido` ≠ `nao_executado`. Colapsá-los seria otimismo."""
    p = app.montar_prontidao(handoff=HANDOFF_COMPLETO, broker_configurado=True,
                             persistencia=SEM_PERSISTENCIA)
    assert p["qa_visual"]["estado"] == "nao_persistido"
    assert p["qa_visual"]["job"] is None
    assert "migration" in p["qa_visual"]["motivo"] or "persistência" in p["qa_visual"]["motivo"]


def test_prontidao_diz_nao_executado_quando_ha_onde_guardar_e_ninguem_rodou():
    p = app.montar_prontidao(handoff=HANDOFF_COMPLETO, broker_configurado=True,
                             persistencia=COM_PERSISTENCIA, job=None)
    assert p["qa_visual"]["estado"] == "nao_executado"


def test_prontidao_nao_mostra_captured_como_aprovado():
    """`captured` é 'esperando gente', e a tela precisa saber disso."""
    controle = _controle()
    job = controle.criar(_pedido())
    executado = controle.executar(job.job_id, solicitante=DONO_A)
    p = app.montar_prontidao(handoff=HANDOFF_COMPLETO, broker_configurado=True,
                             persistencia=COM_PERSISTENCIA,
                             job=executado.para_dicionario())
    assert executado.estado == "captured"
    assert p["qa_visual"]["estado"] == "em_execucao"
    assert p["qa_visual"]["estado"] != "aprovado"


def test_prontidao_mostra_indeterminado_como_indeterminado():
    controle = _controle(broker=BrokerDeTeste(modo="timeout"))
    job = controle.criar(_pedido())
    executado = controle.executar(job.job_id, solicitante=DONO_A)
    p = app.montar_prontidao(handoff=HANDOFF_COMPLETO, broker_configurado=True,
                             persistencia=COM_PERSISTENCIA,
                             job=executado.para_dicionario())
    assert p["qa_visual"]["estado"] == "indeterminado"
    assert "NÃO reprova" in p["proxima_acao"]


def test_prontidao_mostra_aprovado_so_depois_do_humano():
    controle = _controle()
    job = controle.criar(_pedido())
    controle.executar(job.job_id, solicitante=DONO_A)
    aprovado = controle.aprovar(job.job_id, solicitante=DONO_A, revisor="t", nota="ok")
    p = app.montar_prontidao(handoff=HANDOFF_COMPLETO, broker_configurado=True,
                             persistencia=COM_PERSISTENCIA,
                             job=aprovado.para_dicionario())
    assert p["qa_visual"]["estado"] == "aprovado"
    assert p["qa_visual"]["artefato"]["sha256"] == "a" * 64


def test_prontidao_nunca_carrega_localizador_nem_id_bruto():
    controle = _controle()
    job = controle.criar(_pedido())
    executado = controle.executar(job.job_id, solicitante=DONO_A)
    p = app.montar_prontidao(handoff=HANDOFF_COMPLETO, broker_configurado=True,
                             persistencia=COM_PERSISTENCIA,
                             job=executado.para_dicionario())
    import json as _json
    texto = _json.dumps(p, ensure_ascii=False)
    assert "op://" not in texto and "user_id" not in texto and "localizador" not in texto


def test_todos_os_estados_de_qa_estao_declarados():
    for estado in app._ESTADO_DE_QA_POR_JOB.values():
        assert estado in app.ESTADOS_DE_QA
    assert set(app._ESTADO_DE_QA_POR_JOB) == set(dom.ESTADOS_DO_JOB)
