"""One-shot patch proposals; the host, not the LLM, applies and tests each round."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import google_search
from google.adk.workflow import FunctionNode, START, Workflow
from google.genai import types

from config import MODEL
from host import Host
from tasks import Ticket, preload


class Edit(BaseModel):
    path: str
    sha256: str
    old: str = Field(min_length=1)
    new: str


class PatchProposal(BaseModel):
    summary: str
    blocked_reason: str
    edits: list[Edit] = Field(max_length=12)


def apply_proposal(host: Host, raw: str | dict[str, Any]) -> dict[str, Any]:
    """Validate every anchor against the starting revision before any write."""
    try:
        proposal = (PatchProposal.model_validate(raw) if isinstance(raw, dict)
                    else PatchProposal.model_validate_json(raw))
        if proposal.blocked_reason:
            return {'blocked': proposal.blocked_reason, 'applied': 0}
        if not proposal.edits:
            return {'error': 'No edits proposed; a report is not an implementation.', 'applied': 0}
        originals: dict[str, str] = {}
        simulated: dict[str, str] = {}
        for edit in proposal.edits:
            content = host._path(edit.path, write=True).read_text()
            read = host.read_file(edit.path, 1, 1)
            if read.get('sha256') != edit.sha256:
                raise ValueError('Proposal SHA does not match current source: ' + edit.path)
            originals[edit.path] = content
            current = simulated.get(edit.path, content)
            if current.count(edit.old) != 1 or edit.old == edit.new:
                raise ValueError('Anchor must be unique and changed: ' + edit.path)
            simulated[edit.path] = current.replace(edit.old, edit.new, 1)
        applied = []
        for edit in proposal.edits:
            result = host.replace_text(edit.path, host.read_hashes[edit.path], edit.old, edit.new)
            applied.append(result)
            if result.get('error'):
                return {'error': result['error'], 'results': applied}
        return {'applied': len(applied), 'summary': proposal.summary, 'results': applied}
    except (ValueError, OSError) as exc:
        return {'error': str(exc), 'applied': 0}


def build_ticket_workflow(host: Host, api: Any, ticket: Ticket, rounds: int) -> Workflow:
    master = Path(__file__).with_name('MISSION.md').read_text() + '\n' + Path(__file__).with_name('EXECUTION.md').read_text()
    generation = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH, include_thoughts=False),
        # HIGH reasoning shares this allowance with the actual patch. Smaller
        # 16k/32k allowances truncated live JSON; incomplete proposals never apply.
        max_output_tokens=65_536,
    )

    def agent(name: str, instruction, **kwargs):
        return LlmAgent(name=name, model=Gemini(model=MODEL, client=api, retry_options=types.HttpRetryOptions(attempts=1)),
                        include_contents='none', instruction=instruction,
                        generate_content_config=generation.model_copy(deep=True),
                        before_model_callback=host.before_model, after_model_callback=host.after_model, **kwargs)

    researcher = agent('meta_api_researcher', ticket.research +
        '\nUse Google Search. Apenas fontes oficiais Meta, React e W3C. Cite URLs e incertezas. '
        'Não invente regra. Máximo 400 palavras. Nenhum dado interno deve entrar na busca.',
        tools=[google_search], output_key='api_research')

    def implementation_prompt(ctx):
        return master + '\n' + ticket.contract() + '\n' + (
            'MODO PATCH ESTRUTURADO: não há ferramentas a chamar. Entregue JSON no schema fornecido com '
            'edições literais COMPACTAS prontas para aplicar: path, sha256, old, new. Nunca substitua arquivo inteiro. '
            'Use âncoras curtas e mudanças locais para caber em até 6000 tokens de JSON. '
            'Não entregue pseudocódigo, diff markdown '
            'nem relato de mudanças imaginárias. O host aplicará o patch e rodará o teste obrigatório automaticamente. '
            'Use hashes fornecidos; para múltiplas edições no mesmo arquivo use o mesmo hash inicial e âncoras '
            'válidas sequencialmente. old/new não têm prefixos de número de linha. Inclua código E testes de '
            'regressão nesta resposta. Não apague testes existentes. Se impossível, edits=[] e blocked_reason real. '
            'Implemente todos os aceites, não uma recomendação. Máximo 24000 caracteres por replacement.\n'
        ) + '\nFontes atuais:\n' + preload(host, ticket) + '\nPesquisa:\n' + str(ctx.state.get('api_research', '')) + (
            '\nÚltima revisão e resultado real de aplicação/testes:\n' + json.dumps({
                k: ctx.state.get(k, '') for k in ('verdict', 'patch_result', 'test_result')
            }, ensure_ascii=False)
        )

    engineer = agent('meta_engineer', implementation_prompt, output_schema=PatchProposal, output_key='patch_proposal')

    async def apply_and_test(ctx):
        result = apply_proposal(host, ctx.state.get('patch_proposal', ''))
        ctx.state['patch_result'] = result
        gate = 'backend' if ticket.test.endswith('.py') else 'frontend'
        ctx.state['test_result'] = await host.run_gate(gate, ticket.test)
        await host.run_gate('diff')
        return result

    def critique_prompt(ctx):
        return master + '\n' + ticket.contract() + '\n' + (
            'Revisor independente: avalie o diff REAL e testes do host abaixo contra CADA aceite. '
            'Não aceite narrativa do executor como prova. Retorne apenas JSON verdict candidate/revise/blocked, '
            'findings, coverage, remaining, summary. Se revise, dê trechos concretos a corrigir. '
            'Patch sem implementação ou sem regressão é revise. Falha de gate é revise. Sem evidência visual '
            'anote limite, não invente inspeção de browser.\n'
        ) + json.dumps({'diff': host.show_diff(), 'patch_result': ctx.state.get('patch_result', ''),
                        'research': ctx.state.get('api_research', '')}, ensure_ascii=False)

    critic = agent('meta_critic', critique_prompt, output_key='verdict')

    def decide(ctx):
        ctx.route = host.evaluate_critic(str(ctx.state.get('verdict', '')), rounds)
        return {'route': ctx.route}

    def done(ctx):
        return {'ticket': ticket.slug, 'status': host.status}

    apply = FunctionNode(func=apply_and_test, name='apply_and_test')
    decision = FunctionNode(func=decide, name='route_after_critic')
    terminal = FunctionNode(func=done, name='ticket_terminal')
    return Workflow(name='meta_ticket_' + ticket.slug, max_concurrency=1, edges=[
        (START, researcher, engineer, apply, critic, decision),
        (decision, {'revise': engineer, 'done': terminal}),
    ])
