"""O manifesto cobre o lock, e nenhuma dependência direta fica sem justificativa nem smoke."""
import json
import tomllib
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]


def test_manifesto_cobre_lock():
    lock = {p["name"]: p["version"] for p in tomllib.loads((LAB / "uv.lock").read_text())["package"]
            if p["name"] != "volc-freedom-lab"}
    man = {i["pacote"]: i for i in json.loads((LAB / "DEPENDENCIAS.json").read_text())["pacotes"]}
    assert set(lock) == set(man), set(lock) ^ set(man)
    assert all(man[n]["versao"] == v for n, v in lock.items())


def test_diretas_tem_campos_humanos():
    py = tomllib.loads((LAB / "pyproject.toml").read_text())
    nomes = {d.split("[")[0].split(">")[0].split("=")[0].split("<")[0].strip()
             for d in py["project"]["dependencies"] + py["dependency-groups"]["test"]}
    man = {i["pacote"]: i for i in json.loads((LAB / "DEPENDENCIAS.json").read_text())["pacotes"]}
    for n in nomes:
        assert man[n]["direta"], n
        for campo in ("justificativa", "risco", "smoke_test", "decisao", "licenca", "fonte"):
            assert man[n][campo] and man[n][campo] != "transitiva", (n, campo)
        assert "não" not in man[n]["licenca"], (n, man[n]["licenca"])


def test_google_ads_fora_do_lab():
    assert "google-ads" not in (LAB / "uv.lock").read_text()
