"""A posição manda no sufixo do slug — não o texto que o arquiteto escreveu.

⚠️ Custou um run inteiro em 19/08/2026. O arquiteto escreveu a `current_url` da
landing page do card 65 como `fgts-saque-aniversario-p1` — sufixo de página
solução. `_slug_com_sufixo` era idempotente no sentido fraco: viu um sufixo e
não mexeu. `derive_role` leu `-p1` e devolveu SOLUTION. Nenhuma das cinco
páginas ficou com papel LP, o BFS de `reachable_slugs` partiu de lista vazia, e
as CINCO saíram como `unreachable_page`.

O run terminou `done` em nove segundos, com zero páginas e US$ 0,0048 gastos.

A raiz é haver duas fontes de verdade: o backend declara `role: "landing"` no
job e o engine RE-DERIVA o papel do texto do slug. O engine não pode deixar de
derivar — é o contrato dele. Mas pode garantir que o slug corresponda à posição.
"""
import pytest

from funnelforge.adapters.briefing_volc import _slug_com_sufixo
from funnelforge.domain.models import PageRole, derive_role


@pytest.mark.parametrize("slug, posicao, esperado", [
    # O caso real que quebrou o card 65.
    ("fgts-saque-aniversario-p1", 1, "fgts-saque-aniversario"),
    # Já correto: não mexe.
    ("fgts-saque-aniversario", 1, "fgts-saque-aniversario"),
    ("vantagens-desvantagens-pr", 2, "vantagens-desvantagens-pr"),
    # Sem sufixo: põe o da posição.
    ("vantagens-desvantagens", 2, "vantagens-desvantagens-pr"),
    ("como-ativar-p1", 3, "como-ativar-p1"),
    # Sufixo ERRADO: troca pelo da posição.
    ("como-ativar-pr", 3, "como-ativar-p1"),
    ("antecipacao-p9", 4, "antecipacao-p2"),
])
def test_posicao_vence_o_texto(slug, posicao, esperado):
    assert _slug_com_sufixo(slug, posicao) == esperado


def test_a_pagina_1_sempre_vira_LP():
    """É o invariante que o BFS de `reachable_slugs` depende para existir."""
    for slug in ("qualquer-coisa", "qualquer-coisa-p1", "qualquer-coisa-pr",
                 "qualquer-coisa-p7"):
        assert derive_role(_slug_com_sufixo(slug, 1)) is PageRole.LP


def test_slug_vazio_continua_vazio():
    """Sem slug o adaptador levanta erro com mensagem própria — não é aqui."""
    assert _slug_com_sufixo("", 1) == ""
    assert _slug_com_sufixo("   ", 3) == ""
