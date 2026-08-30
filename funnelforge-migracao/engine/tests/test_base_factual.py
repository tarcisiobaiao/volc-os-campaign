from datetime import date
from funnelforge.domain.models import ResearchFacts, VerifiedFact
from funnelforge.pipeline.base_factual import base_para_o_redator, tem_numero_publicavel

def _fato(fonte, valor="1,85"):
    return VerifiedFact(valor=valor, unidade="% ao mês", fonte_primaria=fonte,
                        dispositivo="Resolução X, art. 3º",
                        vigente_desde=date(2026,1,1), verificado_em=date(2026,8,17))

def test_numero_sem_fonte_resolvida_nao_chega_ao_redator():
    """O caso do run #4: `100% do CDI` tinha fato tipado, mas a fonte não
    resolveu. O redator usou assim mesmo e o gate matou a página 3 vezes."""
    f = ResearchFacts(resumo="rende 100% do CDI",
                      fatos_verificados=[_fato("https://naoresolveu.com/", "100")],
                      fontes_resolvidas=[])
    saida = base_para_o_redator(f)
    assert "100" not in saida
    assert "FATOS VERIFICADOS: NENHUM" in saida
    assert not tem_numero_publicavel(f)

def test_fato_com_fonte_resolvida_chega_pronto_para_citar():
    f = ResearchFacts(resumo="o teto é de 1.85% ao mês",
                      fatos_verificados=[_fato("https://www.gov.br/")],
                      fontes_resolvidas=["https://www.gov.br/"])
    saida = base_para_o_redator(f)
    assert "1,85 % ao mês" in saida
    assert "AO USAR ESTE NÚMERO, inclua este link na MESMA frase: https://www.gov.br/" in saida
    # e o mesmo número, na prosa NÃO verificada, foi podado
    assert "o teto é de [número não verificado" in saida
    assert tem_numero_publicavel(f)

def test_poda_usa_a_mesma_regra_do_gate():
    """Simetria: o que o validador reprovaria é exatamente o que some da
    entrada. Se as duas divergirem, volta a sobrar número tentador."""
    f = ResearchFacts(resumo="R$ 500,00 em 30 dias, conforme a Lei 8.036/90, com 5% de taxa")
    saida = base_para_o_redator(f)
    for proibido in ("R$ 500", "30 dias", "Lei 8.036", "5%"):
        assert proibido not in saida, proibido

def test_sem_pesquisa_nenhuma_o_contrato_continua_explicito():
    saida = base_para_o_redator(None)
    assert "NENHUM" in saida and "sem cifra" in saida.lower()
