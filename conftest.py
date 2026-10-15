"""Conftest da raiz (volc_ads, scripts, tools): sessão de teste sem credencial Google real.

Ver volc_ads/hermetico_testes.py. backend/tests tem o seu conftest, que faz o mesmo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from volc_ads import hermetico_testes as _hermetico
    _hermetico.aplicar()
except ImportError:  # venv sem volc_ads importável (ex.: .venv-lab): nada de Google aqui
    pass
