"""O ledger de lançamento: o que precisa estar gravado antes de a rede ser tocada.

Estes testes existem por causa de um defeito medido, não de uma preocupação
abstrata. Até 31/08/2026 o `/subir` chamava o Google e SÓ DEPOIS gravava — em
best-effort, sem teste nenhum. Se a resposta não chegasse, não havia registro
local de que uma chamada tinha saído, e a única defesa contra a segunda campanha
era uma leitura remota que também podia falhar.

O que cada bloco aqui prova:

* erro de persistência bloqueia o mutate (e não o contrário);
* o recibo `em_voo` está gravado ANTES da fronteira;
* ausência de resposta vira `indeterminado` e NUNCA oferece reenvio;
* erro respondido pela plataforma é outra coisa, e continua reentrável;
* sucesso sem id externo não é sucesso;
* a campanha nasce PAUSED no payload que de fato sai.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import asyncio
import socket

import pytest
from fastapi import HTTPException

from app.trafego import canario, ledger as led
from app.routers import trafego
from app.seguranca.identidade import Identidade

from test_trafego_canario import (  # noqa: E402  (fixtures herméticas já provadas)
    _instalar_portas_hermeticas,
    _payload_da_rota,
)


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    def recusar_rede(_socket, _address):
        pytest.fail("teste do ledger tentou abrir uma conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


IDENTIDADE = Identidade(
    sub="operador-sub-1", email="tarcisio@agenciavolc.com.br",
    papel="ADMIN", origem="teste",
)


class LedgerDeTeste:
    """Um ledger que registra a ORDEM dos atos — é a ordem que está sob prova."""

    def __init__(self, *, diario: list, disponivel: bool = True,
                 erro_no_despachar: Exception | None = None,
                 erro_no_abrir: Exception | None = None):
        self.diario = diario
        self._disponivel = disponivel
        self._erro_no_despachar = erro_no_despachar
        self._erro_no_abrir = erro_no_abrir

    @property
    def disponivel(self) -> bool:
        return self._disponivel

    async def abrir(self, **kw):
        self.diario.append(("abrir", kw))
        if self._erro_no_abrir:
            raise self._erro_no_abrir
        return {"idempotency_key": "volc-ga-0000-abcdef0123456789",
                "item_id": "item-1", "lote_id": "lote-1",
                "intencao_id": "int-1", "reaproveitado": False}

    async def despachar(self, **kw):
        self.diario.append(("despachar", kw))
        if self._erro_no_despachar:
            raise self._erro_no_despachar
        return led.Despacho(item_id="item-1", lote_id="lote-1",
                            recibo_id="recibo-1", tentativa=1)

    async def fechar_sucesso(self, **kw):
        self.diario.append(("fechar_sucesso", kw))
        return {"id_externo": kw["id_externo"], "item_estado": "criada_pausada"}

    async def fechar_erro(self, **kw):
        self.diario.append(("fechar_erro", kw))
        return {}

    async def fechar_sem_resposta(self, **kw):
        self.diario.append(("fechar_sem_resposta", kw))
        return {}


def _montar(monkeypatch, *, ledger: LedgerDeTeste, subir):
    """Instala as portas herméticas, o ledger de teste e um `subir` observável."""
    from volc_ads import subir as sb

    planos = _instalar_portas_hermeticas(monkeypatch)
    monkeypatch.setattr(trafego, "_ledger", lambda: ledger)
    monkeypatch.setattr(canario, "campanhas_com_marca",
                        lambda **_: ())
    monkeypatch.setattr(canario, "campanhas_com_destino",
                        lambda **_: ())
    monkeypatch.setattr(sb, "subir", subir)

    async def _sem_registro_legado(*_a, **_k):
        return ""

    monkeypatch.setattr(trafego, "_registrar_campanha", _sem_registro_legado)
    return planos


def _corpo(prova_impressao: str):
    return trafego.SubirEntrada(**{
        **_payload_da_rota(),
        "motivo": "canário pausado com aprovação humana",
        "plano_impressao": prova_impressao,
        "confirmar_criacao_pausada": True,
    })


def _impressao_aprovada(monkeypatch):
    """Roda a prova de verdade e devolve o selo que ela emitiu."""
    _instalar_portas_hermeticas(monkeypatch)
    prova = asyncio.run(trafego.provar(trafego.ProvarEntrada(**_payload_da_rota()),
                                       identidade=IDENTIDADE))
    return prova["autorizacao"]["plano_impressao"]


def _recibo_criado(campaign_id: str = "24183717006", *, com_id: bool = True):
    """Um `Recibo` do executor com a forma que `projecao.recibo` de fato lê.

    Faltar um campo aqui daria `AttributeError` no meio da rota — e um dublê que
    não tem a forma do original prova a rota errada.
    """
    criados = ()
    if com_id:
        criados = (SimpleNamespace(
            posicao=0, tipo="campaign_result",
            resource_name=f"customers/5478096539/campaigns/{campaign_id}"),)
    return SimpleNamespace(
        estado="CRIADA", carimbo="20260831_120000",
        customer_id=canario.CONTA, login_customer_id=canario.MCC,
        nome_campanha="VOLC-CANARY-teste", n_operacoes=72,
        impressao="a" * 64, motivo="canário pausado com aprovação humana",
        criados=criados, request_id="req-1", linhagem=(), falha=None,
        explicacao="",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Erro de persistência BLOQUEIA o mutate
# ═══════════════════════════════════════════════════════════════════════════

def test_recusa_do_ledger_impede_qualquer_chamada_que_muta(monkeypatch):
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    def subir_proibido(*_a, **_k):
        pytest.fail("o mutate saiu mesmo com o ledger tendo recusado")

    _montar(monkeypatch,
            ledger=LedgerDeTeste(
                diario=diario,
                erro_no_despachar=led.LedgerRecusou(
                    "o item ja tem 1 recibo(s) sem desfecho", codigo="23001")),
            subir=subir_proibido)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    assert "recibo(s) sem desfecho" in str(erro.value.detail)
    assert "Nada foi enviado ao Google" in str(erro.value.detail)
    assert [ato for ato, _ in diario] == ["abrir", "despachar"]


def test_ledger_nao_configurado_recusa_a_escrita_em_vez_de_seguir_sem_recibo(monkeypatch):
    """⚠️ Ausência de ledger é RECUSA, não permissão.

    `/subir` não tem modo dry: ele cria campanha de verdade. Seguir sem ledger
    produziria exatamente o objeto que este trabalho existe para eliminar — uma
    campanha que existe na conta, não existe aqui, e que ninguém consegue
    reconciliar depois porque não há chave, item nem recibo para procurar.
    """
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    def subir_proibido(*_a, **_k):
        pytest.fail("o mutate saiu com o ledger sequer configurado")

    _montar(monkeypatch,
            ledger=LedgerDeTeste(diario=diario, disponivel=False),
            subir=subir_proibido)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 503
    assert "não está configurado" in str(erro.value.detail)
    assert "NADA foi enviado ao Google" in str(erro.value.detail)
    assert diario == [], "o ledger indisponível não deveria ter sido chamado"


def test_ledger_fora_do_ar_tambem_impede_o_mutate(monkeypatch):
    """Indisponível não é permissão. Uma campanha sem recibo é irreconciliável."""
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    def subir_proibido(*_a, **_k):
        pytest.fail("o mutate saiu com o ledger fora do ar")

    _montar(monkeypatch,
            ledger=LedgerDeTeste(
                diario=diario,
                erro_no_abrir=led.LedgerIndisponivel("o ledger não respondeu")),
            subir=subir_proibido)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 503
    assert "NADA foi enviado ao Google" in str(erro.value.detail)


# ═══════════════════════════════════════════════════════════════════════════
# 2. O recibo em voo existe ANTES da fronteira
# ═══════════════════════════════════════════════════════════════════════════

def test_o_recibo_em_voo_e_gravado_antes_da_chamada_que_muta(monkeypatch):
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    def subir(preparo, *, motivo):
        diario.append(("MUTATE", motivo))
        return _recibo_criado()

    _montar(monkeypatch, ledger=LedgerDeTeste(diario=diario), subir=subir)
    saida = asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    atos = [ato for ato, _ in diario]
    assert atos.index("despachar") < atos.index("MUTATE"), (
        "a chamada que muta saiu antes de o recibo em voo estar gravado")
    assert atos == ["abrir", "despachar", "MUTATE", "fechar_sucesso"]
    assert saida["recibo"]["ledger"]["desfecho"] == "sucesso"
    assert saida["recibo"]["ledger"]["id_externo"] == "24183717006"


def test_a_aprovacao_persistida_carrega_a_identidade_e_a_impressao(monkeypatch):
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []
    _montar(monkeypatch, ledger=LedgerDeTeste(diario=diario),
            subir=lambda preparo, *, motivo: _recibo_criado())
    asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    despachar = next(kw for ato, kw in diario if ato == "despachar")
    assert despachar["aprovacao_impressao"] == impressao
    assert despachar["aprovado_por_sub"] == "operador-sub-1"
    assert despachar["conta_externa"] == canario.CONTA
    assert despachar["canal"] == "SEARCH"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Sem resposta ≠ falha. E não oferece reenvio.
# ═══════════════════════════════════════════════════════════════════════════

def test_sem_resposta_vira_indeterminado_e_recusa_reenvio(monkeypatch):
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    def subir_sem_resposta(*_a, **_k):
        raise TimeoutError("deadline exceeded")  # sem `.failure`: transporte

    _montar(monkeypatch, ledger=LedgerDeTeste(diario=diario),
            subir=subir_sem_resposta)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 504
    detalhe = erro.value.detail
    assert detalhe["estado"] == "indeterminado"
    assert detalhe["reenvio_permitido"] is False
    assert "NÃO reenvie" in detalhe["mensagem"]
    assert detalhe["recibo_id"] == "recibo-1"
    assert [ato for ato, _ in diario] == [
        "abrir", "despachar", "fechar_sem_resposta"]
    assert "fechar_erro" not in [ato for ato, _ in diario], (
        "um timeout foi registrado como falha, que é o convite a reenviar")


def test_erro_respondido_pelo_google_e_falha_confirmada_e_nao_ignorancia(monkeypatch):
    """`failure` preenchido significa que o servidor processou e recusou."""
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    class RecusaDoGoogle(Exception):
        failure = SimpleNamespace(errors=())
        request_id = "req-1"

    def subir_recusado(*_a, **_k):
        raise RecusaDoGoogle("headline excede 30 caracteres")

    _montar(monkeypatch, ledger=LedgerDeTeste(diario=diario), subir=subir_recusado)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 502
    atos = [ato for ato, _ in diario]
    assert atos == ["abrir", "despachar", "fechar_erro"]
    assert "fechar_sem_resposta" not in atos, (
        "uma recusa respondida foi tratada como ignorância, e o item ficaria "
        "preso em indeterminado sem motivo")


def test_trava_de_escrita_fechada_nao_vira_indeterminado(monkeypatch):
    """A trava dispara antes da rede: é falha confirmada, e reentrável."""
    from volc_ads import subir as sb

    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    def subir_travado(*_a, **_k):
        raise sb.TravaAberta("a trava de escrita está fechada")

    _montar(monkeypatch, ledger=LedgerDeTeste(diario=diario), subir=subir_travado)

    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert erro.value.status_code == 409
    assert [ato for ato, _ in diario] == ["abrir", "despachar", "fechar_erro"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Sucesso sem id externo não é sucesso
# ═══════════════════════════════════════════════════════════════════════════

def test_criou_sem_devolver_id_externo_fecha_como_sem_resposta(monkeypatch):
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    def subir_mudo(*_a, **_k):
        return _recibo_criado(com_id=False)

    _montar(monkeypatch, ledger=LedgerDeTeste(diario=diario), subir=subir_mudo)
    saida = asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    atos = [ato for ato, _ in diario]
    assert "fechar_sucesso" not in atos
    assert "fechar_sem_resposta" in atos
    assert saida["recibo"]["ledger"]["desfecho"] == "sem_resposta"
    assert "reconcilie" in saida["recibo"]["ledger"]["motivo"]


def test_falha_ao_fechar_deixa_o_recibo_em_voo_e_diz_isso(monkeypatch):
    """Perder a escrita do fechamento é ruim; perder o rastro seria pior."""
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []

    class LedgerQueQuebraNoFim(LedgerDeTeste):
        async def fechar_sucesso(self, **kw):
            self.diario.append(("fechar_sucesso", kw))
            raise led.LedgerIndisponivel("o ledger caiu depois do mutate")

    _montar(monkeypatch, ledger=LedgerQueQuebraNoFim(diario=diario),
            subir=lambda preparo, *, motivo: _recibo_criado())
    saida = asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    ledger_saida = saida["recibo"]["ledger"]
    assert ledger_saida["registrado"] is False
    assert ledger_saida["desfecho"] == "em_voo"
    assert ledger_saida["id_externo"] == "24183717006"
    assert "Reconcilie" in ledger_saida["motivo"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. A campanha nasce PAUSED — no payload que de fato sai
# ═══════════════════════════════════════════════════════════════════════════

def test_a_campanha_que_sai_para_a_conta_nasce_pausada(monkeypatch):
    impressao = _impressao_aprovada(monkeypatch)
    diario: list = []
    estados: list = []

    def subir(preparo, *, motivo):
        for op in preparo.operacoes:
            if op._pb.WhichOneof("operation") == "campaign_operation":
                estados.append(
                    getattr(op.campaign_operation.create.status, "name",
                            str(op.campaign_operation.create.status)))
        return _recibo_criado()

    _montar(monkeypatch, ledger=LedgerDeTeste(diario=diario), subir=subir)
    asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert estados, "nenhuma operação de campanha chegou à fronteira"
    assert set(estados) == {"PAUSED"}, (
        f"a campanha não nasceu pausada: {estados}")
    abrir = next(kw for ato, kw in diario if ato == "abrir")
    assert abrir["blueprint_corpo"]["cria_pausada"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 6. O módulo do ledger, isolado
# ═══════════════════════════════════════════════════════════════════════════

def test_a_intencao_e_deterministica_entre_tentativas():
    argumentos = dict(plataforma="GOOGLE_ADS", conta_externa="5478096539",
                      objetivo="leads", rotulo="Maquininha",
                      declarada_com_base_em="oportunidade:1")
    assert led.intencao_determinista(**argumentos) == \
        led.intencao_determinista(**argumentos)
    outra = {**argumentos, "conta_externa": "8017851692"}
    assert led.intencao_determinista(**argumentos) != \
        led.intencao_determinista(**outra), (
            "a mesma intenção em outra conta não pode ter o mesmo id")


def test_a_identidade_da_instancia_e_derivada_e_nao_sorteada():
    a = led.volc_campaign_id_de(plataforma="GOOGLE_ADS",
                                conta_externa="5478096539",
                                id_externo="24183717006")
    b = led.volc_campaign_id_de(plataforma="GOOGLE_ADS",
                                conta_externa="5478096539",
                                id_externo="24183717006")
    assert a == b, "duas leituras do mesmo recurso criariam duas identidades"
    assert a != led.volc_campaign_id_de(plataforma="GOOGLE_ADS",
                                       conta_externa="5478096539",
                                       id_externo="99999999999")


@pytest.mark.parametrize(
    ("codigo", "e_recusa"),
    [
        ("23001", True),    # restrict_violation — a guarda disparou
        ("23514", True),    # CHECK violado
        ("22023", True),    # argumento recusado pela própria função
        ("P0001", True),    # RAISE genérico
        ("P0002", True),    # no_data_found
        ("22P02", False),   # literal malformado: defeito de quem chamou
        ("42P01", False),   # tabela inexistente: a migration não está aplicada
        ("53300", False),   # sem conexão disponível: infraestrutura
        ("", False),
    ],
)
def test_o_ledger_separa_recusa_de_regra_de_banco_quebrado(codigo, e_recusa):
    """`22023` e `22P02` são da mesma classe e significam o oposto.

    Sem essa separação, "a guarda recusou" e "o banco está fora do ar" chegariam
    iguais a quem chama — e as duas exigem reações opostas.
    """
    assert led._e_recusa_de_regra(codigo) is e_recusa


def test_achou_nulo_nao_e_podado_do_corpo_da_reconciliacao():
    """`None` em `achou` é uma afirmação: "não consegui ler"."""
    enviados: dict = {}

    class SupaDeTeste:
        enabled = True

        async def rpc(self, funcao, argumentos):
            enviados.update({"funcao": funcao, "corpo": argumentos})
            return {"achou": None}

    ledger = led.Ledger(SupaDeTeste())
    asyncio.run(ledger.reconciliar(
        item_id="item-1", metodo="listagem_da_conta", achou=None,
        verificado_por="operador", plataforma="GOOGLE_ADS",
        conta_externa="5478096539", motivo="a conta não respondeu"))

    assert enviados["funcao"] == "trafego_ledger_reconciliar"
    assert "p_achou" in enviados["corpo"], (
        "`achou=None` foi podado e viraria o DEFAULT da função — ausência de "
        "leitura teria virado ausência de verificação")
    assert enviados["corpo"]["p_achou"] is None
    assert "p_volc_campaign_id" not in enviados["corpo"]
