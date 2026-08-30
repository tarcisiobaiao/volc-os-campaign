"""A rigidez que fazia perder página por coisa contornável.

Cada teste aqui nasce de um número medido no run #6 (17/08/2026), o funil de
"Cartão para Negativado" que precisou de cinco tentativas e ainda assim entregou
3 de 5 páginas.

O que se afrouxa é a CONSEQUÊNCIA de não conseguir verificar. O que NÃO se
afrouxa é a regra: número publicado continua exigindo fonte que respondeu ao
vivo. A diferença é que agora "não deu para conferir" custa a cifra, não a
página inteira.
"""
from __future__ import annotations


from funnelforge.adapters.url_verifier_http import HttpUrlVerifier
from funnelforge.domain.models import ResearchFacts, StepResult, StepStatus
from funnelforge.pipeline.steps import _gate_research
from funnelforge.pipeline.validators.checks import critical_fact_grounding


# ── 1 · bloqueado não é inexistente ────────────────────────────────────────

class _VerificadorFalso:
    """Espelha o contrato do `HttpUrlVerifier`: `verify_url` + `bloqueada`."""

    def __init__(self, bloqueadas=(), recusadas=()):
        self._bloq = set(bloqueadas)
        self._rec = set(recusadas)

    def verify_url(self, url: str) -> bool:
        return url not in self._bloq and url not in self._rec

    def bloqueada(self, url: str) -> bool:
        return url in self._bloq

    def motivo(self, url: str) -> str:
        if url in self._bloq:
            return "bloqueado/indisponível para verificação (HTTP 403)"
        return "HTTP 404"


class _Deps:
    def __init__(self, verifier):
        self.url_verifier = verifier
        self.settings = type("S", (), {
            "steps": {}, "run": type("R", (), {"research_max_age_days": 45})()})()


def _facts_com(*fontes) -> ResearchFacts:
    """⚠️ `fontes` precisa listar as mesmas URLs de `fonte_primaria`.

    O `research_facts_contract` reprova fato cuja fonte primária não aparece na
    lista de fontes — e sem isso a fixture falha por um motivo que não é o que
    o teste quer medir, dando falso vermelho no gate de bloqueio.
    """
    return ResearchFacts(
        resumo="x", sparse=False, fontes=list(fontes),
        fatos_verificados=[{
            "valor": "300", "unidade": "pontos", "dispositivo": "faixa de score",
            "fonte_primaria": f, "vigente_desde": "2026-01-01",
            "verificado_em": "2026-08-17",
        } for f in fontes],
    )


def test_fonte_bloqueada_nao_derruba_a_pesquisa():
    """O caso literal da página 4: `bancobmg.com.br` responde 403 a qualquer
    User-Agent declarado. É um WAF num banco de verdade — não uma URL morta.

    A página tinha outros fatos com fonte boa e morria junto."""
    facts = _facts_com("https://www.bancobmg.com.br", "https://www.serasa.com.br/")
    res = StepResult(step="research_p4", status=StepStatus.OK, attempts=1)
    _gate_research(facts, res, _Deps(_VerificadorFalso(
        bloqueadas={"https://www.bancobmg.com.br"})))

    assert res.status is not StepStatus.FAILED, "bloqueio não pode matar a pesquisa"
    codes = {i.code for i in res.issues}
    assert "fact_source_unverifiable" in codes
    assert "fact_source_unreachable" not in codes


def test_a_fonte_bloqueada_sai_de_fontes_resolvidas():
    """A rigidez que PERMANECE: sem verificação ao vivo, nenhuma cifra daquela
    fonte pode ser publicada. `base_factual` poda o que não está resolvido."""
    facts = _facts_com("https://www.bancobmg.com.br", "https://www.serasa.com.br/")
    res = StepResult(step="research_p4", status=StepStatus.OK, attempts=1)
    _gate_research(facts, res, _Deps(_VerificadorFalso(
        bloqueadas={"https://www.bancobmg.com.br"})))

    assert facts.fontes_resolvidas == ["https://www.serasa.com.br/"]


def test_url_morta_continua_reprovando():
    """404 e HTML de erro são outra coisa: a fonte não serve, e uma busca nova
    pode achar outra. Continua fatal e continua retentável."""
    facts = _facts_com("https://exemplo.invalido/pagina-morta")
    res = StepResult(step="research_p4", status=StepStatus.OK, attempts=1)
    _gate_research(facts, res, _Deps(_VerificadorFalso(
        recusadas={"https://exemplo.invalido/pagina-morta"})))

    assert res.status is StepStatus.FAILED
    assert "fact_source_unreachable" in {i.code for i in res.issues}


def test_todas_bloqueadas_ainda_deixa_a_pagina_viver():
    """O caso extremo, e é o que o operador pediu: se NENHUMA fonte pôde ser
    conferida, a página é escrita sem cifra nenhuma — não é perdida."""
    facts = _facts_com("https://a.exemplo", "https://b.exemplo")
    res = StepResult(step="research_p4", status=StepStatus.OK, attempts=1)
    _gate_research(facts, res, _Deps(_VerificadorFalso(
        bloqueadas={"https://a.exemplo", "https://b.exemplo"})))

    assert res.status is not StepStatus.FAILED
    assert facts.fontes_resolvidas == []


def test_verificador_de_verdade_classifica_403_como_bloqueio():
    """O contrato que o gate consome, no adapter real."""
    v = HttpUrlVerifier()
    v.stats.reasons["https://x"] = "bloqueado/indisponível para verificação (HTTP 403)"
    v.stats.reasons["https://y"] = "HTTP 404"
    v.stats.reasons["https://z"] = "falha de rede: ConnectTimeout"
    assert v.bloqueada("https://x") is True
    assert v.bloqueada("https://y") is False      # não existe ≠ não deu para saber
    assert v.bloqueada("https://z") is True       # timeout também é "não deu"


# ── 5 · o portão que aprovava em silêncio ──────────────────────────────────

TEXTO_COM_CIFRA = "<p>Aguarde um intervalo de 30 a 60 dias entre as tentativas.</p>"


def test_portao_sem_fatos_nao_aprova_texto_com_cifra():
    """⚠️ O defeito mais caro dos cinco: sem `facts` no contexto o validador
    devolvia `[]` e APROVAVA qualquer coisa.

    Medido no run #6: `widget_p3` gravou OK com "30 a 60 dias" dentro, e o
    portão final reprovou a página inteira pelo mesmo texto — com pesquisa,
    redação, juiz, SEO, imagem e widget já pagos. Rodando o validador à mão no
    mesmo bloco COM os fatos, ele acusa. Ou seja: no run ele não os recebeu.

    Aprovar em silêncio é o pior desfecho de um portão: quem lê não distingue
    "não havia o que reprovar" de "eu não consegui olhar".
    """
    issues = critical_fact_grounding(TEXTO_COM_CIFRA, {})
    assert [i.code for i in issues] == ["fact_grounding_sem_contexto"]


def test_portao_sem_fatos_deixa_passar_texto_sem_cifra():
    """Não é para virar reprovação universal: sem afirmação crítica não há o
    que ancorar, e barrar aí seria trocar um defeito por outro."""
    assert critical_fact_grounding("<p>Texto sem número nenhum.</p>", {}) == []


def test_portao_com_fatos_continua_funcionando():
    facts = ResearchFacts(
        sparse=False,
        fatos_verificados=[{
            "valor": "30 a 60", "unidade": "dias", "dispositivo": "intervalo",
            "fonte_primaria": "https://www.serasa.com.br/",
            "vigente_desde": "2026-01-01", "verificado_em": "2026-08-17",
        }],
        fontes_resolvidas=["https://www.serasa.com.br/"],
    )
    texto = TEXTO_COM_CIFRA.replace("</p>", " https://www.serasa.com.br/</p>")
    codes = {i.code for i in critical_fact_grounding(texto, {"facts": facts})}
    assert "ungrounded_critical_claim" not in codes
    assert "fact_grounding_sem_contexto" not in codes


# ── 3 · vigência no futuro poda o FATO, não a página ───────────────────────
#
# ⚠️ A SEGUNDA morte da p2 na run 9 (19/08/2026). Oito fatos verificados, UM
# com `vigente_desde='2026-11-01'`. Os outros quatro da mesma fonte diziam
# `2025-11-01` — um dígito trocado. `research_facts_contract` reprovava, o
# passo virava FAILED, `write_p2` morria com `research_dependency_failed` e a
# página não chegava a ser escrita.
#
# É a mesma doutrina do bloco 1: o que não pode chegar ao texto é a cifra do
# fato ruim. Podá-lo garante isso melhor do que matar a página garantia.

def _facts_com_futuro(fonte: str, vigencias: list[str]) -> ResearchFacts:
    return ResearchFacts(
        resumo="x", sparse=False, fontes=[fonte],
        fatos_verificados=[{
            "valor": str(i), "unidade": "dias", "dispositivo": "prazo",
            "fonte_primaria": fonte, "vigente_desde": v, "verificado_em": "2026-08-19",
        } for i, v in enumerate(vigencias, 1)],
    )


def test_fato_com_vigencia_futura_nao_derruba_a_pagina():
    facts = _facts_com_futuro("https://www.caixa.gov.br",
                              ["2025-11-01", "2026-11-01", "2025-11-01"])
    res = StepResult(step="research_p2", status=StepStatus.OK, attempts=1)
    _gate_research(facts, res, _Deps(_VerificadorFalso()))

    assert res.status is not StepStatus.FAILED, (
        "um fato datado no futuro voltou a matar a página inteira")
    assert "fato_vigencia_futura_podado" in {i.code for i in res.issues}


def test_o_fato_futuro_some_e_os_bons_ficam():
    """A rigidez que PERMANECE: a cifra do fato não-vigente não chega ao texto."""
    facts = _facts_com_futuro("https://www.caixa.gov.br",
                              ["2025-11-01", "2026-11-01", "2025-11-01"])
    res = StepResult(step="research_p2", status=StepStatus.OK, attempts=1)
    _gate_research(facts, res, _Deps(_VerificadorFalso()))

    vigencias = [str(f.vigente_desde) for f in facts.fatos_verificados]
    assert vigencias == ["2025-11-01", "2025-11-01"]
    assert all("2026-11-01" not in str(f.valor) for f in facts.fatos_verificados)


def test_o_aviso_diz_qual_data_e_qual_fonte():
    """A retentativa precisa saber O QUE podar — e o operador, por quê."""
    facts = _facts_com_futuro("https://www.caixa.gov.br", ["2026-11-01", "2025-11-01"])
    res = StepResult(step="research_p2", status=StepStatus.OK, attempts=1)
    _gate_research(facts, res, _Deps(_VerificadorFalso()))

    aviso = next(i for i in res.issues if i.code == "fato_vigencia_futura_podado")
    assert "2026-11-01" in aviso.message
    assert "caixa.gov.br" in aviso.message


def test_podar_tudo_marca_a_pesquisa_como_sparse():
    """Quando NADA sobra, o motor tem de dizer isso com o vocabulário que já
    tem: `sparse=True`. É o que faz o redator escrever de forma qualitativa em
    vez de achar que tem base factual.

    Não vira reprovação: inventar aqui uma morte nova seria trocar um excesso
    de rigidez por outro. Quem impede número sem lastro é o
    `critical_fact_grounding` no gate final — e ele continua de pé."""
    facts = _facts_com_futuro("https://www.caixa.gov.br", ["2026-11-01", "2027-01-01"])
    res = StepResult(step="research_p2", status=StepStatus.OK, attempts=1)
    _gate_research(facts, res, _Deps(_VerificadorFalso()))

    assert facts.fatos_verificados == []
    assert facts.sparse is True
    assert len([i for i in res.issues if i.code == "fato_vigencia_futura_podado"]) == 2
