"""A regra de legado da tipagem de fatos — carregada do ARQUIVO do motor.

A regra mora em UM lugar: `funnelforge-migracao/engine/src/funnelforge/domain/
tipagem_de_fatos.py` (ver o porquê lá). O volc_ads roda no ambiente do backend,
que não importa o pacote do motor; por isso carrega aquele arquivo por caminho,
sem executar o `__init__` do pacote. O arquivo só usa a biblioteca padrão.

Se o motor não estiver no checkout, isto FALHA na importação, com o caminho: uma
ponte que tipasse fatos por uma cópia divergente da regra é exatamente o defeito
que este módulo existe para impedir.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ARQUIVO = (Path(__file__).resolve().parents[1] / "funnelforge-migracao" / "engine" / "src"
           / "funnelforge" / "domain" / "tipagem_de_fatos.py")
_NOME = "volc_ads._tipagem_de_fatos_do_motor"


def _carregar():
    if _NOME in sys.modules:
        return sys.modules[_NOME]
    if not ARQUIVO.is_file():
        raise ImportError(f"regra de tipagem de fatos do motor ausente: {ARQUIVO}")
    spec = importlib.util.spec_from_file_location(_NOME, ARQUIVO)
    if spec is None or spec.loader is None:
        raise ImportError(f"não consegui carregar {ARQUIVO}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_NOME] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(_NOME, None)
        raise
    return mod


_regra = _carregar()

ORIGENS = _regra.ORIGENS
tipo_pela_regra_de_legado = _regra.tipo_pela_regra_de_legado
unidade_e_norma = _regra.unidade_e_norma
