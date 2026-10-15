"""Ads: plano de mensuração compartilhado, pré-checagens juntas, uma montagem.

Hermético como `test_trafego_plano_persistido.py`: o socket é recusado em todo
teste deste arquivo, e as portas de saída (Google, Supabase, destino público)
são dublês. O que é REAL é o que se quer provar — a rota, a montagem, o portão
do conjunto pago, o builder de Search e a primitiva de leitura compartilhada.

As provas, na ordem da missão:

  1-5   o plano de mensuração: uma leitura por chave em voo, cache curto só de
        plano lido por inteiro, nada de `None`/timeout/falha no cache, chaves
        isoladas e `/subir` sempre fresco;
  6-9   as duas pré-checagens de `/subir` correm juntas, falham fechado, recusam
        duplicidade antes do ledger e levam o canal;
  10-14 `/provar` e `/subir` montam pelo MESMO montador e produzem a mesma
        impressão que o código anterior produzia (caracterização gravada antes
        da refatoração), e as recusas HTTP não viram 500.
"""
from __future__ import annotations

import asyncio
import socket
import threading

import pytest
from fastapi import HTTPException

from app.routers import trafego
from app.seguranca.identidade import Identidade
from app.trafego import canario, plano_mensuracao as pm

from test_trafego_canario import (  # noqa: E402
    _instalar_portas_hermeticas,
    _payload_da_rota,
)
from test_trafego_plano_persistido import _plano_lido  # noqa: E402

IDENTIDADE = Identidade(sub="operador-sub-1", email="teste@agenciavolc.com.br",
                        papel="ADMIN", origem="sessao")

#: A função REAL, guardada antes de qualquer dublê. `_instalar_portas_hermeticas`
#: troca `_plano_de_mensuracao` por um que devolve `None`; quem quer medir a
#: leitura compartilhada devolve esta e dubla só `mef.ler_plano`.
_PLANO_REAL = trafego._plano_de_mensuracao

#: ⚠️ CARACTERIZAÇÃO, gravada contra o código ANTERIOR à montagem comum
#: (HEAD 959ce78), com o payload de `_payload_da_rota()`. Se a refatoração
#: mudasse um byte do que vai ao `validate_only`, esta impressão mudaria.
IMPRESSAO_SEARCH_ANTES = (
    "b1d508a5405baed7a9474b77249cc434df80cf7016419ddffc4dbcb404edb5a0")
POSITIVAS_SEARCH_ANTES = [("guia do saque anual", "PHRASE", "")]


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    def recusar_rede(_socket, _address):
        pytest.fail("teste de leitura compartilhada tentou abrir conexão")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


def _corpo_de_subida(impressao: str, **mudancas) -> "trafego.SubirEntrada":
    return trafego.SubirEntrada(**{
        **_payload_da_rota(**mudancas),
        "motivo": "canário pausado com aprovação humana",
        "plano_impressao": impressao,
        "confirmar_criacao_pausada": True,
    })


def _espiar_preparo(monkeypatch) -> list:
    """Guarda o que cada `sb.preparar` recebeu e devolveu, sem trocar nada."""
    from volc_ads import subir as sb

    vistos: list = []
    original = sb.preparar

    def preparar(cid, brief, **k):
        preparo = original(cid, brief, **k)
        vistos.append({
            "canal": k.get("canal"),
            "impressao": preparo.selo.impressao if preparo.selo else None,
            "positivas": sorted(
                (c.texto, c.match_type, c.grupo or "")
                for c in getattr(brief, "criterios", []) if not c.negativa),
            "url_final": brief.url_final,
        })
        return preparo

    monkeypatch.setattr(sb, "preparar", preparar)
    return vistos


def _sem_efeito_de_escrita(monkeypatch) -> dict:
    """Ledger e mutate que FALHAM o teste se forem tocados."""
    from volc_ads import subir as sb

    tocados = {"ledger": 0, "mutate": 0}

    class _LedgerProibido:
        disponivel = True

        async def abrir(self, **_k):
            tocados["ledger"] += 1
            pytest.fail("o ledger foi aberto antes de a recusa acontecer")

        async def despachar(self, **_k):
            tocados["ledger"] += 1
            pytest.fail("o ledger despachou antes de a recusa acontecer")

    def _mutate(*_a, **_k):
        tocados["mutate"] += 1
        pytest.fail("o mutate foi alcançado")

    monkeypatch.setattr(trafego, "_ledger", lambda: _LedgerProibido())
    monkeypatch.setattr(sb, "subir", _mutate)
    return tocados


# ═══════════════════════════════════════════════════════════════════════════
# 10 · CARACTERIZAÇÃO — a mesma impressão, canal e positivas de antes
# ═══════════════════════════════════════════════════════════════════════════


def test_caracterizacao_provar_e_reprova_de_subir_selam_o_mesmo_plano(monkeypatch):
    _instalar_portas_hermeticas(monkeypatch)
    vistos = _espiar_preparo(monkeypatch)
    _sem_efeito_de_escrita(monkeypatch)

    prova = asyncio.run(trafego.provar(
        trafego.ProvarEntrada(**_payload_da_rota()), identidade=IDENTIDADE))
    impressao = prova["autorizacao"]["plano_impressao"]
    assert impressao, prova["preparo"]

    duplicada = ({"campaign_id": "ja-existe", "campaign_name": "x"},)
    monkeypatch.setattr(canario, "campanhas_com_marca", lambda **_: duplicada)
    monkeypatch.setattr(canario, "campanhas_com_destino", lambda **_: ())
    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(_corpo_de_subida(impressao),
                                  identidade=IDENTIDADE))
    assert erro.value.status_code == 409

    assert len(vistos) == 2
    assert vistos[0] == vistos[1], "a reprova de /subir selou outro plano"
    assert vistos[0]["canal"] == "SEARCH"
    assert vistos[0]["impressao"] == impressao
    assert impressao == IMPRESSAO_SEARCH_ANTES
    assert vistos[0]["positivas"] == POSITIVAS_SEARCH_ANTES


# ═══════════════════════════════════════════════════════════════════════════
# 1-5 · o plano de mensuração compartilhado
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ Ids FICTÍCIOS: nenhuma conta real entra numa fixture nova.

CID, MID = "1234567890", "9876543210"
CHAVE = "c" * 64


def _plano_integro() -> pm.PlanoDeMensuracao:
    return _plano_lido(customer_id=CID, login_customer_id=MID,
                       chave_intencao=CHAVE)


def _plano_com_leitura_falha() -> pm.PlanoDeMensuracao:
    base = _plano_integro()
    return pm.montar(customer_id=CID, login_customer_id=MID,
                     meta_efetiva=base.meta_efetiva, acoes=(),
                     acoes_estado=pm.FALHOU, chave_intencao=CHAVE)


class _LeitorDePlano:
    """Dublê de `mef.ler_plano`: conta chamadas e pode segurar a thread."""

    def __init__(self):
        self.chamadas: list = []
        self.porta: threading.Event | None = None
        self.devolve = _plano_integro()
        self.erro: Exception | None = None
        self._lock = threading.Lock()

    def __call__(self, cid, *, login_customer_id, campaign_id=None,
                 chave_intencao=None, **_):
        with self._lock:
            self.chamadas.append((cid, login_customer_id, campaign_id,
                                  chave_intencao))
        if self.porta is not None:
            assert self.porta.wait(5), "a porta do teste nunca abriu"
        if self.erro is not None:
            raise self.erro
        return self.devolve


@pytest.fixture
def ler_plano(monkeypatch):
    from app.trafego import metas_efetivas as mef

    leitor = _LeitorDePlano()
    monkeypatch.setattr(mef, "ler_plano", leitor)
    monkeypatch.setattr(trafego, "_plano_de_mensuracao", _PLANO_REAL)
    monkeypatch.setattr(trafego, "_ttl_do_plano_s", lambda: 45.0)
    return leitor


async def _ate(condicao, *, voltas: int = 300):
    for _ in range(voltas):
        if condicao():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("a condição esperada não aconteceu")


def _ler(**k):
    k.setdefault("chave_intencao", CHAVE)
    return trafego._plano_de_mensuracao(CID, MID, **k)


async def test_1_cliques_concorrentes_iguais_fazem_uma_unica_leitura(ler_plano):
    ler_plano.porta = threading.Event()
    cliques = [asyncio.ensure_future(_ler(reaproveitar=True)) for _ in range(5)]
    await _ate(lambda: len(ler_plano.chamadas) == 1)
    for _ in range(5):
        await asyncio.sleep(0)
    ler_plano.porta.set()
    planos = await asyncio.gather(*cliques)
    assert len(ler_plano.chamadas) == 1
    assert all(p is planos[0] for p in planos)
    tel = trafego._LEITURA_DO_PLANO.telemetria()
    assert (tel["miss"], tel["compartilhada"]) == (1, 4)


async def test_2_cache_hit_evita_as_consultas_seguintes(ler_plano):
    primeiro = await _ler(reaproveitar=True)
    segundo = await _ler(reaproveitar=True)
    assert segundo is primeiro
    assert len(ler_plano.chamadas) == 1
    assert trafego._LEITURA_DO_PLANO.telemetria()["hit"] == 1


async def test_2b_o_ttl_vencido_rele(ler_plano, monkeypatch):
    agora = [0.0]
    monkeypatch.setattr(trafego, "_LEITURA_DO_PLANO",
                        trafego.lcomp.LeituraCompartilhada(
                            "plano-teste", max_entradas=8,
                            relogio=lambda: agora[0]))
    await _ler(reaproveitar=True)
    agora[0] = 44.0
    await _ler(reaproveitar=True)
    assert len(ler_plano.chamadas) == 1
    agora[0] = 46.0
    await _ler(reaproveitar=True)
    assert len(ler_plano.chamadas) == 2


@pytest.mark.parametrize("configurado,efetivo", [
    (45, 45.0), (30, 30.0), (3600, 60.0), (-5, 0.0), (None, 0.0)])
def test_2c_o_ttl_do_plano_e_curto_e_recortado(monkeypatch, configurado, efetivo):
    from types import SimpleNamespace

    monkeypatch.setattr(trafego, "get_settings", lambda: SimpleNamespace(
        trafego_plano_mensuracao_cache_ttl_s=configurado))
    assert trafego._ttl_do_plano_s() == efetivo


def test_2d_o_default_do_ttl_esta_entre_30_e_60_segundos():
    from app.config import Settings

    assert 30 <= Settings(_env_file=None).trafego_plano_mensuracao_cache_ttl_s <= 60


@pytest.mark.parametrize("caso", ["none", "excecao", "leitura_falhou"])
async def test_3_none_falha_e_plano_parcial_nao_entram_no_cache(ler_plano, caso):
    if caso == "none":
        ler_plano.devolve = None
    elif caso == "excecao":
        ler_plano.erro = RuntimeError("RATE_EXCEEDED")
    else:
        ler_plano.devolve = _plano_com_leitura_falha()
    primeiro = await _ler(reaproveitar=True)
    await _ler(reaproveitar=True)
    assert len(ler_plano.chamadas) == 2, "um desfecho sem conclusão foi guardado"
    if caso == "leitura_falhou":
        # A SEMÂNTICA não muda: o plano com leitura falha chega inteiro à
        # prontidão, com o estado `falhou` — ele só não é guardado.
        assert primeiro.acoes_estado == pm.FALHOU
    else:
        assert primeiro is None
    assert trafego._LEITURA_DO_PLANO.telemetria()["entradas"] == 0


async def test_3b_vazio_medido_e_conclusao_e_se_guarda(ler_plano):
    """Plano lido por inteiro e `completo=False` NÃO é falha."""
    base = _plano_integro()
    ler_plano.devolve = pm.montar(customer_id=CID, login_customer_id=MID,
                                  meta_efetiva=base.meta_efetiva, acoes=(),
                                  acoes_estado=pm.VAZIO_CONFIRMADO,
                                  chave_intencao=CHAVE)
    assert ler_plano.devolve.completo is False
    await _ler(reaproveitar=True)
    await _ler(reaproveitar=True)
    assert len(ler_plano.chamadas) == 1


async def test_3c_depois_do_timeout_a_leitura_unica_termina_e_preenche_o_cache(
        ler_plano, monkeypatch):
    """O defeito medido: dez cliques, dez threads iguais. Agora: uma."""
    monkeypatch.setattr(trafego, "TIMEOUT_PLANO_S", 0.05)
    ler_plano.porta = threading.Event()
    assert await _ler(reaproveitar=True) is None      # o 1º clique desiste
    assert await _ler(reaproveitar=True) is None      # o 2º pega carona e desiste
    assert len(ler_plano.chamadas) == 1, "o segundo clique abriu outra thread"
    ler_plano.porta.set()
    await _ate(lambda: trafego._LEITURA_DO_PLANO.telemetria()["em_voo"] == 0)
    terceiro = await _ler(reaproveitar=True)
    assert terceiro is ler_plano.devolve
    assert len(ler_plano.chamadas) == 1


async def test_3d_timeout_que_termina_em_erro_nao_preenche_nada(ler_plano, monkeypatch):
    monkeypatch.setattr(trafego, "TIMEOUT_PLANO_S", 0.05)
    ler_plano.porta = threading.Event()
    ler_plano.erro = RuntimeError("DEADLINE_EXCEEDED")
    assert await _ler(reaproveitar=True) is None
    ler_plano.porta.set()
    await _ate(lambda: trafego._LEITURA_DO_PLANO.telemetria()["em_voo"] == 0)
    ler_plano.erro, ler_plano.porta = None, None
    assert await _ler(reaproveitar=True) is ler_plano.devolve
    assert len(ler_plano.chamadas) == 2


async def test_4_chaves_distintas_nao_compartilham(ler_plano):
    await _ler(reaproveitar=True)
    await trafego._plano_de_mensuracao("1234567891", MID, chave_intencao=CHAVE,
                                       reaproveitar=True)
    await trafego._plano_de_mensuracao(CID, "9876543211", chave_intencao=CHAVE,
                                       reaproveitar=True)
    await _ler(campaign_id="555", reaproveitar=True)
    await _ler(chave_intencao="d" * 64, reaproveitar=True)
    assert len(ler_plano.chamadas) == 5
    assert len(set(ler_plano.chamadas)) == 5


async def test_5_o_default_e_fresco_e_ignora_cache_e_leitura_em_voo(ler_plano):
    await _ler(reaproveitar=True)
    await _ler()                                   # o caminho de /subir
    assert len(ler_plano.chamadas) == 2, "a leitura fresca usou o cache"

    trafego._LEITURA_DO_PLANO.limpar()
    ler_plano.chamadas.clear()
    ler_plano.porta = threading.Event()
    em_voo = asyncio.ensure_future(_ler(reaproveitar=True))
    await _ate(lambda: len(ler_plano.chamadas) == 1)
    fresca = asyncio.ensure_future(_ler())
    await _ate(lambda: len(ler_plano.chamadas) == 2)
    ler_plano.porta.set()
    await asyncio.gather(em_voo, fresca)
    assert len(ler_plano.chamadas) == 2, "a leitura fresca pegou carona"


def test_5b_provar_reaproveita_e_subir_le_fresco_pela_rota(monkeypatch):
    """Pelas ROTAS: duas provas, uma leitura; a subida relê."""
    _instalar_portas_hermeticas(monkeypatch)
    _sem_efeito_de_escrita(monkeypatch)
    from app.trafego import metas_efetivas as mef

    leitor = _LeitorDePlano()
    # A conta do plano é a da rota (`_payload_da_rota`), não uma nova.
    leitor.devolve = _plano_lido(chave_intencao=None)
    monkeypatch.setattr(mef, "ler_plano", leitor)
    monkeypatch.setattr(trafego, "_plano_de_mensuracao", _PLANO_REAL)
    monkeypatch.setattr(trafego, "_ttl_do_plano_s", lambda: 45.0)

    corpo = trafego.ProvarEntrada(**_payload_da_rota())
    prova = asyncio.run(trafego.provar(corpo, identidade=IDENTIDADE))
    asyncio.run(trafego.provar(trafego.ProvarEntrada(**_payload_da_rota()),
                               identidade=IDENTIDADE))
    assert len(leitor.chamadas) == 1, "a segunda prova releu o plano"

    monkeypatch.setattr(canario, "campanhas_com_marca", lambda **_: ())
    monkeypatch.setattr(canario, "campanhas_com_destino", lambda **_: ())
    from types import SimpleNamespace

    monkeypatch.setattr(trafego, "_repositorio_de_plano",
                        lambda: SimpleNamespace(habilitado=False))
    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(
            _corpo_de_subida(prova["autorizacao"]["plano_impressao"]),
            identidade=IDENTIDADE))
    # Parou na falta do repositório do plano — DEPOIS de ler o plano.
    assert erro.value.status_code == 503
    assert "repositório do plano" in str(erro.value.detail)
    assert len(leitor.chamadas) == 2, "/subir usou o plano guardado por /provar"


# ═══════════════════════════════════════════════════════════════════════════
# 6-9 · as pré-checagens remotas de /subir
# ═══════════════════════════════════════════════════════════════════════════


def _subir_ate_as_prechecagens(monkeypatch, marca_fn, destino_fn):
    _instalar_portas_hermeticas(monkeypatch)
    tocados = _sem_efeito_de_escrita(monkeypatch)
    prova = asyncio.run(trafego.provar(
        trafego.ProvarEntrada(**_payload_da_rota()), identidade=IDENTIDADE))
    monkeypatch.setattr(canario, "campanhas_com_marca", marca_fn)
    monkeypatch.setattr(canario, "campanhas_com_destino", destino_fn)
    with pytest.raises(HTTPException) as erro:
        asyncio.run(trafego.subir(
            _corpo_de_subida(prova["autorizacao"]["plano_impressao"]),
            identidade=IDENTIDADE))
    return erro.value, tocados


def test_6_as_duas_prechecagens_se_sobrepoem(monkeypatch):
    """Uma barreira de DOIS: só abre se as duas estiverem em curso juntas.

    Na versão sequencial, a primeira esperaria a segunda que nunca começa, a
    barreira quebraria em 2 s e a rota responderia 503.
    """
    barreira = threading.Barrier(2, timeout=2)
    vistos: dict = {}

    def marca(**_k):
        barreira.wait()
        vistos["marca"] = True
        return ({"campaign_id": "111", "campaign_name": "x"},)

    def destino(*, canal, **_k):
        barreira.wait()
        vistos["destino"] = canal
        return ()

    erro, tocados = _subir_ate_as_prechecagens(monkeypatch, marca, destino)
    assert erro.status_code == 409, erro.detail
    assert vistos == {"marca": True, "destino": "SEARCH"}
    assert tocados == {"ledger": 0, "mutate": 0}


@pytest.mark.parametrize("quem_falha", ["marca", "destino"])
def test_7_falha_de_qualquer_uma_e_503_sem_abandonar_a_outra(monkeypatch, quem_falha):
    terminou = threading.Event()

    def _falha(**_k):
        raise RuntimeError("UNAVAILABLE")

    def _lenta(**_k):
        threading.Event().wait(0.05)
        terminou.set()
        return ()

    marca, destino = (_falha, _lenta) if quem_falha == "marca" else (_lenta, _falha)
    erro, tocados = _subir_ate_as_prechecagens(monkeypatch, marca, destino)
    assert erro.status_code == 503
    assert "Não consegui provar que este plano ainda não existe" in erro.detail
    assert isinstance(erro.__cause__, RuntimeError)
    assert terminou.is_set(), "a outra leitura foi abandonada no meio"
    assert tocados == {"ledger": 0, "mutate": 0}


@pytest.mark.parametrize("quem_acha", ["marca", "destino", "as_duas"])
def test_8_duplicidade_de_qualquer_uma_e_409_antes_do_ledger(monkeypatch, quem_acha):
    achada = ({"campaign_id": "222", "campaign_name": "y"},)
    outra = ({"campaign_id": "111", "campaign_name": "z"},)
    marca = (lambda **_: achada + outra) if quem_acha in ("marca", "as_duas") else (lambda **_: ())
    destino = (lambda **_: achada) if quem_acha in ("destino", "as_duas") else (lambda **_: ())
    erro, tocados = _subir_ate_as_prechecagens(monkeypatch, marca, destino)
    assert erro.status_code == 409
    assert "já aparece na conta" in erro.detail
    esperado = "111, 222" if quem_acha != "destino" else "222"
    assert f"campanha(s) {esperado}," in erro.detail, erro.detail
    assert tocados == {"ledger": 0, "mutate": 0}


# ═══════════════════════════════════════════════════════════════════════════
# 11-14 · /provar não cria; recusas HTTP atravessam a thread intactas
# ═══════════════════════════════════════════════════════════════════════════


def test_11_provar_nao_toca_ledger_nem_mutate(monkeypatch):
    _instalar_portas_hermeticas(monkeypatch)
    tocados = _sem_efeito_de_escrita(monkeypatch)
    prova = asyncio.run(trafego.provar(
        trafego.ProvarEntrada(**_payload_da_rota()), identidade=IDENTIDADE))
    assert prova["prontidao"]["plano_persistido"]["persistido"] is False
    assert prova["autorizacao"]["ativacao_incluida"] is False
    assert tocados == {"ledger": 0, "mutate": 0}


@pytest.mark.parametrize("rota", ["provar", "subir"])
def test_14_a_recusa_http_da_thread_continua_422_nas_duas_rotas(monkeypatch, rota):
    """`_criterios_do_corpo` levanta `HTTPException(422)` DENTRO da montagem.

    Ela atravessa a fronteira thread → coroutine e precisa chegar como 422,
    nunca como o 500 genérico do `except Exception`.
    """
    _instalar_portas_hermeticas(monkeypatch)
    tocados = _sem_efeito_de_escrita(monkeypatch)
    criterio = {"texto": "exemplo negativo", "negativa": True,
                "evidencia": {"fonte": "teste", "janela_inicio": "31/12/2026"}}
    payload = _payload_da_rota(criterios=[criterio])
    with pytest.raises(HTTPException) as erro:
        if rota == "provar":
            asyncio.run(trafego.provar(trafego.ProvarEntrada(**payload),
                                       identidade=IDENTIDADE))
        else:
            asyncio.run(trafego.subir(_corpo_de_subida("f" * 64, criterios=[criterio]),
                                      identidade=IDENTIDADE))
    assert erro.value.status_code == 422
    assert "AAAA-MM-DD" in str(erro.value.detail)
    assert tocados == {"ledger": 0, "mutate": 0}


def test_10b_a_montagem_entrega_o_suprimento_que_o_montador_do_canal_devolveu(
        monkeypatch):
    """O hash do suprimento atravessa a montagem comum sem ser recalculado."""
    from types import SimpleNamespace

    from volc_ads import pautador_ponte as pp

    vistos = {}

    class _Sb:
        @staticmethod
        def preparar(cid, brief, **k):
            vistos["preparar"] = (cid, brief, k)
            return SimpleNamespace(selo=None, canal=k["canal"])

    plano = SimpleNamespace(brief=SimpleNamespace(url_final="https://exemplo.com.br/"))
    monkeypatch.setattr(pp, "carregar", lambda *_a, **_k: SimpleNamespace(cluster=None))
    monkeypatch.setattr(pp, "montar_cockpit", lambda *_a, **_k: object())
    monkeypatch.setattr(trafego, "_montar_plano_display",
                        lambda *_a, **_k: (plano, "s" * 64))
    corpo = trafego.ProvarEntrada(**_payload_da_rota(canal="DISPLAY"))
    montado = trafego._montar_e_preparar_plano(
        pp, _Sb, corpo, canal_resolvido="DISPLAY", cid=CID, mid=MID,
        prefixo_nome="VOLC-TESTE")
    assert montado.supply_sha256 == "s" * 64
    assert montado.plano is plano
    assert vistos["preparar"][0] == CID
    assert vistos["preparar"][2]["login_customer_id"] == MID
    assert vistos["preparar"][2]["canal"] == "DISPLAY"
