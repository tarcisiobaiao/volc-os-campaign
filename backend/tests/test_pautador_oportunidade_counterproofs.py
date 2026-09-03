"""Contraprovas da Camada 2 — a tese de oportunidade.

Escritas ANTES da implementação. Cada uma nasce vermelha e descreve um erro que
o motor não pode cometer, não um comportamento que já funciona.

A numeração segue a seção 9 da missão. Onde uma contraprova da missão já é
garantida por outro módulo, o teste aponta para lá em vez de reimplementar a
garantia (e diz isso no docstring) — duplicar a garantia esconderia qual módulo
de fato a sustenta.
"""
from __future__ import annotations

import pytest

from app.validacao.oportunidade import (
    APROFUNDAR,
    COBERTURA_MINIMA_PARA_COMPARAR,
    EXPERIMENTAR,
    INADEQUADO,
    INSUFICIENTE,
    RETIDO,
    SEM_VALIDACAO,
    VERSAO_DO_CONTRATO,
    TeseDeOportunidade,
    comparar,
    tese_do_resumo,
)

# ── fixtures de resumo, no formato que `validacao.orquestrador._resumir` grava ──


def _resumo(**over):
    """Um resumo bem formado, medido, de tema com ramificação real."""
    base = {
        "apto": True,
        "motivo": None,
        "indice": 0.72,
        "cobertura": 1.0,
        "perfil": "alvo",
        "portoes_disparados": [],
        "alertas": [],
        "eixos": {
            "volume": {"nivel": "alto", "proveniencia": "medido", "motivo_ausencia": None},
            "reposicao": {"nivel": "continua", "proveniencia": "medido", "motivo_ausencia": None},
            "vacuo": {"nivel": "raso", "proveniencia": "medido", "motivo_ausencia": None},
            "densidade": {"nivel": "densa", "proveniencia": "medido", "motivo_ausencia": None},
            "formato_consumo": {"nivel": "texto_busca", "proveniencia": "medido", "motivo_ausencia": None},
            "ignorancia": {"nivel": "nao_sei_se_sirvo", "proveniencia": "julgado", "motivo_ausencia": None},
            "engajamento": {"nivel": "sustenta", "proveniencia": "julgado", "motivo_ausencia": None},
            "opacidade": {"nivel": "fragmentada", "proveniencia": "julgado", "motivo_ausencia": None},
        },
        "ficha": {
            "share_dado_unico": 0.25,
            "n_perguntas": 4,
            "pergunta_mais_rica": "Quem tem direito?",
            "perguntas": [
                {"pergunta": "Quem tem direito?", "ramos": 3, "condicoes": 3,
                 "decide_depois": True, "oficial_fecha_sozinho": False,
                 "engajamento": "sustenta", "tensao": "acesso_negado", "estavel": True},
                {"pergunta": "Quando cai?", "ramos": 1, "condicoes": 0,
                 "decide_depois": False, "oficial_fecha_sozinho": True,
                 "engajamento": "dado_unico", "tensao": "medo_de_perder", "estavel": True},
                {"pergunta": "Como calculo?", "ramos": 2, "condicoes": 2,
                 "decide_depois": True, "oficial_fecha_sozinho": False,
                 "engajamento": "sustenta", "tensao": "acesso_negado", "estavel": True},
                {"pergunta": "E se eu perder o prazo?", "ramos": 2, "condicoes": 1,
                 "decide_depois": True, "oficial_fecha_sozinho": False,
                 "engajamento": "sustenta", "tensao": "medo_de_perder", "estavel": True},
            ],
            "comparacao": {"estavel": True, "shares": [0.25, 0.25, 0.25],
                           "concordancia_por_pergunta": 1.0},
        },
        "tensao": {"tensao": "acesso_negado", "share_com_tensao": 1.0,
                   "intensidade_prior": 0.64},
        "sensores": {"limpos": True},
    }
    base.update(over)
    return base


def _resumo_suporte(**over):
    """Lookup puro: toda pergunta esgota, o canal oficial fecha sozinho."""
    r = _resumo()
    r["apto"] = False
    r["motivo"] = "portao_engajamento"
    r["indice"] = 0.0
    r["perfil"] = "descartar"
    r["portoes_disparados"] = ["engajamento"]
    r["eixos"]["engajamento"]["nivel"] = "dado_unico"
    r["ficha"]["share_dado_unico"] = 1.0
    for q in r["ficha"]["perguntas"]:
        q.update(ramos=1, condicoes=0, decide_depois=False,
                 oficial_fecha_sozinho=True, engajamento="dado_unico")
    r.update(over)
    return r


# ══════════════════════════════════════════════════════════════════════════════
# 1 · Volume alto com intenção de suporte não vira melhor oportunidade
# ══════════════════════════════════════════════════════════════════════════════

def test_cp01_volume_alto_com_suporte_nao_vira_oportunidade():
    forte = tese_do_resumo(_resumo(), tema="tema-rico")
    suporte = tese_do_resumo(_resumo_suporte(), tema="tema-lookup")
    assert suporte.decisao == INADEQUADO
    assert forte.decisao == APROFUNDAR
    # e o volume massivo NÃO resgata o suporte
    suporte_massivo = _resumo_suporte()
    suporte_massivo["eixos"]["volume"]["nivel"] = "massivo"
    assert tese_do_resumo(suporte_massivo, tema="t").decisao == INADEQUADO


# ══════════════════════════════════════════════════════════════════════════════
# 2 · Linguagem emocional sem demanda nem evidência não compra prioridade
# ══════════════════════════════════════════════════════════════════════════════

def test_cp02_tensao_forte_sozinha_nao_promove():
    """`protecao_familiar` tem a maior intensidade da tabela (0,84). Ela não pode
    mover a decisão — o prior veio de desfecho contaminado."""
    r = _resumo_suporte()
    r["tensao"] = {"tensao": "protecao_familiar", "share_com_tensao": 1.0,
                   "intensidade_prior": 0.84}
    assert tese_do_resumo(r, tema="t").decisao == INADEQUADO


def test_cp02b_intensidade_prior_nunca_entra_na_tese():
    baixa = _resumo(); baixa["tensao"]["intensidade_prior"] = 0.10
    alta = _resumo(); alta["tensao"]["intensidade_prior"] = 0.99
    assert tese_do_resumo(baixa, tema="t").decisao == tese_do_resumo(alta, tema="t").decisao
    texto = repr(tese_do_resumo(alta, tema="t"))
    assert "0.99" not in texto


# ══════════════════════════════════════════════════════════════════════════════
# 3 e 4 · Dado ausente não vira zero; zero confirmado continua diferente de ausência
# ══════════════════════════════════════════════════════════════════════════════

def test_cp03_ausente_vai_para_desconhecidos_nunca_para_fatos():
    r = _resumo()
    r["eixos"]["volume"] = {"nivel": None, "proveniencia": "ausente",
                            "motivo_ausencia": "sem_credencial_dataforseo"}
    t = tese_do_resumo(r, tema="t")
    assert any("volume" in d for d in t.desconhecidos)
    assert not any("volume" in f for f in t.fatos)


def test_cp04_zero_confirmado_difere_de_ausencia():
    ausente = _resumo()
    ausente["eixos"]["volume"] = {"nivel": None, "proveniencia": "ausente",
                                  "motivo_ausencia": "serie_curta"}
    medido_zero = _resumo()
    medido_zero["eixos"]["volume"] = {"nivel": "residual", "proveniencia": "medido",
                                      "motivo_ausencia": None}
    ta, tz = tese_do_resumo(ausente, tema="t"), tese_do_resumo(medido_zero, tema="t")
    assert ta.decisao != tz.decisao
    assert any("volume" in d for d in ta.desconhecidos)
    assert not any("volume" in d for d in tz.desconhecidos)


# ══════════════════════════════════════════════════════════════════════════════
# 5 e 6 · Resposta oficial que encerra vs complexidade real preservada
# ══════════════════════════════════════════════════════════════════════════════

def test_cp05_oficial_que_fecha_sozinho_nao_ganha_profundidade():
    t = tese_do_resumo(_resumo_suporte(), tema="t")
    assert t.decisao == INADEQUADO
    assert t.formato_de_funil is None


def test_cp06_multiplas_condicoes_e_ramos_reais_sao_preservados():
    t = tese_do_resumo(_resumo(), tema="t")
    assert t.formato_de_funil is not None
    assert t.observaveis_do_formato, "CP#23: o formato precisa citar observáveis"
    # os números contados sobrevivem à derivação
    juntos = " ".join(t.observaveis_do_formato)
    assert "ramos" in juntos and "condicoes" in juntos


# ══════════════════════════════════════════════════════════════════════════════
# 7 · O mesmo tema com evidência melhor não pode pontuar pior (monotonicidade)
# ══════════════════════════════════════════════════════════════════════════════

ORDEM = {SEM_VALIDACAO: 0, RETIDO: 1, INSUFICIENTE: 2, INADEQUADO: 2,
         EXPERIMENTAR: 3, APROFUNDAR: 4}


def test_cp07_evidencia_melhor_nunca_decide_pior():
    pobre = _resumo()
    for e in ("volume", "reposicao", "vacuo"):
        pobre["eixos"][e] = {"nivel": None, "proveniencia": "ausente",
                             "motivo_ausencia": "nao_medido"}
    pobre["cobertura"] = 0.625
    rico = _resumo()
    assert ORDEM[tese_do_resumo(rico, tema="t").decisao] >= \
           ORDEM[tese_do_resumo(pobre, tema="t").decisao]


# ══════════════════════════════════════════════════════════════════════════════
# 8 · Evidência pós-desfecho da própria campanha não entra como input pré-lançamento
# ══════════════════════════════════════════════════════════════════════════════

def test_cp08_desfecho_da_propria_campanha_e_recusado():
    from app.agents.mining.paid_eligibility import VazamentoDeDesfecho
    with pytest.raises(VazamentoDeDesfecho):
        tese_do_resumo(
            _resumo(), tema="t",
            evidencias_externas=[{"momento": "pos_lancamento", "campanha_ref": "C-1",
                                  "afirmacao": "deu lucro"}],
            campanha_ref="C-1",
        )


def test_cp08b_desfecho_de_outra_campanha_entra_como_hipotese_marcada():
    t = tese_do_resumo(
        _resumo(), tema="t",
        evidencias_externas=[{"momento": "pos_lancamento", "campanha_ref": "C-9",
                              "afirmacao": "densidade de anuncio alta correlaciona com perda"}],
        campanha_ref="C-1",
    )
    assert any("C-9" not in h for h in t.hipoteses)
    assert t.hipoteses, "prior de outra campanha precisa aparecer como hipótese"


# ══════════════════════════════════════════════════════════════════════════════
# 9, 10 e 21 · Padrão presente nos controles não vira sinal; prior fraco não decide
# ══════════════════════════════════════════════════════════════════════════════

def test_cp09_prior_sem_controle_nao_move_decisao():
    from app.validacao.oportunidade import PRIORS_WEBGO
    for p in PRIORS_WEBGO:
        assert p["confianca"] in ("baixa", "media", "alta")
        if p["confianca"] != "alta":
            assert p["pode_decidir"] is False
    # nenhum prior, de qualquer confiança, decide neste motor
    assert all(p["pode_decidir"] is False for p in PRIORS_WEBGO)


def test_cp10_prior_fraco_nem_bloqueia_nem_autoriza():
    sem = tese_do_resumo(_resumo(), tema="t")
    com = tese_do_resumo(_resumo(), tema="t", aplicar_priors=True)
    assert sem.decisao == com.decisao


def test_cp21_sofisticacao_visual_nao_e_observavel_desta_camada():
    """O benchmark provou que elemento visual recorrente é template: aparece
    igual em vencedora, perdedora e controle (14 de 18 domínios servem mais de
    um grupo). Nada visual entra na tese."""
    from app.validacao.oportunidade import OBSERVAVEIS_ACEITOS
    proibidos = {"hero", "cta", "selo", "layout", "template", "design", "cor"}
    assert not (proibidos & {o.lower() for o in OBSERVAVEIS_ACEITOS})


# ══════════════════════════════════════════════════════════════════════════════
# 11 e 12 · O LLM não devolve o score; paráfrases dão a mesma derivação
# ══════════════════════════════════════════════════════════════════════════════

def test_cp11_tese_ignora_qualquer_nota_vinda_do_llm():
    r = _resumo()
    r["score"] = 999.0
    r["ficha"]["perguntas"][0]["nota_do_modelo"] = 10
    assert tese_do_resumo(r, tema="t").decisao == tese_do_resumo(_resumo(), tema="t").decisao


def test_cp12_parafrase_da_pergunta_nao_muda_a_derivacao():
    a = _resumo()
    b = _resumo()
    for q in b["ficha"]["perguntas"]:
        q["pergunta"] = q["pergunta"].upper() + "  "
    ta, tb = tese_do_resumo(a, tema="t"), tese_do_resumo(b, tema="t")
    assert ta.decisao == tb.decisao
    assert ta.formato_de_funil == tb.formato_de_funil


# ══════════════════════════════════════════════════════════════════════════════
# 13 · Construtos sobrepostos não contam duas vezes o mesmo fato
# ══════════════════════════════════════════════════════════════════════════════

def test_cp13_um_fato_aparece_uma_vez_so():
    t = tese_do_resumo(_resumo(), tema="t")
    assert len(t.fatos) == len(set(t.fatos))
    assert not (set(t.fatos) & set(t.hipoteses))
    assert not (set(t.fatos) & set(t.desconhecidos))
    assert not (set(t.hipoteses) & set(t.desconhecidos))


# ══════════════════════════════════════════════════════════════════════════════
# 14 e 20 · Falta de sensor vira cobertura menor, não reprovação; sem cobertura não ordena
# ══════════════════════════════════════════════════════════════════════════════

def test_cp14_sensor_ausente_reduz_cobertura_sem_reprovar():
    r = _resumo()
    r["eixos"]["vacuo"] = {"nivel": None, "proveniencia": "ausente",
                           "motivo_ausencia": "sem_trafego"}
    r["cobertura"] = 0.875
    t = tese_do_resumo(r, tema="t")
    assert t.decisao != INADEQUADO
    assert t.cobertura == pytest.approx(0.875)


def test_cp20_cobertura_baixa_retem_a_priorizacao():
    r = _resumo(cobertura=0.3)
    t = tese_do_resumo(r, tema="t")
    assert t.decisao == RETIDO
    assert t.comparavel is False
    assert t.motivo_incomparavel


def test_cp20b_comparar_nao_ordena_silenciosamente_o_incomparavel():
    boa = tese_do_resumo(_resumo(), tema="boa")
    magra = tese_do_resumo(_resumo(cobertura=0.2, indice=0.99), tema="magra")
    ranking, fora = comparar([boa, magra])
    assert [t.tema for t in ranking] == ["boa"]
    assert [t.tema for t in fora] == ["magra"]


# ══════════════════════════════════════════════════════════════════════════════
# 15, 16 e 24 · A fronteira com o lado pago
# ══════════════════════════════════════════════════════════════════════════════

def test_cp15_tema_forte_com_zero_keywords_pagas_e_estado_valido():
    t = tese_do_resumo(_resumo(), tema="t")
    assert t.decisao == APROFUNDAR
    assert "paga" not in (t.porque or "").lower()


def test_cp16_nenhum_campo_de_economia_paga_aparece_na_tese():
    from app.agents.mining.ponte_editorial import CAMPOS_PROIBIDOS_NO_EDITORIAL
    r = _resumo()
    r["eixos"]["spread"] = {"nivel": "excelente", "proveniencia": "medido",
                            "motivo_ausencia": None}
    r["cpc"] = 4.90
    r["roas"] = 3.1
    t = tese_do_resumo(r, tema="t")
    texto = repr(t).lower()
    for campo in CAMPOS_PROIBIDOS_NO_EDITORIAL:
        assert campo not in texto, f"{campo!r} vazou para a tese editorial"


def test_cp24_a_tese_nao_toca_o_conjunto_pago():
    """A Camada 2 não importa nada que decida keyword paga."""
    import app.validacao.oportunidade as mod
    fonte = open(mod.__file__, encoding="utf-8").read()
    assert "decidir_keyword" not in fonte
    assert "montar_conjunto" not in fonte
    assert "aprovar" not in fonte


# ══════════════════════════════════════════════════════════════════════════════
# 17 e 18 · Cards antigos; reprocessar é determinístico e idempotente
# ══════════════════════════════════════════════════════════════════════════════

def test_cp17_card_antigo_recebe_estado_explicito_e_continua_legivel():
    for vazio in (None, {}, {"apto": True}):
        t = tese_do_resumo(vazio, tema="antigo")
        assert t.decisao == SEM_VALIDACAO
        assert t.comparavel is False
        assert t.versao_do_contrato == VERSAO_DO_CONTRATO


def test_cp18_reprocessar_a_mesma_evidencia_e_identico():
    r = _resumo()
    a = tese_do_resumo(r, tema="t")
    b = tese_do_resumo(_resumo(), tema="t")
    assert a == b
    # e a tese não muta o resumo que recebeu
    antes = _resumo()
    tese_do_resumo(antes, tema="t")
    assert antes == _resumo()


def test_cp18b_ordem_dos_eixos_nao_muda_o_resultado():
    r1 = _resumo()
    r2 = _resumo()
    r2["eixos"] = dict(reversed(list(r2["eixos"].items())))
    assert tese_do_resumo(r1, tema="t") == tese_do_resumo(r2, tema="t")


# ══════════════════════════════════════════════════════════════════════════════
# 19, 22 e 23 · Honestidade da tese
# ══════════════════════════════════════════════════════════════════════════════

def test_cp19_fato_hipotese_e_desconhecido_sao_conjuntos_separados():
    t = tese_do_resumo(_resumo(), tema="t")
    assert t.fatos and isinstance(t.fatos, tuple)
    assert isinstance(t.hipoteses, tuple) and isinstance(t.desconhecidos, tuple)


def test_cp22_sequencia_longa_nao_e_automaticamente_melhor():
    """Uma resposta curta e completa não perde para uma sequência longa só por
    ser curta. O que decide é ramificação REAL, não contagem de páginas."""
    curta = _resumo()
    for q in curta["ficha"]["perguntas"]:
        q.update(ramos=3, condicoes=3, decide_depois=True)
    curta["ficha"]["n_perguntas"] = 2
    curta["ficha"]["perguntas"] = curta["ficha"]["perguntas"][:2]
    longa = _resumo()
    for q in longa["ficha"]["perguntas"]:
        q.update(ramos=1, condicoes=0, decide_depois=False)
    assert ORDEM[tese_do_resumo(curta, tema="c").decisao] >= \
           ORDEM[tese_do_resumo(longa, tema="l").decisao]


def test_cp23_o_formato_cita_os_observaveis_que_o_produziram():
    t = tese_do_resumo(_resumo(), tema="t")
    assert t.formato_de_funil
    assert len(t.observaveis_do_formato) >= 2
    for o in t.observaveis_do_formato:
        assert any(ch.isdigit() for ch in o), f"observável sem contagem: {o!r}"


# ══════════════════════════════════════════════════════════════════════════════
# 25 · Nenhum caminho cria campanha, publica página ou chama mutate
# ══════════════════════════════════════════════════════════════════════════════

def test_cp25_a_camada_nao_tem_efeito_externo():
    """Lido por AST, não por substring: um scanner de texto acusaria a própria
    frase do docstring que promete não fazer isso, e um teste que falha na
    própria promessa ensina a apagar a promessa."""
    import ast
    import app.validacao.oportunidade as mod

    arvore = ast.parse(open(mod.__file__, encoding="utf-8").read())

    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
            importados.add(no.module)

    for proibido in ("httpx", "requests", "aiohttp", "urllib", "socket",
                     "subprocess", "google", "googleads"):
        assert proibido not in importados, f"import proibido: {proibido!r}"

    # Acoplamento permitido, e a lista é curta de propósito:
    #   - as duas de `mining` são a fronteira paga, importadas SOMENTE para
    #     reusar vocabulário de estado e a guarda de vazamento (nunca decisão);
    #   - `app.validacao.ficha` é intra-pacote: dela vem o piso de N, que é a
    #     mesma constante medida que governa o portão. Duplicar o número aqui
    #     criaria duas verdades sobre o mesmo piso.
    externos = {m for m in importados if m.startswith("app.")}
    assert externos <= {
        "app.agents.mining.paid_eligibility",
        "app.agents.mining.ponte_editorial",
        "app.validacao.ficha",
    }, f"acoplamento inesperado: {externos}"
    assert not any(m.startswith("app.entities") for m in externos), (
        "a Camada 2 não pode importar a descoberta"
    )

    chamadas = {no.func.attr for no in ast.walk(arvore)
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)}
    for proibida in ("mutate", "post", "put", "patch", "delete", "insert",
                     "upsert", "select", "publicar"):
        assert proibida not in chamadas, f"chamada proibida: {proibida!r}"


# ══════════════════════════════════════════════════════════════════════════════
# Extra · o experimento barato e a comparabilidade
# ══════════════════════════════════════════════════════════════════════════════

def test_experimento_e_proposto_quando_a_incerteza_e_redutivel():
    r = _resumo()
    r["eixos"]["volume"] = {"nivel": None, "proveniencia": "ausente",
                            "motivo_ausencia": "sem_credencial_dataforseo"}
    r["cobertura"] = 0.875
    t = tese_do_resumo(r, tema="t")
    assert t.proximo_experimento
    assert "volume" in t.proximo_experimento


def test_sem_desconhecidos_nao_inventa_experimento():
    t = tese_do_resumo(_resumo(), tema="t")
    assert t.proximo_experimento is None or t.desconhecidos


def test_contradicao_e_reportada_nao_resolvida_em_silencio():
    r = _resumo()
    r["apto"] = True
    r["portoes_disparados"] = ["engajamento"]  # apto com portão é contradição
    t = tese_do_resumo(r, tema="t")
    assert t.contradicoes


# ══════════════════════════════════════════════════════════════════════════════
# Achado do REPLAY · o veto de formato tinha a mesma vacuidade que
# `N_MINIMO_PARA_PORTAO = 3` existe para evitar
# ══════════════════════════════════════════════════════════════════════════════

def test_veto_de_formato_respeita_o_piso_de_n():
    """"Todas as perguntas esgotam" é regra VAZIA com poucas perguntas.

    `ficha.N_MINIMO_PARA_PORTAO = 3` foi medido custando uma entidade: com uma
    pergunta só, 1/1 = 1,0 satisfaz qualquer unanimidade. O veto do roteador de
    formato tem a MESMA forma (`fecham == n`) e o replay mostrou que ele matava
    192 casos em que o motor de eixos dizia `apto`, com n=2.

    Abaixo do piso o veto não mata: o máximo que o card recebe é
    `insuficiente`, que é o estado que significa "humano olha".
    """
    from app.validacao.ficha import N_MINIMO_PARA_PORTAO
    from app.validacao.oportunidade import _rotear_formato

    fecha = {"ramos": 1, "condicoes": 0, "decide_depois": False,
             "fecha_sozinho": True, "engajamento": "dado_unico"}

    # abaixo do piso: não veta
    for n in range(1, N_MINIMO_PARA_PORTAO):
        formato, _ = _rotear_formato([dict(fecha) for _ in range(n)])
        assert formato is not None, f"vetou com n={n}, abaixo do piso"

    # no piso e acima: veta
    for n in (N_MINIMO_PARA_PORTAO, N_MINIMO_PARA_PORTAO + 2):
        formato, citacoes = _rotear_formato([dict(fecha) for _ in range(n)])
        assert formato is None, f"não vetou com n={n}"
        assert any(str(n) in c for c in citacoes)


def test_abaixo_do_piso_o_card_nao_e_reprovado_por_veto():
    r = _resumo_suporte()
    r["ficha"]["perguntas"] = r["ficha"]["perguntas"][:2]
    r["ficha"]["n_perguntas"] = 2
    r["portoes_disparados"] = []
    r["apto"] = True
    t = tese_do_resumo(r, tema="t")
    assert t.decisao == INSUFICIENTE, (
        "com n abaixo do piso o veto não pode matar; o humano olha"
    )
