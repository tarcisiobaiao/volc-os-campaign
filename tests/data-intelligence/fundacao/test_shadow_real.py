"""Adaptador para dado real (pronto, não executado): fixtures SINTÉTICAS no formato da junção de 02 §9
com os padrões do recibo do integrador."""
from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal

from volc_dil.fundacao.shadow.linhas_formato_real import fixture_padroes_reais
from volc_dil.fundacao.shadow.ledger import verificar_cadeia
from volc_dil.fundacao.shadow.politicas import catalogo_padrao
from volc_dil.fundacao.shadow.real import carregar_jsonl, deduplicar, observacoes_de_linhas_reais, replay_de_linhas_reais
from volc_dil.fundacao.observacao import adaptar_google_ads_v21


def test_padroes_do_recibo_passam_pelos_adaptadores_da_thread_a():
    fx = fixture_padroes_reais()
    a = observacoes_de_linhas_reais(fx["v21"], fx["joinads"])
    assert a.dead_letter == () and a.quarentena == ()
    assert a.runs_presos == tuple(fx["runs_presos"]) and len(a.runs_presos) == 3
    # zero sintetizado (R3/L11): sem linha de métrica → missing, nunca zero_confirmed
    sem = set(fx["campanhas_sem_metrica"])
    zeros = [o for o in a.observacoes if o.entidade.id in sem and o.fonte == "google_ads"]
    assert zeros and all(o.status.value == "missing" and o.motivo == "zero_sem_linha_de_metrica" for o in zeros)
    assert not any(o.status.value == "zero_confirmed" and o.entidade.id in sem for o in a.observacoes)


def test_repeticao_d0_perto_de_80_por_cento_e_deduplicada_por_payload():
    fx = fixture_padroes_reais()
    d0 = [l for l in fx["v21"] if l["run_id"].startswith("gads-d0")]
    brutas = [o for l in d0 for o in adaptar_google_ads_v21(l)]
    mantidas, descartadas, _ = deduplicar(brutas)
    assert 0.75 <= descartadas / len(brutas) <= 0.85  # recibo (a): ~80% das leituras D0 repetem a anterior
    # 1 de 5 campanhas muda por hora: por hora sobram as 4 métricas de uma campanha
    por_hora = Counter(o.observed_at.hour for o in mantidas if o.metrica.value == "cost")
    assert all(n == 1 for h, n in por_hora.items() if h > 6)


def test_reexecucao_do_mesmo_slot_nao_duplica_janela():
    fx = fixture_padroes_reais()
    d1 = [l for l in fx["v21"] if l["run_id"].startswith("gads-d1")]
    assert len({l["run_id"] for l in d1}) == 2  # mesmo slot executado duas vezes
    brutas = [o for l in d1 for o in adaptar_google_ads_v21(l)]
    mantidas, descartadas, _ = deduplicar(brutas)
    assert len(mantidas) == len(brutas) // 2 and descartadas == len(brutas) // 2
    # dedup por run (o que o v21 faz) manteria as duas cópias
    assert len({(o.run_id, o.chave_natural) for o in brutas}) == len(brutas)
    # fica a PRIMEIRA leitura (conhecimento datado da primeira chegada)
    assert all(o.run_id == "gads-d1-a" for o in mantidas)


def test_a_b_a_e_preservado_na_deduplicacao():
    fx = fixture_padroes_reais()
    l1 = fx["v21"][0]
    a1 = adaptar_google_ads_v21(l1)
    l2 = dict(l1, collected_at="2026-10-15T23:30:00-03:00", created_at="2026-10-15T23:31:00-03:00",
              metrics=dict(l1["metrics"], cost_micros=l1["metrics"]["cost_micros"] + 10_000),
              batch_payload={**l1["batch_payload"], "metrics": {**l1["batch_payload"]["metrics"], "costMicros": "x"}},
              batch_payload_sha256="b" * 64)
    l3 = dict(l1, collected_at="2026-10-16T00:30:00-03:00", created_at="2026-10-16T00:31:00-03:00")
    obs = [o for l in (l1, l2, l3) for o in adaptar_google_ads_v21(l) if o.metrica.value == "cost"]
    mantidas, _, _ = deduplicar(obs)
    assert [o.valor for o in mantidas] == [a1[0].valor, a1[0].valor + 10_000, a1[0].valor]


def test_replay_de_linhas_reais_ponta_a_ponta(tmp_path):
    fx = fixture_padroes_reais()
    adapt, res, led = replay_de_linhas_reais(fx["v21"], fx["joinads"], politicas=catalogo_padrao(), diretorio_ledger=tmp_path)
    assert res.decisoes and verificar_cadeia(tmp_path / "ledger.jsonl") == len(res.decisoes)
    # janela de um dia só: nada maduro → nenhuma política honesta corta; a anti-baseline cai na armadilha do zero
    for d in res.decisoes:
        for p in d.decisao.propostas:
            if d.politica != "regra_margem_null_zero":
                assert p.acao.value not in ("pausar", "reduzir_verba"), (d.politica, p.motivo)
    mortas = {p.entidade.campaign_id for d in res.da_politica("regra_margem_null_zero") for p in d.decisao.propostas
              if p.motivo.startswith("campanha_morta")}
    assert mortas >= set(fx["campanhas_sem_metrica"])


def test_carregar_jsonl_le_float_como_decimal(tmp_path):
    arq = tmp_path / "v21.jsonl"
    arq.write_text(json.dumps({"x": 1.25, "y": "a"}) + "\n\n" + json.dumps({"x": 2}) + "\n")
    linhas = carregar_jsonl(arq)
    assert linhas == [{"x": Decimal("1.25"), "y": "a"}, {"x": 2}] and isinstance(linhas[0]["x"], Decimal)
