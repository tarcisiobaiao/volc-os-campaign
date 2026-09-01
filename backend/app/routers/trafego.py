"""Hub de Tráfego — prova multicanal e escrita real restrita.

## A ordem das rotas é a ordem das decisões

    GET  /candidatos/{opportunity_id}   o que existe para virar campanha
    POST /provar                        monta o Brief e roda os juízes
    POST /subir                         cria de verdade

Ela não é acidental. `provar` é pré-requisito ESTRUTURAL de `subir`: o
`preparar()` emite um `Selo` só quando a validação local e o `validate_only`
passam, e `subir()` recusa payload sem selo. A prova deixou de ser uma etapa que
alguém lembra de rodar.

## O que estas rotas fazem de diferente do flow n8n

O flow fazia 13 HTTP em sequência. Se a sétima falhava, sobrava meia campanha na
conta e ninguém sabia. Aqui é um **mutate atômico**: entra tudo ou não entra
nada, e `validate_only` roda contra a conta real antes, de graça.

## Provar não é criar

Search e Display possuem builder e caminho real já registrado. Demand Gen só
entra na porta `validate_only`, atrás de capacidade de servidor desligada por
padrão. O executor, `/subir` e o canário real continuam recusando o canal.

## A trava de escrita não é aberta aqui

`gads/modo.py` é de dois fatores: `destravar()` no código **e**
`FORGE_PERMITIR_ESCRITA=1` no ambiente. Esta rota chama o caminho e deixa o
`EscritaBloqueada` subir com a mensagem inteira — que é informação acionável,
não erro a mascarar. Quem define a variável de ambiente é quem opera o servidor,
deliberadamente, nunca este arquivo.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import pathlib
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

from app.services.supabase_service import SupabaseService
from app.config import get_settings
from app.trafego import (canario, capacidades as cap, escopo, inteligencia_lab,
                         ledger as led, projecao)

log = logging.getLogger("volc.trafego")

from app.seguranca.identidade import Identidade, exigir_admin, exigir_usuario

# ---------------------------------------------------------------------------
# PORTÃO DE IDENTIDADE (fatia 1A.1b — 24/08/2026)
# ---------------------------------------------------------------------------
# `dependencies` no router vale para TODAS as rotas daqui, inclusive as que
# alguém adicionar depois. É a diferença entre uma regra e um hábito: com
# portão por rota, a rota nova nasce aberta e ninguém percebe — foi assim que
# este backend chegou a 64 rotas com zero checagem de identidade.
#
# Rotas administrativas sobem o portão no próprio decorador com
# `dependencies=[Depends(exigir_admin)]`. As duas dependências compõem: o
# `exigir_admin` encadeia `exigir_usuario`, então não há caminho que chegue a
# ADMIN sem antes provar identidade.
#
# O que NÃO passa por aqui: `GET /health` e `GET /` (em main.py) e as rotas de
# documentação do FastAPI, que não são APIRoute e não aceitam Depends — elas
# são tratadas em main.py.
router = APIRouter(prefix="/api/trafego", tags=["trafego"], dependencies=[Depends(exigir_usuario)])

TABELA_RUNS = "pautador_funnel_runs"

# `validate_only` sobe ~72 operações para a API e espera o veredito. Medido no
# `copy/provar.py`, é a chamada mais lenta do fluxo. O teto existe para a tela
# poder explicar a demora em vez de ficar girando: sem ele, um timeout de
# gateway devolveria 504 sem mensagem, e o operador não saberia se a campanha
# subiu ou não (não subiu — `validate_only` nunca cria nada; mas ele não tem
# como saber disso por uma tela em branco).
TIMEOUT_PROVA_S = 120.0

# ⚠️ ESTE NÚMERO FOI MEDIDO, E O PRIMEIRO CHUTE ESTAVA ERRADO.
#
# Medido em 18/08/2026 no card 73: DUAS rodadas de conjunto levaram 174,19 s
# (29.078 tokens de entrada, 34.315 de saída) — o prompt do `PROMPT.md` tem
# ~48 kB e a resposta é o conjunto inteiro. O teto inicial era 180 s: a segunda
# rodada raspou nele, e um card que precisasse de uma terceira teria estourado
# com token já gasto.
#
# `copy/ciclo.TETO_RODADAS` é 8. Oito rodadas de conjunto passariam de 10 min,
# então este teto NÃO cobre o pior caso — ele corta antes, e a mensagem do 504
# diz que houve consumo. Cobrir o pior caso exigiria fila, não uma requisição
# HTTP mais longa.
TIMEOUT_COPY_S = 480.0


# ── laboratório de inteligência sintética ──────────────────────────────────

@router.get("/laboratorio/inteligencia/{scenario_id}")
async def laboratorio_de_inteligencia(scenario_id: str) -> Dict[str, Any]:
    """Replay hermético por cenário, autenticado pelo portão do router.

    O endereço recebe somente `scenario_id`. Identidade real de campanha não é
    aceita e a função não possui porta para Supabase, Google Ads ou n8n.
    """

    try:
        return inteligencia_lab.projetar(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="cenário sintético não encontrado.") from exc


def _fonte_de_reconciliacao() -> Any:
    """A leitura do inventário para a prova de duplicidade.

    Vive atrás de uma função para o router não guardar credencial em módulo — e
    para o teste poder trocar a fonte sem tocar em variável de ambiente.
    """
    from app.config import get_settings as _cfg  # noqa: PLC0415
    from app.trafego import persistencia  # noqa: PLC0415

    cfg = _cfg()
    base = str(getattr(cfg, "supabase_url", "") or "")
    chave = str(getattr(cfg, "supabase_service_role_key", "") or "")
    if not base or not chave:
        raise HTTPException(
            status_code=503,
            detail="sem credencial para ler o inventário; a prova de "
                   "duplicidade não pode ser feita.")
    return persistencia.FonteDeReconciliacao(base, chave)


def _supa() -> SupabaseService:
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(
            status_code=503,
            detail="Supabase não configurado no backend — sem de onde ler os candidatos.",
        )
    return supa


# A raiz do repositório. O backend roda com `cwd=backend` (`uvicorn app.main:app`)
# e o `volc_ads` mora um nível acima, então ele NÃO está no caminho de importação
# daqui. É o espelho exato do que `volc_ads/ponte.py` faz na direção contrária —
# e, como lá, o ajuste fica num lugar só, greppável.
_RAIZ = pathlib.Path(__file__).resolve().parents[3]


def _ledger() -> "led.Ledger":
    """O ledger de lançamento, sobre o MESMO SupabaseService do resto do router.

    Um cliente novo aqui seria o terceiro deste backend, e três clientes com três
    tratamentos de erro diferentes é como uma falha de escrita vira aviso numa
    rota e exceção noutra.
    """
    return led.Ledger(_supa())


def _ponte():
    """Importa o `volc_ads` tarde, e o motivo é operacional.

    O pacote puxa o SDK `google-ads` (grpc, protobuf, oauth). Importá-lo no topo
    faria o backend inteiro deixar de subir num ambiente sem o SDK — inclusive
    as rotas do Pautador e do Redator, que não têm nada a ver com isso.

    ⚠️ AS DUAS CAUSAS DE FALHA SÃO DIFERENTES E A MENSAGEM TEM DE DIZER QUAL.

    A primeira versão disto culpava o SDK em qualquer `ImportError`. Medido: com
    o SDK instalado e funcionando, `/trava` respondia "falta o SDK: pip install
    google-ads" — porque o que faltava era o `volc_ads` no `sys.path`. Um
    diagnóstico que aponta para o lugar errado é pior que nenhum: manda o
    operador reinstalar o que já está lá e esconde o defeito real.
    """
    if str(_RAIZ) not in sys.path:
        sys.path.insert(0, str(_RAIZ))
    try:
        from volc_ads import pautador_ponte as pp
        from volc_ads import subir as sb
        return pp, sb
    except ImportError as exc:  # noqa: BLE001
        faltando = getattr(exc, "name", "") or ""
        if faltando.split(".")[0] in ("google", "grpc", "proto"):
            detalhe = (f"O SDK do Google Ads não está instalado neste servidor "
                       f"({exc}). Instale com `pip install google-ads`.")
        elif faltando.startswith("volc_ads"):
            detalhe = (f"O pacote `volc_ads` não foi encontrado a partir de "
                       f"{_RAIZ} ({exc}). O backend precisa rodar dentro do "
                       f"repositório do Volc OS.")
        else:
            detalhe = f"O engine de tráfego não pôde ser carregado: {exc}"
        raise HTTPException(status_code=503, detail=detalhe) from exc


# ── as contas ───────────────────────────────────────────────────────────────

def _no_escopo(customer_id: Any, login_customer_id: Any) -> tuple[str, str]:
    """O portão da casa, traduzido para HTTP. Não faz rede.

    403 e não 409: não é conflito de estado (isso é a trava, que pode abrir), é
    uma fronteira que não se negocia — a conta pedida não é da casa.
    """
    try:
        return escopo.exigir_escopo(customer_id, login_customer_id)
    except escopo.ForaDoEscopo as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/escopo")
async def escopo_da_casa() -> Any:
    """A árvore de contas em que este sistema pode operar. Somente leitura.

    É o que a aba Integrações consome. A tela NÃO monta essa lista chamando
    `/contas` id a id: seriam 12 idas e voltas para produzir 39 contas
    anunciáveis das quais 36 são de cliente e nenhuma pode ser escolhida.
    """
    _ponte()

    try:
        return await asyncio.to_thread(escopo.mapa)
    except Exception as exc:  # noqa: BLE001
        log.exception("leitura do escopo falhou")
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc


@router.get("/politica/verticais")
async def verticais_e_portoes() -> Any:
    """As verticais e o que cada uma exige, do `policy/spec.json`. Leitura pura.

    ## Por que isto é rota e não constante no front

    O portão de habilitação é o eixo país × vertical do `policy/spec.py` — a
    mesma fonte que REPROVA o payload. Se a tela tivesse a própria cópia da
    lista, ela poderia oferecer uma vertical que o engine desconhece, ou
    esconder um portão que ele aplica. Uma verdade, dois leitores.

    ## Por que o operador precisa escolher isto

    Medido no card 74 em 19/08/2026: a vertical veio `financeiro`, que em BR
    exige `verificacao_servicos_financeiros`, e o portão barrou o lançamento.
    Só que a própria copy diz "este portal apenas explica as regras" — se o
    site não presta o serviço, a vertical é `informativo` e não há portão.
    Essa é uma decisão de fato sobre o negócio, e quem a tem é o operador.
    """
    # ⚠️ `_ponte()` acima já pôs a raiz no `sys.path` — sem ela este import
    # levanta `ModuleNotFoundError: volc_ads`, que foi o que aconteceu na
    # primeira versão desta rota. O import é tarde de propósito: ver `_ponte`.
    _ponte()
    from volc_ads.policy import spec as _spec

    dados = await asyncio.to_thread(_spec.carregar)
    hab = dados.get("habilitacao", {})
    saida = [{
        "id": "informativo",
        "titulo": "Informativo",
        "descricao": "O site explica e compara. Não presta o serviço nem intermedia contratação.",
        "exige": None,
        "severidade": None,
        "paises_exigem": [],
    }]
    for chave, regra in hab.items():
        if chave.startswith("_"):
            continue
        saida.append({
            "id": chave,
            "titulo": chave.replace("_", " ").capitalize(),
            "descricao": regra.get("nota", ""),
            "exige": regra.get("exige"),
            "severidade": regra.get("severidade"),
            "url": regra.get("url"),
            "paises_exigem": regra.get("paises_exigem", []),
        })
    return {"verticais": saida}


@router.get("/contas", dependencies=[Depends(exigir_admin)])
async def listar_contas(mcc: Optional[str] = Query(None, description="um MCC; sem ele, só os ids acessíveis")) -> Any:
    """As contas do Google Ads que a credencial alcança. Somente leitura.

    ## Por que existe

    O cockpit pedia `customer_id` e `login_customer_id` num campo de texto: dois
    números de dez dígitos sem separador, que o operador teria de achar noutro
    lugar e colar. Um dígito errado devolve `USER_PERMISSION_DENIED` — erro que
    não diz "você errou o id".

    Sem `mcc`, devolve os ids que `ListAccessibleCustomers` alcança (ele não dá
    nome nem hierarquia). Com `mcc`, devolve as contas sob ele, com nome, moeda
    e o que é manager.

    ⚠️ Esta rota NÃO passa pelo portão de `escopo.py`, e é a única assim. Ela é
    o diagnóstico que MEDIU o problema — foi por ela que se descobriu que a
    credencial alcança 39 contas anunciáveis e só 3 são da casa. Fechá-la
    tiraria a capacidade de medir isso de novo, e ela não leva a operação
    nenhuma: quem monta o seletor é `/escopo`, e quem recebe `customer_id` para
    operar (`/projetos/{id}/conta`, `/provar`, `/subir`) recusa fora da casa.
    A linha é entre OLHAR e OPERAR.
    """
    _ponte()
    from app.trafego import contas as ct

    def _ler():
        if mcc:
            return ct.descobrir(mcc)
        return {"acessiveis": ct.acessiveis()}

    try:
        return await asyncio.to_thread(_ler)
    except Exception as exc:  # noqa: BLE001
        log.exception("descoberta de contas falhou")
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc


class ContaDoProjeto(BaseModel):
    """⚠️ Escreve em `projects`, que é NOSSA tabela — não em conta de terceiro.

    A distinção importa: a trava de `gads/modo.py` protege escrita na API do
    Google. Guardar em qual conta um projeto anuncia é registro do nosso lado,
    e é o que faz o cockpit parar de perguntar.

    `google_ads_manager_id` continua no corpo mesmo tendo um valor só possível
    (o MCC da casa): é ele que o portão confere. Um cliente que mandar outro MCC
    tem de ser RECUSADO, não silenciosamente corrigido — corrigir esconderia
    que alguém tentou operar fora da casa.
    """
    google_ads_customer_id: str
    google_ads_manager_id: str


@router.put("/projetos/{project_id}/conta", dependencies=[Depends(exigir_admin)])
async def vincular_conta(project_id: int, body: ContaDoProjeto = Body(...)) -> Any:
    """Liga um projeto à conta de anúncios onde ele veicula.

    As colunas já existiam em `projects` (`google_ads_customer_id`,
    `google_ads_manager_id`) e estavam vazias. O funil já carrega `project_id`,
    então preencher isto é o que permite ao cockpit derivar a conta.

    ## Esta rota confere a conta contra a árvore, e as outras não

    Aqui o operador ESCOLHE, e uma escolha errada tem de falhar agora, dizendo
    o quê — não daqui a três telas com `USER_PERMISSION_DENIED`. Custa a leitura
    da árvore (~1,6 s medido em 18/08/2026). `/provar` e `/subir` só repassam o
    que já foi escolhido, então neles basta o portão sem rede.

    ## `google_ads_status` NÃO é escrita aqui

    ⚠️ Essa coluna é do webgo: `supabaseDataService.ts` a lê como
    `=== 'connected'` para acender "Google Ads conectado" no card do projeto, e
    lá isso significa que a INGESTÃO DE GASTO está funcionando. Gravar
    'connected' ao vincular acendia esse selo sem nada ter sido sincronizado. A
    verdade do vínculo são os dois ids — é o que `/candidatos` já consulta.
    """
    # O portão vem ANTES de tocar o Supabase, e de propósito: recusar conta de
    # terceiro não pode depender de o banco estar de pé. Com a ordem invertida,
    # um Supabase fora do ar devolveria 503 para uma tentativa que deveria ser
    # 403 — e o registro do servidor não teria a recusa.
    cid, mid = _no_escopo(body.google_ads_customer_id, body.google_ads_manager_id)

    supa = _supa()
    linhas = await supa.select("projects", {"id": f"eq.{project_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

    try:
        conta = await asyncio.to_thread(escopo.conta_da_casa, cid)
    except escopo.ForaDoEscopo as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("conferência da conta %s contra a árvore da casa falhou", cid)
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc

    await supa.patch("projects", {"id": f"eq.{project_id}"}, {
        "google_ads_customer_id": cid,
        "google_ads_manager_id": mid,
    })
    return {"vinculado": True, "project_id": project_id,
            "google_ads_customer_id": cid, "google_ads_manager_id": mid,
            "conta": conta}


@router.delete("/projetos/{project_id}/conta", dependencies=[Depends(exigir_admin)])
async def desvincular_conta(project_id: int) -> Any:
    """Desfaz o vínculo. Existe porque o `PUT` não consegue desfazê-lo.

    O portão recusa id vazio — é o que impede o hífen e o campo em branco de
    chegarem à API. O efeito colateral é que "apagar mandando string vazia"
    deixou de funcionar, e sem esta rota um vínculo errado só sairia por SQL.
    """
    supa = _supa()
    linhas = await supa.select("projects", {"id": f"eq.{project_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")

    # NULO, não string vazia: `/candidatos` decide por `bool(cid and mid)`, e
    # `""` passaria como "tem coluna, está falso" — mesmo desfecho por acidente.
    await supa.patch("projects", {"id": f"eq.{project_id}"}, {
        "google_ads_customer_id": None,
        "google_ads_manager_id": None,
    })
    return {"vinculado": False, "project_id": project_id}


@router.get("/projetos")
async def projetos_com_conta() -> Any:
    """Os projetos e a conta de anúncios de cada um — o que a aba Integrações
    edita e o que o cockpit consome.

    ⚠️ `vinculada` vem dos DOIS IDS, nunca de `google_ads_status`. Essa coluna é
    do webgo e significa outra coisa lá (ingestão de gasto); medido em
    18/08/2026, o projeto 1 está `'connected'` com os dois ids NULOS. Quem
    acreditar nela mostra conta vinculada onde não há nenhuma.

    A derivação sai daqui e não da tela porque `/candidatos` já decide pela
    mesma regra — a invariante existe uma vez, no servidor.
    """
    supa = _supa()
    linhas = await supa.select("projects", {"order": "id", "limit": 200})
    saida = []
    for p in linhas:
        cid, mid = p.get("google_ads_customer_id"), p.get("google_ads_manager_id")
        saida.append({
            "id": int(p["id"]),
            "dominio": p.get("domain") or "",
            "nome": p.get("project_name") or p.get("domain") or f"projeto {p['id']}",
            "google_ads_customer_id": cid,
            "google_ads_manager_id": mid,
            "vinculada": bool(cid and mid),
            # Repassado porque o painel do webgo o exibe, e sumir com ele daqui
            # esconderia a divergência em vez de resolvê-la.
            "google_ads_status": p.get("google_ads_status") or "UNKNOWN",
        })
    return {"projetos": saida}


# ── o quadro ────────────────────────────────────────────────────────────────

@router.get("/quadro")
async def quadro() -> Any:
    """Onde cada campanha está no ciclo.

    A primeira coluna é a que gera trabalho, e ela NÃO vem da tabela de
    campanhas: são os funis do Redator que já publicaram página E têm cluster de
    keywords no Pautador. Sem ela, montar uma campanha exige saber de cor um
    `opportunity_id` — e quem abriu o Hub para trabalhar não tem por onde
    começar.

    ⚠️ Não há coluna de performance, e isso é decisão de fato: `metrics.` tem
    zero ocorrências no `volc_ads`. Uma coluna com ROAS seria desenhada, não
    medida.
    """
    supa = _supa()

    runs = await supa.select(TABELA_RUNS, {"order": "criado_em.desc", "limit": 100})
    clusters = await supa.select("pautador_keyword_clusters",
                                 {"select": "id,opportunity_id,total_volume,main_keyword,"
                                            "production_ads_queue,summary,services_used",
                                  "limit": 200})
    cards = await supa.select("pautador_entity_opportunities",
                              {"order": "updated_at.desc", "limit": 200})
    projetos = await supa.select("project_wordpress", {"limit": 100})
    entidades = await supa.select("pautador_entities", {"limit": 300})

    # ⚠️ A coluna é `wp_url`. `wp_base_url` não existe, e como `.get` devolve
    # `None` em silêncio o domínio saía vazio em toda linha sem nenhum erro —
    # defeito que já aconteceu no quadro do Redator.
    dominio = {int(p["project_id"]): (p.get("wp_url") or "")
               .replace("https://", "").replace("http://", "").rstrip("/")
               for p in projetos}
    nome_entidade = {int(e["id"]): (e.get("canonical_name") or e.get("full_name") or "")
                     for e in entidades}
    por_oportunidade = {int(c["opportunity_id"]): c
                        for c in clusters if c.get("opportunity_id")}

    def titulo(card: Dict[str, Any]) -> str:
        """`display_title` está NULO em todos os cards de hoje — a cadeia de
        recuo importa mais que o campo preferido."""
        if card.get("display_title"):
            return str(card["display_title"])
        ent = nome_entidade.get(int(card.get("entity_id") or 0), "")
        if ent:
            return ent
        paginas = ((card.get("funnel_architecture") or {}).get("pages") or [])
        if paginas and paginas[0].get("h1_title"):
            return str(paginas[0]["h1_title"])
        return f"card #{card['id']}"

    titulos = {int(c["id"]): titulo(c) for c in cards}

    prontos: List[Dict[str, Any]] = []
    for r in runs:
        # Um funil só é candidato a campanha se publicou alguma página: sem URL
        # no ar, não há para onde mandar o clique.
        publicadas = r.get("paginas_publicadas") or []
        if r.get("status") != "done" or not publicadas:
            continue
        oid = int(r["opportunity_id"])
        cluster = por_oportunidade.get(oid)
        fila = (cluster or {}).get("production_ads_queue") or []
        # As URLs REAIS das páginas publicadas, e não só quantas são. A
        # reconciliação compara destino: `lp_url` é cópia desnormalizada e pode
        # divergir da página que de fato foi ao ar.
        urls_publicadas = tuple(
            str(pg.get("url_wp") or "") for pg in publicadas
            if isinstance(pg, dict) and pg.get("url_wp"))
        prontos.append({
            "opportunity_id": oid,
            "run_id": int(r["id"]),
            "project_id": (int(r["project_id"])
                           if r.get("project_id") is not None else None),
            "urls_publicadas": list(urls_publicadas),
            "titulo": titulos.get(oid, f"card #{oid}"),
            # ⚠️ `project_id` PODE ser nulo. Um run sem projeto entra no quadro
            # como qualquer outro, e `int(None)` derrubava a rota inteira com um
            # TypeError — 500 no lugar de um domínio vazio.
            "dominio": (dominio.get(int(r["project_id"]), "")
                        if r.get("project_id") is not None else ""),
            "lp_url": r.get("lp_url"),
            "paginas_publicadas": len(publicadas),
            # O que decide "vale a pena abrir?" sem precisar abrir.
            "tem_cluster": cluster is not None,
            "keywords_para_anuncio": len(fila),
            "volume_total": (cluster or {}).get("total_volume"),
            # A procedência viaja junto desde o quadro. Um número de CPC ou de
            # volume sem ela é o defeito que esta entrega inteira existe para
            # não cometer.
            "servicos_declarados": (cluster or {}).get("services_used") or [],
            # Preenchido logo abaixo, numa consulta só para todos os runs.
            "campanhas_lancadas": 0,
        })

    # ── a reconciliação: "este funil já tem campanha?" ─────────────────────
    #
    # ⚠️ A pergunta MUDOU. Ela era "há linha no nosso cadastro com este
    # `funnel_run_id`?" e passou a ser "há, na conta deste projeto, campanha que
    # aponte para o destino deste funil?".
    #
    # A troca não é de implementação, é de AUTORIDADE. `campaigns` só conhece o
    # que nasceu pela porta `/subir`: medido em 26/08/2026, ela tem quatro
    # linhas e só uma com `funnel_run_id`. As campanhas que a conta mostra
    # ENABLED e gastando agora não estavam lá — e o quadro respondia zero e
    # oferecia "montar campanha" para um funil que já tem campanha no ar. Duas
    # campanhas do mesmo termo, na mesma conta, disputam o mesmo leilão com
    # verba de verdade; cada uma encarece a outra.
    #
    # A tabela legada não some: ela vira UM SINAL entre outros, com a força de
    # uma declaração nossa — e a conta de anúncio passa a ser a autoridade
    # (ADR-01).
    runs = [p["run_id"] for p in prontos]
    reconciliacoes = await _reconciliar_o_quadro(supa, prontos, projetos, runs)
    for p_ in prontos:
        r = reconciliacoes.get(_rec_chave(p_))
        if r is None:
            # Sem prova não há veredito. `campanhas_lancadas` fica NULO — e
            # nulo não é zero: zero afirmaria "não há campanha", que é
            # exatamente o que não foi apurado.
            p_["reconciliacao"] = None
            p_["campanhas_lancadas"] = None
            continue
        p_["reconciliacao"] = r.json()
        # Compatibilidade declarada: quem ainda lê `campanhas_lancadas` recebe
        # quantas candidatas PRESENTES existem. O campo continua verdadeiro; ele
        # só deixou de ser a autoridade.
        p_["campanhas_lancadas"] = sum(1 for c in r.candidatas if c.presente)

    return {
        "prontos": prontos,
        "totais": {
            "funis_publicados": len(prontos),
            "com_cluster": sum(1 for p in prontos if p["tem_cluster"]),
            "keywords_disponiveis": sum(p["keywords_para_anuncio"] for p in prontos),
        },
        # Dito na resposta, não só na tela: quem consumir esta rota não deve
        # procurar métrica de performance aqui.
        "sem_metrica": True,
        "por_que": "Não existe camada de métrica no engine (`metrics.` = 0 "
                   "ocorrências). Performance viria do Google Ads e do GAM, e "
                   "nenhum dos dois está ligado.",
    }


def _rec_chave(cartao: Dict[str, Any]) -> Any:
    """A chave do cartão na tabela de vereditos: `(oportunidade, run)`.

    Uma oportunidade pode ter mais de um run, e os dois viram cartões distintos.
    Chavear só pela oportunidade faria um receber o veredito do outro.
    """
    from app.trafego import reconciliacao as rec  # noqa: PLC0415

    return rec.chave_do_funil(cartao["opportunity_id"], cartao.get("run_id"))


async def _reconciliar_o_quadro(
        supa: Any, prontos: List[Dict[str, Any]],
        projetos: List[Dict[str, Any]], runs: List[int],
) -> Dict[int, Any]:
    """A prova somente-leitura para todos os funis do quadro, de uma vez.

    Três consultas, e nenhuma por cartão: a conta de cada projeto, o universo de
    campanhas dessas contas, e a tabela legada. Consultar por linha custaria N
    idas ao banco numa tela que existe para ser rápida — e é assim que uma
    consulta escondida por cartão aparece antes de alguém somar.

    Falha de leitura devolve `{}`, e o chamador transforma isso em veredito
    NULO. Não em `sem_campanha`: "não consegui provar" e "provei e não há" são
    coisas diferentes, e só a segunda pode liberar a montagem.
    """
    from app.trafego import reconciliacao as rec  # noqa: PLC0415

    if not prontos:
        return {}

    try:
        # 1 · a conta de anúncio de cada projeto. É PRÉ-REQUISITO da prova
        #     (ADR-03): sem conta não há onde procurar, e comparar URL entre
        #     contas diferentes casaria o funil de um cliente com a campanha de
        #     outro.
        # ⚠️ Só os projetos que ESTES cartões citam, e não "os 200 primeiros".
        #
        # Um teto silencioso aqui falha na direção errada: o projeto que cair
        # fora do lote perde a conta, o funil dele vira `sem_campanha` e a tela
        # oferece montar — numa requisição sim, na seguinte não, sem nada mudar
        # no banco. `in.(…)` pede exatamente o que se precisa e não tem teto
        # para estourar em silêncio.
        alvos = sorted({int(p["project_id"]) for p in prontos
                        if p.get("project_id") is not None})
        if not alvos:
            return {}
        linhas_projeto = await supa.select("projects", {
            "select": "id,google_ads_customer_id",
            "id": f"in.({','.join(str(a) for a in alvos)})"})
        conta_do_projeto = {
            int(l["id"]): str(l.get("google_ads_customer_id") or "").strip()
            for l in (linhas_projeto or []) if l.get("id") is not None}

        contas = sorted({c for c in conta_do_projeto.values() if c})
        if not contas:
            return {}

        # 2 · o universo de campanhas dessas contas, do INVENTÁRIO — não do
        #     cadastro legado. Inclui as históricas: sem elas, "não há campanha"
        #     e "há, e foi removida" responderiam a mesma coisa, e a primeira
        #     libera a montagem enquanto a segunda pede relançamento declarado.
        fonte = _fonte_de_reconciliacao()
        universo = [
            rec.CampanhaConhecida(
                volc_campaign_id=str(l.get("volc_campaign_id") or ""),
                campaign_id=str(l.get("campaign_id") or ""),
                customer_id=(str(l["customer_id"])
                             if l.get("customer_id") else None),
                nome=str(l.get("nome") or ""),
                estado_externo=l.get("estado_externo"),
                canal=l.get("canal"),
                historico=bool(l.get("historico")),
                url_final=l.get("url_final"),
                lido_em=(str(l["lido_em"]) if l.get("lido_em") else None),
                campaign_lineage_id=(str(l["campaign_lineage_id"])
                                     if l.get("campaign_lineage_id") else None),
                vinculo_id=(str(l["vinculo_id"]) if l.get("vinculo_id") else None),
                vinculo_opportunity_id=(int(l["opportunity_id"])
                                        if l.get("opportunity_id") is not None
                                        else None),
                vinculo_run_id=(int(l["funnel_run_id"])
                                if l.get("funnel_run_id") is not None else None),
            )
            for l in await fonte.campanhas_conhecidas(contas)
        ]

        # 3 · a tabela legada, agora como SINAL e não como autoridade.
        legado_por_run: Dict[int, set] = {}
        if runs:
            for l in (await supa.select("campaigns", {
                    "funnel_run_id": f"in.({','.join(str(r) for r in runs)})",
                    "select": "funnel_run_id,campaign_id"}) or []):
                rid, cid = l.get("funnel_run_id"), l.get("campaign_id")
                if rid is not None and cid:
                    legado_por_run.setdefault(int(rid), set()).add(str(cid))

        funis = []
        for p in prontos:
            projeto = p.get("project_id")
            paginas = p.get("urls_publicadas") or ()
            funis.append(rec.Funil(
                opportunity_id=int(p["opportunity_id"]),
                run_id=int(p["run_id"]) if p.get("run_id") is not None else None,
                project_id=int(projeto) if projeto is not None else None,
                customer_id=(conta_do_projeto.get(int(projeto))
                             if projeto is not None else None) or None,
                lp_url=p.get("lp_url"),
                urls_publicadas=tuple(paginas),
            ))
        return rec.reconciliar_muitos(funis, universo,
                                      legado_por_run=legado_por_run)
    except Exception:  # noqa: BLE001
        log.warning("a reconciliação do quadro não pôde ser feita", exc_info=True)
        return {}


# ── os candidatos ───────────────────────────────────────────────────────────

async def _campanhas_lancadas(supa: Any, run_id: Optional[int],
                              opportunity_id: int) -> List[Dict[str, Any]]:
    """As campanhas que ESTE funil já produziu. Vazio quando nenhuma.

    ⚠️ Sem isto o cockpit oferecia "lançar campanha" mesmo depois de lançar —
    ele não tinha como saber. O operador relançava sem perceber, e a conta
    ganhava duas campanhas para o mesmo termo, contra a doutrina P7
    (um termo, uma campanha).

    Filtra por `funnel_run_id`, que é a coluna que `/subir` passou a gravar.
    `REMOVED` não conta: uma campanha removida não impede lançar de novo — foi
    exatamente o que o operador fez em 19/08/2026.
    """
    if run_id is None:
        return []
    try:
        linhas = await supa.select("campaigns", {
            "funnel_run_id": f"eq.{run_id}",
            "select": "campaign_id,campaign_name,status,google_ads_status,"
                      "customer_id,budget_amount,created_at",
            "order": "created_at.desc",
        })
    except Exception:  # noqa: BLE001
        # O cockpit não pode cair porque a consulta de histórico falhou.
        return []
    return [l for l in (linhas or [])
            if str(l.get("google_ads_status") or "").upper() != "REMOVED"]


@router.get("/candidatos/{opportunity_id}")
async def candidatos(
    opportunity_id: int,
    run_id: Optional[int] = Query(None, description="funil específico; o padrão é o mais recente"),
    com_texto_da_lp: bool = Query(False, description="inclui o artigo inteiro da LP"),
) -> Any:
    """O cockpit: o que o funil e a mineração já entregam para virar campanha.

    ⚠️ `com_texto_da_lp` é `False` por padrão porque o texto é o artigo inteiro —
    dezenas de kB num payload que a tela pede a cada abertura. Ele só viaja
    quando alguém vai cruzar anúncio × página, e aí viaja inteiro: comparar
    contra um resumo produziria falso negativo justamente no caso que importa.
    """
    pp, _ = _ponte()

    # A ponte é síncrona e faz I/O (Supabase + disco). Rodá-la direto no laço de
    # eventos travaria o servidor inteiro durante a leitura.
    def _carregar():
        return pp.montar_cockpit(pp.carregar(opportunity_id, run_id=run_id))

    try:
        cockpit = await asyncio.to_thread(_carregar)
    except pp.PonteIncompleta as exc:
        # Não é 500: é configuração ausente, e a mensagem da ponte já diz qual.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("cockpit do card %s explodiu", opportunity_id)
        raise HTTPException(status_code=500, detail=str(exc)[:400]) from exc

    saida = projecao.cockpit(cockpit, com_texto_da_lp=com_texto_da_lp)

    # A CONTA VEM DO PROJETO, não do operador.
    #
    # `pautador_funnel_runs` carrega `project_id` e `projects` guarda
    # `google_ads_customer_id` e `google_ads_manager_id`. O funil já sabia em
    # que conta a campanha ia entrar; a tela é que perguntava — dois números de
    # dez dígitos sem separador, e um dígito errado devolve
    # `USER_PERMISSION_DENIED`, que não diz "você errou o id".
    #
    # Projeto sem conta vinculada devolve `conta: null` com o motivo. A tela
    # manda para Integrações em vez de abrir um campo de texto.
    # ⚠️ A conta é ENFEITE em relação ao cockpit: sem ela a tela ainda mostra
    # origem, keywords e triagem, e manda o operador a Integrações. Por isso a
    # leitura fica isolada num try — a primeira versão chamava `_supa()` no topo
    # da rota e derrubava o cockpit INTEIRO com 503 quando a configuração do
    # Supabase não estava disponível, mesmo com a ponte lendo o `.env` do disco
    # por conta própria. Sete testes passaram a pular por causa disso.
    # O que este funil JÁ lançou. Isolado num try pela mesma razão da conta: o
    # cockpit não pode cair porque a consulta de histórico falhou.
    saida["campanhas_lancadas"] = []
    try:
        saida["campanhas_lancadas"] = await _campanhas_lancadas(
            _supa(), run_id, opportunity_id)
    except Exception:  # noqa: BLE001
        log.warning("não consegui ler as campanhas já lançadas do run %s", run_id)

    pid = (cockpit.origem.project_id if cockpit.origem else None)
    saida["conta"] = None
    if pid:
      try:
        proj = await _supa().select("projects", {"id": f"eq.{pid}", "limit": 1})
        p = proj[0] if proj else {}
        cid, mid = p.get("google_ads_customer_id"), p.get("google_ads_manager_id")
        saida["conta"] = {
            "project_id": int(pid),
            "dominio": p.get("domain") or "",
            "customer_id": cid,
            "login_customer_id": mid,
            "vinculada": bool(cid and mid),
            "motivo": None if (cid and mid) else
                      "Este projeto ainda não tem conta do Google Ads vinculada. "
                      "Vincule em Integrações — o cockpit não pede o número à mão.",
        }

        # O QUE A CAMPANHA VAI FAZER, ANTES DE ALGUÉM MONTÁ-LA.
        #
        # Moeda e fuso MUDAM o payload: o fuso decide a que hora o dia do
        # orçamento vira, e a moeda é a unidade do lance que o operador digita.
        # A meta de conversão decide o que o `maximize_conversions` persegue.
        # Nada disso aparecia em lugar nenhum da tela — o operador montava 20
        # minutos de campanha e só descobria dentro do overlay de lançamento.
        #
        # ⚠️ Isolado num try próprio: são DUAS chamadas à API do Google (~2 s),
        # e nenhuma delas é essencial ao cockpit. Derrubar a tela inteira por
        # causa de um detalhe de conta seria o mesmo defeito que já custou sete
        # testes quando `_supa()` ficava no topo da rota.
        if cid and mid:
            def _detalhes():
                from app.trafego import contas as ct
                return (ct.detalhe(cid, login_customer_id=mid),
                        ct.meta_de_conversao(cid, login_customer_id=mid))
            try:
                det, meta = await asyncio.to_thread(_detalhes)
                saida["conta"].update({
                    "nome": det.get("nome"),
                    "moeda": det.get("moeda"),
                    "fuso": det.get("fuso"),
                    "teste": det.get("teste"),
                    # ⚠️ Item que estava LIDO E NÃO CONSUMIDO desde o início:
                    # `marcacao.py` recusa `marcacao_gclid=True` quando o
                    # auto-tagging da conta está ligado, porque o Google já
                    # anexa o gclid e declarar a macro duplica o parâmetro.
                    # Medido na Crédito Up: `True`.
                    "auto_tagging": det.get("auto_tagging"),
                    "meta_conversao": meta,
                })
            except Exception as exc:  # noqa: BLE001
                log.warning("detalhes da conta %s indisponíveis: %s", cid, exc)
                saida["conta"]["detalhes_indisponiveis"] = str(exc)[:200]
      except HTTPException:
        saida["conta"] = {"project_id": int(pid), "dominio": "", "customer_id": None,
                          "login_customer_id": None, "vinculada": False,
                          "motivo": "Não consegui ler o projeto para descobrir a conta."}
    return saida


# ── a copy ──────────────────────────────────────────────────────────────────

class CopyPedido(BaseModel):
    """O estágio 3, que existia no engine e não existia em lugar nenhum na tela.

    `keywords` são as SELECIONADAS, achatadas. A copy é escrita contra o que vai
    de fato para o anúncio — escrevê-la contra a fila inteira produziria título
    ancorado em termo que o operador desmarcou.
    """
    opportunity_id: int
    run_id: Optional[int] = None
    keywords: List[str] = Field(default_factory=list)
    # O que a CONTA comprovadamente tem. Vazio restringe mais, e errar para o
    # lado restritivo custa copy mais pobre; errar para o outro custa anúncio
    # reprovado por política numa vertical regulada.
    certificacoes: List[str] = Field(default_factory=list)
    match_type: str = "PHRASE"
    url_final: Optional[str] = None
    # A vertical escolhida no portão de política. `None` herda a da entidade.
    # Sem ela, a copy era escrita com as regras de uma vertical e o payload
    # provado com as de outra.
    vertical: Optional[str] = None
    # ⚠️ Não existe modelo MEDIDO para copy nesta operação. Este campo existe
    # para PODER comparar — rodar o mesmo card em modelos diferentes e olhar o
    # resultado lado a lado é a única forma honesta de escolher um.
    # `None` usa o do ambiente.
    modelo: Optional[str] = None


TABELA_COPY = "pautador_trafego_copy"

# Referência forte para as tarefas de escrita em andamento. Sem isto o asyncio
# pode coletar a task no meio de uma geração de ~174 s — a linha ficaria
# `running` para sempre e os tokens já estariam gastos. Mesmo cuidado que
# `routers/publicacao.py` documenta para os runs do Redator.
_ESCRITAS: set = set()


def _copy_para_tela(linha: Dict[str, Any]) -> Dict[str, Any]:
    """A linha do banco projetada, com o veredito de PERDIDA já calculado.

    ⚠️ `status='running'` NÃO PROVA QUE ALGO ESTÁ RODANDO.

    A tarefa vive dentro do processo do backend. Um reinício — e em
    desenvolvimento o `--reload` reinicia a cada arquivo salvo — mata a tarefa e
    deixa a linha `running` para sempre. Uma tela que confia no status fica
    girando um cronômetro eterno, e o operador espera por algo que morreu.
    """
    from datetime import datetime, timezone

    status = str(linha.get("status") or "")
    atualizado = linha.get("atualizado_em")
    perdida = False
    if status == "running" and atualizado:
        try:
            quando = datetime.fromisoformat(str(atualizado))
            idade = (datetime.now(timezone.utc) - quando).total_seconds()
            # Passou do teto da própria rota: ninguém está mais escrevendo isto.
            perdida = idade > TIMEOUT_COPY_S
        except ValueError:
            perdida = False

    return {
        "existe": True,
        "status": status,
        "perdida": perdida,
        "opportunity_id": linha.get("opportunity_id"),
        "run_id": linha.get("run_id"),
        # As keywords para as quais este texto foi escrito. A tela compara com a
        # seleção atual — sem isso, uma copy ancorada em termos desmarcados
        # parece perfeitamente válida e só falha no leilão.
        "keywords": linha.get("keywords") or [],
        # A vertical declarada quando esta copy foi escrita. A tela repõe o
        # portão com ela em vez de voltar ao inferido — que é o que fazia a
        # escolha do operador sumir no refresh.
        "vertical": linha.get("vertical"),
        "certificacoes": linha.get("certificacoes") or [],
        "copy": linha.get("copy"),
        "medicao": linha.get("medicao") or {},
        "pendentes": _pendencias(linha.get("pendentes") or []),
        "diario": linha.get("diario") or [],
        "fatos_usados": linha.get("fatos_usados") or 0,
        "fatos_descartados": linha.get("fatos_descartados") or [],
        "aceita": linha.get("aceita"),
        "segundos": float(linha["segundos"]) if linha.get("segundos") is not None else 0.0,
        "erro": linha.get("erro"),
        "criado_em": linha.get("criado_em"),
        "atualizado_em": linha.get("atualizado_em"),
    }


def _pendencias(cruas: List[Any]) -> List[Dict[str, Any]]:
    """Normaliza a pendência, tolerando as linhas gravadas ANTES da estrutura.

    ⚠️ Até 18/08/2026 cada pendência era uma FRASE (`str(Achado)`), e a tela
    mostrava as seis primeiras dizendo "não impedem lançar". Medido no card 74:
    das 10, seis eram contabilidade do modelo e quatro eram o anúncio errado —
    inclusive uma descrição de 91 caracteres num teto de 90, que o Google
    recusa. A frase tranquilizadora era falsa exatamente sobre o que o corte
    escondia.

    Agora a pendência viaja com `classe`. As linhas antigas continuam no banco,
    e converter aqui evita que a tela renderize `undefined` em cima delas — que
    seria trocar um defeito de informação por um defeito de render.
    """
    saida: List[Dict[str, Any]] = []
    for p in cruas:
        if isinstance(p, dict):
            saida.append(p)
            continue
        texto = str(p)
        # `[classe] codigo @alvo: detalhe` — o formato de `Achado.__str__`.
        m = re.match(r"^\[([a-z_]+)\]\s+(\S+?)(?:\s+@(\S+?))?:\s*(.*)$", texto)
        if m:
            saida.append({"classe": m.group(1), "codigo": m.group(2),
                          "alvo": m.group(3), "detalhe": m.group(4), "texto": texto})
        else:
            saida.append({"classe": "", "codigo": "", "alvo": None,
                          "detalhe": texto, "texto": texto})
    return saida


async def _linha_de_copy(supa: SupabaseService, opportunity_id: int,
                         run_id: Optional[int]) -> Optional[Dict[str, Any]]:
    filtro: Dict[str, Any] = {"opportunity_id": f"eq.{opportunity_id}", "limit": 1}
    filtro["run_id"] = f"eq.{run_id}" if run_id is not None else "is.null"
    linhas = await supa.select(TABELA_COPY, filtro)
    return linhas[0] if linhas else None


@router.get("/copy/{opportunity_id}")
async def ler_copy(opportunity_id: int,
                   run_id: Optional[int] = Query(None)) -> Any:
    """A copy já escrita para este card, se existir.

    O cockpit chama isto AO ABRIR. É o que faz sair da página e voltar não
    jogar fora ~174 s de LLM pago.
    """
    supa = _supa()
    linha = await _linha_de_copy(supa, opportunity_id, run_id)
    if linha is None:
        return {"existe": False}
    return _copy_para_tela(linha)


async def _escrever_em_segundo_plano(linha_id: int, body: "CopyPedido") -> None:
    """Roda a cascata e grava o desfecho na linha. Nunca levanta.

    Qualquer exceção que escapasse daqui mataria a task em silêncio e deixaria a
    linha `running` — que é exatamente o estado mentiroso que esta tabela existe
    para evitar.
    """
    from datetime import datetime, timezone

    supa = SupabaseService(get_settings())

    def _fim(campos: Dict[str, Any]) -> Dict[str, Any]:
        return {**campos, "atualizado_em": datetime.now(timezone.utc).isoformat()}

    try:
        pp, _ = _ponte()

        def _escrever():
            from volc_ads.copy import encomendar as enc

            cockpit = pp.montar_cockpit(pp.carregar(body.opportunity_id, run_id=body.run_id))
            return enc.escrever(
                cockpit, keywords=body.keywords, certificacoes=body.certificacoes,
                match_type=body.match_type, url_final=body.url_final,
                vertical=body.vertical, modelo=body.modelo,
            )

        escrita = await asyncio.wait_for(
            asyncio.to_thread(_escrever), timeout=TIMEOUT_COPY_S)
    except asyncio.TimeoutError:
        await supa.patch(TABELA_COPY, {"id": f"eq.{linha_id}"}, _fim({
            "status": "error",
            "erro": (f"A escrita passou de {int(TIMEOUT_COPY_S)}s e foi encerrada. "
                     f"Houve consumo de token nas rodadas que rodaram."),
        }))
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("escrita de copy do card %s explodiu", body.opportunity_id)
        # ⚠️ O ERRO PRECISA DIZER ONDE FOI.
        #
        # Antes daqui saía só `str(exc)`, e a tela mostrava
        # "RemoteProtocolError: Server disconnected without sending a response."
        # — uma frase sem lugar nenhum. Com ela eu diagnostiquei errado DUAS
        # vezes em 19/08/2026: apostei no transporte do Gemini (que respondia
        # 200 em 2,7 s) e depois no modelo escolhido na tela (os três
        # respondiam 200). O traceback estava no log do uvicorn, num terminal
        # que ninguém lê, e a linha do banco — que é o que a tela mostra e o
        # que sobrevive ao reinício — guardava só o rótulo.
        #
        # As últimas molduras bastam: elas dizem o ARQUIVO e a LINHA. É a
        # diferença entre consertar e adivinhar.
        import traceback as _tb

        molduras = _tb.format_exception(type(exc), exc, exc.__traceback__)
        onde = "".join(molduras[-6:]).strip()
        await supa.patch(TABELA_COPY, {"id": f"eq.{linha_id}"}, _fim({
            "status": "error", "erro": f"{exc}\n\n{onde}"[:2000],
        }))
        return

    projetada = projecao.escrita(escrita)
    await supa.patch(TABELA_COPY, {"id": f"eq.{linha_id}"}, _fim({
        "status": "done",
        "copy": projetada["copy"],
        "medicao": projetada["medicao"],
        "pendentes": projetada["pendentes"],
        "diario": projetada["diario"],
        "fatos_usados": projetada["fatos_usados"],
        "fatos_descartados": projetada["fatos_descartados"],
        "aceita": projetada["aceita"],
        "segundos": projetada["segundos"],
        "erro": None,
    }))


@router.post("/copy")
async def escrever_copy(body: CopyPedido = Body(...)) -> Any:
    """Escreve a copy do anúncio com a cascata de `volc_ads/copy`.

    ## Por que ela vem ANTES do lançamento, e não dentro dele

    A copy é o que o anúncio DIZ. Gerá-la dentro do lançamento faria o operador
    descobrir o texto depois de a campanha existir — pausada, mas existindo, e
    o conserto passaria a ser no painel do Google. Aqui ele lê e edita antes.

    ## Esta rota não fala com o Google

    A cascata roda com o juiz do contrato (determinístico, local, 5 classes) e
    com o juiz do Google NULO — ver o cabeçalho de `copy/encomendar.py`. O
    Google julga esta copy uma linha depois, em `/provar`, dentro do payload
    inteiro da campanha, que é o que vai ser criado de verdade.

    ⚠️ Ela GASTA: cada rodada é uma chamada de LLM paga. `medicao` traz tokens,
    latência e custo por papel — e `custo` vem `None` quando o preço do modelo
    não está configurado, porque `copy/cliente.py` não inventa preço.

    ## Ela DEVOLVE NA HORA, e a escrita continua atrás

    Medido no card 73: **174,19 s**. A primeira versão desta rota era síncrona e
    o resultado vivia só na memória do browser — sair da página descartava, sem
    linha no banco nem log de que aquilo tinha rodado. O operador voltava, via o
    botão de novo, e os tokens já estavam gastos.

    Agora a rota grava a linha como `running`, dispara a cascata em segundo
    plano e responde imediatamente. Quem quer o resultado consulta
    `GET /copy/{opportunity_id}` — inclusive num browser que foi fechado e
    reaberto.
    """
    # `_ponte()` aqui, na requisição, e não dentro da tarefa: SDK ausente ou
    # `volc_ads` fora do caminho viram 503 com a mensagem certa, agora, em vez
    # de uma linha `error` que o operador só descobre depois de esperar.
    _ponte()

    if not body.keywords:
        raise HTTPException(
            status_code=422,
            detail="Sem keywords selecionadas não há o que ancorar: a copy é "
                   "escrita contra os termos que vão para o anúncio.")

    supa = _supa()
    existente = await _linha_de_copy(supa, body.opportunity_id, body.run_id)

    # ⚠️ Não dispara duas cascatas para o mesmo card. Cada uma custa ~174 s e
    # tokens pagos; dois cliques no botão gastariam dobrado e a segunda
    # sobrescreveria a primeira.
    if existente and str(existente.get("status")) == "running":
        emcurso = _copy_para_tela(existente)
        if not emcurso["perdida"]:
            return emcurso

    from datetime import datetime, timezone
    agora = datetime.now(timezone.utc).isoformat()
    valores = {
        "opportunity_id": body.opportunity_id,
        "run_id": body.run_id,
        "status": "running",
        "keywords": list(body.keywords),
        # ⚠️ A VERTICAL PERSISTE AQUI, e por isso não morre mais no F5.
        #
        # Ela é o eixo do portão de habilitação (`policy/spec.py`) e quem a
        # declara é o OPERADOR — é afirmação sobre o negócio, não inferência.
        # Vivia num `useState` do React: sobrevivia a cliques e morria num
        # refresh. Medido no card 65 em 19/08/2026: o operador escolheu
        # `informativo`, a página recarregou, a escolha voltou ao inferido
        # `governo_documentos`, e a prova reprovou exigindo certificação.
        #
        # Fica ao lado da copy de propósito: a copy É ESCRITA contra uma
        # vertical, e guardá-las juntas mantém as duas coerentes por construção.
        "vertical": body.vertical,
        "certificacoes": list(body.certificacoes or []),
        # Zera o resultado anterior: manter a copy velha ao lado de um `running`
        # faria a tela mostrar texto antigo como se fosse o que está sendo
        # escrito agora.
        "copy": None, "medicao": None, "pendentes": [], "diario": [],
        "fatos_usados": 0, "fatos_descartados": [], "aceita": None,
        "segundos": None, "erro": None, "atualizado_em": agora,
    }

    if existente:
        await supa.patch(TABELA_COPY, {"id": f"eq.{existente['id']}"}, valores)
        linha_id = int(existente["id"])
    else:
        criada = await supa.insert(TABELA_COPY, [{**valores, "criado_em": agora}])
        if not criada:
            raise HTTPException(status_code=500,
                                detail="Não consegui gravar a linha da copy.")
        linha_id = int(criada[0]["id"])

    tarefa = asyncio.create_task(_escrever_em_segundo_plano(linha_id, body))
    _ESCRITAS.add(tarefa)
    tarefa.add_done_callback(_ESCRITAS.discard)

    linha = await _linha_de_copy(supa, body.opportunity_id, body.run_id)
    return _copy_para_tela(linha) if linha else {"existe": False}


# ── a prova ─────────────────────────────────────────────────────────────────

class GrupoEscolhido(BaseModel):
    """Uma sub-intenção que o operador marcou. Vira UM ad group."""
    tipo: str
    keywords: List[str]
    # `None` herda o lance do brief. Preencher só com CPC medido na CONTA —
    # nunca com o minerado, que superestima em 7,4× e inverte a ordem.
    cpc_inicial: Optional[float] = None
    negativas: List[str] = Field(default_factory=list)


class EvidenciaEntrada(BaseModel):
    """O que sustenta um critério, e de que tipo é esse sustento.

    `MEDIDO` exige janela e métricas — número sem período não sustenta decisão.
    `HIPOTESE` é o que um modelo ou uma heurística propôs e ninguém mediu; a
    tela tem obrigação de mostrar a diferença.
    """
    tipo: str = "HIPOTESE"           # MEDIDO | HIPOTESE
    fonte: str
    janela_inicio: Optional[str] = None   # ISO-8601, AAAA-MM-DD
    janela_fim: Optional[str] = None
    metricas: Optional[Dict[str, Any]] = None


class CriterioEntrada(BaseModel):
    """Uma keyword — positiva ou negativa — com tudo o que a define.

    Substitui o par `List[str]` + `match_type` global. Quem ainda manda o
    contrato antigo continua funcionando: `_criterios_do_corpo` converte.
    """
    texto: str
    match_type: str = "PHRASE"      # EXACT | PHRASE | BROAD
    negativa: bool = False
    nivel: str = "AD_GROUP"         # CAMPAIGN | AD_GROUP
    # `None` num critério de ad group significa TODOS os grupos.
    grupo: Optional[str] = None
    # ⚠️ `LEGADO` e não `MANUAL` por default. `MANUAL` significa "o operador
    # digitou no cockpit" — uma afirmação de autoria HUMANA. Um cliente que
    # não declara procedência não pode receber essa afirmação de graça: seria
    # ausência virando fato, que é exatamente o que este contrato existe para
    # impedir. `LEGADO` diz o que de fato se sabe: veio de um pedido que não
    # declarou de onde. O cockpit sempre declara.
    origem: str = "LEGADO"          # MANUAL | PAUTADOR | SITE | SEARCH_TERM | LEGADO
    motivo: Optional[str] = None
    evidencia: Optional[EvidenciaEntrada] = None
    observado_em: Optional[str] = None
    aprovado_por: Optional[str] = None


class CopyEntrada(BaseModel):
    headlines: List[str] = Field(default_factory=list)
    descriptions: List[str] = Field(default_factory=list)
    long_headlines: List[str] = Field(default_factory=list)
    sitelinks: List[Dict[str, str]] = Field(default_factory=list)
    callouts: List[str] = Field(default_factory=list)
    snippet: Optional[Dict[str, Any]] = None
    business_name: str = ""


class ControlesDemandGenEntrada(BaseModel):
    estrategia: str
    selected_channels: Optional[List[str]] = None


class ConfiguracaoDemandGenEntrada(BaseModel):
    # Optional de propósito: ausência é diferente de False para o imutável.
    upgraded_targeting: Optional[bool] = None
    controles_de_canal: Optional[ControlesDemandGenEntrada] = None
    audiencias: Optional[List[str]] = None
    intencoes: Optional[List[str]] = None
    exclusoes_de_audiencia: Optional[List[str]] = None


class ProcedenciaAssetDemandGenEntrada(BaseModel):
    motor: str
    versao_do_motor: str = ""
    insumo: str
    quando: str
    pedido: str = ""
    custo_usd: Optional[float] = None


class AssetDemandGenEntrada(BaseModel):
    tipo: str
    nome: str
    dados_base64: str
    conteudo_hash: str
    origem: str
    procedencia: ProcedenciaAssetDemandGenEntrada


# Limites da FRONTEIRA HTTP, não uma afirmação sobre aceitação remota. O
# builder mantém os limites semânticos por papel em `limites.yaml`; estes
# tetos impedem que um pedido ainda não confiável consuma memória sem limite
# antes de chegar à régua do Estúdio ou ao `validate_only`.
TETO_QUANTIDADE_ASSETS_DEMAND_GEN = 25  # 20 marketing + 5 logos no contrato
TETO_BYTES_ASSET_DEMAND_GEN = 5 * 1024 * 1024
TETO_BYTES_LOTE_DEMAND_GEN = 25 * 1024 * 1024
TETO_BASE64_ASSET_DEMAND_GEN = 4 * ((TETO_BYTES_ASSET_DEMAND_GEN + 2) // 3)


class ProvarEntrada(BaseModel):
    opportunity_id: int
    customer_id: str
    login_customer_id: str
    run_id: Optional[int] = None

    grupos: List[GrupoEscolhido] = Field(default_factory=list)
    keywords_fora: List[str] = Field(default_factory=list)
    # ⚠️ O campo se chama `texto_do_anuncio` e NÃO `copy`. `BaseModel.copy()` é
    # um método do pydantic; um campo com esse nome o sombreia, e qualquer
    # `.copy()` num modelo passa a devolver o payload em vez de duplicar o
    # objeto — falha silenciosa, longe daqui. O alias mantém o JSON como `copy`,
    # que é o vocabulário do engine.
    # ⚠️ `Annotated`, não `Field(alias=...)` solto: `Optional[X]` é uma UNIÃO, e
    # o pydantic anexa o alias ao membro da união em vez de ao campo — silencioso,
    # com um `UnsupportedFieldAttributeWarning` que ninguém lê. O JSON continua
    # usando `copy`, que é o vocabulário do engine.
    texto_do_anuncio: Annotated[Optional[CopyEntrada], Field(alias="copy")] = None

    model_config = {"populate_by_name": True}

    budget_diario: float = 10.0
    cpc_inicial: float = 0.12
    match_type: str = "PHRASE"

    # ── como a campanha NASCE ───────────────────────────────────────────────
    # Estes quatro campos existiam como decisão implícita do engine e viraram
    # escolha do operador. Todos têm padrão, então quem já chamava `/provar`
    # sem eles continua recebendo exatamente o comportamento anterior.
    #
    # `canal` é o parâmetro que evita reescrever o cockpit quando PMax, Display
    # e Geração de Demanda entrarem: cada canal declara que estágios a tela
    # mostra e que campos o pedido carrega. Só SEARCH tem tela hoje.
    canal: str = "SEARCH"
    # ⚠️ MANUAL_CPC é o padrão porque é assim que a casa opera, e a razão é
    # documentada: broad match sem Smart Bidding não tem sinal de leilão que
    # filtre a consulta. Nascer em MAXIMIZE_CONVERSIONS sem histórico entrega
    # o lance a um modelo que ainda não tem o que aprender.
    estrategia_lance: str = "MANUAL_CPC"
    # Em quantas conversões a campanha troca de estratégia. Medido no flow
    # `GOOGLE ADS - New Campaigns Validation`, nó `Code1`:
    # `TCPA_GRADUATION_CONVS: 30`. Zero desliga a graduação.
    #
    # O lançamento apenas REGISTRA a regra — não a executa. Quem executa é o
    # motor de gestão, lendo o que o nascimento declarou.
    graduacao_em_conversoes: int = 30
    # A ação de conversão que esta campanha persegue, quando a conta tem uma.
    # Destino: `campaign.selective_optimization.conversion_actions`. Enquanto o
    # engine não escreve esse campo, ela viaja e é exibida — mas não é aplicada,
    # e a tela diz isso em vez de fingir.
    meta_conversao_id: Optional[str] = None
    # ── contrato ANTIGO de negativas (mantido, e convertido no adaptador) ───
    negativas_campanha: List[str] = Field(default_factory=list)
    negativas_adgroup: List[str] = Field(default_factory=list)
    # ── contrato TIPADO ────────────────────────────────────────────────────
    # Positivas e negativas com match type, nível, grupo, origem, motivo e
    # evidência próprios. Vazio = o cliente ainda fala o contrato antigo, e
    # `_criterios_do_corpo` faz a conversão explícita.
    criterios: List[CriterioEntrada] = Field(default_factory=list)
    vertical: Optional[str] = None
    certificacoes: List[str] = Field(default_factory=list)
    url_final: Optional[str] = None
    prefixo_nome: str = "FORGE"
    # Produzido pelo servidor na primeira prova e devolvido pelo cliente na
    # aprovação. Não é uma decisão do operador; congela os nomes do payload.
    carimbo_nome: Optional[str] = None
    conversao: str = ""
    ai_max: bool = False
    # Só é consumido quando `canal=DEMAND_GEN`. A porta continua fechada por
    # flag de servidor, e os bytes nunca voltam na resposta.
    demand_gen: Optional[ConfiguracaoDemandGenEntrada] = None
    assets_demand_gen: Optional[List[AssetDemandGenEntrada]] = None

    @model_validator(mode="before")
    @classmethod
    def _demand_gen_tem_fronteira_estrita(cls, dados: Any) -> Any:
        """Discrimina Search/legado e Demand Gen antes da projeção.

        Os modelos compartilhados são permissivos por compatibilidade com
        clientes Search legados. Essa tolerância não pode vazar para o contrato
        vertical: `assets_demand_gen=[]` é uma escolha explícita de Demand Gen,
        mesmo vazio, e não pode ser apagada por um `canal=SEARCH` relabelado.

        A projeção `extra='forbid'` roda no envelope de `/provar` e também no
        de `/subir`; campos exclusivos da aprovação são removidos antes dessa
        projeção para que a herança não reabra a fronteira vertical.
        """
        if cls.__name__ == "ProvarEntradaDemandGenEstrita" or not isinstance(dados, dict):
            return dados
        classe = cls.__name__
        canal = str(dados.get("canal") or "SEARCH").strip().upper()
        campos_demand_gen = [
            campo for campo in ("demand_gen", "assets_demand_gen")
            if campo in dados and dados[campo] is not None
        ]
        if campos_demand_gen and canal != "DEMAND_GEN":
            raise ValueError(
                "Campos Demand Gen pertencem ao contrato vertical e exigem "
                "`canal=DEMAND_GEN`; recebido canal "
                f"{canal!r} com {', '.join(campos_demand_gen)}. "
                "Nada foi projetado para Search."
            )
        if canal != "DEMAND_GEN" or classe not in {"ProvarEntrada", "SubirEntrada"}:
            return dados

        estrategia = str(dados.get("estrategia_lance") or "").strip().upper()
        if estrategia != "MAXIMIZE_CONVERSIONS":
            raise ValueError(
                "canal DEMAND_GEN exige `estrategia_lance="
                "MAXIMIZE_CONVERSIONS`; ausência ou outro valor não herda o "
                "contrato Search."
            )
        ausentes = [
            campo for campo in ("demand_gen", "assets_demand_gen")
            if campo not in dados or dados[campo] is None
        ]
        if ausentes:
            raise ValueError(
                "canal DEMAND_GEN exige campos explícitos do contrato "
                f"vertical: {', '.join(ausentes)}. `null` é ausência."
            )
        campos_search = [
            campo for campo in ("cpc_inicial", "match_type")
            if campo in dados
        ]
        if campos_search:
            raise ValueError(
                "canal DEMAND_GEN proíbe campos Search no envelope: "
                + ", ".join(campos_search)
            )
        if (
            classe == "SubirEntrada"
            and isinstance(dados.get("assets_demand_gen"), (list, tuple))
            and len(dados["assets_demand_gen"]) == 0
        ):
            raise ValueError(
                "canal DEMAND_GEN em /subir exige `assets_demand_gen` com ao "
                "menos um item; lista vazia é ausência explícita."
            )

        def _cru(valor: Any) -> Any:
            # Chamadas internas podem montar os submodelos antes do envelope. A
            # fronteira HTTP recebe dict; esta conversão preserva
            # compatibilidade sem afrouxar o JSON bruto.
            if isinstance(valor, BaseModel):
                return {
                    chave: _cru(item)
                    for chave, item in valor.model_dump(
                        mode="python", by_alias=True
                    ).items()
                }
            if isinstance(valor, dict):
                return {chave: _cru(item) for chave, item in valor.items()}
            if isinstance(valor, (list, tuple)):
                return [_cru(item) for item in valor]
            return valor

        projetado = _cru(dados)
        if classe == "SubirEntrada":
            for campo in (
                "motivo",
                "plano_impressao",
                "confirmar_criacao_pausada",
            ):
                projetado.pop(campo, None)
        ProvarEntradaDemandGenEstrita.model_validate(projetado)
        return dados


class _CopyDemandGenEstrita(CopyEntrada):
    model_config = ConfigDict(extra="forbid")


class _ControlesDemandGenEstritos(ControlesDemandGenEntrada):
    model_config = ConfigDict(extra="forbid")


class _ConfiguracaoDemandGenEstrita(ConfiguracaoDemandGenEntrada):
    controles_de_canal: Optional[_ControlesDemandGenEstritos] = None
    model_config = ConfigDict(extra="forbid")


class _ProcedenciaAssetDemandGenEstrita(ProcedenciaAssetDemandGenEntrada):
    model_config = ConfigDict(extra="forbid")


class _AssetDemandGenEstrito(AssetDemandGenEntrada):
    dados_base64: str = Field(max_length=TETO_BASE64_ASSET_DEMAND_GEN)
    procedencia: _ProcedenciaAssetDemandGenEstrita
    model_config = ConfigDict(extra="forbid")


class ProvarEntradaDemandGenEstrita(ProvarEntrada):
    """Projeção de validação; a rota continua recebendo `ProvarEntrada`.

    Assim Search conserva a compatibilidade histórica (`extra='ignore'`) e
    Demand Gen nasce fail-closed no topo e em cada objeto aninhado.
    """

    texto_do_anuncio: Optional[_CopyDemandGenEstrita] = Field(
        default=None, alias="copy"
    )
    demand_gen: Optional[_ConfiguracaoDemandGenEstrita] = None
    assets_demand_gen: Optional[List[_AssetDemandGenEstrito]] = Field(
        default=None,
        max_length=TETO_QUANTIDADE_ASSETS_DEMAND_GEN,
    )
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


def _campos_explicitos(modelo: BaseModel) -> set[str]:
    """Nomes presentes no JSON, sem transformar defaults em decisões."""
    campos = getattr(modelo, "model_fields_set", None)
    if campos is None:  # compatibilidade Pydantic v1, sem tocar no legado em v2
        campos = getattr(modelo, "__fields_set__", set())
    return set(campos)


def _recusar_campos_nao_operados_demand_gen(body: ProvarEntrada) -> None:
    """Falha fechado para cada superfície que o adaptador não materializa.

    O modelo HTTP é compartilhado com Search e preenche defaults legados. Por
    isso valores escalares são recusados quando vieram explicitamente no JSON,
    enquanto coleções são recusadas quando carregam conteúdo. Assim ausência
    continua ausência e nenhuma decisão aceita pelo Pydantic some do proto.
    """
    recusados: list[str] = []
    explicitos = _campos_explicitos(body)

    for campo in ("cpc_inicial", "match_type", "graduacao_em_conversoes"):
        if campo in explicitos:
            recusados.append(campo)

    for campo in ("meta_conversao_id", "conversao"):
        if getattr(body, campo):
            recusados.append(campo)
    if body.ai_max:
        recusados.append("ai_max")

    for campo in (
        "grupos",
        "keywords_fora",
        "criterios",
        "negativas_campanha",
        "negativas_adgroup",
    ):
        if getattr(body, campo):
            recusados.append(campo)

    copy = body.texto_do_anuncio
    if copy is not None:
        if copy.long_headlines:
            recusados.append("copy.long_headlines")
        if copy.sitelinks:
            recusados.append("copy.sitelinks")
        if copy.callouts:
            recusados.append("copy.callouts")
        if copy.snippet is not None:
            recusados.append("copy.snippet")

    if recusados:
        raise ValueError(
            "DEMAND_GEN recebeu campos que esta onda não materializa em "
            "MutateOperation e por isso não os descarta em silêncio: "
            + ", ".join(sorted(set(recusados)))
            + ". Remova-os do pedido ou use um canal que os opere."
        )


def _assets_decodificados_demand_gen(
    itens: List[AssetDemandGenEntrada],
):
    """Decodifica um lote limitado, sem acumular o item que rompe o teto.

    O tamanho codificado é conferido antes de `b64decode`; o tamanho real é
    conferido logo depois; e o total é conferido antes de entregar o item ao
    chamador. Portanto nem o catálogo, nem a lista de assets canônicos recebe
    o byte que excedeu a fronteira.
    """
    import base64
    import binascii

    if len(itens) > TETO_QUANTIDADE_ASSETS_DEMAND_GEN:
        raise ValueError(
            "assets_demand_gen excede o teto de quantidade da fronteira HTTP: "
            f"{len(itens)} > {TETO_QUANTIDADE_ASSETS_DEMAND_GEN}"
        )

    total = 0
    for item in itens:
        tamanho_codificado = len(item.dados_base64)
        if tamanho_codificado > TETO_BASE64_ASSET_DEMAND_GEN:
            raise ValueError(
                f"asset {item.nome!r}: base64 excede o teto codificado da "
                f"fronteira HTTP ({tamanho_codificado} > "
                f"{TETO_BASE64_ASSET_DEMAND_GEN})"
            )
        try:
            dados = base64.b64decode(item.dados_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                f"asset {item.nome!r}: dados_base64 inválidos"
            ) from exc
        if not dados:
            raise ValueError(f"asset {item.nome!r}: conteúdo ausente")
        if len(dados) > TETO_BYTES_ASSET_DEMAND_GEN:
            raise ValueError(
                f"asset {item.nome!r}: conteúdo decodificado excede o teto "
                f"por item ({len(dados)} > {TETO_BYTES_ASSET_DEMAND_GEN})"
            )
        proximo_total = total + len(dados)
        if proximo_total > TETO_BYTES_LOTE_DEMAND_GEN:
            raise ValueError(
                "assets_demand_gen excede o teto total decodificado da "
                f"fronteira HTTP ({proximo_total} > "
                f"{TETO_BYTES_LOTE_DEMAND_GEN})"
            )
        total = proximo_total
        yield item, dados


def _plano_aprovavel(body: ProvarEntrada, *, cid: str, mid: str) -> Dict[str, Any]:
    """O conteúdo exato que o humano aprova, sem campos do ato de aprovar.

    O builder acrescenta um carimbo ao nome do recurso. Esse instante não é
    decisão humana; todo o resto — conta, canal, verba, lance, critérios, copy
    e destino — está aqui e entra na impressão.
    """
    bruto = body.model_dump(mode="json", by_alias=True, exclude_none=False)
    # ⚠️ `carimbo_nome` SAI DAQUI, e a ausência dele é a regra — não um detalhe.
    #
    # O docstring acima sempre disse que o instante do carimbo não é decisão
    # humana, e `canario.impressao_do_plano` diz o mesmo com todas as letras
    # ("não usa o nome temporizado"). As duas afirmações eram falsas: o campo
    # ficava no dicionário e entrava tanto no hash da impressão quanto, por
    # `plano_do_ledger`, na chave de idempotência.
    #
    # O custo disso é a segunda campanha. Uma tentativa indeterminada cria a
    # campanha com a marca `VOLC-CANARY-<impressao[:12]>`; o operador roda
    # `/provar` de novo, `carimbo_do_nome` gera outro instante, e o MESMO plano
    # passa a ter outra impressão, outra marca e outra chave. A pré-checagem
    # remota procura a marca nova, não encontra nada, e o ledger não reconhece
    # a chave anterior. As duas defesas contra duplicidade olham para o lado
    # errado ao mesmo tempo, e o leilão recebe duas campanhas.
    #
    # O carimbo continua no NOME da campanha, que é onde ele serve para alguma
    # coisa: distinguir duas execuções no relatório. Ele só não participa mais
    # da identidade.
    for campo in ("motivo", "plano_impressao", "confirmar_criacao_pausada",
                  "carimbo_nome"):
        bruto.pop(campo, None)
    bruto["customer_id"] = cid
    bruto["login_customer_id"] = mid
    bruto["canal"] = str(body.canal or "SEARCH").upper()
    return bruto


class PlanoIrrepresentavel(ValueError):
    """O plano aprovado não tem representação canônica para o ledger."""


class LeituraDaContaIndisponivel(RuntimeError):
    """Não deu para ler a conta. NÃO significa que a campanha não existe."""


# Dinheiro viaja em micros — a unidade que a própria API do Google usa, e a
# única que o `plano` pode carregar sem virar float na travessia.
UM_MILHAO = Decimal("1000000")


def _micros(valor: Any, campo: str) -> int:
    """Reais → micros, por `Decimal`, sem jamais passar por `float` binário.

    ⚠️ `Decimal(str(valor))` e não `Decimal(valor)`: o segundo leria o float
    binário inteiro (`Decimal(0.1)` é `0.1000000000000000055511151231257827`) e
    devolveria micros diferentes conforme a plataforma. `str()` de um float em
    CPython é o repr mais curto que reconstrói o valor — determinístico — e é
    dele que sai a mesma chave em qualquer máquina.
    """
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PlanoIrrepresentavel(
            f"{campo}={valor!r} não é um valor monetário representável.") from exc
    if not numero.is_finite() or numero <= 0:
        raise PlanoIrrepresentavel(
            f"{campo}={valor!r} precisa ser um valor finito e maior que zero.")
    # ⚠️ A CONVERSÃO É A DO EXECUTOR, LITERALMENTE — e isso não é preguiça.
    #
    # A primeira versão recusava qualquer resíduo abaixo de um micro; a segunda
    # arredondava com `ROUND_HALF_UP` sobre `Decimal`. As duas erravam a mesma
    # coisa: a chave de idempotência existe para identificar O QUE FOI ENVIADO,
    # e quem envia é `brief.micros`, que é `int(round(valor * 1_000_000))`
    # (volc_ads/campanha/brief.py:1283).
    #
    # `round()` do Python arredonda para o PAR no empate, e sobre float o
    # empate nem sempre é onde parece. Medido: `0.1200005` vira 120000 no
    # executor e virava 120001 aqui. Uma chave que descreve 120001 micros para
    # uma campanha que subiu com 120000 identifica um plano que nunca existiu —
    # e na retomada ela não reconhece o que foi enviado.
    #
    # O `Decimal` acima continua fazendo o trabalho dele: recusar o que não é
    # dinheiro (não finito, zero, negativo, texto). A CONVERSÃO, essa, tem de
    # ser bit a bit a do executor. Ela é determinística: IEEE754 dá o mesmo
    # resultado em qualquer máquina para o mesmo float de entrada.
    return int(round(float(numero) * 1_000_000))


def plano_do_ledger(body: ProvarEntrada, *, cid: str, mid: str) -> Dict[str, Any]:
    """O plano aprovado na forma que a chave de idempotência aceita.

    ⚠️ Este é o conserto do defeito que deixou `/subir` inoperante. O plano que
    ia ao ledger era o `model_dump(mode="json")` cru, e `ProvarEntrada` declara
    `budget_diario: float` e `cpc_inicial: float`. `lote._sem_float` recusa float
    na travessia — com razão, e a guarda NÃO foi afrouxada: `repr(0.1 + 0.2)` não
    é `'0.3'`, e dinheiro em float faria a mesma campanha produzir duas chaves em
    máquinas diferentes, que é o oposto de idempotência.

    A correção é na origem: o dinheiro atravessa em micros inteiros. Note que a
    IMPRESSÃO que o humano aprova continua saindo de `_plano_aprovavel` — ela
    mostra reais, porque é o que o operador leu na tela. São dois consumidores
    do mesmo plano com necessidades diferentes: a tela precisa ser legível, a
    chave precisa ser determinística.
    """
    plano = _plano_aprovavel(body, cid=cid, mid=mid)
    for campo in ("budget_diario", "cpc_inicial"):
        if campo in plano:
            plano[f"{campo}_micros"] = _micros(plano.pop(campo), campo)
    grupos = []
    for i, grupo in enumerate(plano.get("grupos") or []):
        canonico = dict(grupo)
        if canonico.get("cpc_inicial") is not None:
            canonico["cpc_inicial_micros"] = _micros(
                canonico.pop("cpc_inicial"), f"grupos[{i}].cpc_inicial")
        else:
            canonico.pop("cpc_inicial", None)
        grupos.append(canonico)
    if grupos:
        plano["grupos"] = grupos
    return plano


def _impressao_aprovavel(body: ProvarEntrada, *, cid: str, mid: str) -> str:
    return canario.impressao_do_plano(_plano_aprovavel(body, cid=cid, mid=mid))


def _prefixo_operacional(body: ProvarEntrada, *, impressao: str) -> str:
    """Canário recebe marca estável; as demais provas preservam o contrato."""
    if escopo.so_digitos(body.customer_id) == canario.CONTA:
        return canario.prefixo_da_marca(impressao)
    return body.prefixo_nome


def _criterios_do_corpo(body: Any, pp: Any) -> list:
    """Reúne TODOS os critérios do pedido num contrato tipado só.

    É o adaptador da fronteira, e existe para que o `Brief` nunca receba os
    dois contratos ao mesmo tempo — com os dois, a precedência seria silenciosa
    e uma das listas sumiria do payload sem aviso.

    Quatro fontes entram aqui e saem como uma:

      1. `body.criterios`            o contrato tipado, como veio
      2. `body.negativas_campanha`   antigo → BROAD, nível CAMPAIGN
      3. `body.negativas_adgroup`    antigo → BROAD, nível AD_GROUP, sem grupo
      4. `g.negativas` de cada grupo antigo → BROAD, nível AD_GROUP, no grupo

    BROAD nas três antigas porque era o que o construtor aplicava fixo; mudar o
    default aqui alteraria em silêncio o alcance das negativas de todo cliente
    que ainda manda `List[str]`.

    ⚠️ A fonte 4 é a que estava MORTA: `GrupoEscolhido.negativas` existia no
    contrato HTTP, o Pydantic a aceitava, e nenhum caminho a lia — a negativa
    que o operador declarava por sub-intenção nunca chegava ao payload, e nada
    na resposta dizia isso. Devolver `[]` quando não há nada declarado mantém o
    caminho antigo intacto para quem não usa nenhuma das quatro.
    """
    crits: list = []
    for c in body.criterios:
        ev = None
        if c.evidencia is not None:
            ev = pp.Evidencia(
                tipo=c.evidencia.tipo,
                fonte=c.evidencia.fonte,
                janela_inicio=_data_ou_none(c.evidencia.janela_inicio),
                janela_fim=_data_ou_none(c.evidencia.janela_fim),
                metricas=c.evidencia.metricas,
            )
        crits.append(pp.Criterio(
            texto=c.texto, match_type=c.match_type, negativa=c.negativa,
            nivel=c.nivel, grupo=c.grupo, origem=c.origem, motivo=c.motivo,
            evidencia=ev,
            observado_em=_instante_ou_none(c.observado_em),
            aprovado_por=c.aprovado_por,
        ))

    legado: list = []
    legado += pp.de_lista(list(body.negativas_campanha), match_type="BROAD",
                          negativa=True, nivel="CAMPAIGN")
    legado += pp.de_lista(list(body.negativas_adgroup), match_type="BROAD",
                          negativa=True, nivel="AD_GROUP")
    for g in body.grupos:
        legado += pp.de_lista(list(g.negativas), match_type="BROAD",
                              negativa=True, nivel="AD_GROUP", grupo=g.tipo)

    if not crits and not legado:
        return []
    # Dedup determinístico: o tipado foi declarado primeiro e por isso vence o
    # legado que repita a mesma identidade — o operador revisou aquele.
    unicos, _descartados = pp.deduplicar(crits + legado)
    return unicos


def _data_ou_none(s: Optional[str]):
    """ISO-8601 → `date`. Ausência continua ausência, nunca hoje."""
    if not s:
        return None
    from datetime import date

    try:
        return date.fromisoformat(s[:10])
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"data {s!r} não é ISO-8601 (AAAA-MM-DD)",
        ) from exc


def _instante_ou_none(s: Optional[str]):
    """ISO-8601 → `datetime`. Ausência continua ausência, nunca agora."""
    if not s:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"instante {s!r} não é ISO-8601",
        ) from exc


def _montar_plano_demand_gen(
    pp: Any,
    cockpit: Any,
    escolha: Any,
    copy: Any,
    body: ProvarEntrada,
) -> Any:
    """Monta o Brief Demand Gen sem atravessar o adaptador de Search.

    Bytes são medidos no backend, transformados no ``Asset`` canônico e passam
    por ``criativo_ponte.imagens_de_demand_gen``. Só a entrega aprovada vira
    ``ImagensDemandGen``; o router nunca recalcula proporção ou limite.

    ``pautador_ponte.montar_brief`` exige keywords porque é a fronteira Search.
    Usá-lo e apagar keywords depois tornaria uma superfície irrelevante em
    pré-requisito e esconderia dados preenchidos. Este adaptador usa o mesmo
    ``Brief`` e o mesmo ``Plano`` canônicos, herda destino/geo/política do
    cockpit e recusa qualquer campo Search em vez de descartá-lo.
    """
    from datetime import datetime

    from volc_ads import criativo_ponte
    from volc_ads.campanha.brief import (
        Brief,
        ConfiguracaoDemandGen,
        ControlesDeCanalDemandGen,
        Copy,
    )
    from volc_ads.criativo.adaptadores import medir_imagem
    from volc_ads.criativo.contrato import (
        Asset,
        LoteDeAssets,
        Origem,
        Procedencia,
        TipoDeAsset,
    )

    _recusar_campos_nao_operados_demand_gen(body)

    entrada = body.demand_gen
    if entrada is None:
        raise ValueError(
            "canal DEMAND_GEN exige o objeto `demand_gen`; ausência não usa "
            "defaults de targeting ou canais"
        )
    if body.assets_demand_gen is None:
        raise ValueError(
            "canal DEMAND_GEN exige `assets_demand_gen`; ausência não é lote "
            "vazio confirmado"
        )

    manual = str(escolha.url_final or "").strip()
    ignorados_como_bloqueio = {"SEM_CLUSTER", "SEM_FILA_DE_ANUNCIO"}
    bloqueios = [
        aviso
        for aviso in cockpit.bloqueios
        if aviso.codigo not in ignorados_como_bloqueio
        and not (manual and aviso.codigo in {"SEM_LP", "SEM_FUNIL"})
    ]
    if bloqueios:
        raise pp.PonteIncompleta(
            "o cockpit tem bloqueio aplicável a Demand Gen: "
            + " | ".join(
                f"{a.codigo}: {a.titulo} — {a.detalhe}" for a in bloqueios
            )
        )

    origem = cockpit.origem
    if origem is None:
        raise pp.PonteIncompleta(
            "Demand Gen exige origem publicada com país, idioma e vertical; "
            "uma URL manual decide o destino, mas não pode inventar targeting"
        )
    if not str(origem.pais or "").strip() or not str(origem.idioma or "").strip():
        raise pp.PonteIncompleta(
            "origem Demand Gen sem país ou idioma; ausência não vira BR/pt"
        )
    vertical = str(escolha.vertical or origem.vertical or "").strip()
    if not vertical:
        raise pp.PonteIncompleta(
            "origem Demand Gen sem vertical confirmada; ausência não vira "
            "`informativo`"
        )
    url = str(manual or origem.url_final or "").strip()
    if not url.startswith("https://"):
        raise ValueError(f"destino Demand Gen {url!r} não é https")
    nicho = (
        origem.nicho or "sem nicho declarado"
    )

    controles = None
    if entrada.controles_de_canal is not None:
        selecionados = entrada.controles_de_canal.selected_channels
        canonicos = (
            None
            if selecionados is None
            else [str(canal).strip().lower() for canal in selecionados]
        )
        if canonicos is not None and len(canonicos) != len(set(canonicos)):
            raise ValueError(
                "selected_channels repete canal depois da canonização; "
                "corrija o pedido"
            )
        controles = ControlesDeCanalDemandGen(
            estrategia=str(entrada.controles_de_canal.estrategia).strip().upper(),
            selected_channels=(
                None if canonicos is None else frozenset(canonicos)
            ),
        )
    configuracao = ConfiguracaoDemandGen(
        upgraded_targeting=entrada.upgraded_targeting,
        controles_de_canal=controles,
        audiencias=(None if entrada.audiencias is None else tuple(entrada.audiencias)),
        intencoes=(None if entrada.intencoes is None else tuple(entrada.intencoes)),
        exclusoes_de_audiencia=(
            None
            if entrada.exclusoes_de_audiencia is None
            else tuple(entrada.exclusoes_de_audiencia)
        ),
    )

    assets = []
    conteudo_por_identidade: Dict[str, bytes] = {}
    for item, dados in _assets_decodificados_demand_gen(body.assets_demand_gen):
        try:
            quando = datetime.fromisoformat(
                item.procedencia.quando.replace("Z", "+00:00")
            )
            tipo = TipoDeAsset(item.tipo)
            origem_asset = Origem(item.origem)
        except ValueError as exc:
            raise ValueError(f"asset {item.nome!r}: contrato inválido — {exc}") from exc

        medida = medir_imagem.medir(dados)
        asset = Asset(
            tipo=tipo,
            procedencia=Procedencia(
                motor=item.procedencia.motor,
                versao_do_motor=item.procedencia.versao_do_motor,
                insumo=item.procedencia.insumo,
                quando=quando,
                pedido=item.procedencia.pedido,
                custo_usd=item.procedencia.custo_usd,
            ),
            conteudo_hash=item.conteudo_hash,
            origem=origem_asset,
            bytes_totais=medida.bytes_totais,
            mime=medida.mime,
            largura=medida.largura,
            altura=medida.altura,
            rotulo=item.nome,
        )
        assets.append(asset)
        conteudo_por_identidade[asset.identidade] = dados

    lote = LoteDeAssets(
        canal="DEMAND_GEN",
        assets=tuple(assets),
        intencao=nicho,
    )
    entrega = criativo_ponte.imagens_de_demand_gen(
        lote, conteudo_por_identidade
    )
    if not entrega.ok:
        raise ValueError(
            "assets Demand Gen recusados pela fronteira do Estúdio:\n"
            + entrega.resumo()
        )

    pais = str(origem.pais).strip()
    idioma = str(origem.idioma).strip()
    brief = Brief(
        nicho=nicho,
        slug=origem.slug or "",
        url_final=url,
        copy=copy or Copy(),
        pais=pais,
        idioma=idioma,
        budget_diario=body.budget_diario,
        cpc_inicial=body.cpc_inicial,
        match_type=body.match_type,
        estrategia_lance=body.estrategia_lance,
        vertical=vertical,
        certificacoes=set(escolha.certificacoes),
        prefixo_nome=escolha.prefixo_nome or "FORGE",
        carimbo_nome=escolha.carimbo_nome,
        conversao=escolha.conversao or "",
        keywords=[],
        sub_intencoes=[],
        criterios=[],
        negativas_campanha=[],
        negativas_adgroup=[],
        imagens_display=None,
        imagens_demand_gen=entrega.imagens,
        demand_gen=configuracao,
    )
    avisos = tuple(
        aviso
        for aviso in cockpit.avisos
        if aviso.codigo not in ignorados_como_bloqueio
    )
    if manual:
        avisos += (
            pp.Aviso(
                "URL_MANUAL",
                "atencao",
                "Destino colado à mão",
                "A campanha perde a herança do funil e o cruzamento anúncio × "
                "página; a URL continua sendo uma decisão explícita do pedido.",
            ),
        )
    return pp.Plano(brief=brief, grupos=(), avisos=avisos)


@router.post("/provar")
async def provar(
    body: ProvarEntrada = Body(...),
    identidade: Identidade = Depends(exigir_usuario),
) -> Any:
    """Monta o Brief e submete os três juízes. NADA é criado.

    `validate_only` é leitura para todos os efeitos: a API valida o payload e
    descarta. Por isso esta rota não passa pela trava de escrita, e por isso ela
    pode ser chamada à vontade.

    Quando os dois primeiros juízes passam, `preparar()` emite o `Selo` — a
    impressão digital do payload provado. `subir()` recusa qualquer coisa sem
    ele, então esta rota não é uma sugestão: é o portão.

    ⚠️ O `customer_id` vem NO CORPO, então o bloqueio da tela não vale aqui:
    quem chama a API direto escolheria qualquer uma das 39 contas que a
    credencial alcança. `_no_escopo` é o que faz o limite ser do sistema e não
    do desenho da página.
    """
    canal_pedido = str(body.canal or "SEARCH").strip().upper()
    if canal_pedido == "DEMAND_GEN":
        # O contrato é julgado antes do escopo, da ponte e de qualquer cliente.
        # A mesma guarda é repetida no adaptador para chamadas internas diretas.
        try:
            _recusar_campos_nao_operados_demand_gen(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # A flag é conferida primeiro: servidor fechado não precisa sequer
        # interpretar papel. Quando aberta, a mesma capacidade projetada para
        # a tela é cobrada aqui; não existe promessa de frontend sem portão.
        if not cap.servidor_oferece_demand_gen_validate_only():
            raise HTTPException(
                status_code=403,
                detail=(
                    "A prova Demand Gen está desabilitada neste servidor. Nada "
                    "foi montado, nenhum validate_only foi chamado e criação "
                    "real continua indisponível."
                ),
            )
        capacidade = cap.de_identidade(
            papel=getattr(identidade, "papel", ""),
            escrita_permitida=False,
        )
        if not capacidade.google_demand_gen_validate_only:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Sua sessão não possui a capacidade experimental de prova "
                    "Demand Gen. Nada foi montado e nenhuma chamada foi feita."
                ),
            )

    cid, mid = _no_escopo(body.customer_id, body.login_customer_id)
    # A primeira prova cria; uma repetição ou a escrita reutiliza. O valor entra
    # no plano aprovável e impede que um carimbo novo altere o grafo entre as
    # duas requisições.
    body.carimbo_nome = canario.carimbo_do_nome(body.carimbo_nome)
    chave_intencao = _impressao_aprovavel(body, cid=cid, mid=mid)
    pp, sb = _ponte()
    try:
        canal_resolvido, _ = sb.resolver_provador(body.canal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def _preparar():
        cockpit = pp.montar_cockpit(pp.carregar(body.opportunity_id, run_id=body.run_id))
        escolha = pp.Escolha(
            grupos={g.tipo: list(g.keywords) for g in body.grupos},
            keywords_fora=list(body.keywords_fora),
            budget_diario=body.budget_diario,
            cpc_inicial=body.cpc_inicial,
            cpc_por_grupo={g.tipo: g.cpc_inicial for g in body.grupos
                           if g.cpc_inicial is not None},
            match_type=body.match_type,
            # O adaptador da fronteira reúne os dois contratos num só. Vazio
            # significa que o pedido não declarou negativa nenhuma, e aí as
            # listas antigas seguem o caminho de sempre.
            criterios=tuple(_criterios_do_corpo(body, pp)),
            negativas_campanha=(),
            negativas_adgroup=(),
            vertical=body.vertical,
            certificacoes=set(body.certificacoes),
            url_final=body.url_final,
            prefixo_nome=_prefixo_operacional(body, impressao=chave_intencao),
            carimbo_nome=body.carimbo_nome,
            conversao=body.conversao,
            estrategia_lance=body.estrategia_lance,
            # A doutrina P7 é do sistema, não do chamador: um conjunto, sempre.
            # A sub-intenção continua servindo à triagem no cockpit.
            conjunto_unico=True,
        )
        copy = _copy_do_corpo(body.texto_do_anuncio)
        if canal_resolvido == "DEMAND_GEN":
            plano = _montar_plano_demand_gen(
                pp, cockpit, escolha, copy, body
            )
        else:
            plano = pp.montar_brief(cockpit, escolha, copy=copy)
        # `cid`/`mid` e não `body.*`: são os ids já normalizados pelo portão. O
        # id colado do painel do Google vem `801-785-1692`, com hífen.
        preparo = sb.preparar(
            cid, plano.brief, login_customer_id=mid, canal=canal_resolvido,
            ai_max=body.ai_max,
        )
        return plano, preparo

    try:
        plano, preparo = await asyncio.wait_for(
            asyncio.to_thread(_preparar), timeout=TIMEOUT_PROVA_S)
    except asyncio.TimeoutError:
        # A distinção que a tela precisa fazer: passou do teto NÃO significa que
        # algo foi criado. `validate_only` não cria nada, em nenhum desfecho.
        raise HTTPException(
            status_code=504,
            detail=f"A prova passou de {int(TIMEOUT_PROVA_S)}s e foi encerrada. "
                   f"Nada foi criado — `validate_only` valida e descarta, sempre. "
                   f"Tente de novo; se repetir, a API do Google está lenta.",
        ) from None
    except pp.PonteIncompleta as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        # ⚠️ TEM DE VIR ANTES do `except Exception`. `_criterios_do_corpo` roda
        # dentro da thread e levanta `HTTPException(422)` para data ISO
        # inválida; `HTTPException` NÃO é `ValueError`, então sem esta linha
        # ela caía no genérico abaixo e o operador recebia 500 "explodiu" no
        # lugar de "a data não é AAAA-MM-DD".
        raise
    except ValueError as exc:
        # `Brief.__post_init__` e `montar_brief` levantam ValueError com
        # mensagem acionável (país inválido, url não-https, keywords e
        # sub_intenções ao mesmo tempo). Repassar é melhor que traduzir.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("prova do card %s explodiu", body.opportunity_id)
        raise HTTPException(status_code=500, detail=str(exc)[:400]) from exc

    elegivel, motivo_elegibilidade = canario.elegivel(
        customer_id=cid,
        login_customer_id=mid,
        canal=body.canal,
        budget_diario=body.budget_diario,
        cpc_inicial=body.cpc_inicial,
        chave_intencao=chave_intencao,
        carimbo_nome=body.carimbo_nome,
    )
    return {
        "preparo": projecao.preparo(preparo),
        "avisos": [projecao.aviso(a) for a in (plano.avisos or ())],
        "grupos": [{"tipo": g.tipo, "keywords": len(g.keywords)} for g in (plano.grupos or ())],
        "autorizacao": {
            # Esta é a impressão DAS OPERAÇÕES que passaram no validate_only,
            # depois de toda adaptação/autocorreção. É a única coisa que pode
            # ser aprovada para escrita. Sem selo, não há plano aprovável.
            "plano_impressao": preparo.selo.impressao if preparo.selo else None,
            # Identifica a intenção e produz a marca remota. Não substitui a
            # impressão efetiva acima: os dois campos têm papéis diferentes.
            "chave_intencao": chave_intencao,
            "carimbo_nome": body.carimbo_nome,
            "alvo_canario": cid == canario.CONTA and mid == canario.MCC,
            "elegivel": elegivel and preparo.selo is not None,
            "motivo_elegibilidade": motivo_elegibilidade,
            "politica": canario.POLITICA.para_json(),
            "budget_diario": body.budget_diario,
            "cpc_inicial": body.cpc_inicial,
            "ativacao_incluida": False,
        },
    }


def _copy_do_corpo(c: Optional[CopyEntrada]):
    """Aceita o vocabulário do ENGINE e, por compatibilidade, o do router.

    ⚠️ ESTE ERA UM DESLIGAMENTO SILENCIOSO, NÃO UM ERRO.

    A cascata de `volc_ads/copy` produz `title/description1/description2` no
    sitelink e `values` no snippet — é o vocabulário do `PROMPT.md` e do
    contrato. A primeira versão desta função lia só `texto/descricao1/
    descricao2/valores`, nomes inventados aqui no router. Ligar o estágio 3
    faria toda a copy gerada chegar com **sitelinks vazios e snippet vazio**,
    sem exceção, sem log, sem nada: `.get("texto", "")` devolve `""` e o Brief
    aceita string vazia.

    O engine ganha a precedência porque é ele quem produz. Os nomes em
    português continuam funcionando para quem já os manda.
    """
    from volc_ads.campanha.brief import Copy, Sitelink, Snippet

    if c is None:
        return None

    def _s(d: Dict[str, Any], *nomes: str) -> str:
        for n in nomes:
            v = d.get(n)
            if v:
                return str(v)
        return ""

    snip = c.snippet or {}
    return Copy(
        headlines=list(c.headlines),
        descriptions=list(c.descriptions),
        long_headlines=list(c.long_headlines),
        sitelinks=[Sitelink(texto=_s(s, "title", "texto"),
                            descricao1=_s(s, "description1", "descricao1"),
                            descricao2=_s(s, "description2", "descricao2"))
                   for s in c.sitelinks],
        callouts=list(c.callouts),
        snippet=Snippet(header=_s(snip, "header"),
                        valores=list(snip.get("values") or snip.get("valores") or []))
        if c.snippet else None,
        business_name=c.business_name,
    )


# ── a escrita ───────────────────────────────────────────────────────────────

class SubirEntrada(ProvarEntrada):
    # `subir()` exige motivo descritivo — `destravar()` recusa menos de 10
    # caracteres. Não é burocracia: o motivo vai para o recibo, e recibo sem
    # motivo é um gasto que ninguém sabe explicar depois.
    #
    # ⚠️ A regra repete a do executor DE PROPÓSITO, e a repetição se paga: sem
    # ela, um motivo curto passava por aqui, abria recibo, e só então
    # `_exigir_motivo` levantava um `ValueError` cru lá dentro — que esta rota
    # não consegue distinguir de uma falha posterior ao mutate. O item ficava
    # `indeterminado` por um erro de digitação. Recusar na fronteira HTTP
    # devolve 422 antes de existir recibo, que é onde este erro pertence.
    #
    # E a repetição precisa ser FIEL: `min_length=10` mede a string crua, e o
    # executor mede `len(motivo.strip())` (volc_ads/subir.py:934). Dez espaços
    # passavam no Pydantic e morriam lá dentro — reabrindo exatamente o buraco
    # que esta guarda existe para fechar. Uma guarda que discorda da guarda que
    # ela replica é pior que nenhuma: ela dá confiança sem dar proteção.
    motivo: str

    @field_validator("motivo")
    @classmethod
    def _motivo_descritivo(cls, v: str) -> str:
        if len(str(v or "").strip()) < 10:
            raise ValueError(
                "o motivo precisa ter ao menos 10 caracteres além de espaços. "
                "Ele vai para o recibo e é a única explicação que sobra quando "
                "alguém pergunta, semanas depois, por que essa campanha existe.")
        return v
    # Impressão devolvida pela prova. A rota recalcula sobre o pedido recebido;
    # trocar uma keyword, headline, verba ou destino depois de revisar invalida
    # a autorização antes de qualquer consulta de escrita.
    plano_impressao: Optional[str] = None
    # Booleano deliberadamente explícito: autoriza criar PAUSADA, nunca ativar.
    confirmar_criacao_pausada: bool = False


@router.post("/subir")
async def subir(
    body: SubirEntrada = Body(...),
    identidade: Identidade = Depends(exigir_admin),
) -> Any:
    """Cria a campanha DE VERDADE. Único caminho de escrita deste módulo.

    ## Esta rota não abre a trava, e não deve

    `gads/modo.py` é de dois fatores: `destravar()` no código **e**
    `FORGE_PERMITIR_ESCRITA=1` no ambiente. Se a variável não estiver definida,
    `EscritaBloqueada` sobe com a mensagem completa e ela é repassada inteira —
    o operador precisa ler que faltou a variável, e onde.

    Mascarar isso com um 500 genérico transformaria a trava de segurança numa
    falha misteriosa, que é o oposto do que ela existe para ser.

    ## A campanha nasce PAUSADA

    `comum.py` já faz isso, e a consequência importa: lançar custa **zero** e já
    produz o veredito real de política do Google sobre recurso PERSISTIDO — a
    única coisa que `validate_only` não dá. Subir não é o fim; é o quarto juiz.

    ## Por que a prova roda de novo aqui

    O `Selo` é do payload, não da sessão. Remontar e reprovar antes de escrever
    custa uma chamada de leitura e fecha a janela entre provar e subir — em que
    o operador poderia ter trocado a copy sem reprovar.

    ## Demand Gen morre antes de qualquer efeito

    Enquanto Demand Gen é só prova validate_only, `/subir` recusa esse canal
    antes de escopo, canário, ponte, cliente, trava ou mutate. Um payload
    inválido nem chega aqui: morre na validação do envelope.

    ## O portão da casa vem ANTES da trava para canais autorizáveis

    É o único caminho de escrita do módulo, e o `customer_id` chega no corpo.
    Conferir o escopo antes de qualquer outra coisa é o que garante que nem uma
    trava aberta por engano alcança conta de cliente: são duas condições
    independentes, e esta não depende do estado daquela.

    ⚠️ Aqui a conferência é a CARA (`conta_da_casa`, ~1,6 s), não a barata que
    `/provar` usa. `/provar` pode se apoiar no `USER_PERMISSION_DENIED` do
    Google porque `validate_only` não cria nada em desfecho nenhum. Esta rota
    cria. Apoiar a única escrita do módulo numa recusa de terceiro é confiar que
    o comportamento medido hoje seja o de amanhã — e 1,6 s numa ação deliberada
    e rara não é preço.
    """
    if str(body.canal or "SEARCH").strip().upper() == "DEMAND_GEN":
        raise HTTPException(
            status_code=403,
            detail=(
                "DEMAND_GEN é somente prova validate_only nesta onda. /subir, "
                "o canário real e o executor de mutação permanecem fechados; "
                "nada foi enviado."
            ),
        )
    cid, mid = _no_escopo(body.customer_id, body.login_customer_id)
    chave_intencao = _impressao_aprovavel(body, cid=cid, mid=mid)
    try:
        marca = canario.exigir(
            customer_id=cid,
            login_customer_id=mid,
            canal=body.canal,
            budget_diario=body.budget_diario,
            cpc_inicial=body.cpc_inicial,
            chave_intencao=chave_intencao,
            carimbo_nome=body.carimbo_nome,
            confirmar_criacao_pausada=body.confirmar_criacao_pausada,
        )
    except canario.CanarioRecusado as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    pp, sb = _ponte()
    try:
        canal_resolvido, _ = sb.resolver_construtor(body.canal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await asyncio.to_thread(escopo.conta_da_casa, cid)
    except escopo.ForaDoEscopo as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    def _provar_de_novo():
        cockpit = pp.montar_cockpit(pp.carregar(body.opportunity_id, run_id=body.run_id))
        escolha = pp.Escolha(
            grupos={g.tipo: list(g.keywords) for g in body.grupos},
            keywords_fora=list(body.keywords_fora),
            budget_diario=body.budget_diario,
            cpc_inicial=body.cpc_inicial,
            cpc_por_grupo={g.tipo: g.cpc_inicial for g in body.grupos
                           if g.cpc_inicial is not None},
            match_type=body.match_type,
            # O adaptador da fronteira reúne os dois contratos num só. Vazio
            # significa que o pedido não declarou negativa nenhuma, e aí as
            # listas antigas seguem o caminho de sempre.
            criterios=tuple(_criterios_do_corpo(body, pp)),
            negativas_campanha=(),
            negativas_adgroup=(),
            vertical=body.vertical,
            certificacoes=set(body.certificacoes),
            url_final=body.url_final,
            prefixo_nome=marca,
            carimbo_nome=body.carimbo_nome,
            conversao=body.conversao,
            estrategia_lance=body.estrategia_lance,
            # A doutrina P7 é do sistema, não do chamador: um conjunto, sempre.
            # A sub-intenção continua servindo à triagem no cockpit.
            conjunto_unico=True,
        )
        plano = pp.montar_brief(cockpit, escolha, copy=_copy_do_corpo(body.texto_do_anuncio))
        preparo = sb.preparar(
            cid, plano.brief, login_customer_id=mid, canal=canal_resolvido,
            ai_max=body.ai_max,
        )
        return plano, preparo

    try:
        plano, preparo = await asyncio.to_thread(_provar_de_novo)
    except HTTPException:
        # ⚠️ TEM DE VIR ANTES do `except Exception`. `_criterios_do_corpo` roda
        # dentro da thread e levanta `HTTPException(422)` para data ISO
        # inválida; `HTTPException` NÃO é `ValueError`, então sem esta linha
        # ela caía no genérico abaixo e o operador recebia 500 "explodiu" no
        # lugar de "a data não é AAAA-MM-DD".
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("reprova do card %s explodiu", body.opportunity_id)
        raise HTTPException(status_code=500, detail=str(exc)[:400]) from exc

    if not preparo.selo:
        # ⚠️ O `detail` carrega o PREPARO INTEIRO, não uma frase.
        #
        # A versão anterior dizia "rode /provar para ver qual juiz reprovou" —
        # e `/provar` é a chamada mais lenta do fluxo. A tela era mandada
        # repetir de graça um trabalho que acabara de ser feito aqui dentro,
        # para descobrir o que esta função já tinha na mão.
        raise HTTPException(
            status_code=409,
            detail={
                "mensagem": "O payload não passou na prova — nada foi enviado.",
                "preparo": projecao.preparo(preparo),
            },
        )

    # O operador aprova a impressão das OPERAÇÕES efetivas, depois de qualquer
    # autocorreção. O pedido cru serve apenas para reconstruir; nunca autoriza.
    if body.plano_impressao != preparo.selo.impressao:
        raise HTTPException(
            status_code=409,
            detail=(
                "O payload efetivo mudou depois da prova (inclusive por "
                "autocorreção), ou a impressão aprovada não foi enviada. Rode "
                "a prova novamente e revise o plano resultante. Nada foi criado."
            ),
        )

    # Camada de idempotência REMOTA. Se a chamada anterior perdeu a resposta,
    # repetir o mesmo plano não aposta que nada foi criado: procura a marca
    # estável na conta e para. Falha de leitura também para — ausência de prova
    # nunca libera uma segunda campanha.
    try:
        existentes_marca = await asyncio.to_thread(
            canario.campanhas_com_marca,
            customer_id=cid,
            login_customer_id=mid,
            marca=marca,
        )
        existentes_destino = await asyncio.to_thread(
            canario.campanhas_com_destino,
            customer_id=cid,
            login_customer_id=mid,
            url_final=plano.brief.url_final,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("pré-checagem remota do canário %s falhou", marca)
        raise HTTPException(
            status_code=503,
            detail=(
                "Não consegui provar que este plano ainda não existe na conta. "
                "Por segurança, nada foi criado; tente a verificação novamente."
            ),
        ) from exc
    existentes = {
        c["campaign_id"]: c for c in (*existentes_marca, *existentes_destino)
    }
    if existentes:
        ids = ", ".join(sorted(existentes))
        raise HTTPException(
            status_code=409,
            detail=(
                f"Este plano ou sua URL final já aparece na conta como "
                f"campanha(s) {ids}, sob a marca {marca}. Nada foi reenviado. "
                "Abra o inventário e "
                "reconcilie o recibo antes de qualquer nova tentativa."
            ),
        )

    # ═══════════════════════════════════════════════════════════════════════
    # O LEDGER, ANTES DA ÚNICA CHAMADA QUE MUTA
    # ═══════════════════════════════════════════════════════════════════════
    #
    # ⚠️ A ordem aqui é o assunto inteiro desta rota, e ela não é arbitrária.
    #
    # A pré-checagem remota acima é LEITURA: ela não cria nada na conta, e é
    # justamente ela que decide se vale a pena chamar. Abrir o recibo antes dela
    # teria um custo assimétrico — uma falha transitória de leitura deixaria um
    # `em_voo` órfão, e a camada 4 da v10_03 passaria a bloquear este item até
    # alguém reconciliar uma chamada que nunca saiu. O recibo cobre o MUTATE.
    #
    # `despachar` grava a aprovação vinculada ao plano e o recibo `em_voo` na
    # MESMA transação, e commita. Se ele levantar, `sb.subir` não é alcançado:
    # erro de persistência bloqueia o mutate, e nunca o contrário.
    ledger = _ledger()

    # ⚠️ LEDGER AUSENTE É RECUSA, NÃO PERMISSÃO.
    #
    # A primeira versão desta costura seguia para o mutate quando o Supabase não
    # estava configurado, "para não quebrar o modo dry". Mas `/subir` não tem
    # modo dry: ele cria campanha de verdade. Criar sem recibo produz exatamente
    # o objeto que esta sprint existe para eliminar — uma campanha que existe na
    # conta, não existe aqui, e que ninguém consegue reconciliar depois porque
    # não há chave, item nem recibo para procurar.
    #
    # Um processo sem ledger pode provar à vontade (`/provar` não escreve nada);
    # o que ele não pode é escrever.
    if not ledger.disponivel:
        raise HTTPException(
            status_code=503,
            detail=(
                "O ledger de lançamento não está configurado neste processo, "
                "então não há onde registrar a intenção e o recibo. NADA foi "
                "enviado ao Google: uma campanha criada sem recibo é uma "
                "campanha que ninguém consegue reconciliar depois."
            ),
        )

    despacho = None
    # ⚠️ DENTRO do try, e não antes dele. A derivação do plano canônico pode
    # recusar (valor não representável em micros), e uma recusa que nasce fora
    # do try escapa como 500 nu — que foi exatamente o defeito original, só que
    # com outro nome. Recusa de derivação é 409 com motivo, sem recibo aberto.
    try:
        plano_canonico = plano_do_ledger(body, cid=cid, mid=mid)
    except PlanoIrrepresentavel as exc:
        raise HTTPException(
            status_code=409,
            detail=(f"O plano aprovado não tem representação canônica para o "
                    f"ledger: {exc}. Nada foi registrado e nada foi enviado "
                    "ao Google."),
        ) from exc

    try:
        registro = await ledger.abrir(
            plataforma="GOOGLE_ADS",
            conta_externa=cid,
            canal=preparo.canal,
            objetivo="leads",
            rotulo=str(getattr(plano.brief, "titulo", "")
                       or body.vertical or "campanha"),
            plano=plano_canonico,
            plano_impressao=preparo.selo.impressao,
            declarada_por=identidade.email or identidade.sub,
            declarada_com_base_em=f"oportunidade:{body.opportunity_id}",
            blueprint_chave=f"{preparo.canal.lower()}-canario",
            blueprint_titulo=f"{preparo.canal} — canário pausado",
            blueprint_corpo={"canal": preparo.canal, "cria_pausada": True},
            destino_url=plano.brief.url_final,
            evidencia={"chave_intencao": chave_intencao,
                       "marca_remota": marca,
                       "run_id": body.run_id},
            # As provas que de fato aconteceram, cada uma na sua camada. A
            # leitura remota entra como prova porque foi ela que autorizou a
            # chamada — e uma prova que não fica registrada não é prova.
            validacoes=[
                {"camada": "local", "regra": "brief_montado",
                 "resultado": "passou",
                 "validado_por": identidade.email or identidade.sub},
                {"camada": "validate_only", "regra": "selo_do_preparo",
                 "resultado": "passou",
                 "detalhe": {"impressao": preparo.selo.impressao}},
                {"camada": "local", "regra": "idempotencia_remota",
                 "resultado": "passou",
                 "mensagem": None,
                 "detalhe": {"marca": marca,
                             "encontradas": 0,
                             "url_final": plano.brief.url_final}},
            ],
        )
        despacho = await ledger.despachar(
            idempotency_key=registro["idempotency_key"],
            plataforma="GOOGLE_ADS",
            conta_externa=cid,
            canal=preparo.canal,
            aprovacao_impressao=preparo.selo.impressao,
            aprovado_por=identidade.email or identidade.sub,
            aprovado_por_sub=identidade.sub,
            aprovacao_observacao=body.motivo,
        )
    except led.LedgerRecusou as exc:
        # Uma guarda do banco disparou. Nada foi enviado ao Google, e a
        # mensagem da guarda é acionável — repassá-la inteira vale mais que
        # traduzi-la para "não foi possível".
        raise HTTPException(
            status_code=409,
            detail=(f"O ledger de lançamento recusou: {exc}. "
                    "Nada foi enviado ao Google."),
        ) from exc
    except led.LedgerIndisponivel as exc:
        raise HTTPException(
            status_code=503,
            detail=("Não consegui registrar a intenção e o recibo antes de "
                    f"criar a campanha ({exc}). Por segurança, NADA foi "
                    "enviado ao Google: uma campanha que nasce sem recibo é "
                    "uma campanha que ninguém consegue reconciliar depois."),
        ) from exc

    try:
        recibo = await asyncio.to_thread(sb.subir, preparo, motivo=body.motivo)
    except (sb.TravaAberta, sb.PayloadNaoValidado, sb.CanalSemMutacaoReal) as exc:
        # Guardas locais do executor: as três são levantadas por funções nomeadas
        # no TOPO de `subir()`, antes do `with modo.destravar()` — ou seja, antes
        # de o pré-recibo existir e antes de qualquer byte sair. Nada foi criado,
        # e o item continua reentrável. É a prova de origem que autoriza chamar
        # isto de falha em vez de ignorância.
        await _fechar_recibo_com_erro(ledger, despacho, exc,
                                      codigo=type(exc).__name__)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        from volc_ads.gads.modo import EscritaBloqueada

        if isinstance(exc, EscritaBloqueada):
            await _fechar_recibo_com_erro(ledger, despacho, exc,
                                          codigo="EscritaBloqueada")
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        # ⚠️ A EXCEÇÃO DESCONHECIDA É IGNORÂNCIA, NÃO FALHA.
        #
        # A tentação aqui é carimbar tudo o que sobrou como `erro` — "não voltou
        # recibo, logo não criou". É falso, e o contra-exemplo é curto:
        # `volc_ads.subir` grava o recibo em disco DEPOIS do mutate
        # (`_gravar(recibo, pasta)`, subir.py:917). Um `OSError` ali chega aqui
        # com a campanha JÁ CRIADA na conta. `erro` deixaria o item reentrável,
        # e o reenvio criaria a segunda campanha no mesmo leilão.
        #
        # As exceções que provam ter nascido ANTES da rede — `TravaAberta`,
        # `PayloadNaoValidado`, `EscritaBloqueada` — já saíram acima, como falha
        # confirmada e reentrável. O que chega até aqui não tem essa prova, e
        # sem prova o único desfecho honesto é `sem_resposta`.
        await _fechar_recibo_sem_resposta(ledger, despacho, exc)
        log.exception("subida do card %s ficou indeterminada", body.opportunity_id)
        raise HTTPException(
            status_code=504,
            detail=_detalhe_indeterminado(
                despacho,
                "A chamada de criação não chegou ao fim de forma verificável. "
                "NÃO reenvie: pode haver uma campanha criada na conta. O recibo "
                "ficou registrado e a próxima ação é verificar na conta e "
                "reconciliar."),
        ) from exc

    # ⚠️ O ESTADO QUE O EXECUTOR DEVOLVE — e que a rota ignorava por completo.
    #
    # `volc_ads.subir` NÃO levanta em falha do Google: ele captura `ErroTerminal`
    # e `ErroEsgotado` dentro do `with` e DEVOLVE um `Recibo` com estado
    # `RECUSADO` (a API respondeu; o mutate é atômico, então nada foi criado) ou
    # `INDETERMINADO` (não respondeu). Até 31/08/2026 esta rota só olhava
    # exceção — `grep recibo.estado` não achava nada — e por isso uma recusa
    # RESPONDIDA virava 200 com "a campanha existe, e está pausada".
    #
    # Os três estados mapeiam um-a-um nos três desfechos do ledger, e o mapa é
    # a coisa toda: recusado ≠ sem resposta, e nenhum dos dois é sucesso.
    estado = str(getattr(recibo, "estado", "") or "").strip().upper()

    if estado == sb.RECUSADO:
        fechamento = await _fechar_recibo_com_erro(
            ledger, despacho, _mensagem_do_recibo(recibo),
            codigo=_erro_codigo_do_recibo(recibo),
            resposta_bruta=_resposta_bruta_do_recibo(recibo))
        log.warning("subida do card %s recusada pelo Google", body.opportunity_id)
        raise HTTPException(
            status_code=502,
            detail={
                "estado": "recusado",
                "mensagem": _mensagem_do_recibo(recibo),
                "erro_codigo": _erro_codigo_do_recibo(recibo),
                "request_id": str(getattr(recibo, "request_id", "") or ""),
                "recibo_id": getattr(despacho, "recibo_id", None),
                "item_id": getattr(despacho, "item_id", None),
                # ⚠️ A permissão é a EFETIVA, não a teórica.
                #
                # A plataforma respondeu que não criou e o mutate é atômico, então
                # do lado do Google reenviar é seguro. Mas se o `fechar_erro`
                # falhou, o recibo local continua `em_voo` — e a camada 4 vai
                # recusar a próxima tentativa. Dizer "pode reenviar" aí seria
                # mandar o operador bater numa porta que já sabemos estar
                # trancada; a saída real passa a ser reconciliar.
                "reenvio_permitido": fechamento.get("desfecho") == "erro",
                "ledger": fechamento,
            },
        )

    if estado != sb.ACEITO:
        # `INDETERMINADO` e qualquer estado que não reconhecemos caem juntos, de
        # propósito: um vocabulário novo do executor que chegasse aqui como
        # "sucesso por omissão" seria a pior falha silenciosa deste fluxo.
        motivo = (_mensagem_do_recibo(recibo) if estado == sb.INDETERMINADO
                  else f"o executor devolveu o estado {estado or '(vazio)'}, "
                       "que esta rota não sabe interpretar")
        fechamento = await _fechar_recibo_sem_resposta(
            ledger, despacho, motivo,
            codigo=_erro_codigo_do_recibo(recibo))
        log.warning("subida do card %s ficou indeterminada (estado=%s)",
                    body.opportunity_id, estado or "(vazio)")
        raise HTTPException(
            status_code=504,
            detail=_detalhe_indeterminado(despacho, motivo, ledger=fechamento,
                                          recibo=recibo),
        )

    # ⚠️ A CAMPANHA PASSA A EXISTIR NO NOSSO BANCO, e não só na conta do Google.
    #
    # Até 19/08/2026 o `/subir` gravava o recibo em ARQUIVO e mais nada: a
    # campanha nascia invisível para o sistema. O sintoma que o operador viu é
    # o mais óbvio deles — depois de publicar, o cockpit continuava oferecendo
    # "lançar campanha", porque não tinha como saber que já havia lançado.
    #
    # O menos óbvio é pior: sem `funnel_run_id` gravado, a junta FUNIL→CAMPANHA
    # fica aberta e nada cruza o custo do anúncio com o comportamento da página.
    #
    # A gravação NÃO derruba o lançamento: a campanha já existe na conta quando
    # chegamos aqui, e falhar no INSERT depois disso seria trocar um problema de
    # registro por um de veiculação. O erro vira aviso no recibo.
    projetado = projecao.recibo(recibo)
    projetado["aprovacao"] = {
        "plano_impressao": preparo.selo.impressao,
        "chave_intencao": chave_intencao,
        "aprovado_por_sub": identidade.sub,
        "aprovado_por_email": identidade.email,
        "confirmou_criacao_pausada": True,
        "ativacao_incluida": False,
        "marca_remota": marca,
    }

    # ⚠️ O ID EXTERNO É A ÚNICA COISA QUE SÓ EXISTE DEPOIS DO MUTATE.
    #
    # Fechar o recibo grava, numa transação só, o desfecho, o id externo com a
    # hora da leitura e a identidade da instância. Se ESTA escrita falhar, o
    # recibo fica `em_voo` — e isso é a verdade, não um bug: alguém precisa ir
    # à conta reconciliar. É estritamente melhor que o comportamento anterior,
    # em que a falha do registro virava um aviso e o rastro se perdia.
    campaign_id = _campaign_id_do_recibo(recibo)
    projetado["ledger"] = await _fechar_recibo_com_sucesso(
        ledger, despacho, campaign_id=campaign_id, cid=cid,
        recibo=recibo, preparo=preparo,
    )

    aviso_registro = await _registrar_campanha(
        body, recibo, cid, mid, canal=preparo.canal,
    )
    if aviso_registro:
        projetado["aviso_registro"] = aviso_registro
    return {"recibo": projetado}


# ---------------------------------------------------------------------------
# A saída de `indeterminado` — a leitura tardia, como porta e não como função
# ---------------------------------------------------------------------------
#
# `Ledger.reconciliar` existia desde a v10_03 e não tinha chamador de produção:
# só um teste. Isso é pior do que parece, porque `indeterminado` é o desfecho
# NORMAL de qualquer chamada que não respondeu — e a única saída documentada
# dele era "alguém com psql". Um estado terminal na prática.
#
# ⚠️ Esta rota LÊ e FECHA. Ela nunca reenvia o mutate. É a diferença entre
# descobrir o que aconteceu e apostar que não aconteceu nada.


class ReconciliarEntrada(BaseModel):
    """O pedido de leitura tardia sobre um item que ficou indeterminado.

    ⚠️ `campaign_id` é OPCIONAL, e essa é a diferença entre uma saída e uma
    saída que funciona. O item que mais precisa de reconciliação é justamente
    o que NÃO tem id externo: a chamada não respondeu, e por isso nunca houve
    `resource_name` para guardar. Exigir o id transformaria a rota numa porta
    que só abre para quem já não precisa dela.

    Sem id, a busca é pela MARCA — `VOLC-CANARY-<impressao[:12]>`, derivada do
    plano aprovado e agora estável entre tentativas. É o mesmo método que a
    pré-checagem de idempotência usa antes do mutate, e o banco o reconhece:
    `trafego_verificacao.metodo` aceita `busca_por_marca`.
    """

    item_id: str
    customer_id: str
    campaign_id: Optional[str] = None
    marca: Optional[str] = None
    login_customer_id: Optional[str] = None
    motivo: Optional[str] = None

    @model_validator(mode="after")
    def _exige_um_criterio(self):
        if not str(self.campaign_id or "").strip() and not str(self.marca or "").strip():
            raise ValueError(
                "reconciliar exige `campaign_id` OU `marca`. Sem critério de "
                "busca não há leitura, e sem leitura não há o que reconciliar.")
        return self


def _ler_campanha_na_conta(*, customer_id: str, login_customer_id: str,
                           campaign_id: Optional[str] = None,
                           marca: Optional[str] = None,
                           ) -> tuple[Dict[str, str], ...]:
    """Lê a conta por id OU por marca. Somente leitura.

    ⚠️ `search` não muta nada — é a mesma leitura que a pré-checagem de
    idempotência já fazia antes do recibo. A recusa a qualquer coisa que mute
    mora no fato de que esta função não constrói operação nenhuma.
    """
    kid = str(campaign_id or "").strip()
    marca_limpa = str(marca or "").strip()
    if kid:
        if not re.fullmatch(r"[0-9]{1,20}", kid):
            raise ValueError(
                f"campaign_id={campaign_id!r} precisa conter somente dígitos.")
        onde = f"campaign.id = {int(kid)}"
    elif marca_limpa:
        # ⚠️ `_` NÃO ENTRA, e a razão não é estética.
        #
        # A marca vira `LIKE '<marca>%'`, e no LIKE o `_` é curinga de UM
        # caractere. Aceitá-lo faria `marca="____"` casar com qualquer campanha
        # de quatro letras da conta — e a reconciliação passaria a "encontrar"
        # campanha alheia e carimbá-la no item. A marca real é
        # `VOLC-CANARY-<hex>`: letras, dígitos e hífen, nunca sublinhado.
        if not re.fullmatch(r"[A-Za-z0-9-]{4,64}", marca_limpa):
            raise ValueError(
                f"marca={marca!r} tem formato inesperado; ela é derivada da "
                "impressão do plano e só contém letras, dígitos e '-'. O '_' "
                "fica de fora porque é curinga no LIKE do GAQL.")
        onde = f"campaign.name LIKE '{marca_limpa}%'"
    else:
        raise ValueError("reconciliar exige `campaign_id` ou `marca`.")
    _ponte()
    from volc_ads.gads.client import cliente

    try:
        servico = cliente(login_customer_id).get_service("GoogleAdsService")
        linhas = servico.search(
            customer_id=escopo.so_digitos(customer_id),
            query=("SELECT campaign.id, campaign.name, campaign.status "
                   f"FROM campaign WHERE {onde}"))
        encontradas: Dict[str, Dict[str, str]] = {}
        for linha in linhas:
            c = linha.campaign
            encontradas[str(c.id)] = {
                "campaign_id": str(c.id),
                "campaign_name": str(getattr(c, "name", "") or ""),
                "status": str(getattr(getattr(c, "status", ""), "name",
                                      getattr(c, "status", "")) or ""),
            }
    except Exception as exc:  # noqa: BLE001
        # ⚠️ Falhar a leitura NÃO é "a campanha não existe". Confundir os dois
        # aqui fecharia o recibo como `sem_resposta` com base em ignorância
        # nossa, apagando a diferença entre "conferi e não está" e "não conferi".
        raise LeituraDaContaIndisponivel(str(exc)[:400]) from exc
    return tuple(encontradas[k] for k in sorted(encontradas))


@router.post("/reconciliar")
async def reconciliar_lancamento(
    body: ReconciliarEntrada = Body(...),
    identidade: Identidade = Depends(exigir_admin),
) -> Any:
    """Lê a conta e fecha o MESMO recibo. Nunca reenvia o mutate."""
    cid, mid = _no_escopo(body.customer_id,
                          body.login_customer_id or escopo.MCC_DA_CASA)
    ledger = _ledger()
    if not ledger.disponivel:
        raise HTTPException(
            status_code=503,
            detail=("O ledger de lançamento não está configurado neste "
                    "processo, então não há recibo para fechar. Nada mudou."),
        )

    # Os três resultados possíveis da leitura, e eles são TRÊS — não dois.
    # `achou=None` é um fato sobre nós, não sobre a conta, e o banco registra a
    # verificação sem mover o item.
    # ⚠️ O ITEM PRECISA SER DESTA CONTA, e nada abaixo confere isso por nós.
    #
    # A entrada traz `item_id`, `customer_id` e o critério de busca como três
    # campos independentes, e `trafego_ledger_reconciliar` procura o item só
    # pelo id — ela não confere o lote. Sem a checagem aqui, um admin que
    # trocasse um id por engano reconciliaria o item da conta A com a campanha
    # da conta B, carimbando no item uma identidade externa que não é dele.
    # Isso não cria campanha nenhuma, mas corrompe a procedência de duas.
    try:
        conta_do_item = await ledger.conta_externa_do_item(body.item_id)
    except led.LedgerIndisponivel as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Não consegui ler o item para conferir a conta: {exc}.",
        ) from exc
    if conta_do_item is None:
        raise HTTPException(
            status_code=404,
            detail=f"O item {body.item_id} não existe. Nada foi reconciliado.")
    if escopo.so_digitos(conta_do_item) != escopo.so_digitos(cid):
        raise HTTPException(
            status_code=409,
            detail=(f"O item {body.item_id} pertence à conta {conta_do_item}, "
                    f"e não à {cid}. Reconciliar um item com a campanha de "
                    "outra conta trocaria a procedência das duas. Nada mudou."),
        )

    achou: Optional[bool]
    try:
        encontradas = await asyncio.to_thread(
            _ler_campanha_na_conta, customer_id=cid, login_customer_id=mid,
            campaign_id=body.campaign_id, marca=body.marca)
        achou = len(encontradas) >= 1
        indisponivel = ""
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LeituraDaContaIndisponivel as exc:
        encontradas = ()
        achou = None
        indisponivel = str(exc)
        log.warning("leitura da conta para reconciliar o item %s falhou: %s",
                    body.item_id, exc)

    # ⚠️ DUAS CAMPANHAS NÃO SE RESOLVEM SOZINHAS.
    #
    # `trafego_verificacao` documenta que `quantidade_encontrada >= 2` é o
    # alarme de duplicidade JÁ CONSUMADA. Escolher `encontradas[0]` aí seria a
    # máquina decidindo qual das duas campanhas é "a certa" — e carimbando a
    # outra como se não existisse. A leitura FICA registrada, com a quantidade
    # e a lista, para que a decisão seja humana e informada.
    if achou is True and len(encontradas) > 1:
        await ledger.reconciliar(
            item_id=body.item_id, metodo="listagem_da_conta", achou=None,
            verificado_por=identidade.email or identidade.sub,
            plataforma="GOOGLE_ADS", conta_externa=cid,
            motivo=(f"{len(encontradas)} campanhas casaram o critério; "
                    "duplicidade consumada exige decisão humana"),
            divergencia={"campanhas_encontradas": list(encontradas)},
        )
        raise HTTPException(
            status_code=409,
            detail={
                "estado": "duplicidade_consumada",
                "mensagem": (
                    f"O critério casou {len(encontradas)} campanhas na conta. "
                    "A leitura ficou registrada e NADA foi carimbado: escolher "
                    "uma delas automaticamente esconderia a outra. Decida qual "
                    "é a campanha deste item e reconcilie por `campaign_id`."),
                "item_id": body.item_id,
                "campanhas": list(encontradas),
                "reenvio_permitido": False,
            },
        )

    primeira = encontradas[0] if encontradas else {}
    if achou is None:
        motivo = body.motivo or f"não consegui ler a conta: {indisponivel}"
    elif achou:
        motivo = body.motivo or "campanha encontrada na leitura da conta"
    else:
        motivo = body.motivo or "conferi a conta e a campanha não está lá"

    try:
        reconciliado = await ledger.reconciliar(
            item_id=body.item_id,
            # O método vai ao banco como foi de fato: a CHECK de
            # `trafego_verificacao` só aceita os três nomes conhecidos, e
            # registrar "por id" uma busca por marca mentiria na auditoria.
            metodo=("busca_por_id" if str(body.campaign_id or "").strip()
                    else "busca_por_marca"),
            achou=achou,
            verificado_por=identidade.email or identidade.sub,
            plataforma="GOOGLE_ADS",
            conta_externa=cid,
            id_externo=str(primeira.get("campaign_id") or "") or None,
            quantidade=None if achou is None else len(encontradas),
            motivo=motivo,
            estado_externo=primeira.get("status"),
            divergencia={"campaign_id_solicitado": str(body.campaign_id or "") or None,
                         "marca_solicitada": str(body.marca or "") or None,
                         "campanhas_encontradas": list(encontradas)},
        )
    except led.LedgerRecusou as exc:
        raise HTTPException(
            status_code=409,
            detail=f"O ledger recusou a reconciliação: {exc}. Nada mudou.",
        ) from exc
    except led.LedgerIndisponivel as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Não consegui fechar o recibo no ledger: {exc}.",
        ) from exc

    return {
        "reconciliacao": reconciliado,
        "leitura": {
            "customer_id": cid,
            "campaign_id": str(body.campaign_id or "") or None,
            "marca": str(body.marca or "") or None,
            "achou": achou,
            "quantidade": None if achou is None else len(encontradas),
            "campanhas": list(encontradas),
            "indisponivel": indisponivel or None,
        },
        # Dito com todas as letras porque é a propriedade que esta rota existe
        # para preservar, e a que uma mudança futura poderia quebrar sem notar.
        "reenvio_executado": False,
    }


# ---------------------------------------------------------------------------
# Fechamento do recibo — os três desfechos, e o que cada um significa
# ---------------------------------------------------------------------------
#
# Nenhuma destas funções derruba a resposta ao operador. A campanha já existe (ou
# já não existe) na conta quando elas rodam; falhar aqui e transformar isso num
# 500 trocaria um problema de registro por um de veiculação. O que elas NÃO fazem
# é sumir em silêncio: o desfecho do fechamento vai no corpo da resposta, e um
# recibo que continuou `em_voo` é dito com todas as letras.

def _falha_do_recibo(recibo: Any) -> Optional[Dict[str, Any]]:
    """A falha do executor na projeção canônica — a mesma que a tela já lê."""
    falha = getattr(recibo, "falha", None)
    if falha is None:
        return None
    try:
        return projecao._falha(falha)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        # Uma falha que não projeta ainda é uma falha: perder o texto dela aqui
        # apagaria a única explicação que sobra no recibo.
        return {"resumo": str(falha)[:2000], "erros": []}


def _erro_codigo_do_recibo(recibo: Any) -> str:
    falha = _falha_do_recibo(recibo) or {}
    erros = falha.get("erros") or []
    if erros:
        primeiro = erros[0] or {}
        codigo = ".".join(
            p for p in (str(primeiro.get("familia") or ""),
                        str(primeiro.get("codigo") or "")) if p)
        if codigo:
            return codigo
    estado = str(getattr(recibo, "estado", "") or "").strip().lower()
    return f"executor.{estado or 'sem_estado'}"


def _mensagem_do_recibo(recibo: Any) -> str:
    falha = _falha_do_recibo(recibo) or {}
    if falha.get("resumo"):
        return str(falha["resumo"])[:2000]
    explicacao = str(getattr(recibo, "explicacao", "") or "").strip()
    estado = str(getattr(recibo, "estado", "") or "").strip() or "estado vazio"
    return (explicacao or f"o executor devolveu {estado} sem explicação")[:2000]


def _resposta_bruta_do_recibo(recibo: Any) -> Dict[str, Any]:
    """A evidência crua do que o executor disse, para o `resposta_bruta`.

    ⚠️ Só o desfecho `erro` a persiste: o ramo `sem_resposta` de
    `trafego_ledger_fechar` grava `erro_codigo` e `erro_mensagem` e ignora
    `p_resposta_bruta`. Mandá-la ali seria acreditar num registro que não
    acontece — por isso o chamador de `sem_resposta` não a passa.
    """
    return {
        "estado": str(getattr(recibo, "estado", "") or ""),
        "request_id": str(getattr(recibo, "request_id", "") or ""),
        "explicacao": str(getattr(recibo, "explicacao", "") or ""),
        "falha": _falha_do_recibo(recibo),
    }


def _detalhe_indeterminado(despacho: Any, mensagem: str, *,
                           ledger: Optional[Dict[str, Any]] = None,
                           recibo: Any = None) -> Dict[str, Any]:
    """O corpo do 504. `reenvio_permitido` é False e não tem exceção."""
    detalhe: Dict[str, Any] = {
        "estado": "indeterminado",
        "mensagem": mensagem,
        "recibo_id": getattr(despacho, "recibo_id", None),
        "item_id": getattr(despacho, "item_id", None),
        "reenvio_permitido": False,
        "proxima_acao": "reconciliar_na_conta",
    }
    if recibo is not None:
        detalhe["erro_codigo"] = _erro_codigo_do_recibo(recibo)
        detalhe["request_id"] = str(getattr(recibo, "request_id", "") or "")
    if ledger is not None:
        detalhe["ledger"] = ledger
    return detalhe


def _campaign_id_do_recibo(recibo: Any) -> str:
    """O id que a API atribuiu, extraído do `resource_name`. Única fonte dele."""
    rn = next(
        (c.resource_name for c in (getattr(recibo, "criados", ()) or ())
         if "campaign_result" in getattr(c, "tipo", "") or "/campaigns/" in c.resource_name),
        "")
    return rn.rsplit("/", 1)[-1] if rn and "/campaigns/" in rn else ""


async def _fechar_recibo_com_sucesso(
    ledger: Any, despacho: Any, *, campaign_id: str, cid: str,
    recibo: Any, preparo: Any,
) -> Dict[str, Any]:
    if despacho is None:
        return {"registrado": False,
                "motivo": "o ledger não estava disponível quando a campanha foi criada"}
    if not campaign_id:
        # Criou, mas não sabemos o quê. `sucesso` exige id externo justamente
        # para que este caso não vire um sucesso sem rastro.
        await _fechar_recibo_sem_resposta(
            ledger, despacho,
            "a API não devolveu resource_name de campanha")
        return {"registrado": True, "desfecho": "sem_resposta",
                "recibo_id": despacho.recibo_id, "item_id": despacho.item_id,
                "motivo": "a API não devolveu o id da campanha; reconcilie na conta"}
    try:
        fechado = await ledger.fechar_sucesso(
            recibo_id=despacho.recibo_id,
            id_externo=campaign_id,
            plataforma="GOOGLE_ADS",
            conta_externa=cid,
            operacoes_consumidas=len(getattr(recibo, "criados", ()) or ()),
            resposta_bruta={"canal": preparo.canal,
                            "nome_campanha": getattr(recibo, "nome_campanha", "")},
        )
        return {"registrado": True, "desfecho": "sucesso",
                "recibo_id": despacho.recibo_id, "item_id": despacho.item_id,
                "id_externo": fechado.get("id_externo") or campaign_id,
                "item_estado": fechado.get("item_estado")}
    except Exception as exc:  # noqa: BLE001
        log.exception("fechamento do recibo %s falhou", despacho.recibo_id)
        return {"registrado": False, "desfecho": "em_voo",
                "recibo_id": despacho.recibo_id, "item_id": despacho.item_id,
                "id_externo": campaign_id,
                "motivo": (f"a campanha {campaign_id} existe na conta, mas o recibo "
                           f"continuou em voo: {str(exc)[:180]}. Reconcilie.")}


async def _fechar_recibo_com_erro(
    ledger: Any, despacho: Any, exc: Any, *, codigo: str,
    resposta_bruta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """A plataforma respondeu que não criou. O item volta a ser reenviável."""
    if despacho is None:
        return {"registrado": False,
                "motivo": "o ledger não estava disponível quando a resposta chegou"}
    try:
        fechado = await ledger.fechar_erro(
            recibo_id=despacho.recibo_id, mensagem=str(exc), codigo=codigo,
            resposta_bruta=resposta_bruta)
        return {"registrado": True, "desfecho": "erro",
                "recibo_id": despacho.recibo_id, "item_id": despacho.item_id,
                "item_estado": (fechado or {}).get("item_estado")}
    except Exception:  # noqa: BLE001
        log.exception("não consegui fechar como erro o recibo %s", despacho.recibo_id)
        # O recibo continua `em_voo`, e isso é a verdade — não um detalhe a
        # esconder de quem vai decidir o próximo passo.
        return {"registrado": False, "desfecho": "em_voo",
                "recibo_id": despacho.recibo_id, "item_id": despacho.item_id,
                "motivo": "o fechamento como erro falhou; reconcilie o recibo"}


async def _fechar_recibo_sem_resposta(
    ledger: Any, despacho: Any, motivo: Any, *, codigo: Optional[str] = None,
) -> Dict[str, Any]:
    """⚠️ Ninguém respondeu. O item vira `indeterminado`, e reenviar fica fechado."""
    if despacho is None:
        return {"registrado": False,
                "motivo": "o ledger não estava disponível quando a chamada saiu"}
    try:
        fechado = await ledger.fechar_sem_resposta(
            recibo_id=despacho.recibo_id, motivo=str(motivo), codigo=codigo)
        return {"registrado": True, "desfecho": "sem_resposta",
                "recibo_id": despacho.recibo_id, "item_id": despacho.item_id,
                "item_estado": (fechado or {}).get("item_estado")}
    except Exception:  # noqa: BLE001
        log.exception(
            "não consegui carimbar `sem_resposta` no recibo %s — ele continua "
            "`em_voo`, que também impede reenvio", despacho.recibo_id)
        return {"registrado": False, "desfecho": "em_voo",
                "recibo_id": despacho.recibo_id, "item_id": despacho.item_id,
                "motivo": "o carimbo de `sem_resposta` falhou; reconcilie o recibo"}


def _hoje_iso() -> str:
    from datetime import date

    return date.today().isoformat()


async def _registrar_campanha(
    body: Any,
    recibo: Any,
    cid: str,
    mid: str,
    *,
    canal: str,
) -> str:
    """Grava a campanha recém-criada em `campaigns`. Devolve aviso, ou vazio.

    O `campaign_id` sai do `resource_name` que a API devolveu — é a única fonte
    dele, porque o id é atribuído pelo Google no momento do mutate.
    """
    campanha_rn = next(
        (c.resource_name for c in (getattr(recibo, "criados", ()) or ())
         if "campaign_result" in getattr(c, "tipo", "") or "/campaigns/" in c.resource_name),
        "")
    if not campanha_rn or "/campaigns/" not in campanha_rn:
        return "a API não devolveu resource_name de campanha; nada foi registrado"
    campaign_id = campanha_rn.rsplit("/", 1)[-1]

    try:
        supa = _supa()
        pp, _ = _ponte()
        cockpit = await asyncio.to_thread(
            lambda: pp.montar_cockpit(pp.carregar(body.opportunity_id, run_id=body.run_id)))
        conta = getattr(cockpit, "conta", None)
        linha = {
            "campaign_id": campaign_id,
            "campaign_name": getattr(recibo, "nome_campanha", ""),
            "customer_id": cid,
            "status": "Paused",              # nasce PAUSED, sempre (P7)
            "google_ads_status": "PAUSED",
            # Canal resolvido pelo MESMO registry que construiu e provou o
            # payload. Nunca grave o texto cru recebido no request.
            "advertising_channel_type": canal,
            "bidding_strategy": getattr(body, "estrategia_lance", "MANUAL_CPC"),
            "budget_amount": body.budget_diario,
            "target_value": body.cpc_inicial,
            # É ESTA coluna que fecha a junta FUNIL→CAMPANHA. Sem ela ninguém
            # cruza o custo do anúncio com o comportamento da página.
            "funnel_run_id": body.run_id,
            # ⚠️ `start_date` é NOT NULL na tabela, e `lp_path` é coluna GERADA
            # (o Postgres a extrai do `campaign_name` — mais uma razão para a
            # taxonomia `… / … / {URL}` estar certa). Mandar `lp_path` no INSERT
            # levanta "cannot insert a non-DEFAULT value into a generated column".
            "start_date": _hoje_iso(),
            "project_id": getattr(conta, "project_id", None) if conta else None,
            "status_source": "volc_os",
        }
        await supa.insert("campaigns", [{k: v for k, v in linha.items() if v is not None}])
        return ""
    except Exception as exc:  # noqa: BLE001
        log.exception("registro da campanha %s falhou", campaign_id)
        return f"a campanha existe na conta, mas não foi registrada no banco: {str(exc)[:180]}"


@router.get("/trava")
async def estado_da_trava() -> Any:
    """O estado da trava de escrita, para a tela saber antes de tentar.

    Mostrar "subir" como disponível e só descobrir no clique que a trava está
    fechada é desperdiçar a prova inteira do operador. Esta rota é leitura pura
    de `modo.estado()`.
    """
    _, _ = _ponte()
    from volc_ads.gads import modo

    e = modo.estado()
    return {
        **e,
        # Escopo da janela de criação, separado da trava global. Abrir a trava
        # não autoriza outra conta nem outro canal.
        "canario": canario.POLITICA.para_json(),
        # ⚠️ ESTE TEXTO VAI PARA A TELA DO OPERADOR.
        #
        # A versão anterior citava `destravar()` e o nome da variável de
        # ambiente. Quem lê a tela não tem acesso ao código nem ao servidor: a
        # frase descrevia com precisão uma ação que a pessoa não pode executar,
        # e o efeito prático de instruções impossíveis é o operador concluir
        # que o sistema está quebrado.
        #
        # A regra NÃO mudou — continuam sendo os mesmos dois fatores, e
        # `validate_only` continua isento. Mudou só quem a frase considera seu
        # leitor. O detalhe técnico está na docstring desta rota e em
        # `volc_ads/modo.py`, que é onde quem opera o servidor vai procurar.
        "explicacao": (
            "A criação real está restrita ao canário Search da conta Portal "
            "Mundo Mais (547-809-6539), sempre PAUSADO e com confirmação "
            "humana. Validar é leitura e continua liberado."
        ),
    }


# ── as capacidades de quem está na tela ─────────────────────────────────────


@router.get("/capacidades")
async def capacidades_do_operador(
    quem: Identidade = Depends(exigir_usuario),
) -> Any:
    """O que ESTA pessoa pode, neste servidor, agora.

    A tela pergunta antes de desenhar. Sem esta rota ela derivaria tudo de
    `role === 'ADMIN'`, e um administrador de produto veria botões de gasto que
    a trava do servidor recusa no clique — depois de o operador montar o pedido
    inteiro.

    ⚠️ Isto NÃO é a autorização. `exigir_admin` na rota e
    `modo.exigir_leitura_apenas` na saída da requisição continuam valendo
    mesmo que esta resposta minta. Aqui só se projeta o que aquelas duas já
    decidiram — e é por isso que a resposta pode ser lida sem risco.

    Zero segredo na resposta: nem nome de variável de ambiente, nem chave, nem
    caminho de arquivo. `porque_sem_mutacao` é escrito para o operador.
    """
    from volc_ads.gads import modo

    # ⚠️ `env_presente`, e NÃO `escrita_permitida()`.
    #
    # A trava tem dois fatores: a variável de ambiente, que é configuração
    # DURÁVEL do servidor, e `destravar()`, que é global de processo e só vale
    # DENTRO do bloco `with` de uma operação. `escrita_permitida()` exige os
    # dois — e chamada de fora de qualquer bloco ela devolve `False` sempre,
    # inclusive num servidor onde `POST /subir` cria campanha de verdade.
    #
    # Perguntar isso aqui produzia dois danos: a tela dizia ao operador que a
    # permissão está fechada num servidor que escreve, e o Modo Laboratório
    # ficava ligado justamente onde há consequência real. A pergunta desta
    # rota é "este servidor pode escrever?", e quem responde é o fator durável.
    e = modo.estado()
    c = cap.de_identidade(papel=quem.papel,
                          escrita_permitida=bool(e.get("env_presente")))
    return c.json()


# ── o veredito de política ──────────────────────────────────────────────────
#
# ⚠️ ESTA ROTA EXISTE POR CAUSA DE UM FATO MEDIDO, E O FATO É BOM.
#
# Anúncio em campanha PAUSADA é revisado pelo Google normalmente. Medido em
# 19/08/2026 na conta 5478096539: seis anúncios em campanhas `PAUSED`, todos
# com `review_status = REVIEWED`, quatro `APPROVED` e dois `APPROVED_LIMITED`.
#
# A consequência operacional é grande: **subir pausado é o teste de política
# mais barato que existe**. Você descobre se a vertical foi enquadrada, se a
# copy passou e se falta habilitação — sem gastar um centavo, e sem depender
# da resposta do formulário de desenquadramento.
#
# Sem esta rota o operador teria de abrir a interface do Google Ads e caçar o
# status anúncio a anúncio. Com ela, o veredito volta para a tela onde ele
# montou a campanha.

@router.get("/veredito/{customer_id}/{campaign_id}")
async def veredito_de_politica(customer_id: str, campaign_id: str) -> Any:
    """O que o Google decidiu sobre os anúncios desta campanha. Leitura pura.

    Devolve, por anúncio: aprovação, estado da revisão e os tópicos de política
    que pegaram — com o nome do tópico e se é passível de isenção.

    `APPROVED_LIMITED` é o estado que mais importa aqui: o anúncio veicula, mas
    com restrição — tipicamente é ele que denuncia habilitação faltando.
    """
    _ponte()
    # O MCC não vem da URL: ele É a casa. Pedi-lo ao chamador seria deixar a
    # tela escolher sob qual MCC operar — exatamente o que o portão impede.
    cid, mid = _no_escopo(customer_id, escopo.MCC_DA_CASA)

    from volc_ads.gads.client import cliente

    def _ler() -> dict[str, Any]:
        c = cliente(mid)
        svc = c.get_service("GoogleAdsService")
        q = f"""
            SELECT ad_group_ad.ad.id, ad_group_ad.status, ad_group.name,
                   campaign.id, campaign.name, campaign.status,
                   ad_group_ad.policy_summary.approval_status,
                   ad_group_ad.policy_summary.review_status,
                   ad_group_ad.policy_summary.policy_topic_entries
            FROM ad_group_ad
            WHERE campaign.id = {int(campaign_id)}
        """
        anuncios: list[dict[str, Any]] = []
        nome_campanha, status_campanha = "", ""
        for lote in svc.search_stream(customer_id=cid, query=q):
            for r in lote.results:
                nome_campanha = r.campaign.name
                status_campanha = r.campaign.status.name
                ps = r.ad_group_ad.policy_summary
                anuncios.append({
                    "ad_id": str(r.ad_group_ad.ad.id),
                    "ad_group": r.ad_group.name,
                    "status": r.ad_group_ad.status.name,
                    "aprovacao": ps.approval_status.name,
                    "revisao": ps.review_status.name,
                    "topicos": [{
                        "topico": t.topic,
                        "tipo": t.type_.name,
                        # `is_exemptible` é o que separa "peça isenção" de
                        # "reescreva o anúncio". Achatar isso obrigaria o
                        # operador a descobrir na tentativa e erro.
                        "isentavel": bool(getattr(t, "is_exemptible", False)),
                    } for t in ps.policy_topic_entries],
                })
        return {
            "campanha": {"id": campaign_id, "nome": nome_campanha,
                         "status": status_campanha},
            "anuncios": anuncios,
            # `REVIEW_IN_PROGRESS` em todos = o Google ainda não decidiu. A tela
            # precisa distinguir isso de "aprovado", ou o operador conclui cedo
            # demais que passou.
            "em_revisao": all(a["revisao"] in ("REVIEW_IN_PROGRESS", "UNDER_REVIEW")
                              for a in anuncios) if anuncios else False,
            "sem_anuncios": not anuncios,
        }

    try:
        return await asyncio.to_thread(_ler)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("leitura do veredito falhou")
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc


class CopyEditada(BaseModel):
    """A copy corrigida à mão pelo operador."""

    opportunity_id: int
    run_id: Optional[int] = None
    copy: CopyEntrada


@router.patch("/copy")
async def salvar_copy_editada(body: CopyEditada = Body(...)) -> Any:
    """Grava a copy corrigida à mão. Não chama LLM, não custa token.

    ## ⚠️ Por que esta rota existe

    Medido no card 74 em 19/08/2026: depois que o juiz semântico limpou os
    falsos positivos, restou UM item impublicável — um callout de 26 caracteres
    num teto de 25. Sem esta rota, a única saída era refazer a cascata inteira
    (167 s, ~77 mil tokens) para cortar um caractere.

    A edição já existia na tela, mas vivia só no estado do browser: recarregar
    a página descartava a correção e trazia de volta o texto que não sobe.

    ## O que ela NÃO faz

    Não revalida. Quem julga o texto corrigido é `/provar`, com o
    `validate_only` contra a conta real — e é ele que decide se sobe. Validar
    aqui duplicaria o juiz e abriria espaço para os dois discordarem.

    As pendências antigas são LIMPAS: elas descrevem o texto anterior, e mantê-las
    ao lado do texto novo faria a tela acusar defeito que já não existe.
    """
    from datetime import datetime, timezone

    # `_copy_do_corpo` importa `volc_ads.campanha.brief`; sem a ponte o import
    # levanta ModuleNotFoundError. Ver `_ponte()` para por que ele é tarde.
    _ponte()
    supa = _supa()
    linha = await _linha_de_copy(supa, body.opportunity_id, body.run_id)
    if not linha:
        raise HTTPException(
            status_code=404,
            detail="não há copy gravada para este card. Escreva antes de editar.")

    copy = _copy_do_corpo(body.copy)
    # ⚠️ Os nomes são os da TABELA (`pendentes`, não `pendencias`), e não há
    # coluna `editada_em`. Inventar coluna faz o PostgREST devolver 400 sem
    # dizer qual — o que custou uma rodada de depuração em 19/08/2026.
    valores = {
        "copy": dataclasses.asdict(copy) if dataclasses.is_dataclass(copy) else copy,
        "pendentes": [],
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await supa.patch(TABELA_COPY, {"id": f"eq.{linha['id']}"}, valores)
    except Exception as exc:  # noqa: BLE001
        log.exception("gravação da copy editada falhou")
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc

    nova = await _linha_de_copy(supa, body.opportunity_id, body.run_id)
    return _copy_para_tela(nova) if nova else {"existe": False}


class RemoverEntrada(BaseModel):
    """O desfazer do lançamento."""

    customer_id: str
    campaign_id: str
    # Mesma exigência do `/subir`: `destravar()` recusa menos de 10 caracteres.
    # Remover sem motivo registrado é um recurso que some sem ninguém saber por quê.
    motivo: str
    # Remover campanha ENABLED é outra conversa: ela está gastando agora. Exigir
    # o sinal explícito impede o desfazer casual virar o desfazer perigoso.
    remover_ativa: bool = False


@router.post("/remover", dependencies=[Depends(exigir_admin)])
async def remover_campanha(body: RemoverEntrada = Body(...)) -> Any:
    """Remove uma campanha. Passa pelas MESMAS travas do `/subir`.

    ## Por que isto é rota e não script

    A trava de escrita é de dois fatores, e o segundo mora no processo do
    servidor. Um script à parte só funcionaria se alguém exportasse
    `FORGE_PERMITIR_ESCRITA=1` no shell dele — o que é exatamente o hábito que a
    trava existe para impedir. Aqui a chave continua onde o operador a pôs.

    ## O que ela confere, na ordem

    1. **escopo** — a conta é da casa, ou 403;
    2. **status** — campanha `ENABLED` exige `remover_ativa: true`, porque ela
       está gastando neste momento e o desfazer casual não pode alcançá-la;
    3. **trava** — `destravar(motivo)` com motivo descritivo.

    `REMOVED` é terminal no Google Ads: não há como voltar atrás pela API. O
    histórico e as métricas permanecem; o que some é a possibilidade de reativar.
    """
    _ponte()
    cid, mid = _no_escopo(body.customer_id, escopo.MCC_DA_CASA)

    # ⚠️ `exigir_escopo` confere o MCC, não a CONTA. Medido em 19/08/2026:
    # pedir a remoção numa conta de terceiro passou por ele e só o Google
    # recusou, com UNAUTHENTICATED. Para uma rota que LÊ isso basta — o terceiro
    # muro segura. Para uma que REMOVE, não: o caso perigoso é o login certo
    # operando conta de terceiro sob o MCC, e aí o Google não recusaria.
    #
    # `conta_da_casa` custa ~1,6 s (leitura da árvore). É o preço certo para
    # uma operação que não tem desfazer.
    try:
        await asyncio.to_thread(escopo.conta_da_casa, cid)
    except escopo.ForaDoEscopo as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    from volc_ads.gads import modo
    from volc_ads.gads.client import cliente

    def _fazer() -> Dict[str, Any]:
        c = cliente(mid)
        busca = c.get_service("GoogleAdsService")
        q = (f"SELECT campaign.id, campaign.name, campaign.status "
             f"FROM campaign WHERE campaign.id = {int(body.campaign_id)}")
        nome, status = "", ""
        for lote in busca.search_stream(customer_id=cid, query=q):
            for r in lote.results:
                nome, status = r.campaign.name, r.campaign.status.name
        if not nome:
            raise HTTPException(
                status_code=404,
                detail=f"campanha {body.campaign_id} não existe na conta {cid}.")
        if status == "REMOVED":
            return {"ja_removida": True, "nome": nome, "status": status}
        if status == "ENABLED" and not body.remover_ativa:
            raise HTTPException(
                status_code=409,
                detail=(f"a campanha {nome!r} está ENABLED — está gastando agora. "
                        f"Pause antes, ou mande `remover_ativa: true` se a "
                        f"intenção é remover mesmo assim."))

        svc = c.get_service("CampaignService")
        op = c.get_type("CampaignOperation")
        op.remove = f"customers/{cid}/campaigns/{int(body.campaign_id)}"
        with modo.destravar(body.motivo):
            r = svc.mutate_campaigns(customer_id=cid, operations=[op])
        return {
            "removida": True, "nome": nome, "status_antes": status,
            "resource_name": r.results[0].resource_name,
        }

    try:
        return await asyncio.to_thread(_fazer)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        from volc_ads.gads.modo import EscritaBloqueada

        if isinstance(exc, EscritaBloqueada):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        log.exception("remoção da campanha %s explodiu", body.campaign_id)
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc


# ---------------------------------------------------------------------------
# GET /alertas — REMOVIDA na Fase 1B
# ---------------------------------------------------------------------------
# Ela executava consulta ao Google Ads em tempo de render, e o Layout monta o
# sino em TODA página: abrir o app custava cota da conta de anúncios do
# cliente. O sino não é uma pergunta que o operador faz — é uma que a tela faz
# sozinha, o tempo todo, e cobrar da conta por isso é cobrar por existir.
#
# No lugar: `GET /api/trafego/inventario/alertas`, em
# `app/routers/trafego_inventario.py`, que projeta o SNAPSHOT que a varredura
# já gravou. Mesma fonte que a aba Atenção usa — duas superfícies respondendo à
# mesma pergunta por caminhos de custo oposto era a garantia de que uma delas
# ficaria para trás.
#
# A rota antiga não foi mantida como atalho de compatibilidade de propósito:
# enquanto ela existisse, um consumidor esquecido continuaria pagando a cota, e
# ninguém descobriria até a fatura.
