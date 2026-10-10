"""Defeitos achados na execução real de 10/10 (bucket), corrigidos sem nova chamada."""
from funnelforge.domain.models import Page, PageDraft, PageRole, ResearchFacts
from funnelforge.pipeline.retry_policy import classe_da_issue
from funnelforge.pipeline.steps import seo_deterministico
from funnelforge.pipeline.validators.checks import critical_fact_grounding

ANEEL = "https://www.gov.br/aneel/pt-br/assuntos/tarifas/tarifa-social"
EDP = "https://www.edp.com.br/tarifa-e-desconto-social/"


def _fatos(*pares):
    fatos = [{"valor": v, "unidade": u, "fonte_primaria": f, "dispositivo": "não se aplica",
              "vigente_desde": "2025-07-05", "verificado_em": "2026-10-10", "tipo": "numero"}
             for v, u, f in pares]
    fontes = sorted({f for _v, _u, f in pares})
    return ResearchFacts(fatos_verificados=fatos, fontes=fontes, fontes_resolvidas=fontes)


def test_qualquer_fato_que_sustenta_vale_quando_a_fonte_dele_e_citada():
    """A EDP vem primeiro na lista; a pré-sell cita a ANEEL, que também sustenta."""
    fatos = _fatos(("100", "%", EDP), ("100", "%", ANEEL))
    texto = "<p>O desconto é de 100% nos primeiros 80 kWh, conforme a ANEEL.</p>"
    assert critical_fact_grounding(texto, {"facts": fatos, "role": PageRole.PRESELL}) == []


def test_match_mecanico_de_numero_nao_decide_publicacao():
    fatos = _fatos(("100", "%", ANEEL))
    issues = critical_fact_grounding("<p>O desconto é de 70%, segundo a ANEEL.</p>",
                                     {"facts": fatos, "role": PageRole.PRESELL})
    assert [i.code for i in issues] == ["ungrounded_critical_claim"]
    assert classe_da_issue(issues[0]) == "patchavel"


def test_atribuicao_em_prosa_e_julgada_pelo_revisor_em_todos_os_papeis():
    fatos = _fatos(("60", "anos", EDP))
    texto = "<p>Ter 60 anos não basta, segundo a ANEEL.</p>"
    presell = critical_fact_grounding(texto, {"facts": fatos, "role": PageRole.PRESELL})
    assert [i.code for i in presell] == ["critical_claim_without_citation"]
    assert "edp.com.br" in presell[0].message and classe_da_issue(presell[0]) == "patchavel"
    solucao = critical_fact_grounding(texto, {"facts": fatos, "role": PageRole.SOLUTION})
    assert classe_da_issue(solucao[0]) == "patchavel"


def _pagina(h1):
    return Page(page_number=3, page_type="SOLUÇÃO", h1_title=h1, slug="s")


def _rascunho(paragrafo):
    return PageDraft(page_number=3, page_type="SOLUÇÃO", format="gutenberg",
                     content=f"<p>{paragrafo}</p>")


def test_titulo_visivel_nao_e_cortado_no_meio_da_oracao():
    inteiro = "Tarifa Social de Energia Elétrica: o desconto e por onde começar"
    assert seo_deterministico(_pagina(inteiro), None)["seotitle"] == inteiro
    longo = "Tarifa Social na Cemig, Enel e outras distribuidoras: encontre o atendimento"
    assert seo_deterministico(_pagina(longo), None)["seotitle"] == \
        "Tarifa Social na Cemig, Enel e outras distribuidoras"


def test_descricao_termina_em_frase_inteira():
    p4 = ("Para encontrar onde tratar da Tarifa Social de Energia Elétrica, confira a "
          "distribuidora indicada na sua fatura e confirme que o atendimento encontrado "
          "atende aquela operação e aquela unidade consumidora.")
    assert seo_deterministico(_pagina("Título"), _rascunho(p4))["metadescription"] == (
        "Para encontrar onde tratar da Tarifa Social de Energia Elétrica, confira a "
        "distribuidora indicada na sua fatura.")
    p7 = ("O Desconto Social na conta de luz e a Tarifa Social de Energia Elétrica são "
          "modalidades diferentes: os critérios de acesso e a parcela da cobrança afetada "
          "precisam ser conferidos na fonte de cada modalidade antes de qualquer conclusão.")
    assert seo_deterministico(_pagina("Título"), _rascunho(p7))["metadescription"] == (
        "O Desconto Social na conta de luz e a Tarifa Social de Energia Elétrica são "
        "modalidades diferentes.")


def test_saida_oficial_prefere_a_fonte_da_pagina_e_o_emissor_nacional():
    from types import SimpleNamespace as NS
    from funnelforge.domain.models import RunState
    from funnelforge.pipeline.steps import _ordem_dos_canais
    cemig = "https://www.cemig.com.br/social/tarifa-social/"
    cadunico = "https://www.gov.br/pt-br/servicos/inscrever-se-no-cadastro-unico"
    state = RunState(run_id="r", dossie={"fatos": [
        {"source_url": cemig, "paginas": ["q_x"],
         "proveniencia": {"emissor_verificado": True, "tipo_de_emissor": "outro"}},
        {"source_url": ANEEL, "paginas": ["q_x"],
         "proveniencia": {"emissor_verificado": True, "tipo_de_emissor": "regulador",
                          "escopo": "nacional"}},
        {"source_url": cadunico, "paginas": ["como_obter"], "proveniencia": {}}]})
    pagina = NS(jornada=NS(duvida_id="como_obter"))
    # Emissor nacional conferido primeiro; entre os demais, a fonte da página.
    assert _ordem_dos_canais(state, pagina, [cemig, ANEEL, cadunico]) == [ANEEL, cadunico, cemig]
    outra = NS(jornada=NS(duvida_id="outra"))
    assert _ordem_dos_canais(state, outra, [cemig, ANEEL, cadunico])[0] == ANEEL


def test_fonte_regional_da_pagina_nao_passa_a_frente_do_servico_nacional():
    """Run final de 10/10: as duas fontes eram da p4; a notícia do governo da
    Bahia ficou à frente do "Fale com a sua distribuidora" da ANEEL."""
    from types import SimpleNamespace as NS
    from funnelforge.domain.models import RunState
    from funnelforge.pipeline.steps import _ordem_dos_canais
    bahia = "https://www.ba.gov.br/justica/noticias/2025-01/17854/servico-de-energia"
    fale = "https://www.gov.br/aneel/pt-br/canais_atendimento/fale-com-a-sua-distribuidora"
    state = RunState(run_id="r", dossie={"fatos": [
        {"source_url": bahia, "paginas": ["por_distribuidora"],
         "proveniencia": {"emissor_verificado": True, "escopo": "desconhecido",
                          "declarado": {"escopo": "subnacional"}}},
        {"source_url": fale, "paginas": ["por_distribuidora"],
         "proveniencia": {"emissor_verificado": True, "tipo_de_emissor": "regulador",
                          "escopo": "nacional"}}]})
    pagina = NS(jornada=NS(duvida_id="por_distribuidora"))
    assert _ordem_dos_canais(state, pagina, [bahia, fale]) == [fale, bahia]
