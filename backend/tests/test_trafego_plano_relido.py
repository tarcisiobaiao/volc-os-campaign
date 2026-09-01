"""A releitura governada do plano — e a conta que ninguém estava conferindo.

## Os dois fatos que abrem este arquivo

**1. O plano gravado nunca era relido.** `vigente_da_conta` e
`vigente_da_campanha` existem em `persistencia.py:1157` e `:1177` e têm **zero
chamadores de produção**. O contrato de P05-T12 pede "releitura"; o que existia
era escrita e uma leitura interna usada só pela reconciliação. Uma linha que
ninguém lê é uma linha que ninguém pode conferir — e a v12_02 foi aplicada em
produção justamente para que alguém pudesse.

**2. A reconciliação não conferia a conta da linha achada.**
`_vincular_plano_reconciliado` chama `repo.por_intencao(chave)` ou
`repo.por_prefixo_de_intencao(prefixo)` e usa `linhas[0]` sem nunca comparar
`linha["customer_id"]` com o `cid` do pedido. Para `por_intencao` a chave já
inclui a conta e a travessia é impossível; para `por_prefixo_de_intencao` a
chave é cortada em 12 hex — 48 bits — e a própria docstring do repositório diz
que o prefixo "NÃO é uma identidade: ele é um candidato". Um candidato de outra
conta chegava até o vínculo, e a única barreira era um veto por NOME.

Este arquivo prova o portão que faltava e o caminho de volta.
"""
from __future__ import annotations

import asyncio
import socket

import pytest
from fastapi import HTTPException

from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm
from app.trafego import prontidao as pr
from app.routers import trafego
from app.seguranca.identidade import Identidade

IDENTIDADE = Identidade(sub="operador-sub-1",
                        email="tarcisio@agenciavolc.com.br",
                        papel="ADMIN", origem="teste")

CONTA = "5478096539"
MCC = "6016739364"
OUTRA_CONTA = "4820015411"


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    def recusar_rede(_socket, _address):
        pytest.fail("teste da releitura tentou abrir conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


# ═══════════════════════════════════════════════════════════════════════════
# Dublês
# ═══════════════════════════════════════════════════════════════════════════


def _acao(id_numerico: str = "7498530235", owner: str = "1234567890"):
    return pm.AcaoDeConversao(
        id=id_numerico,
        resource_name=f"customers/{owner}/conversionActions/{id_numerico}",
        owner_customer_id=owner, nome="Compra — site",
        categoria="PURCHASE", origem="WEBSITE", tipo="WEBPAGE",
        status="ENABLED", primaria=True,
    )


def _meta():
    return pm.MetaEfetiva(
        nivel=pm.NIVEL_CUSTOMER, nivel_estado=pm.COM_DADOS,
        metas_da_conta=(pm.Meta(categoria="PURCHASE", origem="WEBSITE",
                                biddable=True),),
        metas_da_conta_estado=pm.COM_DADOS,
        metas_da_campanha=(), metas_da_campanha_estado=pm.INELEGIVEL,
    )


def _plano(*, customer_id: str = CONTA, medindo: bool = True, perfil=None,
           campaign_id=None):
    frescor = (pm.Frescor(estado=pm.COM_DADOS, ultima_conversao_em="2026-08-31",
                          dias_desde_a_ultima=2, conversoes_na_janela=14.0,
                          conversion_action_id="7498530235")
               if medindo else
               pm.Frescor(estado=pm.VAZIO_CONFIRMADO, conversoes_na_janela=0,
                          conversion_action_id="7498530235"))
    return pm.montar(
        customer_id=customer_id, login_customer_id=MCC,
        meta_efetiva=_meta(), acoes=(_acao(),), acoes_estado=pm.COM_DADOS,
        frescor=frescor, campaign_id=campaign_id, perfil=perfil,
        marcacao=pm.InventarioDeMarcacao(
            estado=pm.COM_DADOS, auto_tagging=True,
            conversion_tracking_id="123",
            conversion_tracking_owner_id="1234567890",
            aceitou_termos_de_dados=True, fuso="America/Sao_Paulo"),
    )


def _linha(plano: pm.PlanoDeMensuracao, *, plano_id="11111111-1111-1111-1111-111111111111"):
    """Uma linha como o PostgREST a devolve: colunas + payload."""
    return {
        "plano_id": plano_id,
        "impressao": plano.impressao(),
        "customer_id": plano.customer_id,
        "login_customer_id": plano.login_customer_id,
        "campaign_id": plano.campaign_id,
        "chave_intencao": plano.chave_intencao,
        "versao": plano.versao,
        "completo": plano.completo,
        "lido_em": "2026-09-02T12:00:00+00:00",
        "registrado_em": "2026-09-02T12:00:01+00:00",
        "payload": plano.para_json(),
    }


class RepoDeLeitura:
    """O repositório, com o que a rota de leitura chama — e um diário."""

    habilitado = True

    def __init__(self, *, conta=None, campanha=None, erro: Exception | None = None):
        self._conta = conta
        self._campanha = campanha
        self._erro = erro
        self.chamadas: list = []

    async def vigente_da_conta(self, customer_id: str):
        self.chamadas.append(("vigente_da_conta", customer_id))
        if self._erro:
            raise self._erro
        return self._conta

    async def vigente_da_campanha(self, volc_campaign_id: str):
        self.chamadas.append(("vigente_da_campanha", volc_campaign_id))
        if self._erro:
            raise self._erro
        return self._campanha


def _ler(monkeypatch, repo, **params):
    monkeypatch.setattr(trafego, "_repositorio_de_plano", lambda: repo)
    try:
        return asyncio.run(trafego.plano_de_mensuracao_vigente(
            customer_id=params.get("customer_id", CONTA),
            login_customer_id=params.get("login_customer_id", MCC),
            campaign_id=params.get("campaign_id"),
            identidade=IDENTIDADE))
    except HTTPException as exc:
        return exc


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 1 — a releitura existe e devolve o que foi GRAVADO
# ═══════════════════════════════════════════════════════════════════════════


def test_a_releitura_devolve_o_plano_gravado(monkeypatch):
    plano = _plano()
    saida = _ler(monkeypatch, RepoDeLeitura(conta=_linha(plano)))
    assert not isinstance(saida, HTTPException), saida
    assert saida["persistido"] is True
    assert saida["plano_id"] == "11111111-1111-1111-1111-111111111111"
    assert saida["plano"]["impressao"] == plano.impressao()


def test_a_releitura_reconstroi_o_plano_e_nao_devolve_o_payload_cru(monkeypatch):
    """⚠️ RECONSTRUÍDO por `do_json`, que RECALCULA os derivados.

    Devolver o payload cru entregaria à tela um `completo` e uma lista de
    bloqueadores congelados no instante da gravação, sem que nada os
    conferisse. `do_json` recalcula a eleição e LEVANTA se ela divergir do que
    foi gravado — é a diferença entre reler e repetir.
    """
    plano = _plano()
    linha = _linha(plano)
    linha["payload"]["completo"] = True          # mentira plantada no payload
    linha["payload"]["bloqueadores"] = []
    saida = _ler(monkeypatch, RepoDeLeitura(conta=linha))
    assert saida["plano"]["completo"] is plano.completo


def test_ausencia_de_linha_nao_vira_plano_vazio(monkeypatch):
    """⚠️ "Não há linha" ≠ "há linha e ela diz que a conta não está pronta".

    As duas pedem coisas opostas: a primeira, ler a conta; a segunda, consertar
    a medição. Colapsá-las num `completo: false` faria o operador ir consertar
    o que ninguém mediu.
    """
    saida = _ler(monkeypatch, RepoDeLeitura(conta=None))
    assert saida["persistido"] is False
    assert saida["plano"] is None
    assert saida["porque"]
    assert saida["portoes"]["measurement_ready"] == pr.INDETERMINADO


def test_repositorio_desligado_e_estado_e_nao_prontidao(monkeypatch):
    class Desligado:
        habilitado = False

    saida = _ler(monkeypatch, Desligado())
    assert isinstance(saida, HTTPException)
    assert saida.status_code == 503


def test_falha_de_leitura_nao_vira_ausencia(monkeypatch):
    """⚠️ Falhar em ler não é "não há plano". Nunca 200 com `plano: null`."""
    saida = _ler(monkeypatch, RepoDeLeitura(erro=RuntimeError("banco fora")))
    assert isinstance(saida, HTTPException)
    assert saida.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 2 — ownership: a linha tem de ser DA CONTA pedida
# ═══════════════════════════════════════════════════════════════════════════


def test_linha_de_outra_conta_e_recusada_e_nao_devolvida(monkeypatch):
    """⚠️ Nenhuma leitura devolve plano de conta que não foi pedida.

    O repositório filtra por `customer_id`, e mesmo assim a rota confere: uma
    consulta é um filtro, e um filtro é uma intenção — a conferência é um fato.
    Se o filtro um dia mudar (ou um índice parcial mentir), a rota continua não
    entregando a conta errada.
    """
    alheia = _linha(_plano(customer_id=OUTRA_CONTA))
    saida = _ler(monkeypatch, RepoDeLeitura(conta=alheia))
    assert isinstance(saida, HTTPException)
    assert saida.status_code == 409
    assert OUTRA_CONTA not in str(saida.detail)


def test_a_conta_pedida_passa_pelo_portao_da_casa(monkeypatch):
    """Conta de cliente é 403 antes de qualquer leitura."""
    repo = RepoDeLeitura(conta=None)
    saida = _ler(monkeypatch, repo, customer_id="1111111111",
                 login_customer_id="2222222222")
    assert isinstance(saida, HTTPException)
    assert saida.status_code == 403
    assert repo.chamadas == []


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 3 — os portões saem da linha GRAVADA, não de uma leitura nova
# ═══════════════════════════════════════════════════════════════════════════


def test_o_plano_relido_conta_como_persistido_no_portao(monkeypatch):
    """`plano_persistido=True` só aqui: é a única leitura que PROVA a linha."""
    saida = _ler(monkeypatch, RepoDeLeitura(conta=_linha(_plano())))
    assert saida["portoes"]["measurement_ready"] == pr.PRONTO
    assert not any("PERSISTIDO" in b for b in saida["bloqueadores"])


def test_a_releitura_nao_abre_ativacao_por_si_so(monkeypatch):
    """⚠️ Ler o plano não prova observabilidade nem autoriza política.

    Este é o teste que impede a rota nova de virar um atalho: ela devolve o que
    está gravado, e o que está gravado não diz nada sobre poder despausar.
    """
    saida = _ler(monkeypatch, RepoDeLeitura(conta=_linha(_plano())))
    assert saida["portoes"]["activation_ready"] != pr.PRONTO
    assert saida["portoes"]["campaign_birth"] != pr.PRONTO


def test_a_releitura_devolve_o_perfil_quando_ele_foi_gravado(monkeypatch):
    perfil = pdm.derivar_de_plano(
        _plano(), negocio="portal-mundo-mais", intencao="bpc-loas",
        funil=pdm.FUNIL_ACAO, evento="lead-qualificado")
    plano = _plano(perfil=perfil)
    saida = _ler(monkeypatch, RepoDeLeitura(conta=_linha(plano)))
    assert saida["perfil"]["chave"] == perfil.chave
    assert saida["perfil"]["intencao"] == "bpc-loas"


def test_a_releitura_por_campanha_usa_a_identidade_interna(monkeypatch):
    """⚠️ `volc_campaign_id`, e não o id externo solto.

    `uuid5(gads:<conta>:<campanha>)` carrega a conta dentro da identidade. Ler
    por `campaign_id` cru faria o id de outra conta casar com esta linha.
    """
    from app.trafego import sincronizador as sinc

    plano = _plano(campaign_id="24183717006")
    repo = RepoDeLeitura(campanha=_linha(plano))
    saida = _ler(monkeypatch, repo, campaign_id="24183717006")
    assert not isinstance(saida, HTTPException), saida
    assert repo.chamadas == [
        ("vigente_da_campanha", sinc.volc_campaign_id(CONTA, "24183717006"))]


def test_plano_ilegivel_e_falha_declarada_e_nao_ausencia(monkeypatch):
    """⚠️ Um payload que não reconstrói não é "não há plano".

    `do_json` levanta quando a eleição gravada diverge da recalculada. Engolir
    isso devolveria `plano: null` — indistinguível de conta nunca lida — para
    uma linha que EXISTE e que alguém precisa investigar.
    """
    linha = _linha(_plano())
    linha["payload"]["acao_alvo"] = {"id": "999999999"}
    saida = _ler(monkeypatch, RepoDeLeitura(conta=linha))
    assert isinstance(saida, HTTPException)
    assert saida.status_code == 409
    assert "plano_id" in str(saida.detail)


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 4 — a reconciliação e a conta que ninguém conferia
# ═══════════════════════════════════════════════════════════════════════════


class RepoDeReconciliacao:
    habilitado = True

    def __init__(self, linhas):
        self._linhas = linhas
        self.gravou: list = []

    async def por_intencao(self, chave):
        return [l for l in self._linhas
                if str(l.get("chave_intencao") or "") == chave]

    async def por_prefixo_de_intencao(self, prefixo):
        return [l for l in self._linhas
                if str(l.get("chave_intencao") or "").startswith(prefixo)]

    async def registrar(self, documento):
        self.gravou.append(documento)
        return "22222222-2222-2222-2222-222222222222"


def _linha_de_intencao(chave: str, *, customer_id: str, nome_marca: str = "",
                       campaign_id=None):
    plano = _plano(customer_id=customer_id, campaign_id=campaign_id)
    linha = _linha(plano)
    linha["chave_intencao"] = chave
    linha["payload"]["chave_intencao"] = chave
    return linha


#: 12 hex de prefixo comum — o tamanho REAL da marca `VOLC-CANARY-<12 hex>`.
PREFIXO = "abcdef012345"
CHAVE_DA_CASA = PREFIXO + "0" * 52
CHAVE_ALHEIA = PREFIXO + "f" * 52


def _reconciliar(monkeypatch, repo, **kw):
    monkeypatch.setattr(trafego, "_repositorio_de_plano", lambda: repo)
    return asyncio.run(trafego._vincular_plano_reconciliado(
        cid=kw.get("cid", CONTA),
        campaign_id=kw.get("campaign_id", "24183717006"),
        chave_intencao=kw.get("chave_intencao", ""),
        marca=kw.get("marca", f"VOLC-CANARY-{PREFIXO}"),
        nome_encontrado=kw.get("nome_encontrado", "")))


def test_linha_de_outra_conta_nao_e_vinculada_por_prefixo(monkeypatch):
    """⚠️ O DEFEITO: o prefixo da marca são 12 hex — 48 bits —, e não uma conta.

    A docstring de `por_prefixo_de_intencao` já dizia: "este filtro NÃO é uma
    identidade: ele é um candidato". Um candidato de outra conta chegava até o
    vínculo, e a única barreira era um veto por NOME — que só funciona se a
    campanha ainda carregar a marca. Renomeada à mão, ela passava.
    """
    repo = RepoDeReconciliacao([
        _linha_de_intencao(CHAVE_ALHEIA, customer_id=OUTRA_CONTA)])
    saida = _reconciliar(monkeypatch, repo)
    assert saida["vinculo"]["vinculado"] is False
    assert "não é desta conta" in saida["vinculo"]["porque"]
    assert repo.gravou == []


def test_a_linha_da_conta_certa_continua_sendo_vinculada(monkeypatch):
    """O ramo POSITIVO — sem ele o portão novo só provaria que bloqueia tudo."""
    repo = RepoDeReconciliacao([
        _linha_de_intencao(CHAVE_DA_CASA, customer_id=CONTA)])
    saida = _reconciliar(monkeypatch, repo)
    assert saida["vinculo"]["vinculado"] is True
    assert len(repo.gravou) == 1
    assert repo.gravou[0]["campaign_id"] == "24183717006"


def test_a_conta_alheia_nao_bloqueia_a_reconciliacao_da_conta_certa(monkeypatch):
    """⚠️ A ambiguidade é avaliada DEPOIS do recorte de conta.

    Avaliada no lote cru, duas chaves sob o mesmo prefixo — uma delas de outra
    conta — recusavam por "ambíguo" um caso que é inequívoco. A linha alheia
    nunca foi candidata; deixá-la votar fazia uma conta bloquear a outra.
    """
    repo = RepoDeReconciliacao([
        _linha_de_intencao(CHAVE_DA_CASA, customer_id=CONTA),
        _linha_de_intencao(CHAVE_ALHEIA, customer_id=OUTRA_CONTA),
    ])
    saida = _reconciliar(monkeypatch, repo)
    assert saida["vinculo"]["vinculado"] is True


def test_duas_intencoes_da_MESMA_conta_continuam_ambiguas(monkeypatch):
    """A recusa por ambiguidade continua valendo onde ela é verdadeira."""
    repo = RepoDeReconciliacao([
        _linha_de_intencao(PREFIXO + "a" * 52, customer_id=CONTA),
        _linha_de_intencao(PREFIXO + "b" * 52, customer_id=CONTA),
    ])
    saida = _reconciliar(monkeypatch, repo)
    assert saida["vinculo"]["vinculado"] is False
    assert "intenções diferentes" in saida["vinculo"]["porque"]
    assert repo.gravou == []
