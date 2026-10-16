"""Coletor seguro (revisado na R1): trava por capacidade, dry_run nulo, timeout que não prende o processo,
A→B→A pelo Registro da frente A e equivalência serial × paralela do `as_of` em todos os cortes."""
from __future__ import annotations

import inspect
import random
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from volc_dil.contracts.vocab import Metrica
from volc_dil.fundacao.capacidade import coletor as c
from volc_dil.fundacao.capacidade.coletor import (
    ClienteLeitura,
    ConsultaLeitura,
    ContextoFonte,
    ErroPermanente,
    ErroTransitorio,
    PedidoLeitura,
    PoliticaRetry,
    RespostaLeitura,
    SinkMemoria,
    TravaViolada,
    executar_lote,
    run_coleta,
)
from volc_dil.fundacao.observacao import CampoMetrica, Coletor, EsquemaPayload, StatusObservacao, Unidade

UTC = timezone.utc
ESQ = EsquemaPayload(
    schema_version="fake.v1",
    campo_entidade=("campaign_id",),
    campos_metrica=(CampoMetrica(("impressions",), Metrica.IMPRESSOES, Unidade.CONTAGEM),
                    CampoMetrica(("cost",), Metrica.CUSTO, Unidade.MICROS),
                    CampoMetrica(("conversions",), Metrica.CONVERSOES, Unidade.CONTAGEM)),
)
JANELA = (datetime(2026, 10, 14, 3, tzinfo=UTC), datetime(2026, 10, 15, 3, tzinfo=UTC))


def relogio_sink(inicio=datetime(2026, 10, 16, 9, tzinfo=UTC)):
    estado = {"t": inicio}
    lock = threading.Lock()

    def agora():
        with lock:
            estado["t"] += timedelta(seconds=1)
            return estado["t"]

    return agora


def valores_padrao(conta: str, slot: str) -> list[dict]:
    return [{"campaign_id": f"cmp-{i}", "impressions": 100 + i, "cost": f"{i}.5", "conversions": None} for i in range(3)]


class Transporte:
    """Fake de rede: decide o que devolver pela URL; roteiro de falhas consumido em ordem de chamada."""

    def __init__(self, valores=valores_padrao, roteiro=(), atraso_max_s=0.0):
        self.valores, self.roteiro, self.atraso = valores, list(roteiro), atraso_max_s
        self.chamadas = 0
        self.lock = threading.Lock()

    def executar_leitura(self, consulta: ConsultaLeitura, timeout_s: float):
        with self.lock:
            self.chamadas += 1
            acao = self.roteiro.pop(0) if self.roteiro else None
        if acao == "trava":
            time.sleep(0.5)  # ignora o prazo de propósito: só a contenção do executor salva
        elif isinstance(acao, BaseException):
            raise acao
        if self.atraso:
            time.sleep(random.random() * self.atraso)
        q = dict(p.split("=") for p in consulta.texto.split("?", 1)[1].split("&"))
        return self.valores(q["conta"], q["slot"])


class Adaptador:
    nome = "fake_joinads"

    def ler(self, pedido: PedidoLeitura, cliente: ClienteLeitura) -> RespostaLeitura:
        linhas = cliente.consultar(ConsultaLeitura(
            "http_get", f"https://fonte.invalid/relatorio?conta={pedido.conta}&slot={pedido.slot}"))
        return RespostaLeitura(tuple(linhas), ContextoFonte(
            fonte="fake_fonte", entidade_tipo="campaign", grao=("campaign", "day"), janela_inicio=JANELA[0],
            janela_fim=JANELA[1], timezone="America/Sao_Paulo", coletor=Coletor("coletor_fake", "1"), esquema=ESQ,
            moeda="BRL"))


def ped(slot="06:00", conta="acc-1"):
    return PedidoLeitura(coletor="fake_d1", conta=conta, janela_inicio="2026-10-14", janela_fim="2026-10-14",
                         slot=f"2026-10-16T{slot}:00-03:00")


RAPIDO = PoliticaRetry(max_tentativas=3, base_s=0.5, teto_s=4, timeout_s=0.1)
NADA = dict(dormir=lambda s: None)


def gravar(sink, transporte=None, **kw):
    return dict(adaptador=Adaptador(), transporte=transporte or Transporte(), sink=sink, modo="gravar", **NADA, **kw)


# ---------------------------------------------------------------- dry_run (F11)
def test_dry_run_e_padrao_e_nao_toca_o_sink_nem_em_falha():
    sink = SinkMemoria(relogio_sink())
    r = run_coleta(ped(), adaptador=Adaptador(), transporte=Transporte(), sink=sink, **NADA)
    assert r.status == "dry_run" and r.observacoes == 9 and r.linhas_lidas == 3
    r2 = run_coleta(ped("07:00"), adaptador=Adaptador(), transporte=Transporte(roteiro=[ErroPermanente("400")]),
                    sink=sink, **NADA)
    assert r2.status == "dead_letter" and r2.motivo_dead_letter == "erro_permanente"
    assert len(sink.registro) == 0 and sink.runs == {} and sink.heartbeats == [] and sink.dead_letters == []
    assert sink.chamadas_gravar == 0 and sink.payloads == {}
    # e funciona sem sink algum
    assert run_coleta(ped(), adaptador=Adaptador(), transporte=Transporte(), **NADA).status == "dry_run"


def test_ausencia_vira_missing_nunca_zero_e_dinheiro_em_micros():
    sink = SinkMemoria(relogio_sink())
    run_coleta(ped(), **gravar(sink))
    obs = sink.registro.observacoes
    conv = [o for o in obs if o.metrica is Metrica.CONVERSOES]
    assert conv and all(o.valor is None and o.status is StatusObservacao.MISSING for o in conv)
    custo = sorted(o.valor for o in obs if o.metrica is Metrica.CUSTO)
    assert custo == [500_000, 1_500_000, 2_500_000] and all(o.moeda == "BRL" for o in obs if o.metrica is Metrica.CUSTO)


# ---------------------------------------------------------------- timeout / retry / dead letter
def test_timeout_retry_sucesso_sem_duplicar_e_resultado_tardio_descartado():
    sink = SinkMemoria(relogio_sink())
    esperas: list[float] = []
    t = Transporte(roteiro=["trava", ErroTransitorio("HTTP 429")])
    r = run_coleta(ped(), adaptador=Adaptador(), transporte=t, sink=sink, modo="gravar", politica=RAPIDO,
                   dormir=esperas.append)
    assert r.status == "concluido" and r.tentativas == 3
    assert "timeout" in r.erros[0] and "429" in r.erros[1]
    assert len(esperas) == 2 and all(0 <= e <= 4 for e in esperas)
    assert len(sink.registro) == 9 and sink.chamadas_gravar == 1
    time.sleep(0.6)  # a tentativa travada termina depois; nada dela pode virar escrita
    assert len(sink.registro) == 9 and sink.chamadas_gravar == 1 and sink.dead_letters == []
    estados = [h[2] for h in sink.heartbeats]
    assert estados[0] == "iniciado" and {"retry_1", "retry_2"} <= set(estados) and estados[-1] == "concluido"


@pytest.mark.parametrize("erro, motivo", [(ErroPermanente("HTTP 400 GAQL inválida"), "erro_permanente"),
                                          (KeyError("campo sumiu"), "erro_desconhecido")])
def test_falha_permanente_vai_para_dead_letter_sem_retry(erro, motivo):
    sink = SinkMemoria(relogio_sink())
    esperas: list[float] = []
    t = Transporte(roteiro=[erro] * 5)
    r = run_coleta(ped(), adaptador=Adaptador(), transporte=t, sink=sink, modo="gravar", politica=RAPIDO,
                   dormir=esperas.append)
    assert r.status == "dead_letter" and r.tentativas == 1 and t.chamadas == 1 and esperas == []
    assert len(sink.registro) == 0 and [d.motivo for d in sink.dead_letters] == [motivo]
    assert sink.runs[r.chave_execucao].status == "dead_letter" and not sink.run_concluido(r.chave_execucao)


def test_transitorio_esgotado_vai_para_dead_letter_e_reprocesso_nao_duplica():
    sink = SinkMemoria(relogio_sink())
    t = Transporte(roteiro=[ErroTransitorio("503")] * 10)
    r = run_coleta(ped(), adaptador=Adaptador(), transporte=t, sink=sink, modo="gravar", politica=RAPIDO, **NADA)
    assert r.status == "dead_letter" and t.chamadas == 3 and sink.dead_letters[0].motivo == "tentativas_esgotadas"
    r2 = run_coleta(ped(), **gravar(sink))
    assert r2.status == "concluido" and len(sink.registro) == 9


def test_precisao_acima_de_micros_vira_invalid_pelo_contrato_da_frente_a():
    sink = SinkMemoria(relogio_sink())
    t = Transporte(valores=lambda conta, slot: [{"campaign_id": "c", "impressions": 1, "cost": "9.1234567",
                                                 "conversions": 0}])
    run_coleta(ped(), **gravar(sink, transporte=t))
    custo = [o for o in sink.registro.observacoes if o.metrica is Metrica.CUSTO][0]
    assert custo.status is StatusObservacao.INVALID and custo.motivo.startswith("precisao_acima_de_micros")
    conv = [o for o in sink.registro.observacoes if o.metrica is Metrica.CONVERSOES][0]
    assert conv.status is StatusObservacao.ZERO_CONFIRMED and conv.valor == 0


def test_backoff_exponencial_com_teto_e_deterministico():
    p = PoliticaRetry(base_s=1, teto_s=8)
    a = [p.espera(t, random.Random("x")) for t in range(1, 7)]
    assert a == [p.espera(t, random.Random("x")) for t in range(1, 7)]
    assert all(0 <= e <= min(8, 2 ** (t - 1)) for t, e in zip(range(1, 7), a))


# ---------------------------------------------------------------- idempotência e A→B→A (F10)
def test_mesmo_slot_e_no_op_e_releitura_igual_em_outra_hora_e_confirmacao_d2_linha():
    sink = SinkMemoria(relogio_sink())
    r1 = run_coleta(ped("06:00"), **gravar(sink))
    r2 = run_coleta(ped("06:00"), **gravar(sink))
    r3 = run_coleta(ped("07:00"), **gravar(sink))
    assert r1.status == "concluido" and r1.inseridas == 9
    assert r2.status == "ja_concluido" and sink.chamadas_gravar == 2  # mesmo slot: nem lê
    # [thread A, D2'] reler o MESMO valor em outra hora é leitura nova (observed_at na chave), mas o estado
    # não mudou: vira CONFIRMAÇÃO estreita, não versão — as versões crescem com as mudanças, não com as leituras.
    assert r3.status == "concluido" and r3.inseridas == 0 and r3.noop == 0 and r3.confirmadas == 9
    assert len(sink.registro) == 9 and len(sink.registro.confirmacoes) == 9
    assert len(sink.payloads) == 3  # o payload bruto continua deduplicado por conteúdo
    # e o as_of continua mostrando os mesmos valores (confirmação não entra no as_of)
    fim = sink.as_of(sink.instantes_de_gravacao()[-1])
    assert sorted(v[3] for v in fim.values() if v[0] == "impressions") == [100, 101, 102]


def test_retry_da_mesma_leitura_e_noop():
    sink = SinkMemoria(relogio_sink())
    leitura_fixa = datetime(2026, 10, 16, 8, 59, tzinfo=UTC)  # antes do relógio do sink

    class Carimbado(Adaptador):
        def ler(self, pedido, cliente):
            r = super().ler(pedido, cliente)
            return RespostaLeitura(r.linhas, r.contexto, observado_em=leitura_fixa)

    r1 = run_coleta(ped("06:00"), **{**gravar(sink), "adaptador": Carimbado()})
    # a mesma leitura (mesmo carimbo) reentregue por outro slot = mesma chave de leitura → NOOP
    r2 = run_coleta(ped("06:01"), **{**gravar(sink), "adaptador": Carimbado()})
    assert (r1.inseridas, r2.inseridas, r2.noop) == (9, 0, 9) and len(sink.registro) == 9


def _custo_a_b_a(conta, slot):
    v = {"06:00": "10", "07:00": "20", "08:00": "10"}[slot[11:16]]
    return [{"campaign_id": "cmp-0", "impressions": 1, "cost": v, "conversions": 1}]


def test_a_b_a_e_preservado_como_leitura_nova():
    sink = SinkMemoria(relogio_sink())
    t = Transporte(valores=_custo_a_b_a)
    rs = [run_coleta(ped(s), **gravar(sink, transporte=t)) for s in ("06:00", "07:00", "08:00")]
    # [thread A, D2'] só o custo muda (A→B→A): 1 versão por leitura; impressões/conversões iguais → confirmação
    assert [(r.inseridas, r.noop, r.confirmadas) for r in rs] == [(3, 0, 0), (1, 0, 2), (1, 0, 2)]
    custo = [o for o in sink.registro.observacoes if o.metrica is Metrica.CUSTO]
    hist = sink.registro.historico(custo[0].chave_natural)
    assert [v.observacao.valor for v in hist] == [10_000_000, 20_000_000, 10_000_000]
    cortes = [r.gravado_em for r in rs]
    assert [sink.as_of(t)[custo[0].chave_natural][3] for t in cortes] == [10_000_000, 20_000_000, 10_000_000]


def _a_b_a_por_conta(conta, slot):
    k = int(conta.split("-")[1])
    h = slot[11:16]
    base = {"06:00": 10 + k, "07:00": 20 + k, "08:00": 10 + k}[h]
    return [{"campaign_id": f"cmp-{j}", "impressions": base + j, "cost": str(base), "conversions": None} for j in range(2)]


def _historia(sink: SinkMemoria) -> list[dict]:
    return [sink.as_of(t) for t in sink.instantes_de_gravacao()]


def _versoes(sink: SinkMemoria) -> set:
    return {(v.observacao.chave_natural, v.observacao.status.value, v.observacao.valor, v.observacao.observed_at)
            for v in sink.registro.versoes}


INICIO_LEITURA = datetime(2026, 10, 16, 9, tzinfo=UTC)  # 06:00 em São Paulo
SINK_DEPOIS = datetime(2026, 10, 16, 18, tzinfo=UTC)  # gravação sempre depois das leituras


class AdaptadorCarimbado(Adaptador):
    """Transporte que carimba o instante da leitura. No teste, o carimbo é determinístico por pedido
    (como se cada leitura tivesse de fato acontecido no seu slot) — é isso que torna serial e paralelo
    comparáveis: a semântica é "mesmas leituras ⇒ mesma história", não "mesma ordem de chegada"."""

    def ler(self, pedido, cliente):
        r = super().ler(pedido, cliente)
        h, m = int(pedido.slot[11:13]), int(pedido.slot[14:16])
        k = int(pedido.conta.split("-")[1])
        carimbo = INICIO_LEITURA + timedelta(hours=h - 6, minutes=m, seconds=k)
        return RespostaLeitura(r.linhas, r.contexto, observado_em=carimbo)


def test_equivalencia_serial_paralelo_mesmas_leituras_mesma_historia():
    pedidos = [ped(s, f"acc-{k}") for k in range(6) for s in ("08:00", "06:00", "07:00")]
    random.shuffle(pedidos)  # ordem de submissão arbitrária
    pol = PoliticaRetry(max_tentativas=4, timeout_s=2)
    s_serial = SinkMemoria(relogio_sink(SINK_DEPOIS))
    executar_lote(pedidos, paralelismo=1, adaptador=AdaptadorCarimbado(),
                  transporte=Transporte(_a_b_a_por_conta, roteiro=[ErroTransitorio("429"), None] * 3),
                  sink=s_serial, modo="gravar", politica=pol, **NADA)
    ref, ref_versoes = _historia(s_serial), _versoes(s_serial)
    # 6 contas × 2 linhas × 3 métricas × 3 leituras = versões + confirmações [thread A, D2']
    assert len(ref) == 18 and len(s_serial.registro) + len(s_serial.registro.confirmacoes) == 6 * 2 * 3 * 3
    for rodada in range(8):
        s_par = SinkMemoria(relogio_sink(SINK_DEPOIS))
        executar_lote(pedidos, paralelismo=6, adaptador=AdaptadorCarimbado(),
                      transporte=Transporte(_a_b_a_por_conta, roteiro=[ErroTransitorio("500"), None] * 3,
                                            atraso_max_s=0.02),
                      sink=s_par, modo="gravar", politica=pol, **NADA)
        assert _versoes(s_par) == ref_versoes, f"versões divergiram na rodada {rodada}"
        assert _historia(s_par) == ref, f"as_of divergiu na rodada {rodada}"
        assert s_par.instantes_de_gravacao() == s_serial.instantes_de_gravacao()
    # o último corte mostra A de novo (a leitura das 08h é a mais recente), não B
    custos = sorted(v[3] for v in ref[-1].values() if v[0] == "cost")
    assert custos == sorted([(10 + k) * 1_000_000 for k in range(6)] * 2)


def test_d1_gravacao_fora_de_ordem_nao_desfaz_a_leitura_mais_recente():
    """Sob D1 a ordem de gravação não decide o estado final: vence o maior observed_at."""
    em_ordem, invertido = SinkMemoria(relogio_sink(SINK_DEPOIS)), SinkMemoria(relogio_sink(SINK_DEPOIS))
    t = Transporte(_a_b_a_por_conta)
    for s_, sink in ((("06:00", "07:00", "08:00"), em_ordem), (("08:00", "07:00", "06:00"), invertido)):
        for slot in s_:
            run_coleta(ped(slot, "acc-0"), adaptador=AdaptadorCarimbado(), transporte=t, sink=sink, modo="gravar", **NADA)
    # [thread A, D2'] as LINHAS dependem da ordem de chegada (em ordem, as releituras iguais viram confirmação;
    # invertido, não há versão anterior com que comparar), mas os ESTADOS registrados e o as_of não
    estados = lambda sk: {(v.observacao.chave_natural, v.observacao.status.value, v.observacao.valor)  # noqa: E731
                          for v in sk.registro.versoes}
    assert estados(em_ordem) == estados(invertido)
    fim = lambda sk: sk.as_of(sk.instantes_de_gravacao()[-1])  # noqa: E731
    assert fim(em_ordem) == fim(invertido)
    assert sorted(v[3] for v in fim(invertido).values() if v[0] == "cost") == [10_000_000, 10_000_000]
    # o conhecimento intermediário difere, e deve: gravada depois, a leitura das 07h (B) não desfaz a das 08h
    custo = lambda h: sorted(v[3] for v in h.values() if v[0] == "cost")  # noqa: E731
    assert [custo(h) for h in _historia(em_ordem)] == [[10_000_000] * 2, [20_000_000] * 2, [10_000_000] * 2]
    assert [custo(h) for h in _historia(invertido)] == [[10_000_000] * 2] * 3


def test_observado_em_posterior_a_gravacao_vai_para_dead_letter():
    class Futuro(Adaptador):
        def ler(self, pedido, cliente):
            r = super().ler(pedido, cliente)
            return RespostaLeitura(r.linhas, r.contexto, observado_em=datetime(2030, 1, 1, tzinfo=UTC))

    sink = SinkMemoria(relogio_sink())
    r = run_coleta(ped(), **{**gravar(sink), "adaptador": Futuro()})
    assert r.status == "dead_letter" and r.motivo_dead_letter == "observado_em_invalido" and len(sink.registro) == 0


# ---------------------------------------------------------------- trava por capacidade (F11)
@pytest.mark.parametrize("tipo, texto", [("mutate", "x"), ("gaql", "UPDATE campaign SET x"),
                                         ("gaql", "SELECT a FROM b; DELETE"), ("http_get", "http://x"),
                                         ("http_post", "https://x")])
def test_consulta_so_admite_leitura(tipo, texto):
    with pytest.raises(TravaViolada):
        ConsultaLeitura(tipo, texto)


def test_adaptador_nao_alcanca_o_transporte_e_tentativa_de_escrita_vira_dead_letter():
    class Hostil(Adaptador):
        def ler(self, pedido, cliente):
            assert not hasattr(cliente, "transporte") and not hasattr(cliente, "__dict__")
            with pytest.raises(AttributeError):
                cliente.algo = 1
            cliente.consultar(ConsultaLeitura("gaql", "UPDATE campaign SET status = 'PAUSED'"))

    t = Transporte()
    sink = SinkMemoria(relogio_sink())
    r = run_coleta(ped(), adaptador=Hostil(), transporte=t, sink=sink, modo="gravar", **NADA)
    assert r.status == "dead_letter" and r.motivo_dead_letter == "erro_permanente" and t.chamadas == 0


class SinkSubclasse(SinkMemoria):
    pass


@pytest.mark.parametrize("sink, modo", [(SinkSubclasse(), "gravar"), (object(), "gravar"), (None, "gravar"),
                                        (SinkMemoria(), "producao")])
def test_trava_recusa_destino_que_nao_e_o_de_memoria(sink, modo):
    with pytest.raises(TravaViolada):
        run_coleta(ped(), adaptador=Adaptador(), transporte=Transporte(), sink=sink, modo=modo, **NADA)


def test_modulo_nao_tem_transporte_real_nem_driver():
    fonte = inspect.getsource(c)
    for proibido in ("import requests", "import httpx", "urllib", "psycopg", "supabase.co", "import socket",
                     "googleads", "http.client", "subprocess"):
        assert proibido not in fonte


# ---------------------------------------------------------------- processo sai mesmo com fonte presa (F12)
def test_fonte_presa_nao_impede_o_processo_de_sair(tmp_path: Path):
    src = Path(c.__file__).resolve().parents[3]
    script = tmp_path / "presa.py"
    script.write_text(textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(src)!r})
        from datetime import datetime, timezone
        from volc_dil.fundacao.capacidade.coletor import (PedidoLeitura, PoliticaRetry, RespostaLeitura,
            SinkMemoria, run_coleta)
        class Presa:
            def executar_leitura(self, consulta, timeout_s):
                time.sleep(60)  # ignora o prazo
        class Ad:
            nome = "x"
            def ler(self, pedido, cliente):
                from volc_dil.fundacao.capacidade.coletor import ConsultaLeitura
                return cliente.consultar(ConsultaLeitura("gaql", "SELECT campaign.id FROM campaign"))
        t0 = time.time()
        r = run_coleta(PedidoLeitura("c", "acc", "2026-10-14", "2026-10-14", "s"), adaptador=Ad(),
                       transporte=Presa(), sink=SinkMemoria(), modo="gravar",
                       politica=PoliticaRetry(max_tentativas=2, timeout_s=0.2), dormir=lambda s: None)
        print(r.status, r.tentativas, round(time.time() - t0, 2), flush=True)
    """))
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True, timeout=30)
    dur = time.monotonic() - t0
    assert p.returncode == 0, p.stderr
    status, tentativas, _ = p.stdout.split()
    assert status == "dead_letter" and tentativas == "2"
    assert dur < 10, f"processo levou {dur:.1f}s para sair (thread presa segurando o interpretador)"
