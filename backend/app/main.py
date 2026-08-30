"""
Pautador Pro — FastAPI application entrypoint.

Run locally:  uvicorn app.main:app --reload --port 8000
On Vercel:    served as an ASGI app via api/index.py (root directory = /backend)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.routers import (
    criativos,
    criativos_execucao,
    entities,
    pautador,
    trafego,
    trafego_inventario,
    work_road,
)

import importlib.util
import logging
import os

log = logging.getLogger("volc.main")

# Capacidades que este processo NÃO tem. Preenchidas na carga e no startup, e
# devolvidas por `/health`. Uma capacidade ausente vira dado visível, nunca um
# 404 silencioso nem um `status: ok` que mente.
ROUTERS_AUSENTES: list[dict[str, str]] = []
ROTINAS_AUSENTES: list[dict[str, str]] = []

settings = get_settings()

# ---------------------------------------------------------------------------
# DOCUMENTAÇÃO AUTOMÁTICA — fechada por padrão
# ---------------------------------------------------------------------------
# `/docs`, `/redoc`, `/openapi.json` e `/docs/oauth2-redirect` NÃO são APIRoute:
# o FastAPI as monta fora do roteador, e por isso `Depends()` não alcança
# nenhuma delas. Um portão por dependência — inclusive o do router — é
# estruturalmente cego para as quatro.
#
# E elas não são inofensivas. `/openapi.json` publica o contrato inteiro: todas
# as rotas, todos os schemas Pydantic, nomes de campo e enums. `/docs` ainda
# acrescenta o botão "Try it out" apontando para `POST /api/trafego/subir` (que
# cria campanha na conta real do cliente) e para `DELETE /api/pautador/
# entity-opportunities/{opp_id}` (que apaga em cascata). É o mapa que um
# estranho não precisaria adivinhar, com os botões já ligados.
#
# Ficam fechadas a menos que alguém peça. Em desenvolvimento: VOLC_DOCS_ABERTAS=1
_DOCS_ABERTAS = os.getenv("VOLC_DOCS_ABERTAS", "").strip().lower() in {"1", "true", "sim", "yes"}

app = FastAPI(
    title="Pautador Pro API",
    description="Esteira de arbitragem de atenção: descoberta, mineração e funis por país.",
    version=__version__,
    docs_url="/docs" if _DOCS_ABERTAS else None,
    redoc_url="/redoc" if _DOCS_ABERTAS else None,
    openapi_url="/openapi.json" if _DOCS_ABERTAS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _reconciliar_runs_orfaos() -> None:
    """Fecha os runs do redator que ficaram abertos de um backend anterior.

    Um run vive num PROCESSO separado. Se o backend reinicia no meio, aquele
    processo morre com ele, mas a linha em `pautador_funnel_runs` fica eterna em
    "escrevendo" — a tela mostra trabalho que não existe, e o disparo passa a
    recusar um novo run por duplicata. Sem reconciliação, o card fica preso.

    Nunca derruba a subida da API: banco fora do ar é problema para a primeira
    requisição resolver, não para impedir o processo de existir.
    """
    try:
        # ⚠️ O import mora DENTRO do `try`, e isso é conserto e não estilo.
        #
        # O docstring acima já promete "nunca derruba a subida da API", mas o
        # import estava fora do bloco: em 27/08/2026, num checkout limpo deste
        # branch, `app.redator` não existe (nunca foi commitado) e o
        # `ModuleNotFoundError` matava o startup INTEIRO, com a API sem subir e
        # a mensagem falando de um módulo de reconciliação opcional.
        #
        # Uma rotina de manutenção de melhor esforço não pode ser pré-requisito
        # da existência do processo.
        from app.redator import worker  # noqa: PLC0415
        from app.services.supabase_service import SupabaseService  # noqa: PLC0415

        supa = SupabaseService(settings)
        if not supa.enabled:
            return
        n = await worker.reconciliar(supa)
        if n:
            log.warning("reconciliei %s run(s) do redator que ficaram órfãos", n)
    except ImportError as exc:
        # `ImportError` e não `ModuleNotFoundError`: um módulo que EXISTE e cujo
        # símbolo sumiu levantava `ImportError` puro, caía no `except Exception`
        # abaixo, virava um WARNING sem registro, e `/health` respondia `ok`
        # sobre uma reconciliação morta. Assimetria medida em 28/08/2026.
        ROTINAS_AUSENTES.append({"rotina": "redator.reconciliar", "motivo": str(exc)[:200]})
        log.error(
            "reconciliação de runs órfãos indisponível: %s. "
            "Runs interrompidos podem ficar presos em 'escrevendo'.",
            str(exc)[:200],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("não consegui reconciliar runs órfãos na subida: %s", str(exc)[:200])


app.include_router(pautador.router)
app.include_router(entities.router)
app.include_router(work_road.router)

# ── router opcional: publicação ──────────────────────────────────────────────
#
# ⚠️ DEFEITO PREEXISTENTE, MEDIDO EM 27/08/2026, NÃO INTRODUZIDO AQUI.
#
# `backend/app/routers/publicacao.py` e `backend/app/seguranca/segredo.py`
# **nunca foram commitados** (`git log --oneline -- <arquivo>` sai vazio nos
# dois), mas o import estava no topo deste arquivo desde o HEAD f4cf128. O
# efeito é que QUALQUER checkout limpo deste branch — CI, clone novo, worktree
# de outra frente — não conseguia nem subir a API, e a mensagem falava de
# `CofreSemChave`, que não ajuda ninguém a descobrir que faltou um `git add`.
#
# A casa já resolveu exatamente este problema uma vez, e a decisão está escrita
# quatro linhas abaixo: o router de Tráfego importa `volc_ads` TARDE porque o
# import no topo "faria o backend inteiro deixar de subir num ambiente sem o
# SDK". O mesmo princípio vale aqui.
#
# O que este bloco NÃO faz é esconder a ausência. A capacidade sumida vira dado:
# ela é registrada, logada como erro e aparece em `/health` como `degradado`.
# Um 404 silencioso numa rota de publicação seria pior que o crash.
# ⚠️ A pergunta é "o ARQUIVO existe?", e não "o import deu erro?".
#
# `find_spec` responde a primeira; o `try/except` sozinho respondia a segunda, e
# as duas são fatos muito diferentes. `ModuleNotFoundError` não serve de teste:
# `from app.routers import publicacao` com o submódulo ausente levanta
# `ImportError` puro, porque `app.routers` É importável e só o nome falta.
#
# Capturar `ImportError` largo era o defeito medido em 28/08/2026: um import
# quebrado DENTRO de `publicacao.py` caía no mesmo ramo que "o arquivo não
# existe". Alguém commita `publicacao.py` e esquece `segredo.py`, a suíte fica
# verde, o deploy sobe, e ~21 rotas de publicação respondem 404 sem nada ficar
# vermelho em lugar nenhum.
#
# Ausência de ambiente é tolerável. Fonte PRESENTE e quebrada é defeito, e
# defeito tolerado vira permanente: por isso este ramo RELEVANTA.
if importlib.util.find_spec("app.routers.publicacao") is None:
    ROUTERS_AUSENTES.append(
        {"router": "publicacao", "motivo": "modulo nao versionado"}
    )
    log.error(
        "router 'publicacao' NÃO foi registrado: o módulo não existe neste "
        "checkout. As rotas de publicação respondem 404 até ele ser versionado."
    )
else:
    # O arquivo está aí: qualquer falha daqui em diante é defeito de verdade e
    # sobe, derrubando a subida como deve.
    from app.routers import publicacao  # noqa: PLC0415

    app.include_router(publicacao.router)
# Hub de Tráfego. O router importa o `volc_ads` TARDE (dentro das rotas), de
# propósito: o pacote puxa o SDK google-ads, e importá-lo aqui faria o backend
# inteiro deixar de subir num ambiente sem o SDK — inclusive Pautador e Redator.
app.include_router(trafego.router)
# Inventário operacional (Fase 1B). `registrar()` inclui DOIS routers com o
# mesmo prefixo: o de sessão (`exigir_usuario`) e o de serviço
# (`exigir_servico`), que o agendador usa. Separados porque a origem da
# credencial muda o que a rota pode fazer, e misturá-los faria o portão de
# serviço virar uma exceção dentro do portão de sessão.
trafego_inventario.registrar(app)
# Estúdio Criativo (C0+C1+C3). O router de produto mantém biblioteca, jobs e
# observação; o router de execução conserva os mesmos paths `/bancada` numa
# fronteira separada. Nenhum dos dois publica em plataforma.
app.include_router(criativos.router)
app.include_router(criativos_execucao.router)


@app.get("/health")
async def health() -> dict:
    return {
        # `degradado` e não `ok`: a API sobe, mas uma capacidade não está lá.
        # Reportar `ok` com um router faltando é a definição de painel que
        # inventa controle.
        "status": "ok" if not (ROUTERS_AUSENTES or ROTINAS_AUSENTES) else "degradado",
        "routers_ausentes": [r["router"] for r in ROUTERS_AUSENTES],
        "rotinas_ausentes": [r["rotina"] for r in ROTINAS_AUSENTES],
        "service": "pautador-pro",
        "version": __version__,
        "engine": settings.resolve_engine(),
        "supabase": settings.has_supabase,
    }


@app.get("/")
async def root() -> dict:
    """Cartão de visita, sem mapa.

    A versão anterior listava dez endpoints do Pautador e apontava para /docs.
    Um índice de rotas numa raiz anônima poupa ao estranho justamente o
    trabalho de descobrir a superfície — e o custo de manter a lista em dia era
    pago por quem a mantinha, não por quem a lia. Quem precisa dela tem o
    código.
    """
    return {
        "service": "Pautador Pro API",
        "version": __version__,
    }
