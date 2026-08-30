"""Testes do espaço multidimensional.

O motor não é mais ajustado a operação nenhuma, então não há AUC para testar.
O que há para testar é mais importante: que os PRINCÍPIOS estejam encodados
corretamente, que nada volte a depender de spend, e que ele se cale quando não
sabe.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from motor_pautas import espaco as E

COMPLETO = dict(
    ignorancia="nao_sei_se_existe", engajamento="sustenta", opacidade="fragmentada",
    reposicao="continua", volume="alto", spread="bom", densidade="densa",
    vacuo="disputado", producao="revisao_anual", formato_consumo="texto_busca",
)


def pos(**kw):
    p = dict(COMPLETO)
    p.update(kw)
    return E.posicionar(termo=p.pop("termo", "x"), pais=p.pop("pais", "BR"), **p)


# ── a contaminação não pode voltar ──────────────────────────────────────────

def test_nenhum_eixo_depende_de_spend_ou_receita():
    """Regressão da falha que aposentou a versão anterior.

    O alvo antigo era `lucro > R$ 3.000`, e `spend` sozinho o previa com AUC
    0,971 — o modelo tinha aprendido em que a equipe decidiu investir, não o
    que é um bom tema.
    """
    import ast
    raiz = pathlib.Path(__file__).resolve().parents[2] / "motor_pautas"
    arquivos = ("reverse_temas", "familias_rpm", "modelo_mineracao", "kw_psico",
                "reverse_campanhas")
    for arq in raiz.glob("*.py"):
        arvore = ast.parse(arq.read_text())
        # só literais de código contam; menção em docstring é documentação do
        # que foi retirado, e documentar a retirada é o que impede o retorno
        for no in ast.walk(arvore):
            if isinstance(no, ast.Constant) and isinstance(no.value, str):
                pai_doc = no.value.strip().startswith(("Camada", "O ", "A ", "Motor"))
                if pai_doc or len(no.value) > 200:
                    continue
                for a in arquivos:
                    assert a not in no.value, f"{arq.name} lê {a!r}"


def test_portao_e_par_eixo_nivel_e_zera():
    """Portão é o PAR (eixo, nível), binário. Não é o eixo inteiro.

    A versão anterior fazia `base *= g.valor` em QUALQUER nível dos eixos de
    portão, e o estrago foi reproduzido em revisão externa: `diagnostico ->
    comparativo` custava x0,60 (um passo banal na forma da pergunta) enquanto
    `spread excelente -> ruim` custava só x0,80 — o rótulo declarado por um
    agente movia a nota MAIS que a margem real do negócio.
    """
    assert set(E.PORTOES) == {"engajamento", "ignorancia", "formato_consumo",
                              "spread", "volume"}
    # o par de portão zera...
    assert pos(formato_consumo="video_social").indice == 0.0
    # ...e um nível QUE NÃO É portão no mesmo eixo entra na média como os outros
    texto, misto = pos(formato_consumo="texto_busca"), pos(formato_consumo="misto")
    assert 1.0 < texto.indice / misto.indice < 1.15


def test_sem_stake_e_portao_nao_nivel_baixo():
    """Curiosidade pura: 0% de vitória nas duas rodadas cegas.

    Hiato de conhecimento e interesse são ortogonais — quem busca uma novela
    não sabe nada sobre o capítulo e mesmo assim não paga, porque não há nada
    em jogo.
    """
    curioso = pos(ignorancia=E.SEM_STAKE)
    assert curioso.indice < 0.05
    assert any("SEM STAKE" in a for a in curioso.alertas)


def test_pesos_sao_priores_declarados_e_calibracao_esta_vazia():
    """Enquanto não houver desfecho próprio, calibrar seria repetir o erro."""
    assert E._CALIBRACAO == {}
    assert all(E.peso(d) == E.PRIORES[d] for d in E.PRIORES)


# ── os princípios ───────────────────────────────────────────────────────────

def test_engajamento_nulo_derruba_tudo():
    """A armadilha de lookup: R$ 138.814 gastos, prejuízo líquido.

    O que mata não é falta de páginas — é a resposta que se esgota em segundos:
    o leitor sai antes do anúncio ficar visível e a viewability do domínio cai.
    Nenhuma outra dimensão compensa, e por isso é portão e não peso.
    """
    bom = pos(engajamento="sustenta")
    morto = pos(engajamento="dado_unico", volume="massivo", spread="excelente",
                densidade="densa")
    assert morto.indice < bom.indice / 5
    assert any("ENGAJAMENTO NULO" in a for a in morto.alertas)


def test_ignorancia_manda_mais_que_pressao():
    """O achado do teste cego: o que faz ler é o buraco de conhecimento.

    Quem sabe exatamente o que fazer executa e sai; quem não sabe nem se aquilo
    existe lê tudo.
    """
    ignorante = pos(ignorancia="nao_sei_se_existe")
    sabido = pos(ignorancia="sei_o_que_fazer")
    assert ignorante.indice > sabido.indice


def test_opacidade_maxima_quando_a_regra_mudou():
    assert pos(opacidade="regra_mudou").indice > pos(opacidade="clara").indice


def test_reposicao_vale_mais_que_recorrencia():
    """Gente NOVA entrando na condição > a mesma gente voltando."""
    assert pos(reposicao="continua").indice > pos(reposicao="mesma_gente").indice


def test_spread_e_o_eixo_economico_nao_o_ecpm():
    """Tier 1 tem eCPM alto E CPC alto. O que decide é a razão."""
    assert pos(spread="excelente").indice > pos(spread="ruim").indice
    assert any("SPREAD RUIM" in a for a in pos(spread="ruim").alertas)


# ── honestidade ─────────────────────────────────────────────────────────────

def test_declaracao_parcial_nao_entra_no_ranking():
    """Item mal declarado no meio de uma lista parece avaliado. É pior que ausente."""
    meia = E.posicionar(termo="parcial", pais="PL", ignorancia="so_falta_um_dado",
                        engajamento="dado_unico", volume="massivo")
    completa = pos()
    assert meia.cobertura < 0.5
    assert E.ordenar([meia, completa]) == [completa]


def test_menos_de_quatro_eixos_nao_produz_indice():
    p = E.posicionar(termo="x", ignorancia="nao_sei_se_existe", engajamento="sustenta")
    assert p.indice is None


def test_dimensao_ausente_nao_vira_meio_termo():
    """Preencher buraco com 0,5 é inventar informação."""
    p = pos(vacuo=None)
    assert p.eixos["vacuo"].valor is None
    assert "vacuo" in p.faltando()
    assert p.indice is not None      # calcula sobre os conhecidos


def test_nivel_invalido_falha_alto():
    with pytest.raises(ValueError, match="não existe em"):
        pos(engajamento="inventado")


# ── os quadrantes orientam a ação ───────────────────────────────────────────

def test_quadrante_separa_leitura_de_pagamento():
    alvo = pos()
    assert alvo.perfil() == "alvo"

    # "lê pouco" SEM portão: o quadrante descreve leitura fraca, não tema morto.
    # (usar `nao_preciso_de_nada` aqui confundia as duas coisas — hoje ele é
    # portão e o veredito correto passa a ser `descartar`.)
    rico_sem_leitura = pos(ignorancia="sei_o_que_fazer", engajamento="sustenta",
                           opacidade="clara", reposicao="unica")
    assert rico_sem_leitura.perfil() == "mercado_rico_sem_leitura"

    pobre = pos(volume="baixo", spread="ruim", densidade="rala")
    assert pobre.perfil() == "audiencia_pobre"


def test_indice_e_ordinal_nao_probabilidade():
    """Não existe P(win) aqui. Com priores não ajustados, calibração seria mentira."""
    p = pos()
    assert 0.0 < p.indice < 1.0
    assert not hasattr(p, "probabilidade")


# ═══════════════════════════════════════════════════════════════════════════
# OS CINCO ACHADOS DA REVISÃO EXTERNA (2026-08-10)
#
# Cada um foi REPRODUZIDO no código antes de ser aceito. Estes testes existem
# para que nenhum volte — os quatro primeiros são bugs de produto, não estilo.
# ═══════════════════════════════════════════════════════════════════════════

PERFEITO = dict(ignorancia="nao_sei_se_existe", engajamento="sustenta",
                opacidade="regra_mudou", reposicao="continua", volume="massivo",
                densidade="densa", formato_consumo="texto_busca", vacuo="virgem",
                producao="escreve_uma_vez")


def test_margem_negativa_nao_pode_sair_como_alvo():
    """ERA: `spread=ruim` + todo o resto perfeito -> índice 0,802, perfil "alvo".

    Prejuízo estrutural (RPM/CPC < 0,9) rotulado como "lê e paga" é o modelo
    falhando na decisão para a qual ele existe.
    """
    p = E.posicionar("t", pais="BR", spread="ruim", medidos=["spread"], **PERFEITO)
    assert p.indice == 0.0
    assert p.perfil() == "descartar"


def test_palpite_nao_mata_tema_so_medicao_mata():
    """A trava de proveniência. Na descoberta, `spread` e `volume` são estimativa
    de LLM; deixar um número inventado matar um tema é o mesmo erro, do outro
    lado. Só medição dispara esses dois portões."""
    estimado = E.posicionar("t", pais="BR", spread="ruim", **PERFEITO)
    medido = E.posicionar("t", pais="BR", spread="ruim", medidos=["spread"], **PERFEITO)
    assert estimado.indice > 0.5 and estimado.perfil() == "alvo"
    assert medido.indice == 0.0
    # os portões de julgamento NÃO dependem de medição — o rótulo é o dado
    assert E.posicionar("t", pais="BR", spread="bom",
                        **dict(PERFEITO, engajamento="dado_unico")).indice == 0.0


def test_indice_e_perfil_nunca_se_contradizem():
    """ERA: `dado_unico` + resto perfeito -> índice 0,05 e perfil "alvo". Se o
    quadrante orienta a ação, ele não pode discordar da nota."""
    for portao in ({"engajamento": "dado_unico"},
                   {"ignorancia": E.SEM_STAKE},
                   {"formato_consumo": "video_social"}):
        p = E.posicionar("t", pais="BR", spread="excelente", **dict(PERFEITO, **portao))
        assert p.indice == 0.0, portao
        assert p.perfil() == "descartar", portao


def test_engajamento_nao_tem_passo_intermediario_para_custar():
    """O passo que este teste media DEIXOU DE EXISTIR, e é isso que ele guarda.

    ERA: `diagnostico -> comparativo` custava x0,60 enquanto a margem real
    (`spread` excelente -> ruim) custava x0,80 — o rótulo declarado por um
    agente movia a nota mais que o dinheiro.

    A escala colapsou para dois estados porque os cinco não discriminaram
    (dominante em 62,5% num lote e 76,2% noutro, trocando de nível só com a
    amostra). O efeito colateral é que a classe inteira de defeito some: um
    rótulo de `engajamento` agora só pode fazer duas coisas — zerar o índice
    pelo portão, ou não mexer nele. Não há passo intermediário para custar.
    """
    assert len(E.ENGAJAMENTO) == 2
    nao_portao = [n for n in E.ENGAJAMENTO if n not in E.PORTOES["engajamento"]]
    assert nao_portao == ["sustenta"], "um segundo nível não-portão traria o passo de volta"


def test_rotulo_declarado_nao_pesa_mais_que_a_margem():
    """A propriedade original, agora testada onde ainda existe escala julgada.

    `ignorancia` e `opacidade` continuam com vários níveis declarados por LLM.
    A regra é a mesma: descer um degrau num eixo JULGADO não pode custar mais
    que a margem MEDIDA do negócio, senão a opinião manda no dinheiro.
    """
    base = E.posicionar("t", pais="BR", spread="excelente", **PERFEITO).indice
    margem = E.posicionar("t", pais="BR", spread="ruim", medidos=["spread"],
                          **PERFEITO).indice
    for eixo, degrau in (("ignorancia", "nao_sei_se_sirvo"),
                         ("opacidade", "fragmentada")):
        passo = E.posicionar("t", pais="BR", spread="excelente",
                             **dict(PERFEITO, **{eixo: degrau})).indice
        assert passo / base > 0.85, f"um degrau em {eixo} custou mais que 15%"
        assert margem < passo, f"a margem medida tem de pesar mais que {eixo}"


def test_calar_nao_paga_mais_que_declarar_o_portao():
    """ERA: portão não declarado valia 0,70 — um número inventado que fazia o
    silêncio render 1,08x mais que declarar honestamente `misto`. Contradizia o
    princípio que este módulo enuncia: dimensão desconhecida fica FORA."""
    calado = E.posicionar("t", pais="BR", spread="excelente",
                          **{k: v for k, v in PERFEITO.items() if k != "formato_consumo"})
    honesto = E.posicionar("t", pais="BR", spread="excelente",
                           **dict(PERFEITO, formato_consumo="misto"))
    assert calado.indice / honesto.indice < 1.05
    # e o silêncio TEM de aparecer: índice vazio de portão não é veredito
    assert any("PORTÃO NÃO VERIFICADO" in a for a in calado.alertas)
    assert not any("PORTÃO NÃO VERIFICADO" in a for a in honesto.alertas)


def test_escala_de_ignorancia_nao_contraria_a_medicao():
    """As duas rodadas cegas mediram `sei_o_que_fazer` (0,58 · 0,99) ACIMA de
    `so_falta_um_dado` (0,52 · 0,53), e o código codificava o inverso (0,25 vs
    0,35). A direção é consistente, a magnitude não — e o erro padrão desta base
    é 0,065. Empatados é a leitura honesta; inverter seria trocar um sobreajuste
    por outro."""
    assert E.IGNORANCIA["sei_o_que_fazer"][0] == E.IGNORANCIA["so_falta_um_dado"][0]
    # e a ordem que FOI medida com folga continua valendo
    assert E.IGNORANCIA["nao_sei_se_existe"][0] > E.IGNORANCIA["nao_sei_se_sirvo"][0]


def test_typo_em_eixo_falha_alto_em_vez_de_ser_engolido():
    """Um kwarg com typo virava eixo não declarado — mudava a conta em silêncio."""
    with pytest.raises(ValueError, match="inexistente"):
        E.posicionar("t", pais="BR", engajamentto="diagnostico")


def test_tema_barrado_sai_da_fila_nao_vai_para_o_fim():
    """Ordenar mortos entre si sugere gradiente onde há decisão binária: a 18ª
    posição insinua que existe uma 17ª melhor da mesma natureza. Barrado sai."""
    vivo = E.posicionar("vivo", pais="BR", spread="bom", **PERFEITO)
    morto = E.posicionar("morto", pais="BR", spread="bom",
                         **dict(PERFEITO, engajamento="dado_unico"))
    assert E.ordenar([morto, vivo]) == [vivo]
    # mas o motivo continua acessível — some da fila, não da análise
    assert morto.portoes_disparados() == ["engajamento"]
    assert any("ENGAJAMENTO NULO" in a for a in morto.alertas)


def test_indice_exige_duas_familias_nao_so_tres_eixos():
    """Média sobre UMA família não é índice — é o que `familia()` entrega com o
    nome certo. A regra antiga (>=3 eixos NÃO-portão) impedia isso por acidente;
    ao tornar o portão um par, o acidente sumiu e o caso de 3 eixos de
    julgamento passou a devolver 0,90 sobre 30% de cobertura, toda de
    `demanda_humana` — "ótimo tema" sem saber nada de economia nem posição.
    """
    so_demanda = E.posicionar("x", pais="BR", ignorancia="nao_sei_se_existe",
                              engajamento="sustenta", opacidade="fragmentada")
    assert so_demanda.indice is None
    assert so_demanda.familia("demanda_humana") is not None   # a família, sim

    # com um eixo de outra família, o índice existe
    duas = E.posicionar("x", pais="BR", ignorancia="nao_sei_se_existe",
                        engajamento="sustenta", opacidade="fragmentada",
                        spread="bom")
    assert duas.indice is not None

    # e o portão continua vindo ANTES da regra de cobertura: tema morto é
    # veredito, não "não sei"
    morto = E.posicionar("x", pais="BR", ignorancia="nao_sei_se_existe",
                         engajamento="dado_unico", opacidade="clara")
    assert morto.indice == 0.0 and morto.perfil() == "descartar"
