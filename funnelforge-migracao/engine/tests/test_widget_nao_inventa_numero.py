"""O widget é texto publicado — e estava fora do gate factual.

## O defeito, medido no run #6 (17/08/2026)

A página 3 do funil passou em TUDO: pesquisa OK, redação OK de primeira, juiz
OK, SEO, imagem, print, build, e o widget finalmente OK depois da retentativa
que a camada 3 trouxe. US$ 0,74 de trabalho pronto.

E morreu no `content_gate_p3`:

    [ungrounded_critical_claim] Afirmação crítica sem fato tipado e fonte
    resolvida: '60 dias'.

O `60 dias` não estava no artigo — estava DENTRO do bloco do widget:
"Dê um intervalo de pelo menos 30 a 60 dias entre tentativas". O gerador de
widget recebia o artigo e o arquétipo, e NADA sobre quais números são
permitidos. Seu sanitizador só olhava segurança (script externo, formulário,
`&`), nunca afirmação factual. Então ele inventou um prazo, e o gate final —
que valida o conteúdo COM o widget injetado — matou a página.

## O conserto, em duas pontas

1. O gerador passa a receber a MESMA base podada que o redator (`facts`), com a
   regra escrita: número só da base, e se não houver, escreva o passo sem ele.
2. O gate factual roda sobre o bloco ANTES da injeção, junto com o sanitizador
   — assim a falha vira RETENTATIVA (a camada 3 já existe) em vez de morte da
   página no fim.
"""
from __future__ import annotations

from datetime import date

from funnelforge.domain.models import ResearchFacts, VerifiedFact
from funnelforge.pipeline.validators.checks import run_validators
from funnelforge.prompts import render

BLOCO_COM_PRAZO_INVENTADO = (
    '<!-- wp:html -->\n<div id="wg-x"><div class="wg-step-text">'
    "<strong>Aguarde o tempo de cura:</strong> Dê um intervalo de pelo menos "
    "30 a 60 dias entre tentativas.</div></div>\n<!-- /wp:html -->"
)


def _facts_sem_prazo() -> ResearchFacts:
    return ResearchFacts(
        resumo="r",
        fontes_resolvidas=["https://www.bcb.gov.br/"],
        fatos_verificados=[VerifiedFact(
            valor="1,85", unidade="% ao mês",
            fonte_primaria="https://www.bcb.gov.br/",
            dispositivo="Resolução X, art. 3º",
            vigente_desde=date(2026, 1, 1), verificado_em=date(2026, 8, 17))],
    )


def test_o_gate_factual_pega_o_numero_inventado_no_widget():
    """É o caso literal do run #6. Agora ele é detectado sobre o BLOCO, o que
    permite retentar — antes só aparecia no gate final, com a página perdida."""
    issues = run_validators(["critical_fact_grounding"], BLOCO_COM_PRAZO_INVENTADO,
                            {"facts": _facts_sem_prazo()})
    assert any(i.code == "ungrounded_critical_claim" for i in issues)
    assert any("60 dias" in str(i.message) for i in issues)


def test_widget_sem_numero_nenhum_passa():
    """O caminho que o prompt agora ensina: escrever o passo SEM a cifra."""
    limpo = ('<!-- wp:html -->\n<div id="wg-x"><div class="wg-step-text">'
             "<strong>Aguarde o tempo de cura:</strong> respeite o intervalo "
             "recomendado pelo banco antes de tentar de novo.</div></div>\n"
             "<!-- /wp:html -->")
    assert run_validators(["critical_fact_grounding"], limpo,
                          {"facts": _facts_sem_prazo()}) == []


def test_o_prompt_do_widget_carrega_a_base_factual():
    """Sem a variável no template, o gerador continuaria escrevendo às cegas."""
    saida = render("redator_widget", country="Brasil", year=2026,
                   title="Cartão para negativado", article="<p>x</p>",
                   arquetipo="roteador",
                   facts=("FATOS VERIFICADOS — os ÚNICOS números que você "
                          "pode usar (1):\n  1. 1,85 % ao mês"))
    baixo = saida.lower()
    assert "proibido inventar número" in baixo
    assert "1,85 % ao mês" in saida            # a base chegou mesmo
    assert "derruba a página inteira" in baixo  # a consequência, dita


def test_sem_fatos_o_widget_e_instruido_a_nao_usar_cifra():
    saida = render("redator_widget", country="Brasil", year=2026,
                   title="t", article="<p>x</p>", arquetipo="roteador", facts="")
    assert "sem cifra, sem percentual e sem prazo" in saida.lower()
