"""Número só vale com o mesmo assunto; paráfrase passa; escopo regional vai ao revisor."""
from funnelforge.domain.dossie import FatoDoDossie
from funnelforge.domain.models import PageRole, ResearchFacts
from funnelforge.pipeline.dossie import _INSTRUCAO, _research_facts, escopo_para_o_motor
from funnelforge.pipeline.retry_policy import classe_da_issue
from funnelforge.pipeline.validators.checks import critical_fact_grounding

ANEEL = "https://www.gov.br/aneel/pt-br/assuntos/tarifas/tarifa-social"
CEMIG = "https://www.cemig.com.br/social/tarifa-social/"


def _fato(n, afirmacao, valor, unidade, fonte, escopo=None, jurisdicao=""):
    prov = {"declarado": {"escopo": escopo, "jurisdicao": jurisdicao}} if escopo else {}
    return FatoDoDossie(fact_id=f"f_{n:012x}", afirmacao=afirmacao, tipo="numero", valor=valor,
                        unidade=unidade, source_url=fonte, status="verified",
                        vigente_desde="2025-07-05", verificado_em="2026-10-10",
                        proveniencia=prov)


DESCONTO = _fato(1, "A Tarifa Social concede desconto de 100% nos primeiros 80 kWh do mês.",
                 "100", "%", ANEEL, "nacional", "BR")


def _issues(texto, *fatos, role=PageRole.SOLUTION):
    return critical_fact_grounding(texto, {"facts": _research_facts(list(fatos)), "role": role})


def test_parafrase_com_o_mesmo_assunto_passa():
    texto = (f'<p>Quem tem o benefício paga 0 pelos primeiros 80 kWh: o desconto integral '
             f'é de 100%, segundo a <a href="{ANEEL}">ANEEL</a>.</p>')
    assert [i.code for i in _issues(texto, DESCONTO)] == []


def test_mesmo_numero_de_outro_assunto_vai_ao_revisor():
    texto = f'<p>A aprovação é de 100% para quem pede, segundo a <a href="{ANEEL}">ANEEL</a>.</p>'
    issues = _issues(texto, DESCONTO)
    assert [i.code for i in issues] == ["numero_fora_do_contexto_do_fato"]
    assert classe_da_issue(issues[0]) == "patchavel"           # sentido é do revisor


def test_numero_sem_nenhum_fato_continua_bloqueando():
    issues = _issues(f'<p>O desconto é de 70%, segundo a <a href="{ANEEL}">ANEEL</a>.</p>',
                     DESCONTO)
    assert [i.code for i in issues] == ["ungrounded_critical_claim"]
    assert classe_da_issue(issues[0]) == "estrutural"


def test_numero_so_com_fonte_regional_vira_pista_e_nacional_nao():
    regional = _fato(2, "A Cemig aplica desconto de 100% nos primeiros 80 kWh.", "100", "%",
                     CEMIG, "subnacional", "BR-MG")
    texto = f'<p>O desconto é de 100% nos primeiros 80 kWh (<a href="{CEMIG}">Cemig</a>).</p>'
    codigos = [i.code for i in _issues(texto, regional)]
    assert codigos == ["fonte_so_regional"]
    texto_nacional = texto.replace("(<a", f'(<a href="{ANEEL}">ANEEL</a>, <a')
    assert [i.code for i in _issues(texto_nacional, regional, DESCONTO)] == []


def test_escopo_vem_do_documento_ou_da_declaracao_e_nunca_e_presumido():
    assert escopo_para_o_motor(DESCONTO) == "nacional"
    assert escopo_para_o_motor(_fato(3, "a", "1", "%", CEMIG, "subnacional", "BR-MG")) \
        == "regional:MG"
    assert escopo_para_o_motor(_fato(4, "a", "1", "%", CEMIG, "desconhecido", "BR")) is None
    projecao = _research_facts([DESCONTO])
    assert isinstance(projecao, ResearchFacts)
    assert projecao.fatos_verificados[0].afirmacao.startswith("A Tarifa Social")


def test_lacuna_nao_proibe_o_que_os_fatos_sustentam():
    for estado in ("unavailable", "unsupported"):
        texto = _INSTRUCAO[estado]
        assert "FATOS desta página" in texto and "não esteja nos fatos" in texto
        assert "não afirme valor, prazo nem precisão sobre isso" not in texto


def test_numero_de_fato_de_condicao_e_o_valor_estruturado_nao_a_data():
    """Run final de 10/10: "100%" num fato de condição datado de 05/07/2025
    era lido como 5 e o widget da p6 foi recusado por afirmação sem fato."""
    condicao = FatoDoDossie(
        fact_id="f_00000000000c", tipo="condicao", valor="100", unidade="%",
        afirmacao="Nas faturas emitidas desde 05/07/2025, a TSEE concede desconto de 100% "
                  "sobre a tarifa dos primeiros 80 kWh.", source_url=ANEEL, status="verified")
    texto = f'<p>O desconto é de 100% nos primeiros 80 kWh (<a href="{ANEEL}">ANEEL</a>).</p>'
    assert _issues(texto, condicao) == []
    assert [i.code for i in _issues(texto.replace("100%", "5%"), condicao)] == [
        "ungrounded_critical_claim"]


def test_quantia_escrita_na_frase_do_fato_sem_valor_estruturado():
    """O fato sem `valor` sustenta "100%" que ele mesmo escreve; a data, não."""
    sem_valor = FatoDoDossie(
        fact_id="f_00000000000d", tipo="condicao",
        afirmacao="Nas faturas emitidas desde 05/07/2025, a TSEE concede desconto de 100% "
                  "sobre a tarifa dos primeiros 80 kWh.", source_url=ANEEL, status="verified")
    texto = '<p>Desconto de 100% nos primeiros 80 kWh, segundo a ANEEL.</p>'
    assert _issues(texto, sem_valor, role=PageRole.LP) == []
    assert [i.code for i in _issues(texto.replace("100%", "5%"), sem_valor,
                                    role=PageRole.LP)] == ["ungrounded_critical_claim"]
