"""Gerador da v20_02 pós-v19 e importador de recibos do W4, sem banco.

Cada recusa tem um caso aqui que deixa de passar se a recusa for removida (o recibo
mutado é, fora daquele ponto, válido: o caso só passa pela recusa que testa).
"""
import copy
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("lri", RAIZ / "scripts" / "ledger_recibo_incidente.py")
lri = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lri)
FIX = Path(__file__).parent / "fixtures" / "RECEIPT-lab-passo1.json"
BASE = json.loads(FIX.read_text())


def _rec(tmp_path, d, nome="r.json"):
    p = tmp_path / nome
    p.write_text(json.dumps(d))
    return p


def _passo2(d=None):
    d = copy.deepcopy(d or BASE)
    v = "v8_06_users_sensitive_columns_revoke"
    e = dict(d["eventos"][0], versao=v, arquivo=f"supabase/migrations/{v}.sql",
             sha256=lri.sha_arquivo(f"supabase/migrations/{v}.sql"))
    d.update(operacao="--passo2", eventos=[e], fingerprint_antes="1" * 32, fingerprint_depois="2" * 32)
    return d


def _rollback(d=None):
    d = copy.deepcopy(d or BASE)
    ev = d["eventos"][0]
    d["eventos"] = [dict(ev, versao=v, operacao="reverter", arquivo=lri.V19_99, sha256=lri.sha_arquivo(lri.V19_99),
                         rollback_arquivo=None, rollback_sha256=None) for v in lri.REVERTIDAS]
    d.update(operacao="--rollback", fingerprint_antes="3" * 32, fingerprint_depois="4" * 32)
    return d


def test_fixture_valida_gera():
    sql = lri.gerar_v20_02(FIX)
    assert f"esperado   constant text := '{BASE['fingerprint_depois']}'" in sql
    assert "SET standard_conforming_strings = on;" in sql and "SET LOCAL standard_conforming_strings = on;" in sql
    assert "has_table_privilege('anon', 'public.users', 'SELECT')" in sql
    assert "volc_ops.fingerprint_esperado" not in sql
    assert sql.index("linha_de_base_producao_20261015") < sql.index(BASE["eventos"][0]["versao"]) < sql.index("'v20_01_ledger_migrations'")


MUTACOES_PASSO1 = [
    (lambda d: d.update(pacote="outro"), "pacote"),
    (lambda d: d.update(operacao="--passo2"), "operacao"),
    (lambda d: d.update(resultado="aplicado_mas_anon_aberto"), "resultado"),
    (lambda d: d.update(alvo="producao\nDROP TABLE x"), "alvo"),
    (lambda d: d.update(carimbo="20261015"), "carimbo"),
    (lambda d: d.update(fingerprint_sql="outra/fingerprint.sql"), "fingerprint_sql: caminho"),
    (lambda d: d.update(fingerprint_sql_sha256="0" * 64), "outra SQL"),
    (lambda d: d.update(fingerprint_antes="x"), "fingerprint_antes"),
    (lambda d: d.update(fingerprint_depois="x"), "fingerprint_depois"),
    (lambda d: d.update(fingerprint_depois=d["fingerprint_antes"]), "não mudou o schema"),
    (lambda d: d.update(eventos=[]), "sem eventos"),
    (lambda d: d["eventos"].pop(), "composição"),
    (lambda d: d["eventos"].reverse(), "composição"),
    (lambda d: d["eventos"].append(dict(d["eventos"][0])), "composição"),
    (lambda d: d["eventos"][1].update(operacao="reverter"), "operacao (esperado aplicar)"),
    (lambda d: d["eventos"][0].update(arquivo="supabase/migrations/v8_06_users_sensitive_columns_revoke.sql"), "arquivo diferente do pacote"),
    (lambda d: d["eventos"][0].update(arquivo="supabase/migrations/../README.sql"), "arquivo: formato"),
    (lambda d: d["eventos"][0].update(sha256="0" * 64), "sha256 do recibo"),
    (lambda d: d["eventos"][0].update(rollback_sha256="f" * 64), "rollback diferente"),
    (lambda d: d["eventos"][0].update(rollback_arquivo="/etc/hosts"), "rollback diferente"),
    (lambda d: d["eventos"][1].update(aprovador=" "), "aprovador"),
    (lambda d: d["eventos"][1].update(aprovador="a​"), "aprovador"),
    (lambda d: d["eventos"][1].update(aprovador=True), "aprovador"),
    (lambda d: d["eventos"][1].update(executado_por="x'); DROP TABLE public.users; --"), "executado_por"),
    (lambda d: d["eventos"][1].update(inicio="2026-10-15T13:39:24Z\n"), "inicio"),
    (lambda d: d["eventos"][1].update(fim="$$ DROP TABLE x $$"), "fim"),
    (lambda d: d["eventos"][1].update(aprovado_em="2026-10-15'::date"), "aprovado_em"),
]


@pytest.mark.parametrize("mutar,trecho", MUTACOES_PASSO1)
def test_cada_recusa_do_passo1(tmp_path, mutar, trecho):
    d = copy.deepcopy(BASE)
    mutar(d)
    with pytest.raises(lri.ReciboInvalido, match=trecho.replace("(", r"\(").replace(")", r"\)")):
        lri.gerar_v20_02(_rec(tmp_path, d))


@pytest.mark.parametrize("texto,trecho", [('{"pacote": NaN}', "NaN"), ("[1,2]", "não é objeto"), ("{", "JSON inválido")])
def test_json_com_nan_ou_lixo_e_recusado(tmp_path, texto, trecho):
    (tmp_path / "a.json").write_text(texto)
    with pytest.raises(lri.ReciboInvalido, match=trecho):
        lri.gerar_v20_02(tmp_path / "a.json")


# ---------- injeção: nada do recibo vira SQL ----------

def test_literal_so_aceita_alfabeto_restrito():
    assert lri.literal("v19_00 ok") == "'v19_00 ok'"
    assert lri.literal(None) == "NULL"
    for ruim in ["a'b", "a\nb", "a$$b", "a\\b", "a;b", "a--b\x00", "E'x'", 1]:
        with pytest.raises(lri.ReciboInvalido):
            lri.literal(ruim)


def test_injecao_por_quebra_de_linha_no_alvo_nao_vira_ddl(tmp_path):
    d = copy.deepcopy(BASE)
    d["alvo"] = "producao\nCREATE TABLE public.injetado(i int);\n--"
    with pytest.raises(lri.ReciboInvalido):
        lri.gerar_v20_02(_rec(tmp_path, d))


def test_injecao_por_dollar_quote_e_barra_invertida(tmp_path):
    for campo_, valor in [("executado_por", "a@b$volc_w4$; CREATE TABLE x(i int); DO $volc_w4$"),
                          ("aprovador", "a\\"), ("aprovador", "a'), (x")]:
        d = copy.deepcopy(BASE)
        d["eventos"][2][campo_] = valor
        with pytest.raises(lri.ReciboInvalido):
            lri.gerar_v20_02(_rec(tmp_path, d))


def test_sql_gerado_nao_depende_de_standard_conforming_strings():
    sql = lri.gerar_v20_02(FIX)
    assert "\\" not in sql  # sem barra invertida, standard_conforming_strings=off não muda o sentido
    assert "IF current_setting('standard_conforming_strings') <> 'on'" in sql


def test_nada_do_recibo_em_comentario():
    sql = lri.gerar_v20_02(FIX)
    comentarios = "\n".join(l for l in sql.splitlines() if l.lstrip().startswith("--"))
    for proibido in (BASE["alvo"], BASE["carimbo"], FIX.name, BASE["eventos"][0]["executado_por"]):
        assert proibido not in comentarios


# ---------- importador ----------

def test_importar_passo2_e_rollback_geram(tmp_path):
    s2 = lri.gerar_importacao(_rec(tmp_path, _passo2(), "p2.json"))
    assert "password_hash" in s2 and "n := n + 1;" in s2 and "nada a importar" in s2
    sr = lri.gerar_importacao(_rec(tmp_path, _rollback(), "rb.json"))
    assert sr.count("IF EXISTS (SELECT 1 FROM volc_ops.migracao_estado") == 6
    assert "has_table_privilege('anon', 'public.users', 'SELECT')" in sr
    for s in (s2, sr):
        assert "aprovador IS NULL" in s and "medido IS DISTINCT FROM esperado" in s


@pytest.mark.parametrize("fabrica,mutar,trecho", [
    (_passo2, lambda d: d["eventos"][0].update(operacao="reverter"), "operacao (esperado aplicar)"),
    (_rollback, lambda d: d["eventos"][0].update(operacao="aplicar"), "operacao (esperado reverter)"),
    (_rollback, lambda d: d["eventos"][0].update(rollback_arquivo=lri.V19_99, rollback_sha256=lri.sha_arquivo(lri.V19_99)), "não leva par"),
    (_rollback, lambda d: d["eventos"][0].update(arquivo="supabase/migrations/v19_00_users_gatilho_papel_real.sql"), "arquivo diferente"),
    (_passo2, lambda d: d.update(operacao="--passo1"), "operacao"),
])
def test_recusas_do_importador(tmp_path, fabrica, mutar, trecho):
    d = fabrica()
    mutar(d)
    with pytest.raises(lri.ReciboInvalido, match=trecho.replace("(", r"\(").replace(")", r"\)")):
        lri.gerar_importacao(_rec(tmp_path, d))


def test_importar_recusa_recibo_do_passo1():
    with pytest.raises(lri.ReciboInvalido, match="importar aceita"):
        lri.gerar_importacao(FIX)


# ---------- saída: nunca sobrescreve ----------

def test_importar_exige_saida():
    assert lri.main(["importar", str(FIX)]) == 2


def test_nunca_sobrescreve_arquivo_existente(tmp_path):
    existente = tmp_path / "ja.sql"
    existente.write_text("original")
    with pytest.raises(lri.ReciboInvalido, match="já existe"):
        lri.destino_livre(existente)
    assert lri.main(["v20_02", str(FIX), "--saida", str(existente)]) == 1
    assert existente.read_text() == "original"


def test_nunca_escreve_em_arquivo_versionado():
    versionada = RAIZ / "supabase/migrations/v20_02_ledger_linha_de_base.sql"
    antes = versionada.read_bytes()
    with pytest.raises(lri.ReciboInvalido, match="versionado"):
        lri.destino_livre(versionada)
    assert lri.main(["v20_02", str(FIX), "--saida", str(versionada)]) == 1
    assert versionada.read_bytes() == antes
    r = subprocess.run(["git", "-C", str(RAIZ), "diff", "--quiet", "--", str(versionada)])
    assert r.returncode == 0


def test_saida_padrao_e_arquivo_novo_com_versao_propria():
    assert lri.SAIDA_V20_02 != "supabase/migrations/v20_02_ledger_linha_de_base.sql"
    assert Path(lri.SAIDA_V20_02).stem != "v20_02_ledger_linha_de_base"


def test_recusa_nao_deixa_arquivo(tmp_path):
    d = copy.deepcopy(BASE)
    d["eventos"][0]["sha256"] = "0" * 64
    saida = tmp_path / "x.sql"
    assert lri.main(["v20_02", str(_rec(tmp_path, d)), "--saida", str(saida)]) == 1
    assert not saida.exists() and not list(tmp_path.glob(".ledger-*"))


def test_geracao_deterministica_e_independe_do_nome_do_arquivo(tmp_path):
    a = lri.gerar_v20_02(FIX)
    copia = tmp_path / "outro-nome.json"
    copia.write_bytes(FIX.read_bytes())
    assert lri.gerar_v20_02(copia) == a
