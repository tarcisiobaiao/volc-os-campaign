"""Põe os construtores de entrada (`_entradas.py`) no path dos testes de viabilidade."""
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))
