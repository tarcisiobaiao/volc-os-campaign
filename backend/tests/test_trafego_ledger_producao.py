"""O que separa o fluxo Search de "compila" e "é lançável".

Os 23 testes de `test_trafego_ledger.py` provam a ORDEM dos atos, e provam bem.
O que eles não alcançam é o CONTEÚDO que atravessa a fronteira, porque eles
dublam o `Ledger` inteiro — `LedgerDeTeste.abrir` devolve uma chave literal e
nunca chama a derivação real. Um dublê que não deriva não pode reprovar uma
derivação quebrada.

Este arquivo fecha essa distância em quatro frentes, e cada teste aqui falhava
antes da correção que ele acompanha:

* **A** — a derivação REAL da chave, a partir do corpo real da rota. O
  `ProvarEntrada` declara `budget_diario: float`, `_sem_float` recusa float na
  travessia, e o `ErroDeLote` resultante não era nem `LedgerRecusou` nem
  `LedgerIndisponivel` — escapava como 500, antes de existir recibo.
* **B** — o estado que o executor DEVOLVE. `volc_ads.subir` captura
  `ErroTerminal`/`ErroEsgotado` e devolve `Recibo(estado=RECUSADO|INDETERMINADO)`;
  quem lê só exceção lê o contrato errado.
* **C** — uma identidade só. Duas derivações do `volc_campaign_id` colidiriam no
  índice `trafego_campanha_identidade_externa_ux (customer_id, campaign_id)`,
  que o `ON CONFLICT (volc_campaign_id)` das RPCs não cobre.
* **D** — a saída de `indeterminado` como porta operacional, e não como função
  que só o teste chama.

⚠️ Nada aqui toca rede, Supabase ou Google: a fixture `_rede_bloqueada` derruba
o teste se um socket for aberto.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import asyncio
import socket

import pytest
from fastapi import HTTPException

from app.trafego import canario, ledger as led, lote as dom, sincronizador
from app.routers import trafego
from app.seguranca.identidade import Identidade

from test_trafego_canario import (  # noqa: E402
    _instalar_portas_hermeticas,
    _payload_da_rota,
)


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    def recusar_rede(_socket, _address):
        pytest.fail("teste de produção do ledger tentou abrir conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


IDENTIDADE = Identidade(
    sub="operador-sub-1", email="tarcisio@agenciavolc.com.br",
    papel="ADMIN", origem="teste",
)


# ═══════════════════════════════════════════════════════════════════════════
# Dublês fiéis — o que o original de fato devolve, e não o que seria cômodo
# ═══════════════════════════════════════════════════════════════════════════

class SupaDeTeste:
    """Um Supabase que registra a chamada RPC em vez de fazê-la.

    Este é o ponto: o `Ledger` fica REAL, e é a derivação real da chave e da
    identidade que atravessa. Dublar o `Ledger` esconderia exatamente o defeito.
    """

    enabled = True

    def __init__(self, *, respostas: dict | None = None,
                 conta_do_item: str | None = "5478096539"):
        self.chamadas: list[tuple[str, dict]] = []
        self._respostas = respostas or {}
        self._conta_do_item = conta_do_item
        self.selects: list[tuple[str, dict]] = []

    async def select(self, tabela: str, params: dict):
        """O bastante para a checagem de posse: item -> lote -> conta."""
        self.selects.append((tabela, dict(params)))
        if self._conta_do_item is None:
            return []
        if tabela == "trafego_lote_item":
            return [{"item_id": "item-1", "lote_id": "lote-1"}]
        if tabela == "trafego_lote":
            return [{"lote_id": "lote-1", "conta_externa": self._conta_do_item}]
        return []

    async def rpc(self, funcao: str, corpo: dict):
        self.chamadas.append((funcao, dict(corpo)))
        if funcao in self._respostas:
            resposta = self._respostas[funcao]
            if isinstance(resposta, Exception):
                raise resposta
            return resposta
        return {"item_id": "item-1", "lote_id": "lote-1",
                "recibo_id": "recibo-1", "tentativa": 1,
                "intencao_id": "int-1"}

    def corpo_de(self, funcao: str) -> dict:
        return next(c for f, c in self.chamadas if f == funcao)


def _recibo_do_executor(estado: str, *, campaign_id: str = "24183717006",
                        falha=None, explicacao: str = ""):
    """A forma REAL de `volc_ads.subir.Recibo`, com os estados REAIS.

    ⚠️ `estado` aqui é `ACEITO`/`RECUSADO`/`INDETERMINADO` — o vocabulário do
    executor. Um dublê com `estado="CRIADA"` provaria uma rota que não existe.
    """
    from volc_ads import subir as sb

    criados = ()
    if estado == sb.ACEITO:
        criados = (SimpleNamespace(
            posicao=0, tipo="campaign_result",
            resource_name=f"customers/5478096539/campaigns/{campaign_id}"),)
    return SimpleNamespace(
        estado=estado, carimbo="20260831_120000",
        customer_id=canario.CONTA, login_customer_id=canario.MCC,
        nome_campanha="VOLC-CANARY-teste", n_operacoes=72,
        impressao="a" * 64, motivo="canário pausado com aprovação humana",
        criados=criados, request_id="req-1", linhagem=(), falha=falha,
        explicacao=explicacao,
    )


def _montar(monkeypatch, *, ledger, subir):
    from volc_ads import subir as sb

    _instalar_portas_hermeticas(monkeypatch)
    monkeypatch.setattr(trafego, "_ledger", lambda: ledger)
    monkeypatch.setattr(canario, "campanhas_com_marca", lambda **_: ())
    monkeypatch.setattr(canario, "campanhas_com_destino", lambda **_: ())
    monkeypatch.setattr(sb, "subir", subir)

    async def _sem_registro_legado(*_a, **_k):
        return ""

    monkeypatch.setattr(trafego, "_registrar_campanha", _sem_registro_legado)


def _impressao_aprovada(monkeypatch):
    _instalar_portas_hermeticas(monkeypatch)
    prova = asyncio.run(trafego.provar(trafego.ProvarEntrada(**_payload_da_rota()),
                                       identidade=IDENTIDADE))
    return prova["autorizacao"]["plano_impressao"]


def _corpo(prova_impressao: str, **mudancas):
    return trafego.SubirEntrada(**{
        **_payload_da_rota(**mudancas),
        "motivo": "canário pausado com aprovação humana",
        "plano_impressao": prova_impressao,
        "confirmar_criacao_pausada": True,
    })


# ═══════════════════════════════════════════════════════════════════════════
# A. A derivação real da chave — dinheiro não atravessa como float
# ═══════════════════════════════════════════════════════════════════════════

def test_o_corpo_real_da_rota_deriva_chave_sem_levantar(monkeypatch):
    """⚠️ O teste que os 23 anteriores não podiam fazer.

    `_payload_da_rota` traz `budget_diario=10.0` e `cpc_inicial=0.20`. Com o
    `Ledger` REAL no lugar, `abrir` derivava a chave por `_sem_float` e levantava
    `ErroDeLote` — um `ValueError` que a rota não captura.
    """
    supa = SupaDeTeste()
    ledger = led.Ledger(supa)
    corpo = trafego.ProvarEntrada(**_payload_da_rota())
    plano = trafego.plano_do_ledger(corpo, cid=canario.CONTA, mid=canario.MCC)

    saida = asyncio.run(ledger.abrir(
        plataforma="GOOGLE_ADS", conta_externa=canario.CONTA, canal="SEARCH",
        objetivo="leads", rotulo="canário", plano=plano,
        plano_impressao="a" * 64, declarada_por="tarcisio",
        declarada_com_base_em="oportunidade:1",
        blueprint_chave="search-canario", blueprint_titulo="SEARCH — canário",
        blueprint_corpo={"canal": "SEARCH"},
    ))

    assert saida["idempotency_key"].startswith("volc-gads-0000-")
    enviado = supa.corpo_de("trafego_ledger_abrir_lancamento")["p_plano"]
    assert not _tem_float(enviado), (
        f"o plano chegou ao ledger com float: {enviado}")


def _tem_float(valor) -> bool:
    if isinstance(valor, float):
        return True
    if isinstance(valor, dict):
        return any(_tem_float(v) for v in valor.values())
    if isinstance(valor, (list, tuple)):
        return any(_tem_float(v) for v in valor)
    return False


def test_dinheiro_vira_micros_inteiros_e_nao_perde_precisao(monkeypatch):
    corpo = trafego.ProvarEntrada(**_payload_da_rota(
        budget_diario=10.0, cpc_inicial=0.12))
    plano = trafego.plano_do_ledger(corpo, cid=canario.CONTA, mid=canario.MCC)

    assert plano["budget_diario_micros"] == 10_000_000
    assert plano["cpc_inicial_micros"] == 120_000
    assert "budget_diario" not in plano
    assert "cpc_inicial" not in plano


def test_valores_semanticamente_iguais_produzem_a_mesma_chave(monkeypatch):
    """10.0, 10 e Decimal('10.00') são o mesmo dinheiro — e a mesma chave."""
    chaves = set()
    for valor in (10.0, 10, Decimal("10.00")):
        corpo = trafego.ProvarEntrada(**_payload_da_rota(budget_diario=valor))
        plano = trafego.plano_do_ledger(corpo, cid=canario.CONTA, mid=canario.MCC)
        chaves.add(dom.chave_de_idempotencia(
            intencao_id="int-1", plataforma="GOOGLE_ADS",
            conta_externa=canario.CONTA, canal="SEARCH", ordem=0, plano=plano))
    assert len(chaves) == 1, f"o mesmo dinheiro produziu {len(chaves)} chaves"


def test_valores_diferentes_nao_colidem(monkeypatch):
    def chave(valor):
        corpo = trafego.ProvarEntrada(**_payload_da_rota(budget_diario=valor))
        plano = trafego.plano_do_ledger(corpo, cid=canario.CONTA, mid=canario.MCC)
        return dom.chave_de_idempotencia(
            intencao_id="int-1", plataforma="GOOGLE_ADS",
            conta_externa=canario.CONTA, canal="SEARCH", ordem=0, plano=plano)

    assert chave(10.0) != chave(10.5)
    assert chave(10.0) != chave(10.000001)


def test_erro_de_lote_vira_recusa_tipada_e_nunca_um_500(monkeypatch):
    """A fachada é a fronteira: `ErroDeLote` sai dela como `LedgerRecusou`."""
    ledger = led.Ledger(SupaDeTeste())
    with pytest.raises(led.LedgerRecusou) as erro:
        asyncio.run(ledger.abrir(
            plataforma="GOOGLE_ADS", conta_externa=canario.CONTA, canal="SEARCH",
            objetivo="leads", rotulo="canário",
            plano={"budget_diario": 10.0},  # o float que a rota já não manda
            plano_impressao="a" * 64, declarada_por="tarcisio",
            declarada_com_base_em="oportunidade:1",
            blueprint_chave="search-canario", blueprint_titulo="t",
            blueprint_corpo={},
        ))
    assert erro.value.codigo == "22023"
    assert "float" in str(erro.value)


def test_a_rota_devolve_409_quando_o_plano_e_irrepresentavel(monkeypatch):
    """Recusa de derivação é 409 com motivo, nunca 500 nu — e sem recibo."""
    impressao = _impressao_aprovada(monkeypatch)

    def subir_proibido(*_a, **_k):
        pytest.fail("o mutate saiu com o plano recusado na derivação")

    supa = SupaDeTeste()
    ledger = led.Ledger(supa)
    _montar(monkeypatch, ledger=ledger, subir=subir_proibido)
    monkeypatch.setattr(
        trafego, "plano_do_ledger",
        lambda *_a, **_k: (_ for _ in ()).throw(
            trafego.PlanoIrrepresentavel("budget_diario não vira micros")))

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    assert "micros" in str(erro.value.detail)
    assert supa.chamadas == [], "abriu recibo para um plano que não deriva"


# ═══════════════════════════════════════════════════════════════════════════
# B. O estado que o executor DEVOLVE
# ═══════════════════════════════════════════════════════════════════════════

def _rodar_com_recibo(monkeypatch, recibo_ou_erro):
    from volc_ads import subir as sb

    impressao = _impressao_aprovada(monkeypatch)
    supa = SupaDeTeste()
    ledger = led.Ledger(supa)

    def subir_dublado(*_a, **_k):
        if isinstance(recibo_ou_erro, BaseException):
            raise recibo_ou_erro
        return recibo_ou_erro

    _montar(monkeypatch, ledger=ledger, subir=subir_dublado)
    try:
        saida = asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))
        return supa, saida, None
    except HTTPException as exc:
        return supa, None, exc


def test_aceito_fecha_como_sucesso(monkeypatch):
    from volc_ads import subir as sb

    supa, saida, erro = _rodar_com_recibo(
        monkeypatch, _recibo_do_executor(sb.ACEITO))
    assert erro is None, f"ACEITO virou erro HTTP: {erro}"
    fechar = supa.corpo_de("trafego_ledger_fechar")
    assert fechar["p_desfecho"] == "sucesso"
    assert fechar["p_id_externo"] == "24183717006"


def test_recusado_fecha_como_erro_e_nunca_vira_sucesso(monkeypatch):
    """⚠️ RECUSADO é RESPOSTA: o Google disse que não criou. Nada de sucesso.

    Antes desta correção a rota nem olhava `recibo.estado`: uma recusa
    respondida virava 200 com "a campanha existe, e está pausada".
    """
    from volc_ads import subir as sb

    supa, saida, erro = _rodar_com_recibo(
        monkeypatch,
        _recibo_do_executor(sb.RECUSADO, explicacao="orçamento inválido"))

    assert saida is None, "uma recusa respondida devolveu 200"
    assert erro.status_code == 502
    assert erro.detail["estado"] == "recusado"
    assert erro.detail["reenvio_permitido"] is True
    fechar = supa.corpo_de("trafego_ledger_fechar")
    assert fechar["p_desfecho"] == "erro", (
        f"recusa respondida foi gravada como {fechar['p_desfecho']!r}")


def test_indeterminado_fecha_como_sem_resposta_e_proibe_reenvio(monkeypatch):
    from volc_ads import subir as sb

    supa, saida, erro = _rodar_com_recibo(
        monkeypatch,
        _recibo_do_executor(sb.INDETERMINADO, explicacao="não respondeu"))

    assert saida is None
    assert erro.status_code == 504
    assert erro.detail["estado"] == "indeterminado"
    assert erro.detail["reenvio_permitido"] is False
    fechar = supa.corpo_de("trafego_ledger_fechar")
    assert fechar["p_desfecho"] == "sem_resposta"


def test_estado_desconhecido_do_executor_nao_vira_sucesso(monkeypatch):
    """Um estado que não reconhecemos é ignorância, não aprovação."""
    supa, saida, erro = _rodar_com_recibo(
        monkeypatch, _recibo_do_executor("ESTADO_QUE_NAO_EXISTE"))
    assert saida is None
    assert erro.status_code == 504
    assert supa.corpo_de("trafego_ledger_fechar")["p_desfecho"] == "sem_resposta"


def test_guarda_anterior_ao_mutate_e_falha_confirmada_e_reentravel(monkeypatch):
    """`PayloadNaoValidado` dispara antes de qualquer byte sair: nada foi criado."""
    from volc_ads import subir as sb

    supa, saida, erro = _rodar_com_recibo(
        monkeypatch, sb.PayloadNaoValidado("hash divergente"))

    assert erro.status_code == 409
    fechar = supa.corpo_de("trafego_ledger_fechar")
    assert fechar["p_desfecho"] == "erro", (
        "uma guarda local virou `sem_resposta` e travou o item para sempre")


def test_excecao_desconhecida_e_indeterminada_e_nao_falha_reentravel(monkeypatch):
    """⚠️ O teste que refuta o atalho tentador.

    `volc_ads.subir` grava o recibo em disco DEPOIS do mutate
    (`_gravar(recibo, pasta)`, subir.py:917). Um `OSError` ali escapa com a
    campanha JÁ CRIADA na conta. Carimbar isso como `erro` deixaria o item
    reentrável — e o reenvio criaria a segunda campanha no mesmo leilão.

    Exceção desconhecida é ignorância: `sem_resposta`, item `indeterminado`,
    reenvio fechado, e a saída é reconciliar.
    """
    supa, saida, erro = _rodar_com_recibo(
        monkeypatch, OSError("No space left on device"))

    assert erro.status_code == 504
    assert erro.detail["reenvio_permitido"] is False
    fechar = supa.corpo_de("trafego_ledger_fechar")
    assert fechar["p_desfecho"] == "sem_resposta", (
        "exceção desconhecida virou falha reentrável; isso cria a segunda "
        "campanha quando ela nasce depois do mutate")


# ═══════════════════════════════════════════════════════════════════════════
# C. Uma identidade só
# ═══════════════════════════════════════════════════════════════════════════

def test_as_duas_derivacoes_da_identidade_coincidem():
    """⚠️ Duas derivações = duas identidades para a mesma campanha externa.

    O ledger derivava `volc_cmp_<sigla>_<sha256[:16]>`; o sincronizador já
    derivava `uuid5(gads:<conta>:<campanha>)` e é ele que tem linhas gravadas.
    O índice `trafego_campanha_identidade_externa_ux (customer_id, campaign_id)`
    não é coberto pelo `ON CONFLICT (volc_campaign_id)` das RPCs: com duas
    formas, o INSERT do ledger aborta a transação de `fechar` com 23505 e o
    recibo fica `em_voo` com a campanha já criada na conta.
    """
    conta, campanha = "547-809-6539", "24183717006"
    assert led.volc_campaign_id_de(
        plataforma="GOOGLE_ADS", conta_externa=conta, id_externo=campanha,
    ) == sincronizador.volc_campaign_id(conta, campanha)


def test_a_identidade_e_estavel_entre_formatos_da_conta():
    """`547-809-6539` e `5478096539` são a mesma conta — e a mesma identidade."""
    assert led.volc_campaign_id_de(
        plataforma="GOOGLE_ADS", conta_externa="547-809-6539",
        id_externo="24183717006",
    ) == led.volc_campaign_id_de(
        plataforma="GOOGLE_ADS", conta_externa="5478096539",
        id_externo="24183717006")


def test_identidades_externas_diferentes_nao_colidem():
    a = led.volc_campaign_id_de(plataforma="GOOGLE_ADS",
                                conta_externa="5478096539", id_externo="1")
    b = led.volc_campaign_id_de(plataforma="GOOGLE_ADS",
                                conta_externa="5478096539", id_externo="2")
    c = led.volc_campaign_id_de(plataforma="GOOGLE_ADS",
                                conta_externa="6016739364", id_externo="1")
    assert len({a, b, c}) == 3


def test_reprocessar_converge_para_o_mesmo_registro():
    """Idempotência da identidade: mil leituras, um registro."""
    ids = {led.volc_campaign_id_de(plataforma="GOOGLE_ADS",
                                   conta_externa="5478096539",
                                   id_externo="24183717006")
           for _ in range(50)}
    assert len(ids) == 1


# ═══════════════════════════════════════════════════════════════════════════
# D. A saída de `indeterminado` como porta operacional
# ═══════════════════════════════════════════════════════════════════════════

def _montar_reconciliacao(monkeypatch, *, ledger, encontradas):
    def ler(**_kw):
        return tuple(encontradas)

    monkeypatch.setattr(trafego, "_ler_campanha_na_conta", ler)
    monkeypatch.setattr(trafego, "_ledger", lambda: ledger)


CAMPANHA_NA_CONTA = {"campaign_id": "24183717006",
                     "campaign_name": "VOLC-CANARY-teste", "status": "PAUSED"}


def test_reconciliar_e_rota_de_producao_e_fecha_o_mesmo_recibo(monkeypatch):
    """⚠️ Antes disto, `Ledger.reconciliar` só tinha chamador de teste."""
    # ⚠️ Resposta FIEL à RPC. `trafego_ledger_reconciliar` só fecha recibo que
    # ainda esteja `em_voo` (v10_03:811); no caminho normal de indeterminação a
    # rota já o fechou como `sem_resposta`, então `recibo_fechado_como` volta
    # NULL e quem converge é o ITEM. Fabricar "sucesso" aqui provaria uma
    # transição que a produção não faz.
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {
        "verificacao_id": "v-1", "item_id": "item-1", "achou": True,
        "item_estado": "criada_pausada", "recibo_id": None,
        "recibo_fechado_como": None}})
    _montar_reconciliacao(monkeypatch, ledger=led.Ledger(supa),
                          encontradas=[CAMPANHA_NA_CONTA])

    saida = asyncio.run(trafego.reconciliar_lancamento(
        trafego.ReconciliarEntrada(
            item_id="11111111-1111-1111-1111-111111111111",
            customer_id=canario.CONTA, campaign_id="24183717006"),
        identidade=IDENTIDADE))

    corpo = supa.corpo_de("trafego_ledger_reconciliar")
    assert corpo["p_achou"] is True
    assert corpo["p_quantidade"] == 1
    assert corpo["p_volc_campaign_id"] == sincronizador.volc_campaign_id(
        canario.CONTA, "24183717006")
    assert saida["reenvio_executado"] is False


def test_reconciliar_nunca_reenvia_o_mutate(monkeypatch):
    from volc_ads import subir as sb

    def subir_proibido(*_a, **_k):
        pytest.fail("a reconciliação reenviou o mutate")

    monkeypatch.setattr(sb, "subir", subir_proibido)
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {}})
    _montar_reconciliacao(monkeypatch, ledger=led.Ledger(supa),
                          encontradas=[CAMPANHA_NA_CONTA])

    asyncio.run(trafego.reconciliar_lancamento(
        trafego.ReconciliarEntrada(
            item_id="11111111-1111-1111-1111-111111111111",
            customer_id=canario.CONTA, campaign_id="24183717006"),
        identidade=IDENTIDADE))

    assert [f for f, _ in supa.chamadas] == ["trafego_ledger_reconciliar"]


def test_reconciliar_e_idempotente_no_corpo_que_envia(monkeypatch):
    """Aplicar duas vezes manda exatamente o mesmo corpo — a RPC converge."""
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {}})
    _montar_reconciliacao(monkeypatch, ledger=led.Ledger(supa),
                          encontradas=[CAMPANHA_NA_CONTA])
    pedido = trafego.ReconciliarEntrada(
        item_id="11111111-1111-1111-1111-111111111111",
        customer_id=canario.CONTA, campaign_id="24183717006")

    asyncio.run(trafego.reconciliar_lancamento(pedido, identidade=IDENTIDADE))
    asyncio.run(trafego.reconciliar_lancamento(pedido, identidade=IDENTIDADE))

    primeiro, segundo = [c for _, c in supa.chamadas]
    assert primeiro == segundo


def test_ausencia_na_conta_e_diferente_de_conflito(monkeypatch):
    """Não achou é `achou=False` com quantidade 0 — não é erro, não é conflito."""
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {}})
    _montar_reconciliacao(monkeypatch, ledger=led.Ledger(supa), encontradas=[])

    asyncio.run(trafego.reconciliar_lancamento(
        trafego.ReconciliarEntrada(
            item_id="11111111-1111-1111-1111-111111111111",
            customer_id=canario.CONTA, campaign_id="24183717006"),
        identidade=IDENTIDADE))

    corpo = supa.corpo_de("trafego_ledger_reconciliar")
    assert corpo["p_achou"] is False
    assert corpo["p_quantidade"] == 0
    assert "p_volc_campaign_id" not in corpo


def test_leitura_impossivel_registra_e_nao_move_nada(monkeypatch):
    """`achou=None` é um fato sobre nós, não sobre a conta."""
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {}})

    def ler_falha(**_kw):
        raise trafego.LeituraDaContaIndisponivel("a API não respondeu")

    monkeypatch.setattr(trafego, "_ler_campanha_na_conta", ler_falha)
    monkeypatch.setattr(trafego, "_ledger", lambda: led.Ledger(supa))

    asyncio.run(trafego.reconciliar_lancamento(
        trafego.ReconciliarEntrada(
            item_id="11111111-1111-1111-1111-111111111111",
            customer_id=canario.CONTA, campaign_id="24183717006"),
        identidade=IDENTIDADE))

    corpo = supa.corpo_de("trafego_ledger_reconciliar")
    assert corpo["p_achou"] is None
    assert "p_quantidade" not in corpo


def test_achou_sem_quantidade_e_recusado_pela_fachada():
    """A CHECK do banco já recusa; a fachada recusa antes, com motivo legível."""
    ledger = led.Ledger(SupaDeTeste())
    with pytest.raises(led.LedgerRecusou) as erro:
        asyncio.run(ledger.reconciliar(
            item_id="item-1", metodo="busca_por_id", achou=True,
            verificado_por="tarcisio", plataforma="GOOGLE_ADS",
            conta_externa=canario.CONTA, id_externo="24183717006",
            quantidade=0))
    assert "quantidade" in str(erro.value)


def test_achou_sem_id_externo_e_recusado_pela_fachada():
    ledger = led.Ledger(SupaDeTeste())
    with pytest.raises(led.LedgerRecusou):
        asyncio.run(ledger.reconciliar(
            item_id="item-1", metodo="busca_por_id", achou=True,
            verificado_por="tarcisio", plataforma="GOOGLE_ADS",
            conta_externa=canario.CONTA, id_externo=None, quantidade=1))


def _guardas_da_rota(caminho: str) -> set[str]:
    rota = next(r for r in trafego.router.routes
                if getattr(r, "path", "") == caminho)

    def andar(dep):
        nomes = set()
        for sub in dep.dependencies:
            nomes.add(getattr(sub.call, "__name__", str(sub.call)))
            nomes |= andar(sub)
        return nomes

    return andar(rota.dependant)


def test_reconciliar_exige_a_mesma_identidade_que_subir():
    """Quem reconcilia decide o estado de uma conta de anúncios — é ADMIN.

    Comparado contra `/subir` em vez de contra uma constante: se o portão de
    `/subir` mudar, este teste passa a exigir o portão novo, em vez de continuar
    provando uma regra que o resto do router já abandonou.
    """
    assert "exigir_admin" in _guardas_da_rota("/api/trafego/reconciliar")
    assert (_guardas_da_rota("/api/trafego/reconciliar")
            >= _guardas_da_rota("/api/trafego/subir"))


# ═══════════════════════════════════════════════════════════════════════════
# G. O que a revisão adversarial do Codex Sol reproduziu (31/08/2026)
# ═══════════════════════════════════════════════════════════════════════════

def test_o_instante_do_carimbo_nao_entra_na_identidade(monkeypatch):
    """⚠️ CRÍTICO reproduzido: o relógio decidia a chave E a marca remota.

    `_plano_aprovavel` prometia excluir "campos do ato de aprovar" e
    `impressao_do_plano` prometia não usar "o nome temporizado". As duas
    promessas eram falsas — `carimbo_nome` ficava no dicionário.

    O estrago é a segunda campanha: uma tentativa indeterminada cria a campanha
    com a marca antiga; o operador roda `/provar` de novo, ganha outro carimbo,
    e o MESMO plano passa a ter outra chave (o ledger não reconhece a tentativa)
    e outra marca `VOLC-CANARY-*` (a busca remota não acha a campanha). As duas
    defesas contra duplicidade cegam ao mesmo tempo.
    """
    def identidade(carimbo):
        corpo = trafego.ProvarEntrada(**_payload_da_rota(carimbo_nome=carimbo))
        plano = trafego.plano_do_ledger(corpo, cid=canario.CONTA, mid=canario.MCC)
        chave = dom.chave_de_idempotencia(
            intencao_id="int-1", plataforma="GOOGLE_ADS",
            conta_externa=canario.CONTA, canal="SEARCH", ordem=0, plano=plano)
        impressao = trafego._impressao_aprovavel(
            corpo, cid=canario.CONTA, mid=canario.MCC)
        return chave, impressao, canario.prefixo_da_marca(impressao)

    um_segundo_depois = identidade("20260831_120001")
    assert identidade("20260831_120000") == um_segundo_depois, (
        "o instante do carimbo mudou a identidade do mesmo plano")
    assert "carimbo_nome" not in trafego.plano_do_ledger(
        trafego.ProvarEntrada(**_payload_da_rota()),
        cid=canario.CONTA, mid=canario.MCC)


def test_micros_concorda_com_o_executor_em_vez_de_recusar():
    """⚠️ MÉDIO reproduzido: o ledger recusava o que o executor manda feliz.

    `brief.micros` é `int(round(valor * 1_000_000))`. Dois valores que
    arredondam para o mesmo micro produzem o MESMO payload no Google: eles já
    são o mesmo plano, e dar chaves diferentes a eles é que seria o defeito.
    """
    assert trafego._micros(0.1 + 0.2, "cpc_inicial") == 300_000
    assert trafego._micros(0.3, "cpc_inicial") == 300_000
    assert trafego._micros(10.0, "budget_diario") == 10_000_000

    # ⚠️ E concorda no EMPATE, que é onde as duas convenções divergem.
    # `ROUND_HALF_UP` sobre Decimal dava 120001 para 0.1200005; o executor
    # manda 120000, porque `round()` do Python arredonda para o par e sobre
    # float o empate nem está onde parece. Uma chave que descreve 120001 micros
    # para uma campanha que subiu com 120000 identifica um plano inexistente.
    for valor in (0.1200005, 0.0000005, 1.0000005, 2.5e-6, 0.1 + 0.7):
        assert trafego._micros(valor, "cpc_inicial") == int(round(valor * 1_000_000)), (
            f"o ledger divergiu do executor em {valor!r}")
    # E o que não é dinheiro continua recusado, com motivo.
    for ruim in (0, -1, "abc", float("inf")):
        with pytest.raises(trafego.PlanoIrrepresentavel):
            trafego._micros(ruim, "budget_diario")


def test_motivo_de_dez_espacos_nao_passa_pela_fronteira_http():
    """⚠️ MÉDIO reproduzido: a guarda discordava da guarda que replicava.

    `min_length=10` media a string crua; o executor mede `len(motivo.strip())`.
    Dez espaços passavam, abriam recibo, e morriam lá dentro como indeterminação
    — reabrindo exatamente o buraco que a guarda existia para fechar.
    """
    with pytest.raises(Exception) as erro:
        trafego.SubirEntrada(**_payload_da_rota(), motivo=" " * 10,
                             plano_impressao="a" * 64,
                             confirmar_criacao_pausada=True)
    assert "espaços" in str(erro.value) or "10 caracteres" in str(erro.value)


def test_recusa_com_ledger_quebrado_nao_promete_reenvio(monkeypatch):
    """⚠️ MÉDIO reproduzido: o 502 dizia "pode reenviar" com o recibo em voo.

    Se `fechar_erro` falha, o recibo local continua `em_voo` e a camada 4 vai
    recusar a próxima tentativa. Prometer reenvio ali manda o operador bater
    numa porta que já sabemos trancada.
    """
    from volc_ads import subir as sb

    impressao = _impressao_aprovada(monkeypatch)
    supa = SupaDeTeste(respostas={
        "trafego_ledger_fechar": RuntimeError("o ledger caiu no fechamento")})
    _montar(monkeypatch, ledger=led.Ledger(supa),
            subir=lambda *_a, **_k: _recibo_do_executor(sb.RECUSADO))

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 502
    assert erro.value.detail["estado"] == "recusado"
    assert erro.value.detail["reenvio_permitido"] is False, (
        "prometeu reenvio com o recibo ainda em voo")
    assert erro.value.detail["ledger"]["desfecho"] == "em_voo"


def test_reconciliar_recusa_item_de_outra_conta(monkeypatch):
    """⚠️ ALTO reproduzido: a RPC acha o item só pelo id e não confere o lote.

    Sem esta checagem, trocar um id por engano casaria o item da conta A com a
    campanha da conta B — carimbando no item uma identidade externa que não é
    dele. Não cria campanha nenhuma, e corrompe a procedência de duas.
    """
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {}},
                       conta_do_item="6016739364")  # outra conta
    _montar_reconciliacao(monkeypatch, ledger=led.Ledger(supa),
                          encontradas=[CAMPANHA_NA_CONTA])

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.reconciliar_lancamento(
            trafego.ReconciliarEntrada(
                item_id="11111111-1111-1111-1111-111111111111",
                customer_id=canario.CONTA, campaign_id="24183717006"),
            identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    assert "pertence à conta" in str(erro.value.detail)
    assert [f for f, _ in supa.chamadas] == [], "reconciliou apesar da recusa"


def test_reconciliar_item_inexistente_e_404_e_nao_uma_reconciliacao_vazia(monkeypatch):
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {}},
                       conta_do_item=None)
    _montar_reconciliacao(monkeypatch, ledger=led.Ledger(supa),
                          encontradas=[CAMPANHA_NA_CONTA])

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.reconciliar_lancamento(
            trafego.ReconciliarEntrada(
                item_id="11111111-1111-1111-1111-111111111111",
                customer_id=canario.CONTA, campaign_id="24183717006"),
            identidade=IDENTIDADE))
    assert erro.value.status_code == 404
    assert [f for f, _ in supa.chamadas] == []


def test_reconciliar_por_marca_serve_o_item_que_nao_tem_id_externo(monkeypatch):
    """⚠️ ALTO reproduzido: a saída não servia a quem mais precisa dela.

    O item que fica indeterminado é justamente o que NÃO tem `campaign_id` — a
    chamada não respondeu, então nunca houve `resource_name`. Exigir o id fazia
    da rota uma porta que só abre para quem já não precisa dela.
    """
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {}})
    vistos: list = []

    def ler(**kw):
        vistos.append(kw)
        return (CAMPANHA_NA_CONTA,)

    monkeypatch.setattr(trafego, "_ler_campanha_na_conta", ler)
    monkeypatch.setattr(trafego, "_ledger", lambda: led.Ledger(supa))

    asyncio.run(trafego.reconciliar_lancamento(
        trafego.ReconciliarEntrada(
            item_id="11111111-1111-1111-1111-111111111111",
            customer_id=canario.CONTA, marca="VOLC-CANARY-abc123def456"),
        identidade=IDENTIDADE))

    assert vistos[0]["marca"] == "VOLC-CANARY-abc123def456"
    assert vistos[0]["campaign_id"] is None
    corpo = supa.corpo_de("trafego_ledger_reconciliar")
    # O método vai ao banco como foi de fato — a CHECK de `trafego_verificacao`
    # só aceita os três nomes conhecidos, e mentir aqui corromperia a auditoria.
    assert corpo["p_metodo"] == "busca_por_marca"


def test_reconciliar_sem_criterio_nenhum_e_recusado_na_entrada():
    with pytest.raises(Exception) as erro:
        trafego.ReconciliarEntrada(
            item_id="11111111-1111-1111-1111-111111111111",
            customer_id=canario.CONTA)
    assert "campaign_id" in str(erro.value)


def test_marca_com_gaql_embutido_e_recusada():
    """A marca vira LIKE numa query GAQL: ela não pode carregar query junto."""
    with pytest.raises(ValueError):
        trafego._ler_campanha_na_conta(
            customer_id=canario.CONTA, login_customer_id=canario.MCC,
            marca="VOLC' OR 1=1 --")


def test_marca_com_curinga_de_like_e_recusada():
    """⚠️ `_` é curinga de UM caractere no LIKE do GAQL.

    O regex aceitava `_`, então `marca="____"` virava
    `campaign.name LIKE '____%'` e casava qualquer campanha de quatro letras da
    conta — a reconciliação passaria a "encontrar" campanha alheia e carimbá-la
    no item. A marca real é `VOLC-CANARY-<hex>`: nunca tem sublinhado.
    """
    for ruim in ("____", "VOLC_CANARY_abc", "_"*8):
        with pytest.raises(ValueError):
            trafego._ler_campanha_na_conta(
                customer_id=canario.CONTA, login_customer_id=canario.MCC,
                marca=ruim)
    # E a marca real continua aceita.
    marca_real = canario.prefixo_da_marca("a" * 64)
    assert "_" not in marca_real


def test_duas_campanhas_no_criterio_nao_se_resolvem_sozinhas(monkeypatch):
    """⚠️ `quantidade_encontrada >= 2` é duplicidade JÁ CONSUMADA.

    O schema diz isso com todas as letras. Escolher `encontradas[0]` seria a
    máquina decidindo qual das duas campanhas é a certa e carimbando a outra
    como se não existisse. A leitura fica registrada; o carimbo não acontece.
    """
    supa = SupaDeTeste(respostas={"trafego_ledger_reconciliar": {}})
    outra = {"campaign_id": "24183717007", "campaign_name": "VOLC-CANARY-outra",
             "status": "PAUSED"}
    _montar_reconciliacao(monkeypatch, ledger=led.Ledger(supa),
                          encontradas=[CAMPANHA_NA_CONTA, outra])

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.reconciliar_lancamento(
            trafego.ReconciliarEntrada(
                item_id="11111111-1111-1111-1111-111111111111",
                customer_id=canario.CONTA, marca="VOLC-CANARY-abc123def456"),
            identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    assert erro.value.detail["estado"] == "duplicidade_consumada"
    assert len(erro.value.detail["campanhas"]) == 2
    # A leitura FICA registrada — e como ignorância, que é o que ela é: a
    # máquina não sabe qual é a certa, e `achou=None` não move nada.
    corpo = supa.corpo_de("trafego_ledger_reconciliar")
    assert corpo["p_achou"] is None
    assert "p_volc_campaign_id" not in corpo
