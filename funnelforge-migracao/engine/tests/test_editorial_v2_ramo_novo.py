"""O RAMO EDITORIAL NOVO de ponta a ponta (etapa B4), com LLM falso.

- o que o ARQUITETO sabe do leitor e do tom (tone_voice, avatar_summary) e a
  TENSÃO medida na validação chegam ao prompt do redator v2 — era exatamente o
  que se perdia entre as etapas (diretriz 3 do operador);
- o briefing roda entre a pesquisa e a redação; o SEO roda antes da revisão;
- briefing inválido depois das retentativas fecha a página sem gasto de redação;
- página sem contrato editorial (arquiteto de fallback) também recebe briefing.
"""
from __future__ import annotations

import json
from pathlib import Path

from funnelforge.domain.models import StepStatus
from funnelforge.pipeline.doctrine import BANNED_CTA_FIRST_PERSON
from tests.cenario_editorial import (
    AVATAR_DO_ARQUITETO,
    TOM_DO_ARQUITETO,
    arquitetura_base,
    briefing_valido,
    congelar_data,
    ordem_do_run,
    prompts_do_run,
    responder_v2,
    rodar_cenario,
    settings_do_cenario,
    texto_da_mensagem,
)

TENSAO = "Acha que precisa pagar alguem para pedir o desconto"
PAA = ["Quem tem direito a tarifa social?", "Como pedir a tarifa social?"]


def _arquitetura_v2(*, editorial: bool = False) -> dict:
    arq = arquitetura_base(editorial=editorial)
    arq["contexto_de_leitura"] = {"perguntas_paa": PAA,
                                  "tensao": {"frase": TENSAO, "evidencia": "validacao:3/4"}}
    return arq


def _rodar(tmp_path: Path, monkeypatch, arq: dict, *, responder=responder_v2,
           passos_v2: bool = True):
    congelar_data(monkeypatch)
    settings = settings_do_cenario(tmp_path, editorial_v2=True, passos_v2=passos_v2)
    return rodar_cenario(tmp_path, arq, settings, responder=responder)


def test_tom_avatar_e_tensao_do_arquiteto_chegam_ao_redator_v2(tmp_path: Path, monkeypatch):
    state, deps, _llm = _rodar(tmp_path, monkeypatch, _arquitetura_v2())
    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    for n in range(1, 6):
        redator = prompts[f"write_p{n}"]
        assert "BRIEFING DESTA PÁGINA" in redator, n
        assert TOM_DO_ARQUITETO in redator, n
        assert AVATAR_DO_ARQUITETO in redator, n
        assert TENSAO in redator, n
        assert PAA[0] in redator, n
    assert state.editorial_v2 is True
    assert sorted(state.briefings) == [1, 2, 3, 4, 5]
    for n in range(1, 6):
        assert state.step_status[f"briefing_p{n}"].status is StepStatus.OK
        assert state.step_status[f"write_p{n}"].status is not StepStatus.FAILED
    pasta = deps.runner.runs_dir / state.run_id
    briefing = json.loads((pasta / "p3.briefing.json").read_text(encoding="utf-8"))
    assert briefing["briefing_do_arquiteto"]["tone_voice"] == TOM_DO_ARQUITETO
    assert briefing["briefing_do_arquiteto"]["tensao"]["frase"] == TENSAO
    assert (pasta / "p3.inventario.json").exists()


def test_briefing_recebe_o_inventario_e_o_plano_do_arquiteto(tmp_path: Path, monkeypatch):
    state, deps, _llm = _rodar(tmp_path, monkeypatch, _arquitetura_v2())
    briefing = prompts_do_run(deps.runner.runs_dir, state.run_id)["briefing_p3"]
    assert TOM_DO_ARQUITETO in briefing and AVATAR_DO_ARQUITETO in briefing
    assert TENSAO in briefing and PAA[1] in briefing
    assert "NÃO COLETADOS" in briefing        # termos ausentes ditos como ausentes
    assert "n1 [numero]" in briefing           # fato tipado (regra de legado) com id
    assert "tipo=funnel destino=como-pedir-tarifa-social-p2" in briefing
    assert 'A INTENÇÃO REAL DA BUSCA É SEMPRE "hipotese"' in briefing


def test_ordem_briefing_antes_da_redacao_e_seo_antes_da_revisao(tmp_path: Path, monkeypatch):
    state, deps, _llm = _rodar(tmp_path, monkeypatch, _arquitetura_v2())
    chamadas = ordem_do_run(deps.runner.runs_dir, state.run_id, state)["chamadas_llm"]

    def primeira(passo: str) -> int:
        return chamadas.index(f"{passo}#1")

    for n in range(1, 6):
        assert primeira(f"research_p{n}") < primeira(f"briefing_p{n}") < primeira(f"write_p{n}")
    # B5: TODA página (a LP sem `editorial` inclusive) passa pelo revisor
    # contextual, depois do SEO; o juiz antigo não roda no ramo novo.
    for n in range(1, 6):
        assert primeira(f"write_p{n}") < primeira(f"seo_p{n}") < primeira(f"revisor_p{n}")
        assert f"judge_p{n}#1" not in chamadas


def test_prompts_do_ramo_novo_sao_os_v2(tmp_path: Path, monkeypatch):
    state, deps, _llm = _rodar(tmp_path, monkeypatch, _arquitetura_v2())
    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    for n in range(1, 6):
        redator = prompts[f"write_p{n}"]
        for velho in ("verbo brando", "transição calma", "ANO CORRENTE", "Agora que você entende"):
            assert velho not in redator, (n, velho)
        for frase in BANNED_CTA_FIRST_PERSON:
            assert frase not in redator.lower(), (n, frase)
        seo = prompts[f"seo_p{n}"]
        assert "Você escreve o TÍTULO SEO" in seo
        assert "curiosidade sem revelar" not in seo and "ANO CORRENTE" not in seo
        assert "Vocational" not in prompts[f"image_p{n}"]


def test_pagina_sem_editorial_e_com_editorial_recebem_briefing(tmp_path: Path, monkeypatch):
    """O arquiteto de fallback gera páginas SEM `editorial`: no ramo novo elas
    também passam pelo briefing (contrato, decisão 5)."""
    legado, _deps, _ = _rodar(tmp_path / "legado", monkeypatch, _arquitetura_v2(editorial=False))
    assert all(p.editorial is None for p in legado.plan.pages)
    assert sorted(legado.briefings) == [1, 2, 3, 4, 5]
    contextual, _deps2, _ = _rodar(tmp_path / "ctx", monkeypatch,
                                    _arquitetura_v2(editorial=True))
    assert all(p.editorial is not None for p in contextual.plan.pages)
    assert sorted(contextual.briefings) == [1, 2, 3, 4, 5]


def test_briefing_invalido_fecha_a_pagina_sem_gasto_de_redacao(tmp_path: Path, monkeypatch):
    def responder(model, messages):
        prompt = texto_da_mensagem(messages[-1])
        if "EDITOR DE BRIEFING" in prompt:
            # intenção declarada como FATO e benefício sem fato, em toda tentativa
            dados = json.loads(briefing_valido(prompt))
            dados["intencao"]["intencao_real_da_busca"] = {
                "texto": "quer o desconto", "base": "fato", "ref": ["n1"]}
            dados["beneficios"] = [{"texto": "desconto garantido", "fatos": [], "limite": ""}]
            return json.dumps(dados)
        return responder_v2(model, messages)

    state, deps, llm = _rodar(tmp_path, monkeypatch, _arquitetura_v2(), responder=responder)

    redacoes = [c for c in llm.calls
                if any(m in texto_da_mensagem(c["messages"][0])
                       for m in ("PÁGINA DE POUSO", "PÁGINA INTERNA", "PÁGINA PRÉ-SELL"))]
    assert redacoes == [], "nenhuma redação pode ser paga sem briefing válido"
    for n in range(1, 6):
        briefing = state.step_status[f"briefing_p{n}"]
        assert briefing.status is StepStatus.FAILED
        codigos = {i.code for i in briefing.issues}
        assert {"intencao_nao_e_fato", "beneficio_sem_fato",
                "briefing_indisponivel"} <= codigos, codigos
        assert briefing.attempts == deps.settings.run.max_retries + 1
        escrita = state.step_status[f"write_p{n}"]
        assert escrita.status is StepStatus.FAILED and escrita.attempts == 0
        assert escrita.cost_usd == 0.0
        assert [i.code for i in escrita.issues] == ["briefing_indisponivel"]
        assert state.step_status[f"blocked_p{n}"].status is StepStatus.FAILED
        assert f"seo_p{n}" not in state.step_status
        assert n not in state.briefings


def test_sem_o_passo_briefing_na_config_fecha_sem_chamar_modelo(tmp_path: Path, monkeypatch):
    state, _deps, llm = _rodar(tmp_path, monkeypatch, _arquitetura_v2(), passos_v2=False)
    assert not any("EDITOR DE BRIEFING" in texto_da_mensagem(c["messages"][0])
                   for c in llm.calls)
    for n in range(1, 6):
        assert state.step_status[f"briefing_p{n}"].status is StepStatus.FAILED
        assert state.step_status[f"write_p{n}"].status is StepStatus.FAILED


def test_sem_termos_observados_nenhum_prompt_oferece_termo_como_evidencia(
        tmp_path: Path, monkeypatch):
    """Canário p5 (30/09): o modelo citou `termo:portal senac`, que ninguém
    digitou. Sem termos observados, briefing e revisor não recebem a forma
    `termo:` como evidência possível, e a ausência vem dita com todas as letras."""
    state, deps, _llm = _rodar(tmp_path, monkeypatch, _arquitetura_v2())
    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    for n in range(1, 6):
        for passo in (f"briefing_p{n}", f"revisor_p{n}"):
            assert "termo:<" not in prompts[passo], passo
            assert "termo:/" not in prompts[passo], passo
            assert "termo: indisponível" in prompts[passo], passo


def test_com_termos_observados_termo_so_se_copiado_da_lista(tmp_path: Path, monkeypatch):
    """Com termos observados, `termo:` só vale copiado da lista; se nenhum trata
    do assunto da página, o modelo é mandado dizer isso em vez de parafrasear."""
    arq = _arquitetura_v2()
    arq["contexto_de_busca"] = {
        "estado": "presente", "janela": {"inicio": "2026-09-01", "fim": "2026-09-29"},
        "coletado_em": "2026-09-30T08:00:00-03:00", "fonte": "search_term_view",
        "termos": [{"termo": "tarifa social quem tem direito", "impressoes": 50, "cliques": 4}]}
    state, deps, _llm = _rodar(tmp_path, monkeypatch, arq)
    prompts = prompts_do_run(deps.runner.runs_dir, state.run_id)
    briefing, revisor = prompts["briefing_p3"], prompts["revisor_p3"]
    assert "tarifa social quem tem direito" in briefing
    assert "termo:<termo copiado literalmente da lista" in briefing
    assert "nenhum termo observado trata do assunto" in briefing
    assert "termo: indisponível" not in briefing
    assert "termo:<termo copiado literalmente da lista" in revisor
    assert "termo: indisponível" not in revisor
