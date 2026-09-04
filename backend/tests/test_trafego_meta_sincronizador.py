from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.trafego.meta import adaptador as adp
from app.trafego.meta import credenciais as cred
from app.trafego.meta import dominio as dom
from app.trafego.meta import persistencia as per
from app.trafego.meta import sincronizador as sinc


AGORA = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Relogio:
    def __init__(self):
        self.agora = AGORA

    def __call__(self):
        atual = self.agora
        self.agora += timedelta(seconds=1)
        return atual


class ResolvedorFalso:
    def __init__(self):
        self.chamadas = 0

    async def resolver(self, referencia):
        self.chamadas += 1
        return cred.SegredoEfemero("segredo-em-memoria")


class ResolvedorQueVazaNoErro:
    async def resolver(self, referencia):
        del referencia
        raise cred.CredencialIndisponivel("token-que-nao-pode-ir-ao-recibo")


class AdaptadorFalso:
    def __init__(self, leituras):
        self.leituras = list(leituras)
        self.chamadas = 0

    async def ler_hierarquia(self, conta, segredo):
        del conta, segredo
        self.chamadas += 1
        proxima = self.leituras.pop(0)
        if isinstance(proxima, Exception):
            raise proxima
        return proxima


def ref(pronta=True):
    return cred.ReferenciaDeCredencial(
        ativo_id="asset:meta-ad-account:piloto", provider="1password",
        nome_logico="META_ADS_READ_TOKEN", estado="referenced",
        verificacao_estado="verified" if pronta else "unverified",
        verificado_em=AGORA if pronta else None, valido_ate=date(2099, 1, 1))


def pedido(janela="2026-09-04"):
    return sinc.PedidoDeSync(
        conta_ativo_id="asset:meta-ad-account:piloto", conta_externa="123",
        referencia=ref(), janela=janela)


def leitura(nome="C"):
    return dom.LeituraDaHierarquia(
        conta_externa="123",
        campanhas=(dom.ObjetoMeta("campaign", "10", nome, "PAUSED", "PAUSED"),),
        conjuntos=(), anuncios=(), criativos=(), paginas_lidas=4)


@pytest.mark.anyio
async def test_sucesso_e_idempotente_e_nao_relê_conta():
    repo = per.RepositorioMetaEmMemoria()
    adapter = AdaptadorFalso([leitura()])
    resolver = ResolvedorFalso()
    ids = iter(["11111111-1111-1111-1111-111111111111"])
    kwargs = dict(adaptador=adapter, resolvedor=resolver, repositorio=repo,
                  relogio=Relogio(), gerar_run_id=lambda: next(ids))
    primeiro = await sinc.sincronizar_conta(pedido(), **kwargs)
    segundo = await sinc.sincronizar_conta(pedido(), **kwargs)
    assert primeiro.resultado == "ok" and not primeiro.repetido
    assert segundo.resultado == "ok" and segundo.repetido
    assert adapter.chamadas == resolver.chamadas == 1
    assert len(repo.recibos) == 1


@pytest.mark.anyio
async def test_falha_e_retryable_e_preserva_ultimo_snapshot_bom():
    repo = per.RepositorioMetaEmMemoria()
    resolver = ResolvedorFalso()
    ids = iter([
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
    ])
    relogio = Relogio()
    bom = await sinc.sincronizar_conta(
        pedido("janela-1"), adaptador=AdaptadorFalso([leitura("boa")]),
        resolvedor=resolver, repositorio=repo, relogio=relogio,
        gerar_run_id=lambda: next(ids))
    falha = await sinc.sincronizar_conta(
        pedido("janela-2"), adaptador=AdaptadorFalso([
            adp.ErroDeLeituraMeta("META_RATE_LIMIT", "limite", True)]),
        resolvedor=resolver, repositorio=repo, relogio=relogio,
        gerar_run_id=lambda: next(ids))
    retry = await sinc.sincronizar_conta(
        pedido("janela-2"), adaptador=AdaptadorFalso([leitura("nova")]),
        resolvedor=resolver, repositorio=repo, relogio=relogio,
        gerar_run_id=lambda: next(ids))
    assert bom.resultado == "ok"
    assert falha.resultado == "falhou" and falha.erro_codigo == "META_RATE_LIMIT"
    assert retry.resultado == "ok"
    assert repo.projecoes["123"].leitura.campanhas[0].nome == "nova"


@pytest.mark.anyio
async def test_so_leitura_completa_marca_objeto_anterior_ausente():
    repo = per.RepositorioMetaEmMemoria()
    resolver = ResolvedorFalso()
    relogio = Relogio()
    ids = iter([
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ])
    await sinc.sincronizar_conta(
        pedido("primeira"), adaptador=AdaptadorFalso([leitura()]),
        resolvedor=resolver, repositorio=repo, relogio=relogio,
        gerar_run_id=lambda: next(ids))
    chave_objeto = ("123", "campaign", "10")
    assert chave_objeto in repo.objetos and chave_objeto not in repo.ausentes

    vazia = dom.LeituraDaHierarquia(
        conta_externa="123", campanhas=(), conjuntos=(), anuncios=(),
        criativos=(), paginas_lidas=4)
    await sinc.sincronizar_conta(
        pedido("segunda"), adaptador=AdaptadorFalso([vazia]),
        resolvedor=resolver, repositorio=repo, relogio=relogio,
        gerar_run_id=lambda: next(ids))
    assert chave_objeto in repo.objetos
    assert chave_objeto in repo.ausentes


@pytest.mark.anyio
async def test_referencia_nao_pronta_falha_antes_de_resolver_ou_ler():
    repo = per.RepositorioMetaEmMemoria()
    resolver = ResolvedorFalso()
    adapter = AdaptadorFalso([leitura()])
    bloqueado = sinc.PedidoDeSync(
        conta_ativo_id="asset:meta-ad-account:piloto", conta_externa="123",
        referencia=ref(pronta=False), janela="janela")
    recibo = await sinc.sincronizar_conta(
        bloqueado, adaptador=adapter, resolvedor=resolver, repositorio=repo,
        relogio=Relogio(),
        gerar_run_id=lambda: "11111111-1111-1111-1111-111111111111")
    assert recibo.resultado == "falhou"
    assert recibo.erro_codigo == "META_CREDENTIAL_UNAVAILABLE"
    assert resolver.chamadas == adapter.chamadas == 0
    assert repo.projecoes == {}


@pytest.mark.anyio
async def test_erro_do_broker_nao_e_copiado_para_recibo():
    repo = per.RepositorioMetaEmMemoria()
    adapter = AdaptadorFalso([leitura()])
    recibo = await sinc.sincronizar_conta(
        pedido(), adaptador=adapter, resolvedor=ResolvedorQueVazaNoErro(),
        repositorio=repo, relogio=Relogio(),
        gerar_run_id=lambda: "11111111-1111-1111-1111-111111111111")
    assert recibo.resultado == "falhou"
    assert "token-que" not in (recibo.erro_mensagem or "")
    assert adapter.chamadas == 0


@pytest.mark.anyio
async def test_falha_de_uma_conta_nao_apaga_ou_bloqueia_outra():
    repo = per.RepositorioMetaEmMemoria()
    resolver = ResolvedorFalso()
    relogio = Relogio()
    falho = await sinc.sincronizar_conta(
        pedido("falha"), adaptador=AdaptadorFalso([
            adp.ErroDeLeituraMeta("META_REMOTE_FAILURE", "temporaria", True)]),
        resolvedor=resolver, repositorio=repo, relogio=relogio,
        gerar_run_id=lambda: "11111111-1111-1111-1111-111111111111")
    outro = sinc.PedidoDeSync(
        conta_ativo_id="asset:meta-ad-account:outra", conta_externa="999",
        referencia=ref(), janela="ok")
    leitura_outra = dom.LeituraDaHierarquia(
        conta_externa="999", campanhas=(), conjuntos=(), anuncios=(),
        criativos=(), paginas_lidas=4)
    ok = await sinc.sincronizar_conta(
        outro, adaptador=AdaptadorFalso([leitura_outra]), resolvedor=resolver,
        repositorio=repo, relogio=relogio,
        gerar_run_id=lambda: "22222222-2222-2222-2222-222222222222")
    assert falho.resultado == "falhou"
    assert ok.resultado == "ok"
    assert "999" in repo.projecoes and "123" not in repo.projecoes
