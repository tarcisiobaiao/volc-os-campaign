from __future__ import annotations

import importlib.util
from pathlib import Path


CAMINHO = Path(__file__).resolve().parents[1] / "verificar_autoridade_supabase.py"
SPEC = importlib.util.spec_from_file_location("autoridade_supabase", CAMINHO)
assert SPEC and SPEC.loader
MODULO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULO)


def test_templates_e_ambientes_vivos_usam_a_autoridade_oficial():
    assert MODULO.conferir() == []


def test_url_hospedada_e_recusada_sem_imprimir_segredo(tmp_path, monkeypatch):
    divergente = tmp_path / ".env.server"
    divergente.write_text(
        "SUPABASE_URL=https://projeto.supabase.co\n"
        "SUPABASE_SERVICE_ROLE_KEY=segredo-que-nao-pode-vazar\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(MODULO, "TEMPLATES", {})
    monkeypatch.setattr(MODULO, "AMBIENTES_LOCAIS", {divergente: ("SUPABASE_URL",)})
    monkeypatch.setattr(MODULO, "RAIZ", tmp_path)

    erros = MODULO.conferir()

    assert erros == [".env.server: SUPABASE_URL aponta para outro Supabase"]
    assert "segredo-que-nao-pode-vazar" not in " ".join(erros)
