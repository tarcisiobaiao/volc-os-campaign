"""RECIBO DO CANÁRIO: o que rodou, com que modelo e autenticação, e a prova de
que nada foi publicado. Nenhum segredo entra aqui — só o que o estado já tem
(modelo pedido/servido, esforço, tentativas, tokens, status dos portões)."""
from __future__ import annotations

from typing import Any

from funnelforge.domain.models import RunState, StepStatus

_PORTOES = ("funnel_graph", "revisao_esqueleto", "revisao_global")


def recibo_do_canario(state: RunState, settings: Any, *, publisher_ligado: bool,
                      image_gen_ligado: bool, chamadas: int) -> dict:
    etapas = []
    for chave, r in state.step_status.items():
        if not (r.prompt_tokens or r.completion_tokens or r.model_used):
            continue
        plano = r.auth_mode == "chatgpt_plan"
        etapas.append({
            "etapa": chave, "status": r.status.value, "auth_mode": r.auth_mode or "?",
            "modelo_pedido": r.model_requested, "modelo_servido": r.model_used,
            "reasoning_effort": r.reasoning_effort or None, "tentativas": r.attempts,
            "tokens_entrada": r.prompt_tokens or None, "tokens_saida": r.completion_tokens or None,
            "latencia_ms": r.latency_ms,
            "custo": ("não aplicável — uso do plano ChatGPT" if plano
                      else f"API faturada: US$ {r.cost_usd:.6f}"),
        })
    paginas = state.plan.pages if state.plan else []
    portoes = {k: state.step_status[k].status.value for k in _PORTOES if k in state.step_status}
    for p in paginas:
        n = p.page_number
        for k in (f"content_gate_p{n}", f"revisor_p{n}", f"judge_p{n}", f"blocked_p{n}"):
            if k in state.step_status:
                portoes[k] = state.step_status[k].status.value
    publicados = [k for k, r in state.step_status.items()
                  if k.startswith("publish_p") and r.status is not StepStatus.FAILED]
    return {
        "versao": "recibo-canario-v1",
        "run_id": state.run_id,
        "auth_mode": settings.openai.auth_mode,
        "chamadas_llm": chamadas,
        "teto_de_chamadas": settings.run.max_chamadas_llm or None,
        "etapas": etapas,
        "portoes": portoes,
        "imagem": "não exercitada" if not settings.run.imagens_habilitadas else "exercitada",
        "custo_api_faturada_usd": round(sum(r.cost_usd for r in state.step_status.values()), 6),
        "uso_do_plano": "reportado em tokens por etapa; sem equivalência financeira",
        "publicacao": {
            "publish": bool(settings.run.publish), "publish_status": settings.run.publish_status,
            "publisher_ligado": publisher_ligado, "gerador_de_imagem_ligado": image_gen_ligado,
            "paginas_publicadas": publicados, "respostas_do_wordpress": len(state.published),
            "nada_publicado": not publicados and not state.published and not publisher_ligado,
        },
    }


def pre_carregar_fatos(plan: Any, deps: Any, origem: Any, timestamp: str) -> RunState:
    """Canário SEM pesquisa paga: o inventário factual de um run anterior entra
    no lugar da pesquisa, mas NÃO como verdade pronta. Cada página passa pelo
    MESMO portão da pesquisa (`_gate_research`, com o verificador de URL ao
    vivo, só leitura HTTP) e pela escolha de canais oficiais — fatos com fonte
    morta ou fora da janela de vigência caem como cairiam numa pesquisa nova.
    A etapa fica marcada como `pesquisa_nao_exercitada`."""
    from funnelforge.domain.models import Issue, StepResult
    from funnelforge.pipeline import steps as st

    state = RunState(run_id=f"_pending-{timestamp}")
    for page in plan.pages:
        bruto = origem.facts.get(page.page_number)
        if bruto is None:
            continue
        facts = bruto.model_copy(deep=True)
        facts.fontes_resolvidas = []          # re-verificadas agora, ao vivo
        chave = f"research_p{page.page_number}"
        res = StepResult(step=chave, status=StepStatus.OK, attempts=0, issues=[Issue(
            code="pesquisa_nao_exercitada",
            message=f"fatos do inventário do run {origem.run_id}, re-verificados ao vivo; "
                    "nenhuma chamada de pesquisa")])
        st._gate_research(facts, res, deps)
        state.facts[page.page_number] = facts
        state.step_status[chave] = res
        st.registrar_canais_oficiais(state, page, deps)
    return state
