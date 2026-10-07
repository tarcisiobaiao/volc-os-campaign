"""PACOTE DE POLÍTICAS DO REVISOR (etapa B5).

O revisor contextual só pode bloquear com regra de plataforma que exista no
livro-razão da Frente A — nunca com uma regra que ele mesmo "lembrou". O pacote
é gerado do ledger: só entradas A e B pertinentes a `search_ads`,
`landing_page` e `monetizacao_publisher`; C vira nota; D não entra. Tem dono e
validade (refresh em 30 dias).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from funnelforge.politicas import (
    CAMINHO_DO_PACOTE,
    SUPERFICIES,
    carregar_pacote,
    gerar_pacote,
    pacote_para_o_revisor,
)

LEDGER_DA_FRENTE_A = (
    Path(__file__).resolve().parents[3]
    / ".claude-ads/runs/editorial-refactor-20260930/frente-a-politicas/ledger.json"
)


def _mini_ledger() -> list[dict]:
    return [
        {"id": "ADS-MIS-04", "tipo": "regra", "titulo": "Unreliable claims",
         "superficie": "search_ads", "superficies_secundarias": ["landing_page"],
         "url": "https://support.google.com/adspolicy/answer/1",
         "url_final": "https://support.google.com/adspolicy/answer/1?hl=en",
         "consultado_em": "2026-09-30", "classes_presentes": ["A", "B"],
         "o_que_exige": ["Não prometer resultado improvável como provável."],
         "o_que_apenas_sugere_risco": ["Gratuidade universal quando há critério."]},
        {"id": "PUB-10", "tipo": "regra", "titulo": "Ad labels",
         "superficie": "monetizacao_publisher", "url": "https://support.google.com/x",
         "consultado_em": "2026-09-30", "classes_presentes": ["A"],
         "o_que_exige": ["Não pedir clique em anúncio."], "o_que_apenas_sugere_risco": []},
        {"id": "API-02", "tipo": "regra", "titulo": "Limites do RSA", "superficie": "api",
         "superficies_secundarias": ["search_ads"], "url": "https://developers.google.com/y",
         "consultado_em": "2026-09-30", "classes_presentes": ["A"],
         "o_que_exige": ["Título até 30 caracteres."], "o_que_apenas_sugere_risco": []},
        {"id": "SEO-04", "tipo": "regra", "titulo": "Interstitials", "superficie": "search_organico",
         "url": "https://developers.google.com/z", "consultado_em": "2026-09-30",
         "classes_presentes": ["B"], "o_que_exige": [],
         "o_que_apenas_sugere_risco": ["Diálogo intrusivo."]},
        {"id": "NE-03", "tipo": "nao_escrito", "titulo": "Crença: CTA em 1ª pessoa viola política",
         "superficie": "landing_page", "url": "https://support.google.com/w",
         "consultado_em": "2026-09-30", "classe_da_crenca": "C",
         "regra_resumo": "Nenhuma política menciona primeira pessoa."},
        {"id": "NE-02", "tipo": "nao_escrito", "titulo": "Crença: exclamação única proibida",
         "superficie": "search_ads", "url": "https://support.google.com/v",
         "consultado_em": "2026-09-30", "classe_da_crenca": "B (risco), não A",
         "regra_resumo": "Exclamação no título é arriscada, não proibida."},
        {"id": "NE-06", "tipo": "nao_escrito", "titulo": "Crença: 'você' é proibido",
         "superficie": "search_ads", "url": "https://support.google.com/u",
         "consultado_em": "2026-09-30", "classe_da_crenca": "D",
         "regra_resumo": "Não é."},
        {"id": "FATO-01", "tipo": "fato_contexto", "titulo": "Natureza jurídica",
         "consultado_em": "2026-09-30"},
    ]


def test_gerador_so_leva_a_e_b_das_tres_superficies_c_vira_nota_d_fica_fora():
    pacote = gerar_pacote(_mini_ledger(), gerado_em=date(2026, 9, 30),
                          dono="operador VOLC", fonte={"arquivo": "ledger.json", "sha256": "x"})
    regras = {r["id"]: r for r in pacote["regras"]}
    assert set(regras) == {"ADS-MIS-04#A1", "ADS-MIS-04#B1", "PUB-10#A1", "NE-02#B1"}
    assert regras["ADS-MIS-04#A1"]["classe"] == "A"
    assert regras["ADS-MIS-04#B1"]["classe"] == "B"
    for r in regras.values():
        assert {"id", "regra", "classe", "texto", "url", "consultado_em", "aplica_a"} <= set(r)
        assert r["url"].startswith("https://")
        assert r["consultado_em"] == "2026-09-30"
        assert len(r["texto"]) <= 280
    assert regras["ADS-MIS-04#A1"]["aplica_a"] == ["search_ads", "landing_page"]
    assert [n["id"] for n in pacote["notas_c"]] == ["NE-03"]
    assert "NE-06" in pacote["excluidos"]["classe_d"]
    assert "API-02" in pacote["excluidos"]["fora_de_superficie"]
    assert "SEO-04" in pacote["excluidos"]["fora_de_superficie"]
    assert pacote["dono"] == "operador VOLC"
    assert pacote["gerado_em"] == "2026-09-30"
    assert pacote["valido_ate"] == "2026-10-30"          # refresh em 30 dias
    assert pacote["refresh_dias"] == 30
    assert pacote["superficies"] == list(SUPERFICIES)


def test_pacote_versionado_no_motor_tem_dono_validade_e_so_a_b():
    pacote = carregar_pacote(hoje=date(2026, 9, 30))
    assert CAMINHO_DO_PACOTE.name == "pacote_revisor.json"
    assert pacote.dono.strip()
    assert pacote.valido_ate == date(2026, 10, 30)
    assert pacote.vencido is False
    assert pacote.regras, "pacote vazio"
    assert {r["classe"] for r in pacote.regras} <= {"A", "B"}
    ids = [r["id"] for r in pacote.regras]
    assert len(ids) == len(set(ids))
    for r in pacote.regras:
        assert set(r["aplica_a"]) & set(SUPERFICIES), r["id"]
        assert r["url"].startswith("https://"), r["id"]
    assert all(n["classe"] == "C" for n in pacote.notas_c)
    assert not any(r["regra"].startswith("API-") for r in pacote.regras)


def test_pacote_vencido_e_declarado_como_vencido():
    assert carregar_pacote(hoje=date(2026, 10, 31)).vencido is True
    assert carregar_pacote(hoje=date(2026, 10, 30)).vencido is False


def test_o_revisor_recebe_as_regras_de_pagina_e_ids_conferiveis():
    pacote = carregar_pacote(hoje=date(2026, 9, 30))
    para_o_revisor = pacote_para_o_revisor(pacote)
    assert para_o_revisor["regras"], "o revisor precisa de regras de página"
    for r in para_o_revisor["regras"]:
        assert r["classe"] in {"A", "B"}
    ids = {r["id"] for r in para_o_revisor["regras"]}
    # desinformação/oferta e destino e publisher: o núcleo de uma página de funil
    assert any(i.startswith("ADS-MIS-04#") for i in ids)
    assert any(i.startswith("ADS-DST-") for i in ids)
    assert any(i.startswith("PUB-") for i in ids)
    # formato de anúncio (pontuação, caixa, repetição, assets) não é regra de página;
    # "empresa não identificada" (ADS-EDI-05) vale também para a landing page
    assert not any(i.startswith(("ADS-EDI-01", "ADS-EDI-02", "ADS-EDI-03", "ADS-EDI-04",
                                 "ADS-FMT-", "NE-02")) for i in ids)
    assert any(i.startswith("ADS-EDI-05#") for i in ids)
    assert pacote.ids_bloqueantes() >= ids


@pytest.mark.skipif(not LEDGER_DA_FRENTE_A.exists(), reason="ledger da Frente A ausente")
def test_pacote_versionado_bate_com_o_ledger_da_frente_a():
    ledger = json.loads(LEDGER_DA_FRENTE_A.read_text(encoding="utf-8"))
    versionado = json.loads(CAMINHO_DO_PACOTE.read_text(encoding="utf-8"))
    regerado = gerar_pacote(ledger, gerado_em=date.fromisoformat(versionado["gerado_em"]),
                            dono=versionado["dono"], fonte=versionado["fonte"])
    assert regerado["regras"] == versionado["regras"]
    assert regerado["notas_c"] == versionado["notas_c"]


def test_item_escrito_para_o_caso_senac_vai_ao_revisor_como_exemplo_da_regra_geral():
    """O revisor serve a qualquer nicho: item do ledger já aplicado ao caso Senac
    não pode virar regra genérica sobre o Senac no prompt."""
    from funnelforge.pipeline.revisao import ContextoDaRevisao, Documento, montar_prompt_do_revisor

    ledger = [{"id": "ADS-MIS-01", "tipo": "regra", "titulo": "Unacceptable business practices",
               "superficie": "search_ads", "url": "https://support.google.com/x",
               "consultado_em": "2026-09-30", "classes_presentes": ["A"],
               "regra_resumo": "Proíbe fazer parecer afiliação com outra marca ou governo.",
               "o_que_exige": ["Não sugerir vínculo com o Senac (o Crédito Up não é parceiro)."],
               "o_que_apenas_sugere_risco": []}]
    [regra] = gerar_pacote(ledger, gerado_em=date(2026, 9, 30), dono="x",
                           fonte={"arquivo": "l", "sha256": "0"})["regras"]
    assert regra["caso_especifico"] is True
    assert regra["regra_geral"].startswith("Proíbe fazer parecer afiliação")
    prompt = montar_prompt_do_revisor(
        Documento(formato="gutenberg", corpo="<p>x</p>"),
        ContextoDaRevisao(pagina={"numero": 2}, politicas={"regras": [regra], "notas_c": [],
                                                           "resumo": {}}))
    linha = next(li for li in prompt.splitlines() if li.startswith("- ADS-MIS-01#A1"))
    assert linha.index("Proíbe fazer parecer afiliação") < linha.index("exemplo registrado")
