"""A pasta de artefatos, nos DOIS formatos que a tabela guarda.

⚠️ Medido em 19/08/2026, na mesma tabela:

    run 7  artefatos = {"carimbo": "20260818-112043"}
    run 9  artefatos = {"pasta": "fgts-saque-aniversario-20260819-135623", ...}

`_pasta_do_run` só conhecia `carimbo`. Para o run 9 devolvia None, a rota
concluía "os arquivos deste run não estão no disco deste servidor", e o desenho
do funil sumiu da tela — com 32 artefatos ali, incluindo 11 kB de HTML da p3 e
13 kB da p4. Nada tinha se perdido; a tela é que não achava.
"""
from __future__ import annotations

import pytest

from app.routers.publicacao import _pasta_do_run


@pytest.fixture()
def raiz_falsa(tmp_path, monkeypatch):
    (tmp_path / "runs" / "fgts-saque-aniversario-20260819-135623").mkdir(parents=True)
    (tmp_path / "runs" / "maquininha-20260818-112043").mkdir(parents=True)
    from app.redator import worker as w

    monkeypatch.setattr(w, "raiz_do_motor", lambda: tmp_path)
    return tmp_path


def test_formato_novo_com_pasta(raiz_falsa):
    """O nome inteiro da pasta — o mais direto, sem varredura."""
    p = _pasta_do_run({"artefatos": {"pasta": "fgts-saque-aniversario-20260819-135623"}})
    assert p is not None and p.name == "fgts-saque-aniversario-20260819-135623"


def test_formato_antigo_com_carimbo(raiz_falsa):
    """A pasta que TERMINA no carimbo."""
    p = _pasta_do_run({"artefatos": {"carimbo": "20260818-112043"}})
    assert p is not None and p.name == "maquininha-20260818-112043"


def test_run_id_como_ultimo_recurso(raiz_falsa):
    """`run_id` é `<slug>-<carimbo>` — o mesmo nome da pasta."""
    p = _pasta_do_run({"artefatos": {},
                       "run_id": "fgts-saque-aniversario-20260819-135623"})
    assert p is not None and p.name == "fgts-saque-aniversario-20260819-135623"


def test_pasta_que_nao_existe_devolve_none(raiz_falsa):
    assert _pasta_do_run({"artefatos": {"pasta": "run-que-nunca-existiu"}}) is None


def test_sem_nenhuma_pista_devolve_none(raiz_falsa):
    assert _pasta_do_run({"artefatos": {}}) is None
    assert _pasta_do_run({}) is None


def test_o_formato_novo_vence_o_antigo(raiz_falsa):
    """Com os dois, a pasta explícita é a verdade — não a varredura."""
    p = _pasta_do_run({"artefatos": {
        "pasta": "fgts-saque-aniversario-20260819-135623",
        "carimbo": "20260818-112043",
    }})
    assert p is not None and p.name == "fgts-saque-aniversario-20260819-135623"
