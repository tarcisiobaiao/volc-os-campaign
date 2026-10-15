"""Gerador da v20_02 pós-v19 e importador de recibos do W4: recusas e SQL seguro, sem banco."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("lri", RAIZ / "scripts" / "ledger_recibo_incidente.py")
lri = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lri)
FIX = Path(__file__).parent / "fixtures" / "RECEIPT-lab-passo1.json"


def _escrever(tmp_path, d, nome="r.json"):
    p = tmp_path / nome
    p.write_text(json.dumps(d))
    return p


def test_gera_v20_02_com_ancora_constante_do_recibo(tmp_path):
    d = json.loads(FIX.read_text())
    sql = lri.gerar_v20_02(FIX, aceitar_lab=True)
    assert f"esperado   constant text := '{d['fingerprint_depois']}'" in sql
    assert "volc_ops.fingerprint_esperado" not in sql
    for e in d["eventos"]:
        assert e["sha256"] in sql and e["versao"] in sql
    assert sql.index("linha_de_base_producao_20261015") < sql.index(d["eventos"][0]["versao"]) < sql.index("'v20_01_ledger_migrations'")


@pytest.mark.parametrize("mutar,trecho", [
    (lambda d: d.update(alvo="volc-lab-x"), "laboratório só com --aceitar-lab"),
    (lambda d: d.update(resultado="aplicado_mas_anon_aberto"), "resultado"),
    (lambda d: d.update(pacote="outro"), "pacote"),
    (lambda d: d.update(fingerprint_sql_sha256="0" * 64), "outra SQL"),
    (lambda d: d["eventos"][0].update(sha256="0" * 64), "sha256 do recibo"),
    (lambda d: d["eventos"][1].update(aprovador=" "), "sem aprovador"),
    (lambda d: d["eventos"].append(dict(d["eventos"][0])), "repetida"),
    (lambda d: d["eventos"][0].update(arquivo="supabase/migrations/../../.env"), "fora do repo"),
    (lambda d: d["eventos"][0].update(rollback_sha256="f" * 64), "rollback"),
    (lambda d: d.update(fingerprint_depois="x"), "fingerprint_depois"),
])
def test_recusas(tmp_path, mutar, trecho):
    d = json.loads(FIX.read_text())
    if "laboratório" not in trecho:
        d["alvo"] = "producao"
    mutar(d)
    with pytest.raises(lri.ReciboInvalido, match=trecho):
        lri.gerar_v20_02(_escrever(tmp_path, d), aceitar_lab=False)


def test_valor_do_recibo_nunca_vira_sql(tmp_path):
    d = json.loads(FIX.read_text())
    for e in d["eventos"]:
        e["executado_por"] = "x'); DROP TABLE public.users; --"
    sql = lri.gerar_v20_02(_escrever(tmp_path, d), aceitar_lab=True)
    assert "x''); DROP TABLE public.users; --" in sql
    assert "x'); DROP" not in sql


def test_importar_rejeita_recibo_do_passo1(tmp_path):
    with pytest.raises(lri.ReciboInvalido, match="operacao"):
        lri.gerar_importacao(FIX, aceitar_lab=True)


def test_rollback_importa_condicional_ao_estado(tmp_path):
    d = json.loads(FIX.read_text())
    d["operacao"] = "--rollback"
    roll = d["eventos"][0]["rollback_arquivo"]
    d["eventos"] = [dict(e, operacao="reverter", arquivo=roll, sha256=lri.sha_arquivo(roll),
                         rollback_arquivo=None, rollback_sha256=None) for e in d["eventos"]]
    sql = lri.gerar_importacao(_escrever(tmp_path, d), aceitar_lab=True)
    assert sql.count("IF EXISTS (SELECT 1 FROM volc_ops.migracao_estado") == len(d["eventos"])
    assert "reverter pulado" in sql


def test_cli_recusa_sem_escrever(tmp_path):
    d = json.loads(FIX.read_text())
    saida = tmp_path / "v20_02.sql"
    assert lri.main(["v20_02", str(_escrever(tmp_path, d)), "--saida", str(saida)]) == 1
    assert not saida.exists()
