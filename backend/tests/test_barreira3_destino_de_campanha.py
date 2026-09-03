"""BARREIRA 3 — o destino da campanha, lido AO VIVO, em `/provar` e `/subir`.

Estes testes existem por causa de um buraco medido nesta worktree, não de uma
preocupação abstrata. Até 03/09/2026 as duas rotas do Hub de Tráfego montavam o
plano, cunhavam o selo e criavam a campanha sem NUNCA olhar a página de destino:
o `url_final` viajava como string dentro do payload, `_impressao_aprovavel` fazia
hash dessa string, e uma impressão idêntica em `/provar` e `/subir` não diz nada
sobre o que aquele endereço serve AGORA.

Pior: `volc_ads/pautador_ponte.montar_brief` deixa uma `url_final` colada à mão
DESARMAR os bloqueadores `SEM_LP`/`SEM_FUNIL` e VENCER a URL derivada do funil,
validada apenas por `startswith("https://")`. Como `/provar` é `exigir_usuario`
(não admin), um não-admin cunhava uma impressão aprovável para um endereço que o
VOLC nunca gerou nem publicou — pulando as barreiras 1 e 2 por construção.

O que cada bloco aqui prova:

* o portão consegue APROVAR (um portão que só sabe dizer não é um portão que a
  operação aprende a ignorar);
* destino inelegível não cunha selo em `/provar` e não chega ao mutate em
  `/subir` — e `/subir` REAVALIA ao vivo em vez de confiar no `/provar`;
* falha fechada: leitura indisponível, HTTP não-200, deriva, recibo ausente,
  vencido ou de política antiga, cadeia excessiva, salto cross-domain e cloaking
  REPROVAM;
* diferença só de dispositivo NÃO vira acusação de cloaking;
* o papel é do servidor: campo do cliente não relaxa nada;
* nenhum caminho bloqueado alcança `volc_ads.subir` — provado com SENTINELA.

⚠️ HERMÉTICOS. A fixture `_rede_bloqueada` derruba qualquer teste que tente abrir
socket, e a leitura pública é dublada em `app.publisher_quality.fetch`. Nenhuma
chamada real ao WordPress, ao Google Ads ou a qualquer host sai daqui.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import socket
import time
from typing import Any

import pytest
from fastapi import HTTPException

from app.landing_policy import (
    CHAVE_DO_RECIBO,
    POLICY_CONTRACT_VERSION,
    PapelDestino,
    impressao_canonica,
    versao_da_fonte,
)
from app.publisher_quality import fetch as pqf
from app.routers import trafego
from app.seguranca.identidade import Identidade
from app.trafego import canario

from test_trafego_canario import (  # noqa: E402  (fixtures herméticas já provadas)
    _instalar_portas_hermeticas,
    _linhas_da_rota,
    _payload_da_rota,
)
from test_trafego_ledger import LedgerDeTeste  # noqa: E402
from test_trafego_plano_persistido import RepoDePlanoDeTeste  # noqa: E402


URL = "https://portalmundomais.com.br/saque-anual/"

IDENTIDADE = Identidade(
    sub="operador-sub-1", email="tarcisio@agenciavolc.com.br",
    papel="ADMIN", origem="teste",
)


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    """Contraprova 26. Um teste de portão que abre socket prova o site, não o portão."""

    def recusar_rede(_socket, _address):
        pytest.fail("teste da barreira 3 tentou abrir uma conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


@pytest.fixture(autouse=True)
def _leituras_da_conta_desligadas(monkeypatch: pytest.MonkeyPatch):
    """As duas portas para o Google que `/provar` e `/subir` abrem por conta própria.

    ⚠️ Sem isto, `_prontidao_do_lancamento` desce até `volc_ads.gads.client.cliente`
    — que é `lru_cache` e, com um `google-ads.yaml` na máquina, REFRESCA o token
    antes de qualquer consulta. A fixture de rede acima derrubaria todo o arquivo
    por um motivo que não é o dele. `None`/exceção é o caminho honesto: é
    exatamente o que a rota produz quando a leitura não completa.
    """
    from app.trafego import contas as ct

    def _sem_metas(*_a, **_k):
        raise RuntimeError("leitura de metas desligada neste arquivo de teste")

    async def _sem_plano(*_a, **_k):
        return None

    monkeypatch.setattr(ct, "meta_de_conversao", _sem_metas)
    monkeypatch.setattr(trafego, "_plano_de_mensuracao", _sem_plano)


# ── a página que passa, e as suas variações ────────────────────────────────
#
# O corpo é longo porque `CONTEUDO_ORIGINAL_INSUFICIENTE` tem piso de palavras,
# e o rodapé carrega CNPJ, contato, privacidade, aviso de não-vínculo e
# divulgação de monetização — cada um deles é um bloqueio no papel estrito. Uma
# fixture "limpa" que não conseguisse ficar verde provaria só que ela envelheceu.

_RODAPE = """
<p>Sobre o nosso site: portal informativo independente.</p>
<p>Os conteudos aqui publicados sao de carater informativo e nao possuem vinculo,
parceria ou qualquer ligacao com orgaos publicos ou entidades governamentais.</p>
<p>O site e financiado por blocos de anuncios em parceria com o Google Adsense.</p>
<p>Projeto da Volc Negocios Digitais 42.724.548/0001-24.</p>
<a href="/sobre">Sobre</a> <a href="/contato">Contato</a>
<a href="/politica-de-privacidade">Politica de Privacidade</a> <a href="/termos">Termos</a>
"""

_CORPO = " ".join(
    [
        "O texto explica com calma as regras vigentes e como o leitor confere cada",
        "informacao no canal oficial, sem prometer resultado nenhum.",
    ]
    * 90
)


def _html(titulo: str = "Guia informativo", extra: str = "") -> str:
    return (
        f"<html><head><title>{titulo}</title></head><body>"
        f"<h1>{titulo}</h1><p>{_CORPO}</p>{extra}{_RODAPE}</body></html>"
    )


HTML_CONFORME = _html()


def _recibo(html: str = HTML_CONFORME, **mudancas: Any) -> dict[str, Any]:
    """O recibo de aprovação que a barreira 2 pendurou em `paginas_publicadas`.

    ⚠️ `observed_at_epoch` é relativo a AGORA, e não uma constante congelada: a
    janela de frescor é de 24 h e um carimbo fixo faria estes testes começarem a
    reprovar sozinhos no dia seguinte — por uma razão que não é a deles.
    """
    base = {
        "policy_contract_version": POLICY_CONTRACT_VERSION,
        "policy_source_version": versao_da_fonte(),
        "observed_at_epoch": time.time() - 60,
        "content_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "content_fingerprint": impressao_canonica(html),
        # ⚠️ `live`, e o escopo NÃO é detalhe de fixture.
        #
        # O recibo do portão 2 impressiona o ARTEFATO (o corpo que o motor
        # escreveu). A barreira 3 lê a página no ar — o mesmo corpo DENTRO do
        # tema do WordPress. Comparar entre escopos emitia `DERIVA_AO_VIVO` e
        # `RECIBO_DE_OUTRO_CONTEUDO` em 100% das páginas reais, e o portão nunca
        # ficava verde.
        #
        # Estas provas exercitam a DERIVA, e deriva só é mensurável contra uma
        # aprovação do mesmo escopo. Um recibo `live` é o que uma reauditoria ao
        # vivo produz. O caminho do recibo de artefato tem prova própria:
        # `test_recibo_do_artefato_nao_mede_deriva_e_reprova_por_ausencia`.
        "fingerprint_scope": "live",
        "paid_destination_ready": True,
    }
    base.update(mudancas)
    return base


def _leitura(html: str, *, status: int = 200, saltos: list[dict] | None = None,
             url: str = URL) -> dict[str, Any]:
    """A forma EXATA que `fetch_public_https_chain` devolve.

    Um dublê com outra forma provaria a rota errada — foi o que o dublê de
    `Recibo` com estado inexistente já custou a esta suíte.
    """
    return {
        "url": url,
        "final_url": (saltos[-1]["to"] if saltos else url),
        "status": status,
        "hops": list(saltos or []),
        "headers": {"content-type": "text/html; charset=utf-8"},
        "user_agent": "irrelevante-para-o-dublê",
        "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "bytes": len(html.encode("utf-8")),
        "html": html,
    }


def _instalar_leitura(monkeypatch: pytest.MonkeyPatch, *,
                      desktop: str = HTML_CONFORME,
                      movel: str | None = None,
                      rastreador: str | None = None,
                      status: int = 200,
                      saltos: list[dict] | None = None,
                      erro: Exception | None = None) -> list[str]:
    """Dubla as três leituras públicas e devolve o diário dos user-agents.

    O dublê escolhe o HTML pelo user-agent — é o único jeito de um teste
    exercitar cloaking sem servidor: cloaking É servir conteúdo diferente para
    quem se identifica como rastreador.
    """
    agentes: list[str] = []

    def dublê(url: str, *, user_agent: str = "", timeout: int = 20,
              max_bytes: int = 2_000_000) -> dict[str, Any]:
        agentes.append(user_agent)
        if erro is not None:
            raise erro
        baixo = user_agent.lower()
        if "bot" in baixo or "crawler" in baixo or "spider" in baixo:
            html = rastreador if rastreador is not None else desktop
        elif "mobile" in baixo or "android" in baixo:
            html = movel if movel is not None else desktop
        else:
            html = desktop
        return _leitura(html, status=status, saltos=saltos, url=url)

    monkeypatch.setattr(pqf, "fetch_public_https_chain", dublê)
    return agentes


def _instalar_linhas(monkeypatch: pytest.MonkeyPatch, *,
                     recibo: dict[str, Any] | None = None,
                     url_publicada: str = URL,
                     publicadas: list[dict] | None = None) -> None:
    """Repõe `pp.carregar` com um run cujo `paginas_publicadas` este teste escolhe.

    ⚠️ Depois de `_instalar_portas_hermeticas`, que também troca `pp.carregar`.
    O recibo mora DENTRO do dict da página publicada — é o contrato de
    `landing_policy.registro`, e é por isso que não há tabela nova.
    """
    from volc_ads import pautador_ponte as pp

    base = _linhas_da_rota(pp)
    if publicadas is None:
        pagina = dict((base.run or {})["paginas_publicadas"][0])
        pagina["url_wp"] = url_publicada
        # ⚠️ `pop` e não "não adiciona": a fixture hermética já traz o recibo do
        # caminho feliz, e `recibo=None` aqui significa "a casa nunca aprovou
        # esta URL". Herdar o recibo alheio faria este arquivo provar o oposto
        # do que ele diz provar.
        pagina.pop(CHAVE_DO_RECIBO, None)
        if recibo is not None:
            pagina[CHAVE_DO_RECIBO] = recibo
        publicadas = [pagina]
    run = {**(base.run or {}), "paginas_publicadas": publicadas}
    linhas = dataclasses.replace(base, run=run)

    def carregar(opportunity_id: int, *, run_id: int | None = None):
        return linhas

    monkeypatch.setattr(pp, "carregar", carregar)


def _provar(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    corpo = trafego.ProvarEntrada(**(payload or _payload_da_rota()))
    return asyncio.run(trafego.provar(corpo, identidade=IDENTIDADE))


def _cenario_conforme(monkeypatch: pytest.MonkeyPatch, **leitura: Any) -> list[str]:
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo())
    return _instalar_leitura(monkeypatch, **leitura)


# ── o portão consegue aprovar ──────────────────────────────────────────────


def test_destino_conforme_deixa_o_selo_sair(monkeypatch: pytest.MonkeyPatch):
    """A linha de base. Sem ela, todo o resto prova um portão quebrado.

    Um portão que nunca aprova é indistinguível de um portão com defeito, e a
    operação aprende a contorná-lo — que é a pior falha possível num portão.
    """
    agentes = _cenario_conforme(monkeypatch)
    d = _provar()

    assert d["destino"]["elegivel"] is True, d["destino"]["motivos"]
    assert d["autorizacao"]["plano_impressao"], "o selo não saiu para um destino conforme"
    assert d["preparo"]["selo"] is not None
    # Três leituras, e uma delas rotulada como rastreador: sem o par
    # rastreador/usuário a verificação de cloaking sai `unavailable` e reprova.
    assert len(agentes) == 3, agentes
    assert any("googlebot" in a.lower() for a in agentes), agentes


def test_o_papel_avaliado_e_sempre_o_do_servidor(monkeypatch: pytest.MonkeyPatch):
    """Contraprova 24: campo do cliente não relaxa o papel nem o rigor.

    `elegibilidade_de_destino_de_campanha` FORÇA `paid_destination`; a rota não
    tem parâmetro de papel para o cliente preencher. O payload abaixo tenta os
    três nomes plausíveis e nenhum deles chega ao portão — `ProvarEntrada` os
    ignora, e mesmo que chegassem o portão não os leria.
    """
    _cenario_conforme(monkeypatch)
    payload = _payload_da_rota(
        papel="organic_article",
        role="ORGANIC_ARTICLE",
        papel_declarado="editorial_solution",
    )
    corpo = trafego.ProvarEntrada(**payload)
    for campo in ("papel", "role", "papel_declarado"):
        assert not hasattr(corpo, campo), f"o envelope aceitou {campo!r} do cliente"

    d = asyncio.run(trafego.provar(corpo, identidade=IDENTIDADE))
    assert d["destino"]["papel"] == PapelDestino.PAID_DESTINATION.value
    assert d["destino"]["ponto"] == "campaign_destination_eligibility"


# ── falha fechada, um motivo por vez ───────────────────────────────────────


def test_sem_recibo_de_aprovacao_o_destino_nao_e_elegivel(monkeypatch: pytest.MonkeyPatch):
    """Contraprova 22, no caso mais comum: ninguém aprovou aquela URL.

    `recibo_da_url` devolve `None`, `varrer_recibo` emite
    `RECIBO_DE_APROVACAO_AUSENTE` e o papel estrito transforma isso em bloqueio.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=None)
    _instalar_leitura(monkeypatch)

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert "RECIBO_DE_APROVACAO_AUSENTE" in d["destino"]["bloqueios"]
    assert d["autorizacao"]["plano_impressao"] is None, "o selo saiu para destino inelegível"
    assert d["preparo"]["selo"] is None
    assert d["preparo"]["selo_retido"]["motivos"], "o selo foi retido sem dizer por quê"


def test_url_manual_do_cliente_nao_desarma_nada(monkeypatch: pytest.MonkeyPatch):
    """O BURACO DA URL MANUAL, fechado no ponto em que ele tinha efeito.

    `montar_brief` continua deixando uma `url_final` colada à mão desarmar
    `SEM_LP`/`SEM_FUNIL` e vencer a URL derivada do funil — essa parte é do
    Pautador. O que muda é que a impressão aprovável deixou de ser cunhada por
    isso: a URL manual é avaliada AO VIVO como destino pago, o recibo de
    aprovação daquela URL não existe em `paginas_publicadas`, e faltar reprova.
    """
    _instalar_portas_hermeticas(monkeypatch)
    # O funil publicou UMA página, com recibo. O cliente aponta para outra.
    _instalar_linhas(monkeypatch, recibo=_recibo())
    _instalar_leitura(monkeypatch)

    manual = "https://portalmundomais.com.br/promo-colada-a-mao/"
    d = _provar(_payload_da_rota(url_final=manual))

    assert d["destino"]["url"] == manual, "o portão avaliou a URL derivada, não a efetiva"
    assert d["destino"]["elegivel"] is False
    assert "RECIBO_DE_APROVACAO_AUSENTE" in d["destino"]["bloqueios"]
    assert d["autorizacao"]["plano_impressao"] is None


def test_alteracao_depois_da_aprovacao_invalida_a_elegibilidade(
    monkeypatch: pytest.MonkeyPatch,
):
    """Contraprova 15. O recibo descreve o que foi aprovado; o ar mudou depois."""
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo(HTML_CONFORME))
    _instalar_leitura(
        monkeypatch,
        desktop=_html(titulo="Saque liberado agora", extra="<h2>Clique e receba</h2>"),
    )

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert "DERIVA_AO_VIVO" in d["destino"]["bloqueios"], d["destino"]["bloqueios"]
    assert d["autorizacao"]["plano_impressao"] is None


def test_deriva_e_medida_pela_impressao_canonica_e_nao_pelo_byte(
    monkeypatch: pytest.MonkeyPatch,
):
    """O simétrico da prova acima, e o falso positivo que ela evita.

    Um comentário HTML a mais muda o byte e não muda nada que o leitor veja.
    Reprovar por deriva a cada rotação de token faria a operação desligar o
    portão — e portão desligado não protege nada.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo(HTML_CONFORME))
    servido = HTML_CONFORME.replace("</body>", "<!-- nonce=8f31a2 --></body>")
    assert servido != HTML_CONFORME
    _instalar_leitura(monkeypatch, desktop=servido)

    d = _provar()
    assert "DERIVA_AO_VIVO" not in d["destino"]["bloqueios"], d["destino"]["bloqueios"]
    assert d["destino"]["elegivel"] is True, d["destino"]["motivos"]


def test_recibo_de_politica_antiga_nao_e_reusado_em_silencio(
    monkeypatch: pytest.MonkeyPatch,
):
    """Contraprova 16. Recibo de outra versão não prova nada sobre a regra vigente."""
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(
        monkeypatch,
        recibo=_recibo(policy_contract_version="paid_destination_policy_spine.v1"),
    )
    _instalar_leitura(monkeypatch)

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert "RECIBO_DE_POLITICA_DESATUALIZADO" in d["destino"]["bloqueios"]


def test_recibo_vencido_nao_vale_como_aprovacao_de_hoje(
    monkeypatch: pytest.MonkeyPatch,
):
    """'Estava apto' não é 'está apto'. A janela é de 24 h e ela não é opcional."""
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(
        monkeypatch,
        recibo=_recibo(observed_at_epoch=time.time() - 8 * 24 * 3600),
    )
    _instalar_leitura(monkeypatch)

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert "RECIBO_DE_APROVACAO_VENCIDO" in d["destino"]["bloqueios"]


def test_recibo_nao_escolhe_a_propria_janela_de_frescor(
    monkeypatch: pytest.MonkeyPatch,
):
    """Um recibo que declarasse a própria validade seria evidência se autoabsolvendo.

    A janela é a do contrato (`JANELA_DE_FRESCOR_PADRAO_S`), e o campo
    `freshness_window_s` que viaja dentro do recibo é ignorado pelo portão.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(
        monkeypatch,
        recibo=_recibo(
            observed_at_epoch=time.time() - 8 * 24 * 3600,
            freshness_window_s=365 * 24 * 3600,
        ),
    )
    _instalar_leitura(monkeypatch)

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert "RECIBO_DE_APROVACAO_VENCIDO" in d["destino"]["bloqueios"]


def test_recibo_que_declara_recusa_nao_vale_como_aprovacao(
    monkeypatch: pytest.MonkeyPatch,
):
    """O recibo passa nos três exames do contrato e ainda assim não aprova.

    `varrer_recibo` pergunta se o recibo EXISTE, se é desta política e se está
    fresco — não se ele APROVA. Um recibo de recusa satisfaz os três. A pergunta
    que falta é feita na rota (`_recusas_do_recibo`), e ela só sabe reprovar.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo(paid_destination_ready=False))
    _instalar_leitura(monkeypatch)

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert d["destino"]["recibo_de_aprovacao"]["presente"] is True
    assert any("recusa" in m for m in d["destino"]["motivos"]), d["destino"]["motivos"]
    assert d["autorizacao"]["plano_impressao"] is None


def test_leitura_ao_vivo_indisponivel_falha_fechada(monkeypatch: pytest.MonkeyPatch):
    """Contraprova 17. 'Não consegui olhar' nunca é 'está limpo'."""
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo())
    _instalar_leitura(monkeypatch, erro=TimeoutError("a leitura do destino estourou"))

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert d["destino"]["leitura_ao_vivo"]["concluida"] is False
    assert d["destino"]["desconhecidos"], "leitura ausente virou ausência de achado"
    assert d["autorizacao"]["plano_impressao"] is None


def test_destino_que_nao_serve_a_pagina_nao_e_destino(monkeypatch: pytest.MonkeyPatch):
    """HTTP 404/5xx é 'destination that doesn't work', e o corpo do erro é outra página.

    Avaliar o corpo de um 404 diria coisas verdadeiras sobre a página errada.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo())
    _instalar_leitura(monkeypatch, status=503)

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert d["destino"]["leitura_ao_vivo"]["concluida"] is False
    assert "503" in d["destino"]["leitura_ao_vivo"]["detalhe"]


def test_redirect_cross_domain_bloqueia(monkeypatch: pytest.MonkeyPatch):
    """Contraprova 18. O clique comprado sai do domínio que o anúncio declara."""
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo())
    _instalar_leitura(monkeypatch, saltos=[
        {"from": URL, "status": 302, "to": "https://outro-dominio.example/oferta"},
    ])

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert "REDIRECIONAMENTO_CROSS_DOMAIN" in d["destino"]["bloqueios"]


def test_cadeia_de_redirecionamento_excessiva_bloqueia(monkeypatch: pytest.MonkeyPatch):
    """Contraprova 19. Um salto é rotina de servidor; uma cadeia é o assunto."""
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo())
    _instalar_leitura(monkeypatch, saltos=[
        {"from": URL, "status": 301, "to": "https://portalmundomais.com.br/a/"},
        {"from": "https://portalmundomais.com.br/a/", "status": 301,
         "to": "https://portalmundomais.com.br/b/"},
        {"from": "https://portalmundomais.com.br/b/", "status": 301,
         "to": "https://portalmundomais.com.br/saque-anual/"},
    ])

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert "CADEIA_DE_REDIRECIONAMENTO_EXCESSIVA" in d["destino"]["bloqueios"]


def test_elegivel_e_paid_destination_ready_e_nao_ausencia_de_bloqueio():
    """A doutrina inteira em um predicado, exercitada no caso que a separa.

    ⚠️ `if not avaliacao.bloqueios` e `if avaliacao.paid_destination_ready` só
    divergem quando existe DESCONHECIDO sem bloqueio — verificação exigida que
    não pôde ser concluída. É exatamente o estado de uma varredura que explodiu,
    e foi por aí que o handoff anterior deixaria publicar uma página que ninguém
    conseguiu ler. Um teste que só usasse páginas com bloqueio passaria com as
    duas implementações e não provaria nada.
    """

    class _AvaliacaoComDesconhecido:
        paid_destination_ready = False
        bloqueios: list = []
        riscos: list = []
        desconhecidos = [{"verificacao": "live_drift", "status": "failed",
                          "motivo": "a varredura levantou exceção"}]
        motivos = ["desconhecido live_drift: a varredura levantou exceção"]
        veredito = type("V", (), {"value": "indeterminate"})()
        papel = type("P", (), {"value": "paid_destination"})()
        ponto = type("Q", (), {"value": "campaign_destination_eligibility"})()
        verificacoes: list = []

    destino = trafego.DestinoDeCampanha(url=URL, avaliacao=_AvaliacaoComDesconhecido())
    assert destino.avaliacao.bloqueios == []
    assert destino.elegivel is False
    assert destino.para_json()["desconhecidos"], "o desconhecido sumiu da resposta"


def test_conteudo_diferente_para_o_rastreador_e_sinalizado(
    monkeypatch: pytest.MonkeyPatch,
):
    """Contraprova 20. É a assinatura de cloaking descrita por circumventing systems."""
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo())
    _instalar_leitura(
        monkeypatch,
        rastreador=_html(titulo="Pagina para o revisor", extra="<p>outro conteudo</p>"),
    )

    d = _provar()
    assert d["destino"]["elegivel"] is False
    assert "DIVERGENCIA_RASTREADOR_USUARIO" in d["destino"]["bloqueios"]


def test_diferenca_so_de_dispositivo_nao_e_falso_positivo(
    monkeypatch: pytest.MonkeyPatch,
):
    """Contraprova 21, e a razão de a leitura ser TRIPLA em vez de dupla.

    Desktop e mobile diferem por layout — foi assim que `/r/fgts-saque-aniversario/`
    quase virou uma acusação de cloaking contra evidência que dizia o contrário
    (o Googlebot recebeu HTML idêntico ao do desktop). Com UMA variante humana
    só, qualquer diferença viraria acusação; com duas, "desktop ≠ mobile" é
    observação de dispositivo e o rastreador continua sendo comparado às duas.
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo())
    _instalar_leitura(
        monkeypatch,
        movel=_html(extra="<p>Versao compacta para telas pequenas.</p>"),
    )

    d = _provar()
    assert "DIVERGENCIA_RASTREADOR_USUARIO" not in d["destino"]["bloqueios"], (
        d["destino"]["bloqueios"]
    )
    assert d["destino"]["elegivel"] is True, d["destino"]["motivos"]


# ── /subir: reavaliação ao vivo e sentinela no mutate ──────────────────────


def _subir_proibido(*_a, **_k):
    """SENTINELA. Contraprova 25: nenhum caminho bloqueado alcança o mutate."""
    pytest.fail("um caminho bloqueado alcançou volc_ads.subir — o mutate seria real")


def _preparar_subida(monkeypatch: pytest.MonkeyPatch, *, ledger: LedgerDeTeste,
                     leitura_remota_proibida: bool = False):
    """Tudo o que `/subir` exige antes do mutate, dublado e sem rede.

    `leitura_remota_proibida` põe SENTINELA também na idempotência remota: o
    portão do destino vem antes dela, e uma recusa que já tivesse consultado a
    conta teria gasto quota para nada.
    """
    from volc_ads import subir as sb

    def _consulta_remota_proibida(**kw):
        pytest.fail(f"a consulta remota ao Google veio antes do portão do destino: {kw}")

    remoto = _consulta_remota_proibida if leitura_remota_proibida else (lambda **_: ())

    monkeypatch.setattr(trafego, "_ledger", lambda: ledger)
    monkeypatch.setattr(trafego, "_repositorio_de_plano",
                        lambda: RepoDePlanoDeTeste(diario=[]))
    monkeypatch.setattr(canario, "campanhas_com_marca", remoto)
    monkeypatch.setattr(canario, "campanhas_com_destino", remoto)
    monkeypatch.setattr(sb, "subir", _subir_proibido)

    async def _sem_registro_legado(*_a, **_k):
        return ""

    monkeypatch.setattr(trafego, "_registrar_campanha", _sem_registro_legado)


def _corpo_de_subida(impressao: str) -> trafego.SubirEntrada:
    return trafego.SubirEntrada(**{
        **_payload_da_rota(),
        "motivo": "canário pausado com aprovação humana",
        "plano_impressao": impressao,
        "confirmar_criacao_pausada": True,
    })


def test_subir_revalida_ao_vivo_e_nao_confia_no_provar(monkeypatch: pytest.MonkeyPatch):
    """Contraprova 23 — a mais importante deste arquivo.

    O selo é do PAYLOAD: `_impressao_aprovavel` faz hash dele, e `url_final` está
    lá como string. Impressão idêntica em `/provar` e `/subir` prova que o pedido
    não mudou; ela não prova nada sobre o que o destino serve agora. Aqui o
    `/provar` acontece com a página conforme, o selo é legítimo, e entre as duas
    requisições o destino passa a servir outra coisa.
    """
    _cenario_conforme(monkeypatch)
    prova = _provar()
    impressao = prova["autorizacao"]["plano_impressao"]
    assert impressao, "a prova precisava passar para o resto do teste ter sentido"

    # A MESMA impressão, o MESMO payload — e o destino trocado depois da prova.
    _instalar_leitura(
        monkeypatch,
        desktop=_html(titulo="Saque liberado pelo governo", extra="<h2>Receba hoje</h2>"),
    )
    ledger = LedgerDeTeste(diario=[])
    _preparar_subida(monkeypatch, ledger=ledger, leitura_remota_proibida=True)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo_de_subida(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    detalhe = erro.value.detail
    assert detalhe["estado"] == "destino_nao_elegivel"
    assert "DERIVA_AO_VIVO" in detalhe["destino"]["bloqueios"]
    # ⚠️ O ledger não abriu. Um recibo `em_voo` para uma chamada que nunca sai
    # deixa a camada 4 bloqueando o item até alguém reconciliar uma tentativa
    # que não existiu.
    assert ledger.diario == [], ledger.diario


def test_subir_recusa_antes_de_abrir_o_ledger_quando_a_leitura_falha(
    monkeypatch: pytest.MonkeyPatch,
):
    """Contraprova 17 no caminho de ESCRITA: indisponível reprova, não libera."""
    _cenario_conforme(monkeypatch)
    impressao = _provar()["autorizacao"]["plano_impressao"]

    _instalar_leitura(monkeypatch, erro=OSError("DNS não resolveu"))
    ledger = LedgerDeTeste(diario=[])
    _preparar_subida(monkeypatch, ledger=ledger)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo_de_subida(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    assert erro.value.detail["destino"]["leitura_ao_vivo"]["concluida"] is False
    assert ledger.diario == []


@pytest.mark.parametrize(
    ("nome", "leitura", "recibo"),
    [
        ("sem recibo", {}, None),
        ("recibo de política antiga", {},
         {"policy_contract_version": "paid_destination_policy_spine.v1"}),
        ("cloaking", {"rastreador": _html(titulo="Outra pagina")}, {}),
        ("cross-domain", {"saltos": [{"from": URL, "status": 302,
                                      "to": "https://outro.example/x"}]}, {}),
        ("leitura indisponível", {"erro": TimeoutError("estourou")}, {}),
        ("destino fora do ar", {"status": 500}, {}),
    ],
)
def test_nenhum_bloqueio_alcanca_o_mutate(monkeypatch: pytest.MonkeyPatch,
                                          nome: str, leitura: dict, recibo: dict | None):
    """Contraprova 25, uma linha por motivo de recusa.

    A sentinela é o coração deste teste: `volc_ads.subir` chama `pytest.fail` se
    for invocado. O status HTTP sozinho não provaria nada — uma rota pode
    devolver 409 depois de já ter criado a campanha.
    """
    _cenario_conforme(monkeypatch)
    impressao = _provar()["autorizacao"]["plano_impressao"]

    _instalar_linhas(monkeypatch,
                     recibo=(None if recibo is None else _recibo(**recibo)))
    _instalar_leitura(monkeypatch, **leitura)
    ledger = LedgerDeTeste(diario=[])
    _preparar_subida(monkeypatch, ledger=ledger)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo_de_subida(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 409, nome
    assert erro.value.detail["estado"] == "destino_nao_elegivel", nome
    assert ledger.diario == [], nome


def test_a_recusa_de_subir_nao_vaza_o_html_do_destino(monkeypatch: pytest.MonkeyPatch):
    """A evidência é estrutural. Um recibo que carrega a página vira coletor.

    O portão lê HTML público de terceiros; devolvê-lo dentro da resposta faria a
    API do VOLC republicar conteúdo que ela apenas observou.
    """
    _cenario_conforme(monkeypatch)
    impressao = _provar()["autorizacao"]["plano_impressao"]

    _instalar_linhas(monkeypatch, recibo=None)
    _instalar_leitura(monkeypatch)
    _preparar_subida(monkeypatch, ledger=LedgerDeTeste(diario=[]))

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo_de_subida(impressao), identidade=IDENTIDADE))

    corpo = str(erro.value.detail)
    assert _CORPO[:60] not in corpo
    assert "<html" not in corpo



def test_recibo_do_artefato_nao_mede_deriva_e_reprova_pelo_motivo_certo(
    monkeypatch: pytest.MonkeyPatch,
):
    """⚠️ O ACHADO QUE A REVISÃO DE OLHOS FRESCOS MEDIU PONTA A PONTA.

    O único produtor de recibo em produção é o motor, e ele carimba a impressão
    do ARTEFATO — o corpo que ele escreveu. A barreira 3 usava esse valor como
    `impressao_aprovada` e o comparava com a leitura ao vivo: dois documentos
    diferentes por construção, porque o tema do WordPress envolve o artefato.

    Efeito medido: `DERIVA_AO_VIVO` e `RECIBO_DE_OUTRO_CONTEUDO` em 100% das
    páginas reais. `/provar` retinha o selo sempre, `/subir` devolvia 409
    sempre, e nenhuma página jamais viraria destino de campanha. Um portão que
    nunca aprova é indistinguível de um portão quebrado.

    A correção não é isentar. Sem aprovação do MESMO escopo a deriva é
    inobservável, e `live_drift` está em `NAO_APLICAVEL_E_DESCONHECIDO_EM` — a
    ausência REPROVA. O destino continua inelegível; muda o MOTIVO, que passa a
    ser verdadeiro e acionável ("ninguém reauditou esta página ao vivo") em vez
    de falso ("o conteúdo mudou").
    """
    _instalar_portas_hermeticas(monkeypatch)
    _instalar_linhas(monkeypatch, recibo=_recibo(fingerprint_scope="artifact"))
    _instalar_leitura(monkeypatch)
    d = _provar()

    assert d["destino"]["elegivel"] is False
    motivos = " ".join(d["destino"]["motivos"])
    assert "DERIVA_AO_VIVO" not in motivos, motivos
    assert "RECIBO_DE_OUTRO_CONTEUDO" not in motivos, motivos
    assert "live_drift" in motivos, motivos
