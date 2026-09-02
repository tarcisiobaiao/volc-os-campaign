"""O adaptador REAL contra um Postiz de mentira que fala HTTP de verdade.

Nenhum teste aqui substitui o adaptador por um dublê: o que roda e
`AdaptadorPostiz`, com o mesmo codigo de montagem de corpo, traducao de estado e
tratamento de erro que ira para producao. So a rede e trocada.

O que estes testes existem para impedir:

- que um timeout vire "falhou" e convide o operador a reenviar (post duplicado);
- que um 200 sem `postId` vire recibo vazio;
- que um 500 DEPOIS de o post ter sido gravado vire falha limpa;
- que o corpo de um 400 que ecoa o header `Authorization` chegue a uma coluna;
- que alguem invente `GET /posts/{id}`, que a API oficial nao tem.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.publicacao_organica import dominio as dom
from app.publicacao_organica.adaptadores import fake as fk
from app.publicacao_organica.adaptadores.postiz import AdaptadorPostiz, validar_base_url
from app.publicacao_organica.portas import (
    CAPACIDADES_NAO_EXERCITADAS,
    DesfechoIncerto,
    FalhaDoControlPlane,
    PortaDePublicacao,
    SolicitacaoExterna,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def plano() -> fk.ControlPlaneFake:
    return fk.ControlPlaneFake()


@pytest.fixture()
def adaptador(plano: fk.ControlPlaneFake) -> AdaptadorPostiz:
    return AdaptadorPostiz(
        base_url="http://control-plane-de-prova.local",
        token=plano.token,
        permitir_rede_interna=True,
        cliente=plano.cliente(),
    )


def _pedido(**troca) -> SolicitacaoExterna:
    base = dict(
        referencia_do_canal="integ-piloto-0001",
        modo="draft",
        texto="Primeira peca organica.",
        instante_utc=None,
        imagens=(),
        plataforma="facebook",
    )
    base.update(troca)
    return SolicitacaoExterna(**base)


# ---------------------------------------------------------------------------
# O contrato
# ---------------------------------------------------------------------------


def test_o_adaptador_real_satisfaz_a_porta(adaptador: AdaptadorPostiz) -> None:
    assert isinstance(adaptador, PortaDePublicacao)


def test_as_capacidades_nao_exercitadas_estao_declaradas() -> None:
    # ⚠️ "nao implementamos" nao pode virar "nao existe". Cada entrada cita o
    # endpoint oficial e a data da consulta.
    assert "promover_rascunho_para_agendado" in CAPACIDADES_NAO_EXERCITADAS
    for texto in CAPACIDADES_NAO_EXERCITADAS.values():
        assert "02/09/2026" in texto or "/" in texto


async def test_nao_existe_busca_por_id_e_a_consulta_usa_a_janela(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    recibo = await adaptador.criar_rascunho(_pedido())
    plano.chamadas.clear()
    await adaptador.consultar(recibo.referencia_externa)

    caminhos = [c[1] for c in plano.chamadas]
    # A API oficial nao documenta `GET /posts/{id}`. Se alguem "otimizar" para
    # isso, producao devolve 404 e o diagnostico aponta para o lugar errado.
    assert all(not c.startswith("/public/v1/posts/") for c in caminhos), caminhos
    assert "/public/v1/posts" in caminhos


# ---------------------------------------------------------------------------
# Caminho feliz
# ---------------------------------------------------------------------------


async def test_rascunho_agendamento_e_agora_produzem_recibo_com_referencia(
    adaptador: AdaptadorPostiz,
) -> None:
    rascunho = await adaptador.criar_rascunho(_pedido())
    assert rascunho.referencia_externa
    assert rascunho.estado_externo == "DRAFT"

    agendado = await adaptador.agendar(_pedido(modo="schedule", instante_utc="2099-07-15T12:30:00Z"))
    assert agendado.estado_externo == "QUEUE"

    agora = await adaptador.publicar_agora(_pedido(modo="now"))
    assert agora.estado_externo == "QUEUE"
    # ⚠️ `now` NAO devolve PUBLISHED. O Postiz aceitou o pedido e enfileirou; o
    # conteudo estar no ar e outra coisa, e so a reconciliacao sabe.
    assert agora.estado_externo != "PUBLISHED"


async def test_o_corpo_enviado_respeita_o_schema_oficial(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    # O fake recusa 400 quando falta `date`, `shortLink` ou `tags` — exatamente
    # os campos que a doc marca como obrigatorios. Passar aqui prova que o corpo
    # montado casa com o contrato publicado.
    await adaptador.agendar(_pedido(modo="schedule", instante_utc="2099-07-15T12:30:00Z"))
    assert ("POST", "/public/v1/posts") in plano.chamadas


async def test_agendar_sem_instante_e_recusado_antes_da_rede(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    with pytest.raises(FalhaDoControlPlane):
        await adaptador.agendar(_pedido(modo="schedule", instante_utc=None))
    assert plano.chamadas == []


async def test_reconciliacao_le_estado_e_url_quando_o_post_e_publicado(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    recibo = await adaptador.agendar(_pedido(modo="schedule", instante_utc="2099-07-15T12:30:00Z"))
    observado = await adaptador.consultar(recibo.referencia_externa)
    assert observado is not None and observado.estado_externo == "QUEUE"
    assert observado.url_publicada is None

    plano.publicar_de_verdade(recibo.referencia_externa,
                              "https://www.facebook.com/piloto/posts/0001")
    observado = await adaptador.consultar(recibo.referencia_externa)
    assert observado is not None
    assert observado.estado_externo == "PUBLISHED"
    assert observado.url_publicada == "https://www.facebook.com/piloto/posts/0001"
    assert observado.publicado_em


async def test_consultar_post_que_nao_existe_devolve_none_e_nao_levanta(
    adaptador: AdaptadorPostiz,
) -> None:
    # ⚠️ NAO ENCONTRAR NAO REPROVA. Devolver None deixa quem chamou manter o
    # estado; levantar faria a reconciliacao parecer indisponivel.
    assert await adaptador.consultar("post-que-nunca-existiu") is None


async def test_estado_externo_desconhecido_nao_vira_published(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    recibo = await adaptador.criar_rascunho(_pedido())
    plano.posts[recibo.referencia_externa].state = "SOMETHING_NEW"
    observado = await adaptador.consultar(recibo.referencia_externa)
    assert observado is not None
    assert observado.estado_externo == "DESCONHECIDO"


# ---------------------------------------------------------------------------
# Contraprova G — timeout e 5xx NAO viram sucesso nem falha
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("injecao", ["timeout", "erro_de_rede", "500_apos_gravar", "corpo_ilegivel", "sem_post_id"])
async def test_desfecho_incerto_nunca_vira_sucesso_nem_falha(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake, injecao: str
) -> None:
    plano.falhar_com(injecao)  # type: ignore[arg-type]
    with pytest.raises(DesfechoIncerto):
        await adaptador.criar_rascunho(_pedido())


async def test_500_apos_gravar_deixa_o_post_existindo_no_control_plane(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    # Este e o cenario que torna `indeterminado` necessario: o conteudo EXISTE
    # la e o chamador nao sabe. Se o adaptador chamasse isso de falha, um retry
    # criaria o segundo post.
    plano.falhar_com("500_apos_gravar")
    with pytest.raises(DesfechoIncerto):
        await adaptador.criar_rascunho(_pedido())
    assert len(plano.posts) == 1


@pytest.mark.parametrize("injecao,permanente", [("401", True), ("400", True), ("429", False)])
async def test_recusa_conhecida_e_falha_e_nao_incerteza(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake, injecao: str, permanente: bool
) -> None:
    plano.falhar_com(injecao)  # type: ignore[arg-type]
    with pytest.raises(FalhaDoControlPlane) as erro:
        await adaptador.criar_rascunho(_pedido())
    assert erro.value.permanente is permanente


# ---------------------------------------------------------------------------
# Contraprova H — o erro externo nao carrega o token
# ---------------------------------------------------------------------------


async def test_o_400_que_ecoa_o_token_nao_vaza_pelo_erro(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    # O fake devolve `{"echo": {"Authorization": "<token>"}}`, que e o que
    # gateways prestativos fazem de verdade.
    plano.falhar_com("400")
    with pytest.raises(FalhaDoControlPlane) as erro:
        await adaptador.criar_rascunho(_pedido())
    texto = str(erro.value)
    assert plano.token not in texto
    assert "[redigido]" in texto or "Authorization" not in texto


async def test_recibo_com_material_de_credencial_e_recusado_antes_de_virar_recibo(
    plano: fk.ControlPlaneFake,
) -> None:
    # Um control plane comprometido (ou um proxy) que devolvesse `access_token`
    # no corpo NAO pode ter isso gravado como prova de publicacao.
    class PlanoQueVaza(fk.ControlPlaneFake):
        def _criar(self, requisicao: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[
                {"postId": "post-9999", "integration": "integ-piloto-0001",
                 # Montado em partes: ver a nota em test_..._dominio.py.
                 "debug": {"access_token": "xox" + "b-0123456789abcdefghij"}},
            ])

    vazando = PlanoQueVaza()
    adaptador = AdaptadorPostiz(
        base_url="http://control-plane-de-prova.local", token=vazando.token,
        permitir_rede_interna=True, cliente=vazando.cliente())
    with pytest.raises(dom.PedidoRecusado):
        await adaptador.criar_rascunho(_pedido())


async def test_token_errado_e_401_e_nao_sucesso_silencioso(plano: fk.ControlPlaneFake) -> None:
    adaptador = AdaptadorPostiz(
        base_url="http://control-plane-de-prova.local", token="token-errado-de-prova",
        permitir_rede_interna=True, cliente=plano.cliente())
    with pytest.raises(FalhaDoControlPlane) as erro:
        await adaptador.criar_rascunho(_pedido())
    assert erro.value.status == 401


# ---------------------------------------------------------------------------
# Egresso / SSRF
# ---------------------------------------------------------------------------


def test_adaptador_sem_token_nao_nasce() -> None:
    # Fail-closed. Um adaptador que aceitasse token vazio faria toda chamada
    # voltar 401 e o diagnostico apontaria para o Postiz, nao para a config.
    with pytest.raises(FalhaDoControlPlane):
        AdaptadorPostiz(base_url="https://postiz.exemplo.com", token="")


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "gopher://exemplo.com",
    "ftp://exemplo.com",
])
def test_esquema_fora_de_http_e_recusado(url: str) -> None:
    with pytest.raises(FalhaDoControlPlane):
        validar_base_url(url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:4007",
    "http://localhost:4007",
    "http://169.254.169.254",
    "http://10.0.0.5:4007",
])
def test_rede_interna_sem_sim_explicito_e_recusada(url: str) -> None:
    # ⚠️ 169.254.169.254 e o endpoint de metadados das nuvens. Uma base_url
    # trocada por engano entregaria o token — e a credencial da instancia junto.
    with pytest.raises(FalhaDoControlPlane):
        validar_base_url(url, permitir_rede_interna=False)


def test_rede_interna_com_sim_explicito_e_aceita() -> None:
    # O caso NORMAL do self-hosted. O sim e por configuracao, nunca por padrao.
    assert validar_base_url("http://postiz:5000", permitir_rede_interna=True) == "http://postiz:5000"


def test_https_publico_nao_precisa_do_sim() -> None:
    assert validar_base_url("https://api.postiz.com").endswith("api.postiz.com")


# ---------------------------------------------------------------------------
# Prontidao — proxy declarado, nao health inventado
# ---------------------------------------------------------------------------


async def test_prontidao_diz_que_e_proxy(adaptador: AdaptadorPostiz) -> None:
    p = await adaptador.prontidao()
    assert p.pronto is True
    assert p.fonte == "proxy:/integrations"
    # A honestidade tem de estar na RESPOSTA, e nao so num comentario.
    assert "nao ha endpoint de health oficial" in p.detalhe
    assert p.canais_visiveis == 2


async def test_prontidao_falha_sem_levantar(plano: fk.ControlPlaneFake) -> None:
    adaptador = AdaptadorPostiz(
        base_url="http://control-plane-de-prova.local", token="errado-de-proposito",
        permitir_rede_interna=True, cliente=plano.cliente())
    p = await adaptador.prontidao()
    assert p.pronto is False
    assert "errado-de-proposito" not in p.detalhe


async def test_canal_desativado_aparece_na_listagem(adaptador: AdaptadorPostiz) -> None:
    # ⚠️ Esconder o canal desativado tornaria impossivel explicar por que um
    # destino ficou inapto. Ele aparece, marcado.
    canais = await adaptador.listar_canais()
    assert any(c.desativado for c in canais)
    assert {c.plataforma for c in canais} == {"facebook", "instagram"}


# ---------------------------------------------------------------------------
# Cancelamento
# ---------------------------------------------------------------------------


async def test_cancelar_remove_do_control_plane(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    recibo = await adaptador.criar_rascunho(_pedido())
    assert await adaptador.cancelar(recibo.referencia_externa) is True
    assert recibo.referencia_externa not in plano.posts


async def test_cancelar_post_inexistente_e_falha_e_nao_sucesso(
    adaptador: AdaptadorPostiz,
) -> None:
    with pytest.raises(FalhaDoControlPlane):
        await adaptador.cancelar("post-que-nunca-existiu")


# ---------------------------------------------------------------------------
# UMA chamada por despacho
# ---------------------------------------------------------------------------


async def test_um_despacho_faz_exatamente_uma_chamada_de_escrita(
    adaptador: AdaptadorPostiz, plano: fk.ControlPlaneFake
) -> None:
    await adaptador.criar_rascunho(_pedido())
    assert plano.chamadas_de_escrita() == [("POST", "/public/v1/posts")]
    assert len(plano.posts) == 1


async def test_o_recibo_bruto_e_serializavel_e_pequeno(adaptador: AdaptadorPostiz) -> None:
    # O recibo vai para uma coluna jsonb e para a tela. Um corpo de provedor
    # inteiro nao cabe e nao ajuda; a poda tem teto.
    recibo = await adaptador.criar_rascunho(_pedido())
    texto = json.dumps(recibo.bruto)
    assert len(texto) < 4000
    assert recibo.como_recibo()["referencia_externa"] == recibo.referencia_externa
