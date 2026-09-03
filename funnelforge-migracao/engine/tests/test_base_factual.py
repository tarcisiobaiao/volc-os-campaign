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


def test_no_destino_pago_a_fonte_e_citada_em_prosa_e_nunca_como_link():
    """CONTRAPROVA 28, na ORIGEM: o redator deixa de receber a URL para embutir.

    A instrução era literal — "AO USAR ESTE NÚMERO, inclua este link na MESMA
    frase: <url>" — e o resultado dela está na evidência preservada: sete links
    `caixa.gov.br` no corpo de `/r/fgts-saque-aniversario/`, o achado mais forte
    do incidente. Num destino pago a fonte pertence ao dossiê de evidência e é
    citada em PROSA, com âncora descritiva; em página editorial ela continua
    permitida, e é o PAPEL que decide.
    """
    f = ResearchFacts(fatos_verificados=[_fato("https://www.caixa.gov.br/fgts/")],
                      fontes_resolvidas=["https://www.caixa.gov.br/fgts/"])

    editorial = base_para_o_redator(f)
    assert "https://www.caixa.gov.br/fgts/" in editorial
    assert "inclua este link" in editorial

    pago = base_para_o_redator(f, destino_pago=True)
    # A URL não é oferecida em lugar nenhum do que o modelo lê.
    assert "https://" not in pago, pago
    # O NOME pelo qual citar, sim — é ele que vira âncora descritiva em prosa.
    assert "caixa.gov.br" in pago
    assert "NÃO escreva a URL" in pago
