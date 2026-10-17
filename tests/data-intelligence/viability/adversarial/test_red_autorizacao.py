"""RED — tolerância do owner só com autorização verificável.

Achado 11 da missão V2 (lado do contrato). Na V1 `PerdaMaxima.proveniencia` é texto livre:
"owner" e "bia" valem o mesmo que "ausente", e nada liga o valor a uma identidade, versão ou
vigência.
"""
from __future__ import annotations

import pytest

from volc_dil.contracts import Dinheiro
from volc_dil.viability.contrato import ContratoViabilidadeViolado, PerdaMaxima


@pytest.mark.parametrize("proveniencia", ["owner", "bia", "agente", "chat", ""])
def test_red11a_perda_maxima_com_proveniencia_textual_sem_autorizacao_e_recusada(proveniencia):
    """Achado 11. `PerdaMaxima` com valor 300 BRL / 14 dias e só um texto de proveniência.

    V1 está errada porque aceita o valor com qualquer string (inclusive vazia): a única
    autoridade de gasto do kernel é um campo de texto que qualquer adapter — ou a Bia por um
    caminho indireto — preenche.

    V2 deve recusar (ContratoViabilidadeViolado) todo valor de perda sem `Autorizacao`;
    `de_json` sem o dict `autorizacao` cai na mesma recusa.
    """
    with pytest.raises(ContratoViabilidadeViolado):
        PerdaMaxima.de_json({"valor": {"micros": 300_000_000, "moeda": "BRL"}, "horizonte_dias": 14, "proveniencia": proveniencia})


def test_red11b_perda_maxima_com_valor_e_sem_autorizacao_e_recusada_no_construtor():
    """Achado 11 (construtor). Valor informado e nenhuma autorização: na V1 o construtor exige
    `proveniencia` posicional e aceita; na V2 `autorizacao=None` com valor precisa levantar."""
    with pytest.raises(ContratoViabilidadeViolado):
        try:
            PerdaMaxima(Dinheiro(300_000_000, "BRL"), 14, None)  # V2: autorizacao=None; V1: proveniencia=None (aceito)
        except TypeError as exc:  # V1 não chega a validar nada
            pytest.fail(f"V1 não valida a proveniência: {exc}")


@pytest.mark.parametrize("issuer", ["owner", "bia", "agente", "chat", ""])
def test_red11c_autorizacao_sem_identidade_e_recusada(autorizacao_v2, issuer):
    """Achado 11 (Autorizacao V2). `issuer` genérico ("owner", "bia", "agente", "chat", "") não
    é identidade. V1 não tem `Autorizacao` (falha por construção). V2 deve recusar."""
    with pytest.raises(ContratoViabilidadeViolado):
        autorizacao_v2(issuer=issuer)


def test_red11d_autorizacao_com_hash_adulterado_e_recusada(autorizacao_v2):
    """Achado 11 (Autorizacao V2). Hash que não é o sha256 do JSON canônico
    {authorization_id, version, issuer, effective_at, expires_at} é recusado."""
    with pytest.raises(ContratoViabilidadeViolado):
        autorizacao_v2(hash_errado=True)


def test_red11e_controle_perda_maxima_ausente_continua_valida():
    """Controle (passa na V1 e na V2): "não informada" segue sendo um estado legítimo —
    `valor=None` sem autorização não levanta; só valor SEM autorização levanta."""
    pm = PerdaMaxima.de_json({"valor": None, "horizonte_dias": None})
    assert not pm.informada()
