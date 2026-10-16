"""Coletor seguro: trava, dry_run, timeout→retry sem duplicar, dead letter, idempotência, serial × paralelo."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from volc_dil.fundacao.capacidade import coletor as c
from volc_dil.fundacao.capacidade.coletor import (
    ErroPermanente,
    ErroTransitorio,
    LinhaFonte,
    PedidoLeitura,
    PoliticaRetry,
    RespostaLeitura,
    SinkMemoria,
    TravaViolada,
    executar_lote,
    run_coleta,
)


class Relogio:
    def __init__(self):
        self.t = datetime(2026, 10, 16, 9, 7, tzinfo=timezone.utc)
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.t += timedelta(seconds=1)
            return self.t


def _linhas(pedido: PedidoLeitura, n: int = 3) -> RespostaLeitura:
    return RespostaLeitura(tuple(
        LinhaFonte(chave=(pedido.conta, "campaign", f"cmp-{i}", "-", pedido.janela_inicio),
                   valores={"impressions": 100 + i, "cost_micros": 1_000_000 * i, "conversions_value_micros": None})
        for i in range(n)))


class FonteFake:
    nome = "google_ads_fake"
    somente_leitura = True

    def __init__(self, roteiro=None, atraso_s=0.0):
        self.roteiro = list(roteiro or [])  # exceções/"lento" a disparar nas primeiras chamadas
        self.chamadas = 0
        self.atraso_s = atraso_s
        self._lock = threading.Lock()

    def ler(self, pedido):
        with self._lock:
            self.chamadas += 1
            acao = self.roteiro.pop(0) if self.roteiro else None
        if acao == "lento":
            time.sleep(0.4)
        elif isinstance(acao, BaseException):
            raise acao
        if self.atraso_s:
            time.sleep(self.atraso_s)
        return _linhas(pedido)


PED = PedidoLeitura(coletor="gads_d0", conta="acc-1", janela_inicio="2026-10-16", janela_fim="2026-10-16",
                    slot="2026-10-16T09:07:00-03:00")
RAPIDO = PoliticaRetry(max_tentativas=3, base_s=0.5, teto_s=4, timeout_s=0.1)


def _dormidas():
    esperas: list[float] = []
    return esperas, esperas.append


def test_modo_padrao_e_dry_run_e_nao_grava():
    sink = SinkMemoria()
    r = run_coleta(PED, adaptador=FonteFake(), sink=sink, relogio=Relogio(), dormir=lambda s: None)
    assert r.status == "dry_run" and r.modo == "dry_run"
    assert r.observacoes == 9 and r.linhas_lidas == 3
    assert sink.observacoes == {} and sink.chamadas_gravar == 0 and sink.runs == {}
    assert [h[2] for h in sink.heartbeats] == ["iniciado", "dry_run"]


def test_ausencia_vira_nao_informado_nunca_zero():
    sink = SinkMemoria()
    run_coleta(PED, adaptador=FonteFake(), sink=sink, modo="gravar", relogio=Relogio(), dormir=lambda s: None)
    vazios = [o for o in sink.observacoes.values() if o.metrica == "conversions_value_micros"]
    assert vazios and all(o.valor is None and o.estado == "nao_informado" for o in vazios)


def test_timeout_retry_sucesso_sem_duplicar():
    sink = SinkMemoria()
    esperas, dormir = _dormidas()
    fonte = FonteFake(roteiro=["lento", ErroTransitorio("HTTP 429")])
    r = run_coleta(PED, adaptador=fonte, sink=sink, modo="gravar", politica=RAPIDO, relogio=Relogio(), dormir=dormir)
    assert r.status == "concluido" and r.tentativas == 3
    assert "timeout" in r.erros[0] and "429" in r.erros[1]
    assert len(esperas) == 2 and all(0 <= e <= 4 for e in esperas)
    assert len(sink.observacoes) == 9 and sink.chamadas_gravar == 1
    time.sleep(0.45)  # a tentativa lenta termina depois; o resultado tardio não pode virar escrita
    assert len(sink.observacoes) == 9 and sink.chamadas_gravar == 1
    assert sink.dead_letters == []
    estados = [h[2] for h in sink.heartbeats]
    assert estados[0] == "iniciado" and "retry_1" in estados and "retry_2" in estados and estados[-1] == "concluido"


def test_mesmo_slot_repetido_e_no_op_e_releitura_igual_nao_cria_linha():
    sink = SinkMemoria()
    kw = dict(adaptador=FonteFake(), sink=sink, modo="gravar", relogio=Relogio(), dormir=lambda s: None)
    r1 = run_coleta(PED, **kw)
    r2 = run_coleta(PED, **kw)
    assert r1.status == "concluido" and r1.gravadas_novas == 9
    assert r2.status == "ja_concluido" and sink.chamadas_gravar == 1
    outro_slot = PedidoLeitura(**{**PED.__dict__, "slot": "2026-10-16T10:07:00-03:00"})
    r3 = run_coleta(outro_slot, **kw)
    assert r3.status == "concluido" and r3.gravadas_novas == 0 and r3.repetidas == 9
    assert len(sink.observacoes) == 9 and len(sink.payloads) == 3


def test_valor_diferente_cria_nova_versao_append_only():
    sink = SinkMemoria()

    class FonteQueMuda(FonteFake):
        def ler(self, pedido):
            base = _linhas(pedido)
            if pedido.slot.endswith("10:07:00-03:00"):
                l0 = base.linhas[0]
                return RespostaLeitura((LinhaFonte(l0.chave, {**l0.valores, "impressions": 999}),) + base.linhas[1:])
            return base

    kw = dict(adaptador=FonteQueMuda(), sink=sink, modo="gravar", relogio=Relogio(), dormir=lambda s: None)
    run_coleta(PED, **kw)
    r = run_coleta(PedidoLeitura(**{**PED.__dict__, "slot": "2026-10-16T10:07:00-03:00"}), **kw)
    assert r.gravadas_novas == 1
    imps = sorted(o.valor for o in sink.observacoes.values() if o.metrica == "impressions" and o.chave[2] == "cmp-0")
    assert imps == [100, 999]  # as duas versões convivem; nada foi sobrescrito


@pytest.mark.parametrize("erro, motivo, tentativas", [
    (ErroPermanente("HTTP 400 GAQL inválida"), "erro_permanente", 1),
    (KeyError("campo sumiu"), "erro_desconhecido", 1),
])
def test_falha_permanente_vai_para_dead_letter_sem_retry(erro, motivo, tentativas):
    sink = SinkMemoria()
    esperas, dormir = _dormidas()
    fonte = FonteFake(roteiro=[erro] * 5)
    r = run_coleta(PED, adaptador=fonte, sink=sink, modo="gravar", politica=RAPIDO, relogio=Relogio(), dormir=dormir)
    assert r.status == "dead_letter" and r.tentativas == tentativas and fonte.chamadas == tentativas
    assert esperas == [] and sink.observacoes == {}
    assert len(sink.dead_letters) == 1 and sink.dead_letters[0].motivo == motivo
    assert sink.runs[r.chave_execucao].status == "dead_letter"
    assert not sink.run_concluido(r.chave_execucao)  # dead letter pode ser reprocessada


def test_transitorio_que_esgota_tentativas_vai_para_dead_letter():
    sink = SinkMemoria()
    esperas, dormir = _dormidas()
    fonte = FonteFake(roteiro=[ErroTransitorio("503")] * 10)
    r = run_coleta(PED, adaptador=fonte, sink=sink, modo="gravar", politica=RAPIDO, relogio=Relogio(), dormir=dormir)
    assert r.status == "dead_letter" and fonte.chamadas == 3 and len(esperas) == 2
    assert sink.dead_letters[0].motivo == "tentativas_esgotadas"
    # reprocessar a dead letter depois que a fonte volta: sucesso, sem duplicar
    r2 = run_coleta(PED, adaptador=FonteFake(), sink=sink, modo="gravar", relogio=Relogio(), dormir=lambda s: None)
    assert r2.status == "concluido" and len(sink.observacoes) == 9


def test_valor_nao_inteiro_e_contrato_invalido():
    class FonteFloat(FonteFake):
        def ler(self, pedido):
            return RespostaLeitura((LinhaFonte(("acc-1", "campaign", "c", "-", "2026-10-16"), {"cost": 9.7}),))

    sink = SinkMemoria()
    r = run_coleta(PED, adaptador=FonteFloat(), sink=sink, modo="gravar", relogio=Relogio(), dormir=lambda s: None)
    assert r.status == "dead_letter" and sink.dead_letters[0].motivo == "contrato_invalido"


def test_backoff_exponencial_com_teto_e_deterministico():
    import random

    p = PoliticaRetry(base_s=1, teto_s=8)
    a = [p.espera(t, random.Random("x")) for t in range(1, 7)]
    b = [p.espera(t, random.Random("x")) for t in range(1, 7)]
    assert a == b
    assert all(0 <= e <= min(8, 2 ** (t - 1)) for t, e in zip(range(1, 7), a))


def test_equivalencia_serial_paralelo():
    pedidos = [PedidoLeitura(coletor="gads_d0", conta=f"acc-{k}", janela_inicio="2026-10-16", janela_fim="2026-10-16",
                             slot=f"2026-10-16T{h:02d}:07:00-03:00") for k in range(6) for h in (9, 10, 11)]
    roteiro = [ErroTransitorio("429"), None, ErroTransitorio("500")] * 4
    s_serial, s_par = SinkMemoria(), SinkMemoria()
    kw = dict(modo="gravar", politica=PoliticaRetry(max_tentativas=4, timeout_s=2), dormir=lambda s: None)
    rs = executar_lote(pedidos, paralelismo=1, adaptador=FonteFake(roteiro=list(roteiro)), sink=s_serial,
                       relogio=Relogio(), **kw)
    rp = executar_lote(pedidos, paralelismo=6, adaptador=FonteFake(roteiro=list(roteiro), atraso_s=0.01),
                       sink=s_par, relogio=Relogio(), **kw)
    assert all(r.status == "concluido" for r in rs + rp)
    assert s_serial.conjunto_final() == s_par.conjunto_final()
    assert len(s_serial.observacoes) == len(s_par.observacoes) == 6 * 9  # 3 slots iguais → 1 versão
    assert set(s_serial.runs) == set(s_par.runs) and len(s_par.runs) == 18
    # repetir o lote inteiro em paralelo não muda nada
    executar_lote(pedidos, paralelismo=6, adaptador=FonteFake(), sink=s_par, relogio=Relogio(), **kw)
    assert s_serial.conjunto_final() == s_par.conjunto_final() and len(s_par.observacoes) == 54


class FonteComMutate(FonteFake):
    def mutate(self, *a):  # pragma: no cover - nunca chamado
        raise AssertionError


class FonteSemDeclaracao:
    nome = "x"

    def ler(self, pedido):  # pragma: no cover
        return _linhas(pedido)


class SinkExterno(SinkMemoria):
    externo = True


@pytest.mark.parametrize("adaptador, sink, modo", [
    (FonteComMutate(), SinkMemoria(), "gravar"),
    (FonteSemDeclaracao(), SinkMemoria(), "dry_run"),
    (FonteFake(), SinkExterno(), "gravar"),
    (FonteFake(), object(), "dry_run"),
    (FonteFake(), SinkMemoria(), "producao"),
])
def test_trava_recusa_escrita_externa(adaptador, sink, modo):
    with pytest.raises(TravaViolada):
        run_coleta(PED, adaptador=adaptador, sink=sink, modo=modo, relogio=Relogio(), dormir=lambda s: None)


def test_modulo_nao_tem_cliente_de_rede_nem_banco():
    import inspect

    fonte = inspect.getsource(c)
    for proibido in ("import requests", "import httpx", "urllib", "psycopg", "supabase.co", "socket", "googleads"):
        assert proibido not in fonte
