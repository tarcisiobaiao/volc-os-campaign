"""Gates do replay/shadow: futuro, restatement tardio, null→0, zero sintetizado (R3), identidade, moeda,
determinismo e equivalência serial × paralela."""
from __future__ import annotations

import dataclasses
import hashlib
from datetime import date, timedelta

import pytest

from volc_dil.fundacao.identidade import CampanhaRegistrada
from volc_dil.fundacao.shadow._gerador_provisorio import preparar
from volc_dil.fundacao.shadow.controles import PoliticaTrapaceira, cortar_por_observed_at
from volc_dil.fundacao.shadow.fluxo import FluxoIndexado
from volc_dil.fundacao.shadow.kernel import aplicar_kernel
from volc_dil.fundacao.shadow.ledger import LedgerShadow, SinkJsonl
from volc_dil.fundacao.shadow.motor import (
    ConfigShadow,
    auditar_null_zero,
    detectar_vazamento,
    executar_replay,
)
from volc_dil.fundacao.shadow.politicas import (
    Guardiao72h,
    Manter,
    RegraMargem,
    equal,
    propor,
    regra_margem_imatura,
    regra_margem_null_zero,
)
from volc_dil.fundacao.shadow.snapshot import ConfigCorte, construir_snapshot
from volc_dil.fundacao.shadow.tipos import BPS, Acao, Confianca, DecisaoShadow, EntidadeCampanha

CONTA = "1234567890"


def _ent(i: int) -> EntidadeCampanha:
    return EntidadeCampanha(CONTA, f"2400000{i:04d}")


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _receitas_finais(obs, campanha: str, dias: set[date]):
    """Versão final (maior available_at) da receita client de `campanha` em cada dia."""
    finais = {}
    for o in obs:
        if (o.fonte == "joinads" and o.entidade.tipo == "campaign" and o.entidade.id == campanha
                and dict(o.dimensoes).get("revenue_basis") == "client" and o.valor is not None):
            d = o.janela_inicio.date()
            if d in dias and (d not in finais or o.available_at > finais[d].available_at):
                finais[d] = o
    return list(finais.values())


def _restatement(obs, campanha: str, dias: set[date], t_disp, divisor: int = 10, retrodatar: bool = False):
    saida = []
    for o in _receitas_finais(obs, campanha, dias):
        h = _h(f"restatement:{o.chave_natural}:{t_disp.isoformat()}")
        saida.append(dataclasses.replace(o, valor=o.valor // divisor // 10_000 * 10_000 or 10_000, payload_sha256=h,
                                         payload_ref=f"restatement:{h}",
                                         observed_at=o.janela_fim if retrodatar else t_disp,
                                         available_at=t_disp, ingested_at=t_disp))
    assert saida
    return saida


@pytest.fixture(scope="module")
def base6h():
    return preparar("base", passo_horas=6, hora_inicial=7)


def _dias(espec_inicio: date, a: int, b: int) -> set[date]:
    return {espec_inicio + timedelta(days=k) for k in range(a, b)}


def test_sem_informacao_futura_e_trapaceira_detectada(base6h):
    fs, cortes, cfg = base6h
    inicio = date(2026, 9, 1)
    t_inj = cortes[len(cortes) // 2] + timedelta(minutes=30)
    inj = _restatement(fs.observacoes, "24000000000", _dias(inicio, 3, 9), t_inj)
    honestas = [RegraMargem(), Manter(), Guardiao72h(RegraMargem())]
    r = detectar_vazamento(fs.observacoes, inj, honestas + [PoliticaTrapaceira(tuple(fs.observacoes))], cortes, config=cfg,
                           politicas_injetadas=honestas + [PoliticaTrapaceira(tuple(fs.observacoes) + tuple(inj))])
    for p in ("regra_margem", "manter", "guardiao_72h[regra_margem]"):
        assert r[p]["antes"] == [] and not r[p]["vazou"], p
    assert r["regra_margem"]["depois"], "a injeção precisa ser material depois de disponível"
    # depois da disponibilidade, até `manter` muda de bytes: a evidência cita o fingerprint do novo corte
    assert r["controle_trapaceira"]["vazou"] and r["controle_trapaceira"]["antes"]


def test_reprocessamento_tardio_nao_reescreve_decisao_gravada(base6h, tmp_path):
    fs, cortes, cfg = base6h
    t_r = cortes[len(cortes) // 2] + timedelta(minutes=10)
    rest = _restatement(fs.observacoes, "24000000000", _dias(date(2026, 9, 1), 3, 9), t_r)
    pols = [RegraMargem(), Guardiao72h(RegraMargem())]
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    la, lb = LedgerShadow(SinkJsonl(tmp_path / "a")), LedgerShadow(SinkJsonl(tmp_path / "b"))
    executar_replay(fs.observacoes, cortes, pols, config=cfg, ledger=la)
    executar_replay(tuple(fs.observacoes) + tuple(rest), cortes, pols, config=cfg, ledger=lb)
    from volc_dil.fundacao.observacao import instante_canonico

    limite = instante_canonico(t_r)
    antes_a = [l for l, e in zip(la.linhas, la.entradas) if e["as_of"] < limite]
    antes_b = [l for l, e in zip(lb.linhas, lb.entradas) if e["as_of"] < limite]
    assert antes_a and antes_a == antes_b  # mesma decisão, mesmos bytes, mesmo hash encadeado
    depois = [(ea["propostas"], eb["propostas"]) for ea, eb in zip(la.entradas, lb.entradas) if ea["as_of"] >= limite]
    assert any(a != b for a, b in depois), "o restatement aparece em T' > T"


def test_null_vira_zero_detectado_pela_auditoria():
    fs, cortes, cfg = preparar("zero_sintetizado", passo_horas=24, hora_inicial=7)
    fi = FluxoIndexado(fs.observacoes)
    snaps = [construir_snapshot(fi, t, cfg.corte) for t in cortes]
    honesta = auditar_null_zero(RegraMargem(), snaps)
    anti = auditar_null_zero(regra_margem_null_zero(), snaps)
    assert honesta["decisoes_que_distinguem_null_de_zero"] > 0 and not honesta["suspeita_null_como_zero"]
    assert anti["suspeita_null_como_zero"] and anti["decisoes_que_distinguem_null_de_zero"] == 0
    cega = auditar_null_zero(Manter(), snaps)
    assert cega["cega_a_dados"] and not cega["suspeita_null_como_zero"]


def test_zero_sintetizado_v21_nao_vira_prova_de_campanha_morta():
    fs, cortes, cfg = preparar("zero_sintetizado", passo_horas=6, hora_inicial=7)
    ent0 = _ent(0)
    custo0 = [o for o in fs.observacoes if o.fonte == "google_ads" and o.entidade.id == ent0.campaign_id
              and o.metrica.value == "cost" and o.janela_inicio.date() >= date(2026, 9, 6) and o.observed_at >= o.janela_fim]
    assert custo0 and all(o.status.value == "missing" and o.motivo.startswith("zero_sem_linha") for o in custo0)
    res = executar_replay(fs.observacoes, cortes, [RegraMargem(), Guardiao72h(regra_margem_imatura()), regra_margem_null_zero()],
                          config=cfg)
    for d in res.decisoes:
        p0 = next(p for p in d.decisao.propostas if p.entidade == ent0)
        if d.politica != "regra_margem_null_zero":
            assert p0.acao not in (Acao.PAUSAR, Acao.REDUZIR_VERBA), (d.as_of, d.politica, p0.motivo)
    mortas = [d for d in res.da_politica("regra_margem_null_zero")
              if next(p for p in d.decisao.propostas if p.entidade == ent0).motivo.startswith("campanha_morta")]
    assert mortas, "a anti-baseline null→0 precisa cair na armadilha (e ser sinalizada)"
    diag = [g for d in res.da_politica("regra_margem") for g in d.decisao.diagnosticos if g.codigo == "zero_sem_prova_de_linha"]
    assert diag


def test_custom_key_trocada_bloqueia_corte():
    fs, cortes, cfg = preparar("identidade_trocada", passo_horas=24, hora_inicial=7)
    res = executar_replay(fs.observacoes, cortes, [RegraMargem()], config=cfg)
    ent4 = _ent(4)
    bloqueadas = []
    for d in res.decisoes:
        p = next(p for p in d.decisao.propostas if p.entidade == ent4)
        if p.acao in (Acao.PAUSAR, Acao.REDUZIR_VERBA) and p.bloqueios:
            bloqueadas.append(p)
            assert any(b.startswith("custom_key_substituida:2026-09-10") for b in p.bloqueios)
            assert p.fator_efetivo_bps == BPS
    assert bloqueadas


def test_colisao_de_identidade_bloqueia():
    fs, cortes, cfg = preparar("base", passo_horas=24, hora_inicial=7)
    registro = tuple(CampanhaRegistrada(CONTA, _ent(i).campaign_id, f"c{i}", date(2026, 8, 1)) for i in range(6)) + (
        CampanhaRegistrada("9999999999", _ent(5).campaign_id, "colide", date(2026, 8, 1)),)
    cfg2 = ConfigShadow(dataclasses.replace(cfg.corte, registro=registro), cfg.kernel)
    snap = construir_snapshot(FluxoIndexado(fs.observacoes), cortes[-2], cfg2.corte)
    assert "colisao_identidade:id_em_duas_contas" in snap.bloqueios_de(_ent(5))
    pol = RegraMargem()
    dec = DecisaoShadow((propor(snap, pol, _ent(5), Acao.PAUSAR, 0, Confianca.ALTA, "teste"),))
    p = aplicar_kernel(snap, pol.nome, dec, cfg2.kernel).propostas[0]
    assert "colisao_identidade:id_em_duas_contas" in p.bloqueios and p.fator_efetivo_bps == BPS
    # e a receita da campanha colidida não é atribuída (vai ao balde)
    assert all(f.receita.estado.value != "medido" for f in snap.fatos_de(_ent(5)))


def test_moeda_misturada_e_sem_cambio_bloqueiam():
    fs, cortes, cfg = preparar("base", passo_horas=24, hora_inicial=7)
    alvo = _receitas_finais(fs.observacoes, _ent(2).campaign_id, {date(2026, 9, 10)})[0]
    h = _h("brl")
    # a mesma campanha com receita em BRL noutro domínio, no mesmo dia (identidade de linha diferente: sem dupla contagem)
    extra = dataclasses.replace(alvo, moeda="BRL", conta="outro-dominio-sintetico.com.br", payload_sha256=h,
                                payload_ref=f"x:{h}")
    snap = construir_snapshot(FluxoIndexado(list(fs.observacoes) + [extra]), cortes[-2], cfg.corte)
    assert "moeda_misturada" in snap.bloqueios_de(_ent(2))
    pol = RegraMargem()
    dec = DecisaoShadow((propor(snap, pol, _ent(2), Acao.REDUZIR_VERBA, 7000, Confianca.ALTA, "teste"),))
    assert "moeda_misturada" in aplicar_kernel(snap, pol.nome, dec, cfg.kernel).propostas[0].bloqueios
    # sem câmbio declarado: margem não se calcula e qualquer corte é bloqueado
    sem = construir_snapshot(FluxoIndexado(fs.observacoes), cortes[-2], ConfigCorte())
    assert all(p.acao is Acao.INSUFICIENTE and p.motivo.startswith("moeda_sem_cambio")
               for p in RegraMargem().decidir(sem).propostas)
    dec2 = DecisaoShadow((propor(sem, pol, _ent(5), Acao.PAUSAR, 0, Confianca.ALTA, "teste"),))
    assert "moeda_sem_cambio:USD->BRL" in aplicar_kernel(sem, pol.nome, dec2, cfg.kernel).propostas[0].bloqueios


def test_grao_misto_de_receita_no_dia_bloqueia_sem_somar():
    fs, cortes, cfg = preparar("base", passo_horas=24, hora_inicial=7)
    alvo = _receitas_finais(fs.observacoes, _ent(4).campaign_id, {date(2026, 9, 10)})[0]
    h = _h("adunit")
    dims = dict(alvo.dimensoes)
    dims.update(joinads_grain="campaign_adunit_day", joinads_endpoint="key_value_campaign_adunit", ad_unit_name="topo")
    outro_corte = dataclasses.replace(alvo, dimensoes=tuple(sorted(dims.items())), grao=tuple(sorted(set(alvo.grao) | {"ad_unit"})),
                                      payload_sha256=h, payload_ref=f"x:{h}")
    snap = construir_snapshot(FluxoIndexado(list(fs.observacoes) + [outro_corte]), cortes[-2], cfg.corte)
    cob = snap.cobertura_de(date(2026, 9, 10))
    assert any(b.startswith("receita_recusada_pela_juncao") for b in cob.bloqueios)
    assert all(f.receita.valor is None for f in snap.fatos if f.dia == date(2026, 9, 10))  # nada somado em dobro
    pol = RegraMargem()
    dec = DecisaoShadow((propor(snap, pol, _ent(4), Acao.PAUSAR, 0, Confianca.ALTA, "teste"),))
    assert any(b.startswith("receita_recusada_pela_juncao") for b in aplicar_kernel(snap, pol.nome, dec, cfg.kernel).propostas[0].bloqueios)


def test_retrodatado_nao_vaza_porque_o_corte_e_por_available_at(base6h):
    fs, cortes, cfg = base6h
    t_inj = cortes[len(cortes) // 2] + timedelta(minutes=30)
    inj = _restatement(fs.observacoes, "24000000000", _dias(date(2026, 9, 1), 3, 9), t_inj, retrodatar=True)
    r = detectar_vazamento(fs.observacoes, inj, [RegraMargem()], cortes, config=cfg)
    assert r["regra_margem"]["antes"] == [] and r["regra_margem"]["depois"]
    t_antes = cortes[1]
    assert any(o in cortar_por_observed_at(inj, t_antes) for o in inj), "corte por observed_at deixaria o futuro entrar"


def test_determinismo_bytes_identicos(base6h, tmp_path):
    fs, cortes, cfg = base6h
    pols = [Manter(), equal(), RegraMargem(), Guardiao72h(regra_margem_imatura())]
    shas = []
    for nome in ("x", "y"):
        (tmp_path / nome).mkdir()
        led = LedgerShadow(SinkJsonl(tmp_path / nome))
        res = executar_replay(fs.observacoes, cortes[::2], pols, config=cfg, seed=fs.seed, ledger=led)
        shas.append((res.sha256(), (tmp_path / nome / "ledger.jsonl").read_bytes()))
    assert shas[0] == shas[1]


def test_serial_igual_paralelo_processo_e_thread(base6h):
    fs, cortes, cfg = base6h
    pols = [Manter(), equal(), RegraMargem(), regra_margem_null_zero()]
    sub = cortes[::3]
    bytes_ = []
    for kw in ({"paralelismo": 1}, {"paralelismo": 2, "executor": "processo"}, {"paralelismo": 3, "executor": "thread"}):
        led = LedgerShadow()
        executar_replay(fs.observacoes, sub, pols, config=cfg, seed=1, ledger=led, **kw)
        bytes_.append(led.bytes())
    assert bytes_[0] == bytes_[1] == bytes_[2] and bytes_[0]
