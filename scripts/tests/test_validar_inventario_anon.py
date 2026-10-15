"""O --passo1 do incidente anon recusa inventário forjado.

A lista dos 8 consumidores e as decisões válidas vivem no validador, não no
JSON. Cada caso abaixo é uma forma de forjar o inventário que o validador tem
de recusar; o último é o inventário legítimo, que tem de passar.
"""
import copy
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]
VALIDADOR = RAIZ / "scripts" / "validar-inventario-anon-w4.py"
spec = importlib.util.spec_from_file_location("validar_inventario", VALIDADOR)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

EVID = "pg_stat_statements desde 05/08: zero chamadas do papel anon neste alvo"


def legitimo() -> dict:
    return {
        "consumidores": [
            {"id": i, "confirmado_em_producao": "2026-10-15", "evidencia": EVID, "decisao": "nao_usa_anon"}
            for i in v.CONSUMIDORES_OBRIGATORIOS
        ],
        "assinado_por": "Tarcísio",
        "assinado_em": "2026-10-15",
        "bloqueia_passo1": False,
    }


def forjar(**mudar):
    d = legitimo()
    for k, f in mudar.items():
        f(d)
    return d


FORJADOS = {
    "minimo-vazio": lambda: {"consumidores": [], "assinado_por": "x", "assinado_em": "y", "bloqueia_passo1": False},
    "um-consumidor-so": lambda: {**legitimo(), "consumidores": legitimo()["consumidores"][:1]},
    "ids-trocados": lambda: forjar(a=lambda d: d["consumidores"][0].update(id="qualquer-coisa")),
    "decisao-inventada": lambda: forjar(a=lambda d: d["consumidores"][2].update(decisao="ok")),
    "decisoes-validas-no-json-nao-valem": lambda: forjar(
        a=lambda d: d.update(decisoes_validas=["ok"]), b=lambda d: d["consumidores"][0].update(decisao="ok")),
    "sem-evidencia": lambda: forjar(a=lambda d: d["consumidores"][1].update(evidencia="sim")),
    "sem-confirmacao": lambda: forjar(a=lambda d: d["consumidores"][3].update(confirmado_em_producao=None)),
    "duplicado-no-lugar-de-um": lambda: forjar(
        a=lambda d: d["consumidores"].__setitem__(7, copy.deepcopy(d["consumidores"][0]))),
    "extra-fora-da-lista": lambda: forjar(a=lambda d: d["consumidores"].append(
        {"id": "inventado", "confirmado_em_producao": "x", "evidencia": EVID, "decisao": "nao_usa_anon"})),
    "sem-assinatura": lambda: forjar(a=lambda d: d.update(assinado_por=" ")),
    "sem-data": lambda: forjar(a=lambda d: d.update(assinado_em="")),
    "bloqueia-true": lambda: forjar(a=lambda d: d.update(bloqueia_passo1=True)),
    "bloqueia-string": lambda: forjar(a=lambda d: d.update(bloqueia_passo1="false")),
    "consumidores-nao-lista": lambda: forjar(a=lambda d: d.update(consumidores={"x": 1})),
}


@pytest.mark.parametrize("nome", sorted(FORJADOS))
def test_inventario_forjado_e_recusado(nome, tmp_path):
    arq = tmp_path / "inv.json"
    arq.write_text(json.dumps(FORJADOS[nome]()), encoding="utf-8")
    r = subprocess.run([sys.executable, str(VALIDADOR), str(arq)], capture_output=True, text=True)
    assert r.returncode == 1, f"{nome}: aceito indevidamente: {r.stdout}"
    assert "RECUSADO" in r.stdout


def test_inventario_legitimo_passa(tmp_path):
    arq = tmp_path / "inv.json"
    arq.write_text(json.dumps(legitimo()), encoding="utf-8")
    r = subprocess.run([sys.executable, str(VALIDADOR), str(arq)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "inventario ok: 8" in r.stdout


def test_modelo_do_repositorio_e_recusado():
    r = subprocess.run([sys.executable, str(VALIDADOR), str(RAIZ / "docs" / "INCIDENTE-ANON-INVENTARIO.modelo.json")],
                       capture_output=True, text=True)
    assert r.returncode == 1


def test_modelo_traz_os_mesmos_8_ids_do_validador():
    d = json.loads((RAIZ / "docs" / "INCIDENTE-ANON-INVENTARIO.modelo.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in d["consumidores"]] == list(v.CONSUMIDORES_OBRIGATORIOS)
