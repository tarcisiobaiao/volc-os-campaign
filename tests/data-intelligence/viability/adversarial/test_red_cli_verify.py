"""RED — recibo da CLI: `verify` tem de sair 4 em QUALQUER artefato ou campo faltante/adulterado.

Achado 10 da missão V2. Na V1, `cmd_verify` pula a checagem do `resultado.json` quando o
arquivo não existe (`if rp.exists() and ...`), ignora `external_actions` e `relatorio.md`, e o
recibo não traz `source_commit`, `ambiente` nem `relatorio_sha256`.

Usa a fixture versionada `campanha_favoravel.json` (a V2 regenera as fixtures no mesmo nome).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[4]
LAB = RAIZ / "experiments" / "data-intelligence-lab"
CLI = LAB / "scripts" / "viability_cli.py"
FIXTURE = LAB / "fixtures" / "viability" / "campanha_favoravel.json"


def _cli(*args):
    return subprocess.run([sys.executable, "-I", str(CLI), *args], capture_output=True, text=True, cwd=str(LAB))


@pytest.fixture
def avaliado(tmp_path):
    r = _cli("evaluate", str(FIXTURE), "--saida", str(tmp_path))
    assert r.returncode in (0, 3), r.stderr
    assert (tmp_path / "recibo.json").exists() and (tmp_path / "resultado.json").exists() and (tmp_path / "relatorio.md").exists()
    return tmp_path


def _editar_recibo(d: Path, fn) -> None:
    rec = json.loads((d / "recibo.json").read_text(encoding="utf-8"))
    fn(rec)
    (d / "recibo.json").write_text(json.dumps(rec, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _set(chave, valor):
    def f(rec):
        rec[chave] = valor
    return f


def _del(chave):
    def f(rec):
        rec.pop(chave, None)
    return f


def test_red10_controle_recibo_integro_verifica_exit_0(avaliado):
    """Controle (passa na V1 e na V2): recibo e artefatos intactos → exit 0."""
    r = _cli("verify", str(avaliado / "recibo.json"))
    assert r.returncode == 0, r.stderr


def test_red10a_resultado_json_apagado_faz_verify_sair_4(avaliado):
    """Achado 10a. Apagar `resultado.json` depois do `evaluate`.

    V1 está errada porque `if rp.exists() and sha != recibo` só acusa quando o arquivo existe:
    um artefato removido passa como íntegro (exit 0). V2 deve sair 4 — artefato ausente é
    recibo não verificável.
    """
    (avaliado / "resultado.json").unlink()
    r = _cli("verify", str(avaliado / "recibo.json"))
    assert r.returncode == 4, (r.returncode, r.stdout, r.stderr)


def test_red10b_external_actions_adulterado_faz_verify_sair_4(avaliado):
    """Achado 10b. `external_actions: 1` no recibo.

    V1 está errada porque `verify` nunca lê `external_actions` do recibo: a declaração "nenhuma
    ação externa" pode ser trocada sem que a verificação acuse. V2 deve sair 4.
    """
    _editar_recibo(avaliado, _set("external_actions", 1))
    assert _cli("verify", str(avaliado / "recibo.json")).returncode == 4


def test_red10c_relatorio_adulterado_faz_verify_sair_4(avaliado):
    """Achado 10c. `relatorio.md` editado depois do `evaluate` (o texto humano que o operador lê).
    V1 não registra `relatorio_sha256` e nunca o confere. V2 deve registrar e sair 4."""
    p = avaliado / "relatorio.md"
    p.write_text(p.read_text(encoding="utf-8").replace("Veredito", "Veredito (editado)"), encoding="utf-8")
    assert _cli("verify", str(avaliado / "recibo.json")).returncode == 4


@pytest.mark.parametrize("chave", ["input_hash", "result_hash", "codigo_sha256", "resultado_sha256", "external_actions", "entrada"])
def test_red10d_campo_removido_do_recibo_faz_verify_sair_4(avaliado, chave):
    """Achado 10d. Campo removido do recibo. V1 usa `rec.get(...)` para `resultado_sha256` e
    nunca lê `external_actions`: a ausência desses dois passa (os demais já saem 4 ou 2).
    V2 deve sair 4 para qualquer campo obrigatório ausente."""
    _editar_recibo(avaliado, _del(chave))
    assert _cli("verify", str(avaliado / "recibo.json")).returncode == 4


@pytest.mark.parametrize("chave", ["input_hash", "result_hash", "codigo_sha256", "resultado_sha256"])
def test_red10e_hash_adulterado_faz_verify_sair_4(avaliado, chave):
    """Controle parcial (V1 já acusa estes quatro): hash trocado por zeros → exit 4."""
    _editar_recibo(avaliado, _set(chave, "0" * 64))
    assert _cli("verify", str(avaliado / "recibo.json")).returncode == 4


def test_red10f_recibo_v2_tem_proveniencia_do_codigo_e_do_ambiente(avaliado):
    """Achado 10e. Campos do recibo V2: kernel_version, codigo_sha256, source_commit,
    ambiente{python, plataforma, uv_lock_sha256}, entrada, input_hash, result_hash,
    resultado_arquivo, resultado_sha256, relatorio_sha256, external_actions.

    V1 está incompleta: sem `source_commit`, `ambiente` e `relatorio_sha256` o recibo não diz
    de qual commit nem de qual interpretador saiu — e `codigo_sha256` cobre só `viability/*.py`,
    não `contracts/money.py` nem a própria CLI.
    """
    rec = json.loads((avaliado / "recibo.json").read_text(encoding="utf-8"))
    obrigatorios = {"kernel_version", "codigo_sha256", "source_commit", "ambiente", "entrada", "input_hash", "result_hash",
                    "resultado_arquivo", "resultado_sha256", "relatorio_sha256", "external_actions"}
    assert obrigatorios <= set(rec), sorted(obrigatorios - set(rec))
    assert {"python", "plataforma", "uv_lock_sha256"} <= set(rec["ambiente"])
    assert rec["external_actions"] == 0
