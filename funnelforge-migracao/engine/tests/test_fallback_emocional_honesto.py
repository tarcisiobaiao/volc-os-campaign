"""O fallback heurístico não pode virar 'leitor sem emoção' no brief.

Regressão do run real da Tarifa Social (09/10/2026): 84% das perguntas caíram
em "ambigua" porque a heurística não conhecia "cadastrar" ou "cemig", e o brief
mandou o arquiteto "não forçar emoção" em todas.
"""
from funnelforge.adapters.decisao_intencao import HeuristicaDeIntencao

PERGUNTAS = ["cemig atende", "tarifa social cemig",
             "tarifa social de energia elétrica: como cadastrar", "quem tem direito"]


def test_pergunta_nao_reconhecida_devolve_a_escolha_ao_arquiteto():
    perfil = HeuristicaDeIntencao().classificar(PERGUNTAS)["perfil_emocional"]
    nao_classificados = [s for s in perfil["sinais"] if s["familia"] == "ambigua"]
    assert nao_classificados
    for sinal in nao_classificados:
        assert "não force emoção" not in sinal["limite_cta"]
        assert "escolha a família" in sinal["direcao_cta"]
    assert "indisponível" in perfil["resumo"]
    assert "movido principalmente por ambigua" not in perfil["resumo"]


def test_familia_reconhecida_mantem_a_direcao_propria():
    perfil = HeuristicaDeIntencao().classificar(["quem tem direito ao benefício"])["perfil_emocional"]
    sinal = perfil["sinais"][0]
    assert sinal["familia"] != "ambigua"
    assert "escolha a família" not in sinal["direcao_cta"]
