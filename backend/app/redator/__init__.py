"""A camada que liga o Pautador ao motor redator (funnelforge).

O motor é um pacote independente: ele não importa `app.*` e não sabe o que é um
card. Esta camada é a tradução — ela monta, por execução, o que o motor precisa
saber sobre o SITE e sobre o TEMA, e que o `config.yaml` dele não tem como saber.
"""
from app.redator.perfil import PerfilIncompleto, montar_perfil

__all__ = ["PerfilIncompleto", "montar_perfil"]
