"""Congela os call sites de mutate do código Google (volc_ads + backend/app + tools/freedom-lab/src).

Toda chamada nova a `*.mutate*(` precisa entrar nesta lista de propósito, num commit
revisado. A lista só contém caminhos que passam por `modo.exigir_leitura_apenas`
(mutar, lote.enviar com validate_only=False) ou que fixam validate_only=True
(validar_mutacoes, pmax.validar_pos_criacao). Medido em 15/10/2026.
"""
import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
PERMITIDOS = {
    ("volc_ads/campanha/pmax.py", "validar_pos_criacao", "mutate_campaign_goal_configs"),
    ("volc_ads/gads/client.py", "mutar", "mutate"),
    ("volc_ads/gads/client.py", "validar_mutacoes", "mutate"),
    ("volc_ads/gestao/lote.py", "enviar", "mutate"),
}


def _achados():
    for base in ("volc_ads", "backend/app", "tools/freedom-lab/src"):
        for arq in (RAIZ / base).rglob("*.py"):
            if arq.name.startswith("test") or arq.name.startswith("testes_"):
                continue
            arvore = ast.parse(arq.read_text(encoding="utf-8"))
            for fn in ast.walk(arvore):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for n in ast.walk(fn):
                        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                and (n.func.attr.startswith("mutate") or n.func.attr == "apply_recommendation")):
                            yield (str(arq.relative_to(RAIZ)), fn.name, n.func.attr)


def test_mutate_so_nos_call_sites_conhecidos():
    achados = set(_achados())
    assert achados <= PERMITIDOS, sorted(achados - PERMITIDOS)


def _fonte(rel: str, nome: str) -> str:
    texto = (RAIZ / rel).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(texto))
              if isinstance(n, ast.FunctionDef) and n.name == nome)
    return ast.get_source_segment(texto, fn)


def test_call_sites_conhecidos_continuam_guardados():
    assert "modo.exigir_leitura_apenas(" in _fonte("volc_ads/gads/client.py", "mutar")
    assert "req.validate_only = True" in _fonte("volc_ads/gads/client.py", "validar_mutacoes")
    assert "validate_only = True" in _fonte("volc_ads/campanha/pmax.py", "validar_pos_criacao")
    assert "exigir_leitura_apenas" in _fonte("volc_ads/gestao/lote.py", "enviar")
