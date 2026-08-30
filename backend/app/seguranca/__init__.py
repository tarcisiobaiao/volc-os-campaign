"""Segredos que o sistema guarda por conta de terceiros.

Hoje: o Application Password do WordPress de cada projeto. Ver `segredo.py`
para o porquê da cifra e onde a chave mora.
"""
from app.seguranca.segredo import (
    CofreSemChave,
    SegredoCorrompido,
    cifrar,
    cofre_configurado,
    decifrar,
    gerar_chave,
    mascara,
)

__all__ = [
    "CofreSemChave",
    "SegredoCorrompido",
    "cifrar",
    "cofre_configurado",
    "decifrar",
    "gerar_chave",
    "mascara",
]
