"""A recomendação shadow depende só de custo e receita reconciliados, nunca de valor de
conversão estático do Google; ausência de receita não vira zero; nada é executado."""
import json
import shutil
from pathlib import Path

import pytest

from volc_lab import prova_vertical as pv

EXP = Path(__file__).resolve().parents[1] / "experimentos" / "senac-shadow-20261015"


@pytest.fixture()
def copia(tmp_path):
    for n in ("custo_ads_snapshot.json", "receita_joinads_snapshot.json"):
        shutil.copy(EXP / n, tmp_path / n)
    return tmp_path


def _mexer(d, arquivo, f):
    p = d / arquivo
    doc = json.loads(p.read_text())
    for linha in doc["linhas"]:
        f(linha)
    p.write_text(json.dumps(doc))


def test_replay_e_deterministico(copia):
    a, b = pv.rodar(copia), pv.rodar(copia)
    a.pop("duracao_s"), b.pop("duracao_s")
    assert a == b
    assert a["recomendacao"]["executada"] is False
    assert a["recomendacao"]["valor_sugerido"] is None


def test_valor_de_conversao_do_google_nao_decide(copia):
    base = pv.rodar(copia)["recomendacao"]["direcao"]
    _mexer(copia, "custo_ads_snapshot.json", lambda l: l.update(conversions_value=l["conversions_value"] * 1000))
    assert pv.rodar(copia)["recomendacao"]["direcao"] == base


def test_receita_ausente_nao_vira_zero(copia):
    r = pv.rodar(copia)
    assert any("ausentes, não zero" in x for x in r["recomendacao"]["lacunas"])
    df, _ = pv.transformar(copia)
    assert df[df["estado"] == "receita_ausente"]["receita_brl"].isna().all()


def test_janela_aberta_nao_entra(copia):
    r = pv.rodar(copia)
    madura = r["janela_madura"]
    _mexer(copia, "receita_joinads_snapshot.json",
           lambda l: l.update(revenue_usd=1e6) if l["date"] >= r["corte_maturidade"] else None)
    assert pv.rodar(copia)["janela_madura"] == madura


def test_pouca_amostra_vira_evidencia_insuficiente():
    rec = pv.decidir({"cliques": 10, "roas": 0.01}, [])
    assert rec.direcao == "evidencia_insuficiente"


def test_data_repetida_e_recusada(copia):
    p = copia / "receita_joinads_snapshot.json"
    doc = json.loads(p.read_text())
    doc["linhas"].append(dict(doc["linhas"][-6]))
    p.write_text(json.dumps(doc))
    with pytest.raises(pv.SnapshotInvalido):
        pv.rodar(copia)


def test_campanha_divergente_e_recusada(copia):
    p = copia / "receita_joinads_snapshot.json"
    doc = json.loads(p.read_text())
    doc["campaign_id"] = "999"
    p.write_text(json.dumps(doc))
    with pytest.raises(pv.SnapshotInvalido):
        pv.rodar(copia)


def test_as_of_no_fuso_da_conta_e_pela_leitura_mais_velha(copia):
    p = copia / "custo_ads_snapshot.json"
    doc = json.loads(p.read_text())
    doc["lido_em"] = "2026-10-15T01:30:00Z"  # 22:30 de 14/10 em São Paulo
    p.write_text(json.dumps(doc))
    assert pv.rodar(copia)["corte_maturidade"] == "2026-10-11"
    r = json.loads((copia / "receita_joinads_snapshot.json").read_text())
    r["lido_em"] = "2026-10-12T12:00:00Z"
    (copia / "receita_joinads_snapshot.json").write_text(json.dumps(r))
    assert pv.rodar(copia)["corte_maturidade"] == "2026-10-09"


def test_janela_vazia_e_ausencia_nao_zero():
    import pandas as pd
    df = pd.DataFrame({"date": pd.to_datetime(["2026-10-01"]), "maduro": [False], "estado": ["reconciliado"],
                       "custo_brl": [1.0], "receita_brl": [1.0], "clicks": [1]})
    assert pv.janela(df)["custo_brl"] is None


def test_muito_custo_sem_receita_vira_evidencia_insuficiente():
    assert pv.decidir({"cliques": 900, "roas": 0.01}, [], 0.5).direcao == "evidencia_insuficiente"


def test_replay_reproduz_o_mesmo_sha(copia):
    import hashlib
    pv.rodar(copia)
    a = hashlib.sha256((copia / "resultado.json").read_bytes()).hexdigest()
    pv.rodar(copia)
    assert hashlib.sha256((copia / "resultado.json").read_bytes()).hexdigest() == a
