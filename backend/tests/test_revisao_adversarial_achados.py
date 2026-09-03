"""Os achados da revisão independente, cada um com o teste que faltava.

Codex (gpt-5.6-sol) e Gemini 3.7 Flash revisaram a árvore congelada. Refutaram
três das sete afirmações da lane e acharam defeitos que os MEUS testes não
pegaram — em dois casos porque o meu teste passava vacuamente.

Cada teste aqui nasceu vermelho contra o commit 983f782.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from app.validacao.oportunidade import (
    APROFUNDAR, FALHA_NA_LEITURA, INSUFICIENTE, RETIDO, SEM_VALIDACAO,
    _bool_observado, _rotear_formato, comparar, tese_do_resumo,
)


def _resumo(**over) -> Dict[str, Any]:
    base = {
        "apto": True, "motivo": None, "indice": 0.72, "cobertura": 1.0,
        "perfil": "alvo", "portoes_disparados": [], "alertas": [],
        "eixos": {
            "volume": {"nivel": "alto", "proveniencia": "medido", "motivo_ausencia": None},
            "engajamento": {"nivel": "sustenta", "proveniencia": "julgado", "motivo_ausencia": None},
        },
        "ficha": {
            "n_perguntas": 2,
            "perguntas": [
                {"pergunta": "a", "ramos": 3, "condicoes": 3,
                 "decide_depois": True, "oficial_fecha_sozinho": False},
                {"pergunta": "b", "ramos": 1, "condicoes": 0,
                 "decide_depois": False, "oficial_fecha_sozinho": True},
            ],
        },
    }
    base.update(over)
    return base


# ══════════════════════════════════════════════════════════════════════════════
# CODEX A2 · booleano ausente virava zero confirmado
# ══════════════════════════════════════════════════════════════════════════════

def test_codex_a2_booleano_ausente_nao_e_false():
    assert _bool_observado(True) is True
    assert _bool_observado(False) is False
    assert _bool_observado(None) is None
    # `bool("false") is True` — string malformada dizia o OPOSTO do que afirma
    assert _bool_observado("false") is None
    assert _bool_observado("true") is None
    assert _bool_observado(0) is None
    assert _bool_observado(1) is None


def test_codex_a2_observavel_ausente_nao_vira_fato_de_zero():
    """Três perguntas sem `oficial_fecha_sozinho`: o motor NÃO pode afirmar
    `oficial_fecha_sozinho em 0 de 3 perguntas` — ninguém observou."""
    r = _resumo()
    r["ficha"]["perguntas"] = [{"pergunta": f"q{i}", "ramos": 1, "condicoes": 0}
                               for i in range(3)]
    t = tese_do_resumo(r, tema="t")
    afirma_zero = [f for f in t.fatos if "oficial_fecha_sozinho em 0" in f]
    assert not afirma_zero, f"ausência virou zero confirmado: {afirma_zero}"


def test_codex_a2_contagem_booleana_e_lixo_e_nao_conta():
    """`True` é `int` em Python: `ramos=True` passaria por `isinstance(int)`."""
    r = _resumo()
    r["ficha"]["perguntas"] = [{"pergunta": "q", "ramos": True, "condicoes": False}]
    t = tese_do_resumo(r, tema="t")
    assert t.decisao == FALHA_NA_LEITURA


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI P0 · o veto abaixo do piso deixava o card chegar a `aprofundar`
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_p0_veto_abaixo_do_piso_nao_aprova():
    """n=2, AMBAS fecham sozinho, mas com 3 condições e 3 ramos.

    O meu teste anterior usou ramos=1/condicoes=0 e por isso NUNCA chegou neste
    ramo: passava sem exercitar a garantia que dizia proteger.
    """
    qs = [{"ramos": 3, "condicoes": 3, "decide_depois": True,
           "fecha_sozinho": True, "engajamento": "sustenta"}] * 2
    formato, citacoes = _rotear_formato(qs)
    assert formato is None, "abaixo do piso, o veto não pode devolver formato"
    assert any("ABAIXO do piso" in c for c in citacoes)

    r = _resumo()
    r["ficha"]["perguntas"] = [
        {"pergunta": "a", "ramos": 3, "condicoes": 3,
         "decide_depois": True, "oficial_fecha_sozinho": True},
        {"pergunta": "b", "ramos": 3, "condicoes": 3,
         "decide_depois": True, "oficial_fecha_sozinho": True},
    ]
    assert tese_do_resumo(r, tema="t").decisao != APROFUNDAR


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI P0 · falha de leitura era apresentada como "cabe numa página"
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_p0_falha_de_leitura_tem_estado_proprio():
    r = _resumo()
    r["ficha"] = {"n_perguntas": 0, "perguntas": []}
    t = tese_do_resumo(r, tema="t")
    assert t.decisao == FALHA_NA_LEITURA
    assert t.decisao != INSUFICIENTE
    assert t.comparavel is False
    assert "falha" in t.porque.lower()


# ══════════════════════════════════════════════════════════════════════════════
# CODEX P1 · cobertura desconhecida escapava da retenção
# ══════════════════════════════════════════════════════════════════════════════

def test_codex_p1_cobertura_none_e_retida_e_nao_comparavel():
    t = tese_do_resumo(_resumo(cobertura=None), tema="t")
    assert t.decisao == RETIDO
    assert t.comparavel is False
    assert t.motivo_incomparavel


def test_codex_p1_cobertura_none_nao_entra_no_ranking():
    boa = tese_do_resumo(_resumo(), tema="boa", opportunity_id=1)
    cega = tese_do_resumo(_resumo(cobertura=None), tema="cega", opportunity_id=2)
    aptos, fora = comparar([boa, cega])
    assert [t.tema for t in aptos] == ["boa"]
    assert [t.tema for t in fora] == ["cega"]


# ══════════════════════════════════════════════════════════════════════════════
# CODEX P1 · empate entre homônimos era não determinístico
# ══════════════════════════════════════════════════════════════════════════════

def test_codex_p1_homonimos_tem_ordem_estavel():
    """Dois cards com o MESMO tema e a mesma medição — duplicata por site.
    Inverter a ordem de entrada não pode trocar o topo."""
    def teses(ordem):
        return [tese_do_resumo(_resumo(), tema="mesmo", opportunity_id=i) for i in ordem]

    a, _ = comparar(teses([101, 202]))
    b, _ = comparar(teses([202, 101]))
    assert [t.opportunity_id for t in a] == [t.opportunity_id for t in b] == [101, 202]


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI P1 · instabilidade interna estava classificada como hipótese externa
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_p1_instabilidade_e_contradicao_nao_hipotese():
    r = _resumo()
    r["ficha"]["comparacao"] = {"estavel": False, "shares": [0.25, 1.0, 0.5]}
    t = tese_do_resumo(r, tema="t")
    assert any("divergiram" in c for c in t.contradicoes)
    assert not any("divergiram" in h for h in t.hipoteses), (
        "a divergência aconteceu NESTE card; hipótese é o que vem de fora"
    )


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI P2 · o experimento afirmava "o mais barato" a partir da ordem alfabética
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_p2_experimento_nao_afirma_custo_que_nao_mede():
    r = _resumo()
    r["eixos"]["volume"] = {"nivel": None, "proveniencia": "ausente",
                            "motivo_ausencia": "sem_credencial"}
    r["eixos"]["vacuo"] = {"nivel": None, "proveniencia": "ausente",
                           "motivo_ausencia": "sem_trafego"}
    r["cobertura"] = 0.75
    t = tese_do_resumo(r, tema="t")
    assert t.proximo_experimento
    assert "mais barato de fechar" not in t.proximo_experimento
    assert "mais muda a leitura" not in t.proximo_experimento
    # e cita TODOS os buracos, não só o primeiro em ordem alfabética
    assert "volume" in t.proximo_experimento and "vacuo" in t.proximo_experimento


# ══════════════════════════════════════════════════════════════════════════════
# CODEX A5 · o acoplamento CPC -> densidade, medido e DECLARADO
# ══════════════════════════════════════════════════════════════════════════════

def test_codex_a5_presenca_de_cpc_move_densidade_quando_serp_nao_tem_comercial():
    """Este teste NÃO conserta o acoplamento: ele o CONGELA para que ninguém o
    descubra de novo por acidente, e delimita onde ele existe.

    A presença de `cpc` no cluster vira `existe_leilao`, que muda `densidade`
    entre `nenhuma` e `rala` — mas SOMENTE quando a SERP não tem nenhum domínio
    comercial no top-10. Com domínio comercial, o CPC é irrelevante.

    Só a PRESENÇA é usada; o VALOR é explicitamente recusado por
    `existe_leilao` (superestima o CPC real em 7,4x).

    O acoplamento é PRÉ-EXISTENTE a esta lane e vive no motor de medição.
    Ver LIMITATIONS.md.
    """
    from app.motor_pautas.sensores import dataforseo as S

    sem_comercial = {"items": [{"type": "organic", "domain": "gov.br"}]}
    com_comercial = {"items": [{"type": "organic", "domain": "blogx.com"}]}

    def densidade(serp, cpc):
        leilao, _ = S.existe_leilao([{"cpc": cpc}])
        nivel, _ = S.nivel_densidade(serp, leilao)
        return nivel

    # onde o acoplamento EXISTE
    assert densidade(sem_comercial, None) == "nenhuma"
    assert densidade(sem_comercial, 1.25) == "rala"
    # onde ele NÃO existe
    assert densidade(com_comercial, None) == densidade(com_comercial, 1.25)

    # e o VALOR do cpc nunca importa, só a presença
    assert densidade(sem_comercial, 0.01) == densidade(sem_comercial, 99.0)


# ══════════════════════════════════════════════════════════════════════════════
# CODEX A7 · o escopo da afirmação de "zero mutação externa"
# ══════════════════════════════════════════════════════════════════════════════

def test_codex_a7_a_camada_2_nao_escreve_mas_o_validador_escreve_por_desenho():
    """A afirmação "nenhum caminho desta missão causa mutação externa" era
    ampla demais: `Validador._gravar_parcial` escreve no Supabase.

    O que é verdade, e o que este teste fixa:
      - a CAMADA 2 não escreve em lugar nenhum (verificado por AST em cp25);
      - o VALIDADOR escreve no Supabase por desenho, e já escrevia antes desta
        lane; `_gravar_parcial` aumentou a FREQUÊNCIA dentro de uma run que o
        operador disparou, com o mesmo upsert idempotente;
      - nenhum caminho novo alcança Google Ads, WordPress, n8n ou deploy.
    """
    import ast
    import inspect

    from app.validacao import orquestrador as orq

    fonte = inspect.getsource(orq)
    arvore = ast.parse(fonte)
    modulos = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module)
        elif isinstance(no, ast.Import):
            modulos.update(a.name for a in no.names)

    for proibido in ("googleads", "google.ads", "wordpress", "n8n"):
        assert not any(proibido in m.lower() for m in modulos), proibido

    # a escrita do validador é a MESMA de sempre: upsert idempotente
    assert "on_conflict=opportunity_id,eixo" in fonte
    assert "resolution=merge-duplicates" in fonte
