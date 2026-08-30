"""A nota do anúncio vem do GOOGLE, não do nosso palpite.

## Por que este arquivo existe

Três rodadas do mesmo erro, medidas em 19/08/2026:

    card 74  · termo em 1 de 15 títulos → Ad Strength **Médio**
    card 65  · termo em 4 de 15 títulos → Ad Strength **Ruim**
    card 65 (2ª) · 7 de 15 → ainda insuficiente

A cada reprovação eu apertava um limiar que eu mesmo havia chutado. A verdade
estava a uma consulta: `ad_group_ad.ad_strength` e `ad_group_ad.action_items`.

⚠️ Nenhum teste aqui abre rede. A consulta é injetada — o que se prova é a
DECISÃO em cima da resposta, que é onde eu vinha errando.
"""
from __future__ import annotations

import pytest

from volc_ads import forca


class _Enum:
    def __init__(self, nome): self.name = nome


class _Pol:
    def __init__(self, ap="APPROVED"): self.approval_status = _Enum(ap)


class _Aga:
    def __init__(self, forca_nome, itens=(), ap="APPROVED"):
        self.resource_name = "customers/1/adGroupAds/2~3"
        self.ad_strength = _Enum(forca_nome)
        self.action_items = list(itens)
        self.policy_summary = _Pol(ap)


class _Camp:
    def __init__(self): self.id = 24156134066; self.name = "BR - x / FGTS / url"


class _Linha:
    def __init__(self, aga): self.campaign = _Camp(); self.ad_group_ad = aga


class _Svc:
    def __init__(self, linhas): self._l = linhas
    def search(self, customer_id, query): return iter(self._l)


# Os itens REAIS que a conta devolveu em 19/08/2026.
ITENS_REAIS = ("Try including more keywords in your headlines.",
               "Try including more keywords in your descriptions.")


def test_le_a_nota_e_os_itens_do_google():
    v = forca.ler("8017851692", "24156134066", login_customer_id="6016739364",
                  servico=_Svc([_Linha(_Aga("AVERAGE", ITENS_REAIS))]))
    assert len(v) == 1
    assert v[0].ad_strength == "AVERAGE"
    assert v[0].itens == ITENS_REAIS
    assert v[0].precisa_refazer and not v[0].boa


@pytest.mark.parametrize("nota,boa,refaz", [
    ("EXCELLENT", True, False), ("GOOD", True, False),
    ("AVERAGE", False, True), ("POOR", False, True),
])
def test_o_veredito_classifica_certo(nota, boa, refaz):
    v = forca.Veredito("r", "1", "n", nota)
    assert v.boa is boa and v.precisa_refazer is refaz


@pytest.mark.parametrize("nota", ["PENDING", "UNKNOWN", "UNSPECIFIED"])
def test_pendente_nao_e_reprovado(nota):
    """⚠️ `PENDING` é "ainda não avaliei", não "está ruim". Tratar como
    reprovado faria o motor refazer uma copy que o Google nem olhou — e refazer
    custa a cascata inteira."""
    v = forca.Veredito("r", "1", "n", nota)
    assert v.pendente
    assert not v.precisa_refazer and not v.boa


def test_a_realimentacao_leva_o_texto_do_google_INTEIRO():
    """Traduzir ou resumir seria eu reinterpretando o veredito — e foi
    exatamente a minha interpretação que errou três vezes."""
    r = forca.realimentar((forca.Veredito("r", "1", "n", "AVERAGE", ITENS_REAIS),))
    p = r.como_prompt()
    for item in ITENS_REAIS:
        assert item in p, "o item do Google não chegou inteiro ao prompt"
    assert "AVERAGE" in p


def test_a_realimentacao_diz_que_descricoes_tambem_contam():
    """O segundo item foi o que revelou que a C9 olhava só títulos."""
    r = forca.realimentar((forca.Veredito("r", "1", "n", "POOR", ITENS_REAIS),))
    assert any("descriptions" in i for i in r.itens)


def test_a_pior_nota_manda():
    """Um anúncio bom não compensa um ruim no mesmo grupo — é o ruim que
    precisa de conserto."""
    r = forca.realimentar((
        forca.Veredito("a", "1", "n", "GOOD"),
        forca.Veredito("b", "1", "n", "POOR", ("x",)),
    ))
    assert r.nota == "POOR"


def test_itens_repetidos_nao_duplicam():
    r = forca.realimentar((
        forca.Veredito("a", "1", "n", "POOR", ITENS_REAIS),
        forca.Veredito("b", "1", "n", "POOR", ITENS_REAIS),
    ))
    assert r.itens == ITENS_REAIS


def test_sem_veredito_nao_realimenta_nada():
    r = forca.realimentar(())
    assert not r.acionavel and r.como_prompt() == ""


def test_o_modulo_nao_escreve_nada():
    """Leitura pura: sem `destravar()`, sem `mutate`. Este módulo lê o veredito
    de uma campanha PAUSADA, que é o juiz que custa zero."""
    import ast
    import inspect

    # As CHAMADAS, não as menções: a própria docstring deste módulo explica que
    # ele não destrava nada, e um `in fonte` casaria com a explicação.
    arvore = ast.parse(inspect.getsource(forca))
    chamadas = {
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(arvore) if isinstance(n, ast.Call)
    }
    assert "destravar" not in chamadas
    assert not any("mutate" in c.lower() for c in chamadas if c)
    # e a única consulta é `search` — leitura
    assert "search" in chamadas


# ── o número medido, e a procedência dele ───────────────────────────────────

def test_o_bom_medido_esta_registrado_com_procedencia():
    """⚠️ Um número sem procedência vira folclore em duas semanas.

    O limiar de variedade que a `C11` cobra não é do Google — é o que ESTA conta
    aceitou, em 19/08/2026, na campanha 24156373085. Se alguém mexer nele, tem
    de saber contra o que ele foi medido, e que a linha do meio (cobertura de
    raiz no teto → mesma nota) é a que prova a causa."""
    import inspect

    from volc_ads import forca
    from volc_ads.copy import contrato

    doc = inspect.getdoc(forca) or ""
    assert "24156373085" in doc and "24161105437" in doc, (
        "as duas campanhas do teste têm de estar nomeadas — uma sozinha não prova")
    assert "16/82" in doc or "16 das 82" in doc

    c11 = inspect.getdoc(contrato._c11_variedade_de_keywords) or ""
    assert "24156373085" in c11
    assert "não é limiar do google" in c11.lower() or \
           "nao e limiar do google" in c11.lower(), (
        "sem essa ressalva o número vira régua publicada que ninguém publicou")


def test_o_atraso_da_api_esta_documentado():
    """Medido: o painel mostrava Bom e a API devolveu PENDING por 40 minutos.

    Sem isto escrito, o próximo a montar o laço 'subir → ler → refazer' conclui
    que a campanha falhou e refaz uma copy que o Google nem olhou."""
    import inspect

    from volc_ads import forca

    doc = inspect.getdoc(forca) or ""
    assert "40 minutos" in doc or "40 min" in doc
    assert "PENDING" in doc
