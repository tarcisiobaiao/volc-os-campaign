"""Canário seco único da missão; usa o motor, configuração e sessão existentes."""
import hashlib
import json
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / 'src'))
from funnelforge.config.settings import Settings, Secrets
from funnelforge.cli import build_deps, conferir_modelos_do_plano
from funnelforge.pipeline.pipeline import run_pipeline
from funnelforge.adapters.pesquisa_plano import ler_documento


def main():
    baseline = ENGINE / 'runs/guia-gas-do-povo-20261008-134021'
    origem = baseline / 'state.json'
    sha_antes = hashlib.sha256(origem.read_bytes()).hexdigest()
    arq = json.loads((baseline / 'funnel_architecture.json').read_text())
    config = json.loads((baseline / 'config_snapshot.json').read_text())
    config["secrets"] = {}  # snapshot deliberadamente não contém segredos
    settings = Settings.model_validate(config)
    settings.secrets = Secrets()
    settings.run.publish = False
    settings.run.imagens_habilitadas = False
    settings.run.official_screenshots = False
    settings.run.page_workers = 3
    settings.run.max_retries = 0
    settings.run.research_max_attempts = 1
    settings.run.max_chamadas_llm = 12
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
    # Recusa UMA segunda execução, mesmo quando a primeira terminou em erro.
    lock = deps.runner.runs_dir / '.pre-redacao-one-shot.lock'
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
              'custo_faturado_usd': None, 'custo': 'não informado', 'erro': None}
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
        state = run_pipeline(None, deps, card_pre_arquitetura=card, publish=False,
                             timestamp='20261008-pre-redacao-unico')
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
    except Exception as exc:
        recibo['erro'] = type(exc).__name__  # não registrar corpo HTTP/credenciais
    finally:
        recibo['chamadas'] = deps.llm.chamadas
        recibo['duracao_s'] = round(time.monotonic()-inicio, 3)
        recibo['baseline_preservada'] = hashlib.sha256(origem.read_bytes()).hexdigest() == sha_antes
        saida = deps.runner.runs_dir / 'pre-redacao-one-shot-recibo.json'
        saida.write_text(json.dumps(recibo, ensure_ascii=False, indent=2))
        print(json.dumps({k:v for k,v in recibo.items() if k not in ('passos','pacotes','concorrencia')}, ensure_ascii=False))
    return 1 if recibo['erro'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
