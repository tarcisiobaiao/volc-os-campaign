"""Canário seco único da missão; usa o motor, configuração e sessão existentes."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / 'src'))
from funnelforge.config.settings import Settings, Secrets
from funnelforge.cli import build_deps, conferir_modelos_do_plano
from funnelforge.domain.models import RunState
from funnelforge.pipeline.pipeline import run_pipeline, _populate_routes
from funnelforge.adapters.pesquisa_plano import ler_documento


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True,
                        help="identificador único desta execução autorizada")
    parser.add_argument("--resume-run", default="",
                        help="run anterior recusado a continuar sem repetir pesquisa/arquitetura")
    parser.add_argument("--prior-calls", type=int, default=0,
                        help="chamadas já consumidas pelo run retomado")
    args = parser.parse_args()
    if not args.tag.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("--tag aceita somente letras, números, hífen e underscore")
    if args.resume_run and not args.resume_run.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("--resume-run aceita somente o nome do run")
    if args.prior_calls < 0 or args.prior_calls >= 12:
        raise SystemExit("--prior-calls deve estar entre 0 e 11")
    baseline = ENGINE / 'runs/guia-gas-do-povo-20261008-134021'
    origem = baseline / 'state.json'
    sha_antes = hashlib.sha256(origem.read_bytes()).hexdigest()
    arq = json.loads((baseline / 'funnel_architecture.json').read_text())
    resume_dir = ENGINE / 'runs-canario' / args.resume_run if args.resume_run else None
    config_dir = resume_dir if resume_dir else baseline
    config = json.loads((config_dir / 'config_snapshot.json').read_text())
    config["secrets"] = {}  # snapshot deliberadamente não contém segredos
    settings = Settings.model_validate(config)
    settings.secrets = Secrets()
    settings.run.publish = False
    settings.run.imagens_habilitadas = False
    settings.run.official_screenshots = False
    settings.run.page_workers = 3
    settings.run.max_retries = 0
    settings.run.research_max_attempts = 1
    settings.run.max_chamadas_llm = 12 - args.prior_calls
    settings.run.inteligencia_pre_redacao = True
    settings.run.jev_enabled = False
    settings.openai.somente_plano = True
    settings.openai.allow_api_key_fallback = False
    # Etapa de imagem desativada; não há substituição de modelo em etapa ativa.
    settings.steps.pop('image_review', None)
    assert all(not c.fallbacks and c.model.startswith('chatgpt/') for c in settings.steps.values())
    deps = build_deps(settings)
    deps.publisher = deps.image_gen = deps.screenshot = deps.sitemap = None
    deps.runner.runs_dir = ENGINE / 'runs-canario'
    deps.ler_documento = ler_documento
    deps.runner.runs_dir.mkdir(exist_ok=True)
    # Cada autorização recebe um tag e um lock próprios. Repetir o mesmo tag
    # nunca dispara outra chamada paga nem sobrescreve o recibo anterior.
    lock = deps.runner.runs_dir / f'.pre-redacao-{args.tag}.lock'
    with lock.open('x') as f:
        f.write('Missão 2026-10-08: um único canário real; não remover para retentar.\n')
    card = {'main_keyword': 'Gás do Povo: entender o direito, consultar e retirar a recarga',
            'entidade': 'Programa Gás do Povo', 'country': 'Brasil', 'native_language': 'pt-BR',
            'description': 'Canário seco da arquitetura registrada, sem alterar os drafts existentes.',
            'contexto_de_busca': arq.get('contexto_de_busca'),
            'contexto_de_anuncio': arq.get('contexto_de_anuncio'),
            'historico': {'origem': str(baseline.relative_to(ENGINE)),
                         'arquitetura_referencia': arq,
                         'orientacao': 'Preserve os IDs e entregas exclusivos coerentes da referência. '
                          'Requisitos factuais explícitos em todas as páginas; no máximo 5 páginas. '
                          'Faça somente correções sustentadas pela pesquisa. Não suponha demanda ausente.'}}
    inicio = time.monotonic()
    state = None
    recibo = {'tipo': 'canario_seco_unico', 'publish': False, 'publisher': False,
              'imagens': False, 'workers_configurados': 3, 'teto_chamadas': 12,
              'custo_faturado_usd': None, 'custo': 'não informado', 'erro': None,
              'continuacao_de': args.resume_run or None,
              'chamadas_anteriores': args.prior_calls}
    try:
        conferir_modelos_do_plano(settings, deps.llm)
        # Proteção de desenho: nunca pagar escritores se exceder a reserva.
        from funnelforge.pipeline import steps
        original = steps.step_extract
        def extrair(state, d):
            original(state, d)
            if state.plan and len(state.plan.pages) + deps.llm.chamadas + 3 > 12:
                raise ValueError('arquitetura excede reserva de complemento e revisão antes da redação')
        steps.step_extract = extrair
        if resume_dir:
            state = RunState.from_json((resume_dir / 'state.json').read_text())
            raw = json.loads((resume_dir / 'arquitetura_pre_redacao.json').read_text())
            from funnelforge.adapters.attention_matrix import modulo_do_repo
            from funnelforge.adapters.briefing_volc import plano_do_funnel_architecture
            contrato = modulo_do_repo('backend/app/agents/funnel_pro/jornada_contrato.py')
            factory = modulo_do_repo('backend/app/agents/funnel_pro/page_factory.py')
            roles = modulo_do_repo('backend/app/entities/funnel_roles.py')
            raw, normalizacao = contrato.normalizar_arquitetura(raw)
            if normalizacao['estado'] == 'invalida':
                raise ValueError('arquitetura gravada continua inválida')
            paginas = factory.architect_pages_to_funnel_pages(raw)
            jobs = factory.page_factory(raw)['writingJobs']
            paginas, jobs = roles.apply_roles_and_slugs(paginas, jobs)
            state.plan = plano_do_funnel_architecture({
                'funnel_strategy': raw.get('funnel_strategy') or {},
                'pages': paginas, 'writing_jobs': jobs})
            state.plan.brief_pre_arquitetura = state.brief_pre_arquitetura
            state.plan.editorial_v2 = True
            state.editorial_v2 = True
            for chave in list(state.step_status):
                if chave in {'funnel_graph', 'revisao_esqueleto', 'contract_advisory'} \
                        or chave.startswith('blocked_p'):
                    state.step_status.pop(chave, None)
            # Reaplica o mesmo pós-processamento do fluxo normal. Chamar só
            # `_populate_routes` deixava todos os ordinais em zero e fazia
            # cada solução retomada parecer a página terminal.
            steps.expand_presell_hubs(state, deps)
            steps.dedupe_slugs(state.plan)
            _populate_routes(state, deps)
            state = run_pipeline(None, deps, resume_state=state, publish=False,
                                 timestamp=f'20261008-pre-redacao-{args.tag}')
        else:
            state = run_pipeline(None, deps, card_pre_arquitetura=card, publish=False,
                                 timestamp=f'20261008-pre-redacao-{args.tag}')
        recibo['run_id'] = state.run_id
        recibo['pacotes'] = {str(n): {'sha256': p['sha256'], 'estado': p['estado']}
                             for n,p in state.pacotes.items()}
        recibo['paginas_redigidas'] = len(state.drafts)
        recibo['publicadas'] = len(state.published)
        recibo['passos'] = {k: {'estado': v.status.value, 'tentativas': v.attempts,
                               'modelo_pedido': v.model_requested, 'modelo_servido': v.model_used,
                               'latencia_ms': v.latency_ms,
                               'causas': [i.code for i in v.issues]}
                            for k,v in state.step_status.items()}
        recibo['concorrencia'] = (state.step_status['paginas_paralelas'].model_dump(mode='json')
                                  if 'paginas_paralelas' in state.step_status else None)
        assert not state.published
        falhas = sorted(k for k, v in state.step_status.items()
                        if v.status.value == 'FAILED')
        revisoes_humanas = sorted(
            k for k in falhas
            if state.step_status[k].issues
            and {i.code for i in state.step_status[k].issues} <= {'revisao_humana'}
        )
        falhas_tecnicas = sorted(set(falhas) - set(revisoes_humanas))
        recibo['falhas'] = falhas_tecnicas
        recibo['revisoes_humanas'] = revisoes_humanas
        if falhas_tecnicas or not state.pacotes or not state.drafts:
            recibo['erro'] = 'PipelineFailed'
    except Exception as exc:
        recibo['erro'] = type(exc).__name__  # não registrar corpo HTTP/credenciais
    finally:
        recibo['chamadas_nesta_etapa'] = deps.llm.chamadas
        recibo['chamadas'] = args.prior_calls + deps.llm.chamadas
        recibo['duracao_s'] = round(time.monotonic()-inicio, 3)
        recibo['baseline_preservada'] = hashlib.sha256(origem.read_bytes()).hexdigest() == sha_antes
        saida = deps.runner.runs_dir / f'pre-redacao-{args.tag}-recibo.json'
        saida.write_text(json.dumps(recibo, ensure_ascii=False, indent=2))
        print(json.dumps({k:v for k,v in recibo.items() if k not in ('passos','pacotes','concorrencia')}, ensure_ascii=False))
    return 1 if recibo['erro'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
