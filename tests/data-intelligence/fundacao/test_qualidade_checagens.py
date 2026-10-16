"""Checagens de qualidade (thread G): caso positivo, negativo e de borda por regra. Puro, sem banco."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from volc_dil.fundacao.qualidade import (
    SLA_PADRAO,
    CelulaEsperada,
    CoberturaSensorDia,
    LinhaReceitaDia,
    ObservacaoDQ,
    RunDQ,
    Severidade,
    StatusDado,
    avaliar_completude_slots,
    avaliar_frescor,
    avaliar_reconciliacao_custo,
    avaliar_reconciliacao_receita,
    checar_cobertura_atribuicao,
    checar_completude_grade,
    checar_dead_letter,
    checar_deriva_esquema,
    checar_duplicacao,
    checar_falha_silenciosa,
    checar_latencia_ingestao,
    checar_runs_orfaos,
    checar_substituicao_fonte,
    checar_zero_sintetizado,
    classificar_celula,
    classificar_duplicacao,
    classificar_zero,
    de_observacoes,
    horas_de_cron,
    runs_de_run_coleta,
)
from volc_dil.fundacao.qualidade.adaptadores import chave_natural_joinads, coletor_logico_joinads, linha_metrica_presente
from volc_dil.fundacao.qualidade.integridade import campos_de_payload

UTC = timezone.utc
AGORA = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)  # 12:00 em São Paulo
D0 = "n8n-google-ads-d0"


def local(d: int, h: int, m: int, mes: int = 10) -> datetime:
    return datetime(2026, mes, d, h, m, tzinfo=UTC) + timedelta(hours=3)  # São Paulo = UTC-3 (sem horário de verão)


def run(coletor=D0, inicio=None, status="completed", linhas=5, sinal=None, rid=None, fonte="google_ads", **kw):
    inicio = inicio or local(16, 11, 7)
    return RunDQ.de_dict({"run_id": rid or f"{coletor}@{inicio.isoformat()}", "fonte": fonte, "coletor": coletor,
                          "status": status, "started_at": inicio,
                          "finished_at": None if status == "running" else inicio + timedelta(minutes=3),
                          "ultimo_sinal": sinal, "linhas_escritas": linhas, **kw})


def d0_ate(ultimo: datetime, desde: datetime = local(15, 6, 7)) -> list[RunDQ]:
    out, t = [], desde
    while t <= ultimo:
        if 6 <= (t - timedelta(hours=3)).hour <= 23:
            out.append(run(inicio=t + timedelta(seconds=20)))
        t += timedelta(hours=1)
    return out


# --------------------------------------------------------------------------- agenda


def test_cron_dos_coletores():
    assert horas_de_cron("7 6-23 * * *") == (7, tuple(range(6, 24)))
    assert horas_de_cron("15 6-22/2 * * *") == (15, (6, 8, 10, 12, 14, 16, 18, 20, 22))
    assert horas_de_cron("23 */4 * * *") == (23, (0, 4, 8, 12, 16, 20))
    assert horas_de_cron("17 6,14 * * *") == (17, (6, 14))
    with pytest.raises(ValueError):
        horas_de_cron("0 6 * * 1")  # semanal: fora do contrato diário


# --------------------------------------------------------------------------- frescor


def _estado(runs, agora=AGORA, coletor=D0):
    return next(e for e in avaliar_frescor(runs, agora) if e.coletor == coletor)


def test_frescor_positivo_negativo_e_parado():
    assert _estado(d0_ate(local(16, 11, 7))).estado == "fresco"  # negativo
    e = _estado(d0_ate(local(16, 9, 7)))  # 10:07 e 11:07 vencidos sem sucesso
    assert (e.estado, e.slots_perdidos, e.severidade) == ("atrasado", 2, "aviso")
    e = _estado(d0_ate(local(16, 7, 7)))
    assert (e.estado, e.severidade) == ("parado", "alto")


def test_frescor_sem_registro_e_falha_nao_conta_como_sucesso():
    e = _estado([run(status="failed", inicio=local(16, 11, 7, ))])
    assert (e.estado, e.severidade) == ("sem_registro", "critico")
    e = _estado([run(status="running", inicio=local(16, 11, 7))])
    assert e.estado == "sem_registro"


def test_frescor_borda_slot_com_prazo_aberto_nao_e_perdido():
    # 12:20 local: o slot 12:07 só vence às 12:37 -> ainda fresco com último sucesso 11:07
    assert _estado(d0_ate(local(16, 11, 7)), agora=local(16, 12, 20)).estado == "fresco"
    assert _estado(d0_ate(local(16, 11, 7)), agora=local(16, 12, 40)).estado == "atrasado"


def test_frescor_borda_madrugada_fora_da_agenda_nao_e_buraco():
    runs = d0_ate(local(15, 23, 7))
    assert _estado(runs, agora=local(16, 4, 0)).estado == "fresco"  # 00–05 não tem slot
    assert _estado(runs, agora=local(16, 6, 40)).estado == "atrasado"  # 06:07 venceu


def test_frescor_partial_conta_como_sucesso():
    assert _estado([run(status="partial", inicio=local(16, 11, 7))]).estado == "fresco"


# --------------------------------------------------------------------------- completude por slot


def test_completude_slot_classes():
    runs = d0_ate(local(16, 9, 7)) + [run(status="failed", inicio=local(16, 10, 7, ) + timedelta(seconds=20))]
    cls = {(s.dia_local, s.hora_local): s.classe for s in avaliar_completude_slots(runs, AGORA) if s.coletor == D0}
    assert cls[(date(2026, 10, 16), 9)] == "ok"
    assert cls[(date(2026, 10, 16), 10)] == "falha_declarada"  # declarado ≠ silencioso
    assert cls[(date(2026, 10, 16), 11)] == "ausente_silencioso"
    assert (date(2026, 10, 16), 12) not in cls  # slot futuro nem existe
    assert all(h >= 6 for (_, h) in cls)  # fora da agenda não gera slot


def test_completude_borda_pendente_e_vigencia():
    runs = d0_ate(local(16, 11, 7))
    cls = {(s.dia_local, s.hora_local): s.classe for s in avaliar_completude_slots(runs, local(16, 12, 20)) if s.coletor == D0}
    assert cls[(date(2026, 10, 16), 12)] == "pendente"
    # o coletor não é cobrado antes do primeiro run: nada em 14/10
    assert min(cls)[0] == date(2026, 10, 15)


# --------------------------------------------------------------------------- órfãos e falha silenciosa


def test_runs_orfaos_positivo_negativo_borda():
    termos = "n8n-google-ads-terms-keywords"
    orfao = run(termos, local(15, 11, 48), "running", sinal=local(15, 11, 49), rid="orfao")
    recente = run(D0, local(16, 11, 50), "running", rid="recente")  # 10 min < 30 min
    com_sinal = run(D0, local(16, 10, 40), "running", sinal=local(16, 11, 45), rid="com_sinal")  # heartbeat salva
    sem_sla = run("coletor_desconhecido", local(16, 11, 20), "running", rid="sem_sla")  # timeout padrão 30 min
    ach = checar_runs_orfaos([orfao, recente, com_sinal, sem_sla], AGORA)
    assert {a.chave for a in ach} == {"orfao", "sem_sla"}
    assert all(a.severidade is Severidade.ALTO for a in ach)


def test_falha_silenciosa_null_nao_e_zero():
    vazio = run(linhas=0, rid="vazio")
    desconhecido = run(linhas=None, rid="desconhecido")
    cheio = run(linhas=5, rid="cheio")
    falhou = run(status="failed", linhas=0, rid="falhou")  # falha declarada não é silenciosa
    assert [a.chave for a in checar_falha_silenciosa([vazio, desconhecido, cheio, falhou], AGORA)] == ["vazio"]


# --------------------------------------------------------------------------- duplicação


def obs(chave="k", run_id="r1", metricas=None, observed_at=None, **kw):
    return ObservacaoDQ(fonte=kw.pop("fonte", "google_ads"), grao=kw.pop("grao", "campaign_day"), chave=chave,
                        run_id=run_id, metricas=metricas if metricas is not None else {"cost_micros": 1, "impressions": 1},
                        observed_at=observed_at or local(16, 10, 0), **kw)


def test_duplicacao_conflito_exata_reingestao_e_releituras():
    t1, t2 = local(16, 9, 0), local(16, 10, 0)
    dados = [
        obs("conf", "r1", {"cost_micros": 1}), obs("conf", "r1", {"cost_micros": 2}),  # conflito no run
        obs("exata", "r1"), obs("exata", "r1"),  # duplicata exata
        obs("reing", "r1", observed_at=t1), obs("reing", "r2", observed_at=t1),  # mesma coleta em 2 runs
        obs("ident", "r1", observed_at=t1), obs("ident", "r2", observed_at=t2),  # releitura idêntica
        obs("rev", "r1", {"cost_micros": 1}, t1), obs("rev", "r2", {"cost_micros": 3}, t2),  # maturação
        obs("unica", "r1"),
    ]
    cls = {(c.chave, c.escopo): c.classe for c in classificar_duplicacao(dados, AGORA)}
    assert cls == {("conf", "no_run"): "conflito_no_run", ("exata", "no_run"): "duplicata_exata_no_run",
                   ("reing", "entre_runs"): "reingestao_suspeita", ("ident", "entre_runs"): "releitura_identica",
                   ("rev", "entre_runs"): "releitura_com_revisao"}
    ach = checar_duplicacao(dados, AGORA)
    sev = {a.regra: a.severidade for a in ach}
    assert sev["duplicacao_conflito_no_run"] is Severidade.CRITICO
    assert sev["duplicacao_releituras_esperadas"] is Severidade.INFO  # esperado não alarma


def test_duplicacao_borda_janela_e_payload_da_fonte():
    velho = local(1, 10, 0)  # fora da janela de 14 dias
    assert classificar_duplicacao([obs("v", "r1", observed_at=velho), obs("v", "r2", observed_at=velho)], AGORA) == []
    # payload_sha256 da fonte manda: mesmas métricas, hashes diferentes -> conflito
    a = obs("p", "r1", payload_sha256="a" * 64)
    b = obs("p", "r1", payload_sha256="b" * 64)
    assert classificar_duplicacao([a, b], AGORA)[0].classe == "conflito_no_run"


# --------------------------------------------------------------------------- zero sintetizado


def test_zero_sintetizado_classes_e_null_nao_e_zero():
    z = {"cost_micros": 0, "impressions": 0}
    assert classificar_zero(obs(metricas=z, atributos={"linha_metrica_presente": False})) == "sintetizado"
    assert classificar_zero(obs(metricas=z, atributos={"linha_metrica_presente": True})) == "zero_com_linha"
    assert classificar_zero(obs(metricas=z)) == "ambiguo"
    assert classificar_zero(obs(metricas=z, status=StatusDado.ZERO_CONFIRMED)) == "zero_com_linha"
    assert classificar_zero(obs(metricas={"cost_micros": None, "impressions": 0})) == "nulo"
    assert classificar_zero(obs(metricas={"impressions": 0})) == "nulo"
    assert classificar_zero(obs(metricas={"cost_micros": "0", "impressions": 0})) == "nulo"  # texto não é número
    assert classificar_zero(obs(metricas={"cost_micros": 0, "impressions": 3})) == "com_valor"


def test_zero_sintetizado_limiar():
    base = dict(metric_date=date(2026, 10, 15), coletor=D0)
    z = {"cost_micros": 0, "impressions": 0}
    sint = [obs(f"s{i}", metricas=z, atributos={"linha_metrica_presente": False}, **base) for i in range(4)]
    ativo = [obs("a", **base)]
    ach = checar_zero_sintetizado(sint + ativo, AGORA)
    assert len(ach) == 1 and ach[0].severidade is Severidade.ALTO and ach[0].evidencia["proporcao_sintetizada"] == 0.8
    ach = checar_zero_sintetizado(sint[:1] + ativo * 4, AGORA)
    assert ach[0].severidade is Severidade.AVISO  # 1/5 < 50%
    assert checar_zero_sintetizado([obs("z", metricas=z, atributos={"linha_metrica_presente": True}, **base)], AGORA) == []


def test_linha_metrica_presente_do_payload_bruto():
    assert linha_metrica_presente({"metrics": {}}) is False
    assert linha_metrica_presente({"metrics": {"metrics": {"costMicros": "1"}}}) is True
    assert linha_metrica_presente({"campaign": {}}) is None
    assert linha_metrica_presente([{"metrics": {}}]) is None


# --------------------------------------------------------------------------- completude de grade


def test_completude_grade_late_nao_e_missing_e_null_nao_e_zero():
    c = lambda k: CelulaEsperada("joinads", "campaign_day", k, date(2026, 10, 15))  # noqa: E731
    d = date(2026, 10, 15)
    leituras = [
        obs("ok", fonte="joinads", grao="campaign_day", metric_date=d),
        obs("late", fonte="joinads", grao="campaign_day", metric_date=d, status=StatusDado.LATE, metricas={}),
        obs("miss", fonte="joinads", grao="campaign_day", metric_date=d, status=StatusDado.MISSING, metricas={}),
        obs("nulo", fonte="joinads", grao="campaign_day", metric_date=d, metricas={"cost_micros": None}),
        obs("tarde", fonte="joinads", grao="campaign_day", metric_date=d, available_at=local(17, 9, 0)),
        obs("unsup", fonte="joinads", grao="campaign_day", metric_date=d, status=StatusDado.UNSUPPORTED, metricas={}),
    ]
    ach = {a.regra: a for a in checar_completude_grade(
        leituras, [c(k) for k in ("ok", "late", "miss", "nulo", "tarde", "unsup", "sumiu")],
        prazo=lambda cel: local(16, 12, 0))}
    assert set(ach) == {"completude_atrasado", "completude_ausente_declarado", "completude_observado_sem_valor",
                        "completude_ausente_silencioso"}
    assert ach["completude_atrasado"].evidencia["n"] == 2  # status late + available_at após o prazo
    assert ach["completude_atrasado"].severidade is Severidade.INFO
    assert ach["completude_ausente_silencioso"].severidade is Severidade.ALTO
    assert ach["completude_ausente_declarado"].severidade is Severidade.AVISO
    # a melhor leitura vence: uma releitura observada cobre um `missing` anterior
    assert classificar_celula([obs(status=StatusDado.MISSING, metricas={}), obs()]) == "observado"


# --------------------------------------------------------------------------- reconciliação


def test_reconciliacao_receita_estados():
    d = date(2026, 10, 15)
    est = {e.metric_date.day: (e.estado, e.severidade) for e in avaliar_reconciliacao_receita([
        LinhaReceitaDia(d.replace(day=10), 100.0, 98.0),
        LinhaReceitaDia(d.replace(day=11), 100.0, 85.0),
        LinhaReceitaDia(d.replace(day=12), 100.0, 30.0),
        LinhaReceitaDia(d.replace(day=13), 100.0, 115.0),
        LinhaReceitaDia(d.replace(day=14), None, 10.0),
        LinhaReceitaDia(d.replace(day=15), 100.0, None),
        LinhaReceitaDia(d.replace(day=16), 100.0, 99.0, n_moedas=2),
        LinhaReceitaDia(d.replace(day=9), 0.0, 0.0),
    ])}
    assert est == {10: ("ok", "ok"), 11: ("cobertura_baixa", "aviso"), 12: ("cobertura_baixa", "alto"),
                   13: ("excesso", "alto"), 14: ("kv_sem_earnings", "aviso"), 15: ("earnings_sem_kv", "alto"),
                   16: ("moeda_mista", "alto"), 9: ("sem_base", "info")}


def test_reconciliacao_custo_d0_d1_e_null():
    def o(coletor, rid, custo, quando, camp="1"):
        return ObservacaoDQ(fonte="google_ads", grao="campaign_day", chave=f"c:{camp}", run_id=rid, coletor=coletor,
                            conta="1234567", entidade=camp, metric_date=date(2026, 10, 15), observed_at=quando,
                            metricas={"cost_micros": custo})
    runs = [run(D0, local(15, 23, 7), rid="d0a"), run(D0, local(15, 22, 7), rid="d0b"),
            run("n8n-google-ads-d1", local(16, 6, 17), rid="d1"), run("n8n-google-ads-d1", local(15, 14, 17), rid="d1_mesmo_dia"),
            run(D0, local(15, 23, 7), status="running", rid="d0_running")]
    obs_ = [o(D0, "d0b", 50, local(15, 22, 8)), o(D0, "d0a", 100, local(15, 23, 8)),
            o(D0, "d0_running", 999, local(15, 23, 30)),  # run não concluído: ignorado
            o("n8n-google-ads-d1", "d1_mesmo_dia", 1, local(15, 14, 18)),  # lido no próprio dia: não é fechado
            o("n8n-google-ads-d1", "d1", 102, local(16, 6, 18)),
            o(D0, "d0a", None, local(15, 23, 8), camp="2"), o("n8n-google-ads-d1", "d1", 10, local(16, 6, 18), camp="2"),
            o(D0, "d0a", 5, local(15, 23, 8), camp="3"), o("n8n-google-ads-d1", "d1", 0, local(16, 6, 18), camp="3")]
    est = {e.campanha: (e.estado, e.severidade, e.diferenca_relativa) for e in avaliar_reconciliacao_custo(obs_, runs, AGORA)}
    assert est["1"] == ("ok", "ok", pytest.approx(0.0196, abs=1e-4))
    assert est["2"][:2] == ("valor_nulo", "aviso")  # null não é zero
    assert est["3"][:2] == ("divergente", "alto")  # D-1 zerou e D0 não


# --------------------------------------------------------------------------- integridade


def test_deriva_esquema_sem_troca_de_versao():
    a = obs("a", fonte="joinads", grao="domain_day", versao_coletor=4, campos_payload=frozenset({"data", "date", "revenue"}),
            observed_at=local(15, 8, 0))
    b = obs("b", fonte="joinads", grao="domain_day", versao_coletor=4,
            campos_payload=frozenset({"data", "date", "revenue", "bonus"}), observed_at=local(15, 10, 0))
    c = obs("c", fonte="joinads", grao="domain_day", versao_coletor=4, campos_payload=frozenset({"data", "date"}),
            observed_at=local(15, 12, 0))
    regras = {x.regra: x for x in checar_deriva_esquema([a, b, c])}
    assert regras["esquema_campo_novo"].evidencia["campos"] == ["bonus"]
    assert regras["esquema_campo_ausente"].severidade is Severidade.ALTO
    assert checar_deriva_esquema([a, obs("d", fonte="joinads", grao="domain_day", versao_coletor=4,
                                         campos_payload=a.campos_payload)]) == []
    v5 = obs("e", fonte="joinads", grao="domain_day", versao_coletor=5, campos_payload=frozenset({"data", "x"}))
    assert [x.regra for x in checar_deriva_esquema([a, v5])] == ["esquema_mudou_com_versao"]
    assert campos_de_payload({"data": [{"a": 1}, {"b": 2}], "ok": True}) == {"data", "ok", "a", "b"}


def test_substituicao_de_fonte():
    pedido = obs("k", fonte="joinads", atributos={"custom_key_pedido": "utm_campaign", "custom_key": "utm_source"})
    certo = obs("k2", fonte="joinads", atributos={"custom_key_pedido": "utm_campaign", "custom_key": "utm_campaign"})
    moeda = [obs("m1", conta="111111", moeda="BRL"), obs("m2", conta="111111", moeda="USD")]
    conta = [obs("c1", conta="111111", entidade="9"), obs("c2", conta="222222", entidade="9")]
    r = run(avisos=[{"code": "custom_key_substituted"}], rid="rj", fonte="joinads", coletor="n8n_joinads_v2:intraday")
    regras = sorted(a.regra for a in checar_substituicao_fonte([pedido, certo, *moeda, *conta], [r]))
    assert regras == ["substituicao_campanha_mudou_de_conta", "substituicao_custom_key", "substituicao_custom_key_run",
                      "substituicao_moeda"]
    assert checar_substituicao_fonte([certo, obs("x", conta="111111", moeda="BRL")]) == []
    assert [a.regra for a in checar_substituicao_fonte([obs("y", moeda="USD", conta="1")], moeda_esperada={"google_ads": "BRL"})] \
        == ["substituicao_moeda"]


def test_cobertura_atribuicao_sensor():
    d = date(2026, 10, 15)
    ach = {a.janela[0]: a for a in checar_cobertura_atribuicao([
        CoberturaSensorDia(d, 28, 0, 28), CoberturaSensorDia(d.replace(day=14), 30, 30),
        CoberturaSensorDia(d.replace(day=13), 5, 0), CoberturaSensorDia(d.replace(day=12), 0, 0),
        CoberturaSensorDia(d.replace(day=11), None, None), CoberturaSensorDia(d.replace(day=10), 20, 16),
    ])}
    assert ach["2026-10-15"].severidade is Severidade.ALTO and ach["2026-10-15"].evidencia["cobertura"] == 0.0
    assert ach["2026-10-13"].regra == "atribuicao_sensor_amostra_insuficiente"
    assert ach["2026-10-10"].severidade is Severidade.AVISO  # 80%
    assert "2026-10-14" not in ach and "2026-10-12" not in ach and "2026-10-11" not in ach  # 0 pagas: sem razão


def test_adaptadores_joinads_chave_e_papel():
    row = {"endpoint": "earnings", "grain": "domain_day", "metric_date": "2026-10-15", "domain": "x.com"}
    assert chave_natural_joinads(row) == "earnings|domain_day|2026-10-15||x.com|||||||"
    base = {"collector": "n8n_joinads_v2", "timezone": "America/Sao_Paulo", "started_at": "2026-10-16T09:15:30+00:00"}
    assert coletor_logico_joinads({**base, "window_end": "2026-10-16"}) == "n8n_joinads_v2:intraday"
    assert coletor_logico_joinads({**base, "window_end": "2026-10-15"}) == "n8n_joinads_v2:d1"
    # 01:00 UTC de 16/10 ainda é 15/10 em São Paulo: janela de 15/10 é intraday
    assert coletor_logico_joinads({**base, "started_at": "2026-10-16T01:00:00+00:00", "window_end": "2026-10-15"}) \
        == "n8n_joinads_v2:intraday"


def test_sla_padrao_cobre_os_cinco_coletores_canonicos():
    assert set(SLA_PADRAO) == {"n8n-google-ads-d0", "n8n-google-ads-d1", "n8n-google-ads-terms-keywords",
                               "n8n_joinads_v2:intraday", "n8n_joinads_v2:d1"}


# --------------------------------------------------------------------------- ponte com o contrato A


def test_ponte_observacao_agrupa_metricas_de_a(obs):  # `obs` = fábrica do conftest da thread A
    from volc_dil.contracts.vocab import Metrica
    from volc_dil.fundacao.observacao import Unidade

    custo = obs(metrica=Metrica.CUSTO, valor=0, status="zero_confirmed")
    imp = obs(metrica=Metrica.IMPRESSOES, valor=0, unidade=Unidade.CONTAGEM, moeda=None, status="zero_confirmed")
    outra = obs(entidade_id="222", metrica=Metrica.CUSTO, valor=None, status="missing", motivo="sem_linha")
    dq = {o.entidade: o for o in de_observacoes([custo, imp, outra])}
    assert dq["111"].metricas == {"cost_micros": 0, "impressions": 0}
    assert classificar_zero(dq["111"]) == "zero_com_linha"  # zero_confirmed de A é zero com prova
    assert dq["222"].status is StatusDado.MISSING and dq["222"].metricas == {"cost_micros": None}
    assert dq["222"].atributos["motivo"] == "sem_linha"
    assert classificar_zero(dq["222"]) == "nulo"


def test_ponte_run_coleta_latencia_e_dead_letter():
    rs = runs_de_run_coleta([{"run_id": "a", "fonte": "google_ads", "coletor_nome": "c", "coletor_versao": "1",
                              "status": "succeeded", "iniciado_em": "2026-10-16T10:00:00Z",
                              "finalizado_em": "2026-10-16T10:05:00Z", "n_inseridas": 0}])
    assert rs[0].status.value == "completed" and rs[0].linhas_escritas == 0
    linhas = [{"run_id": "a", "fonte": "f", "status": "succeeded", "n_lidas": 100, "n_dead_letter": 10,
               "iniciado_em": "2026-10-16T10:00:00Z", "finalizado_em": "2026-10-16T10:05:00Z"},
              {"run_id": "b", "fonte": "f", "status": "succeeded", "n_lidas": 100, "n_dead_letter": 1,
               "iniciado_em": "2026-10-16T10:00:00Z", "finalizado_em": "2026-10-16T10:05:00Z"},
              {"run_id": "c", "fonte": "f", "status": "succeeded", "n_lidas": 0, "n_dead_letter": 0,
               "iniciado_em": "2026-10-16T10:00:00Z", "finalizado_em": "2026-10-16T10:05:00Z"}]
    assert [a.chave for a in checar_dead_letter(linhas)] == ["a"]
    t = local(16, 10, 0)
    lento = [obs(str(i), available_at=t, ingested_at=t + timedelta(hours=2), coletor="x") for i in range(3)]
    rapido = [obs(str(i), available_at=t, ingested_at=t + timedelta(seconds=5), coletor="y") for i in range(3)]
    sem = [obs("s", available_at=None, ingested_at=t, coletor="z")]
    regras = {a.chave: a.regra for a in checar_latencia_ingestao(lento + rapido + sem)}
    assert regras == {"x": "latencia_ingestao_p95", "z": "latencia_sem_relogio"}


@pytest.mark.parametrize("cenario", ["limpo", "producao_conhecida"])
def test_zero_sintetizado_caminho_contrato_a_igual_ao_direto(cenario):
    """Linhas v21 sintéticas -> `adaptar_google_ads_v21` (A) -> ponte -> medição == medição direta das linhas."""
    from volc_dil.fundacao.observacao import adaptar_google_ads_v21
    from volc_dil.fundacao.qualidade.adaptadores import observacoes_de_tabelas
    from volc_dil.fundacao.qualidade.leituras import medir_zero_sintetizado
    from volc_dil.fundacao.qualidade.sintetico import AGORA_PADRAO, gerar_tabelas

    t = gerar_tabelas(20261016, cenario)
    runs = {r["run_id"]: r for r in t["google_ads_collection_run"]}
    lotes = {b["batch_id"]: b for b in t["google_ads_raw_batch"]}
    obs_a = []
    for o in t["google_ads_observation"]:
        if o["grain"] != "campaign_day":
            continue
        b, r = lotes[o["batch_id"]], runs[o["run_id"]]
        linha = dict(o, batch_payload_sha256=b["payload_sha256"], batch_payload=b["payload"], batch_request_id=None,
                     run_collector=r["collector"], run_collector_version=r["collector_version"],
                     run_api_version=r["api_version"], run_timezone=r["timezone"])
        # [thread A, R1-F4] o v21 grava currency_code='BRL' fixo e o payload sintético não traz moeda: a moeda
        # da conta é atestada fora do payload (no mundo sintético, BRL), senão custo vira `moeda_nao_provada`
        obs_a.extend(adaptar_google_ads_v21(linha, moeda_atestada="BRL"))
    via_a = medir_zero_sintetizado(de_observacoes(obs_a), AGORA_PADRAO)
    direto = medir_zero_sintetizado([x for x in observacoes_de_tabelas(t) if x.fonte == "google_ads"], AGORA_PADRAO)
    chave = lambda z: (z.coletor, z.metric_date, z.total, z.sintetizados, z.zeros_com_linha, z.ambiguos, z.nulos)  # noqa: E731
    assert via_a and sorted(map(chave, via_a)) == sorted(map(chave, direto))
    soma = sum(z.sintetizados for z in via_a), sum(z.zeros_com_linha for z in via_a)
    assert soma == ((108, 0) if cenario == "producao_conhecida" else (0, soma[1])) and (cenario != "limpo" or soma[1] > 0)
