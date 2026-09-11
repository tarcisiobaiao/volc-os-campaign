"""ADK 2.x graph: parallel reconnaissance and a routed engineer/critic cycle."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.models.google_llm import Gemini
from google.adk.tools import google_search
from google.adk.workflow import FunctionNode, JoinNode, START, Workflow
from google.genai import types

from config import MODEL, THINKING, Lane
from host import Host


def build_workflow(host: Host, api: Any, lane: Lane, rounds: int) -> Workflow:
    mission = Path(__file__).with_name("MISSION.md").read_text()
    lane_contract = (
        f"\n\n## Lane atual: {lane.title}\n"
        f"Resultado: {lane.outcome}\n"
        f"Pesquisa: {lane.research}\n"
        "Entrypoints obrigatórios:\n- " + "\n- ".join(lane.entrypoints)
    )
    base_instruction = mission + lane_contract

    def model() -> Gemini:
        return Gemini(
            model=MODEL,
            client=api,
            retry_options=types.HttpRetryOptions(attempts=1),
        )

    generation = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.HIGH,
            include_thoughts=False,
        ),
        max_output_tokens=10_000,
    )

    common = {
        "generate_content_config": generation,
        "before_model_callback": host.before_model,
        "after_model_callback": host.after_model,
        "before_tool_callback": host.before_tool,
        "after_tool_callback": host.after_tool,
        "disallow_transfer_to_parent": True,
        "disallow_transfer_to_peers": True,
    }
    mapper_tools = [host.read_file, host.search_source]
    review_tools = [host.read_file, host.search_source, host.show_diff]

    researcher = LlmAgent(
        name="meta_api_researcher",
        model=model(),
        include_contents="none",
        instruction=(
            base_instruction
            + "\n\nVocê é o pesquisador de contrato da API. Use Google Search agora. Consulte apenas "
              "developers.facebook.com, facebook.com/business/help ou documentação Google necessária "
              "para interpretar a integração. Entregue URLs diretas, data/versão quando disponível, "
              "campos/requisitos/limites e incertezas. Não envie código ou identificadores internos na busca. "
              "Máximo 900 palavras."
        ),
        tools=[google_search],
        output_key="api_research",
        **common,
    )

    mapper = LlmAgent(
        name="meta_code_mapper",
        model=model(),
        include_contents="none",
        instruction=(
            base_instruction
            + "\n\nVocê é o cartógrafo do código. Em paralelo ao pesquisador, leia todos os entrypoints, "
              "use busca literal e no máximo duas leituras focais de até 400 linhas. Identifique exatamente um "
              "defeito demonstrável de maior impacto — não faça inventário geral. Não edite. Cite path:line, "
              "comportamento atual, risco, mudança mínima e o teste focal que deve provar a correção. "
              "Na sua última chamada entregue o mapa, sem pedir mais ferramentas e sem explorar outras lanes."
        ),
        tools=mapper_tools,
        output_key="code_map",
        **common,
    )

    def iterative_instruction(role: str):
        def render(context: Any) -> str:
            state = {}
            for key in ("api_research", "code_map", "implementation", "verdict"):
                value = str(context.state.get(key, ""))
                state[key] = value[-8_000:]
            return base_instruction + f"\n\n## Seu papel\n{role}\n\n## Estado da lane\n" + json.dumps(
                state, ensure_ascii=False
            )
        return render

    engineer = LlmAgent(
        name="meta_engineer",
        model=model(),
        include_contents="none",
        instruction=iterative_instruction(
            "Você é o executor, não um consultor. Parta do único defeito mapeado. Não liste arquivos amplamente "
            "e não rode diff antes de editar. Confirme o símbolo com busca e uma leitura focal; então aplique no "
            "máximo uma correção coesa usando hash, crie/ajuste regressão e rode "
            "o gate focal depois da última edição. Se o crítico anterior apontou regressão, resolva-a antes de "
            "abrir novo escopo. Se não houver defeito comprovável, declare BLOCKED com a evidência exata — não "
            "consuma o orçamento em exploração aberta. Finalize com arquivos, prova antes/depois e pendências reais."
        ),
        tools=review_tools + [host.replace_text, host.create_test_file, host.run_gate],
        output_key="implementation",
        **common,
    )

    critic = LlmAgent(
        name="meta_critic",
        model=model(),
        include_contents="none",
        instruction=iterative_instruction(
            "Você é o revisor adversarial independente. Releia diff, chamadores e testes; procure contrato Meta "
            "inventado, estado perdido, duplicação, bypass de aprovação, ativação, falsa atribuição, teste decorativo "
            "e regressão de acessibilidade. Não edite. Candidate só com patch não vazio e gate focal pós-edição. "
            "Devolva exclusivamente JSON estrito no schema exigido pela missão."
        ),
        tools=review_tools,
        output_key="verdict",
        **common,
    )

    join = JoinNode(
        name="reconnaissance_join",
        description="Wait for both isolated reconnaissance branches.",
    )

    def decide(ctx: Context) -> dict[str, str]:
        route = host.evaluate_critic(str(ctx.state.get("verdict", "")), rounds)
        ctx.route = route
        return {"route": route}

    def finalize(ctx: Context) -> dict[str, Any]:
        return {
            "lane": lane.slug,
            "status": host.status,
            "rounds": host.rounds,
            "edits": host.edits,
            "verdict": str(ctx.state.get("verdict", ""))[-12_000:],
        }

    decision = FunctionNode(func=decide, name="route_after_critic")
    terminal = FunctionNode(func=finalize, name="lane_terminal")
    return Workflow(
        name=f"meta_{lane.slug}_workflow",
        description="Parallel reconnaissance followed by a bounded routed implementation/review graph.",
        max_concurrency=2,
        edges=[
            (START, (researcher, mapper)),
            (researcher, join),
            (mapper, join),
            (join, engineer, critic, decision),
            (decision, {"revise": engineer, "done": terminal}),
        ],
    )
