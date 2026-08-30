"""As rotas do inventário operacional. Prefixo `/api/trafego`, router NOVO.

## Por que um segundo router no mesmo prefixo

`routers/trafego.py` tem 1.725 linhas e é território de outra frente. O FastAPI
aceita dois `APIRouter` com o mesmo `prefix`; separar evita o merge conflito
garantido e mantém o caminho de leitura do inventário auditável num arquivo que
cabe na cabeça. O integrador registra os dois em `main.py` — ver `registrar()`.

## ⚠️ A REGRA ESTRUTURAL DESTE ARQUIVO

**O `GET /inventario` não pode tocar no Google Ads.** Ele lê o snapshot em
Postgres e mais nada. Medido em 24/08/2026, `/api/trafego/alertas` roda GAQL em
tempo de render e o sino e o Layout o chamam — abrir qualquer página do produto
custa rede para o Google. É essa rota que dá ao integrador de onde reapontar o
`/alertas` sem GAQL.

`tests/test_trafego_inventario.py::test_leitura_nao_toca_no_google_ads` instala
um bloqueio de import e falha se este caminho tentar carregar `volc_ads` ou
`google.ads`. Por isso os imports do sincronizador vivem DENTRO das rotas de
escrita, e não no topo do módulo.

## Autenticação

Três credenciais, e nenhuma delas opcional. A regra é o CUSTO da rota, não a
sua importância: quem só lê Postgres pede sessão, quem gasta quota da conta de
um cliente pede admin, quem roda sem humano pede uma chave que nunca chega ao
navegador.

    GET  /inventario                  → `exigir_usuario`  (sessão do navegador)
    GET  /inventario/alertas          → `exigir_usuario`  (o sino, em toda página)
    GET  /inventario/vocabulario      → `exigir_usuario`
    POST /inventario/atualizar        → `exigir_admin`    (gasta quota da conta)
    POST /inventario/sincronizacoes   → `exigir_servico`  (n8n/cron, nunca browser)

⚠️ `POST /inventario/atualizar` é o ÚNICO caminho daqui que pode consultar o
Google Ads, e há um teste que enumera as rotas do router para que uma rota nova
não entre sem alguém declarar de que lado da fronteira ela está:
`tests/test_trafego_alertas.py::test_so_a_atualizacao_explicita_pode_consultar_o_google`.

O router de leitura declara `exigir_usuario` no nível do `APIRouter`, para que
uma rota nova nasça fechada em vez de nascer aberta.

## O que estas rotas NÃO fazem

Nenhuma delas escreve na conta de anúncios. A varredura é `SELECT` e o
`_exigir_leitura()` do sincronizador recusa qualquer outra coisa antes de a
requisição sair da máquina. A trava de escrita de `volc_ads/gads/modo.py`
continua fechada e **nenhuma rota daqui a abre** — atualizar inventário e mudar
campanha são operações de naturezas diferentes, e a segunda não está aprovada
(ADR-11).
"""
from __future__ import annotations

import dataclasses
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.seguranca.identidade import (Identidade, exigir_admin, exigir_servico,
                                       exigir_usuario)
from app.trafego import escopo
from app.trafego import dominio as dom
from app.trafego import inventario as inv
from app.trafego import plataforma as plat
from app.trafego import reconciliacao as recon

log = logging.getLogger("volc.trafego.rotas.inventario")

router = APIRouter(prefix="/api/trafego", tags=["trafego"],
                   dependencies=[Depends(exigir_usuario)])

#: Router separado porque a credencial é OUTRA: `exigir_servico` valida uma
#: chave que NUNCA chega ao navegador. Pendurá-lo no router de sessão obrigaria
#: o cron a ter um login de usuário — e foi assim que a `PAUTADOR_API_KEY`
#: acabou dentro do bundle.
router_servico = APIRouter(prefix="/api/trafego", tags=["trafego"],
                           dependencies=[Depends(exigir_servico)])


def registrar(app: Any) -> None:
    """Uma linha para o integrador em `main.py`: `trafego_inventario.registrar(app)`."""
    app.include_router(router)
    app.include_router(router_servico)


# ── fonte de leitura ────────────────────────────────────────────────────────

_FONTE: Optional[inv.FonteDeInventario] = None
_FONTE_DE_ALERTAS: Optional[Any] = None


def definir_fonte(fonte: Optional[inv.FonteDeInventario]) -> None:
    """Injeta a fonte. O teste usa isto; produção usa o padrão."""
    global _FONTE
    _FONTE = fonte


def definir_fonte_de_alertas(fonte: Optional[Any]) -> None:
    """Injeta a fonte do quadro de alertas. Mesma razão de `definir_fonte`."""
    global _FONTE_DE_ALERTAS
    _FONTE_DE_ALERTAS = fonte


def _credenciais() -> tuple[str, str]:
    """A URL e a chave do Supabase, ou 503 com a razão dita em voz alta.

    503 e não 200 com lista vazia: lista vazia é um FATO deste domínio
    (`vazio_confirmado`), e devolvê-la quando a causa é configuração faltando é
    a definição de "parece que está tudo bem".
    """
    s = get_settings()
    base, chave = s.supabase_url or "", s.supabase_service_role_key or ""
    if not (base and chave):
        raise HTTPException(
            status_code=503,
            detail="Supabase não configurado no backend — sem snapshot de onde "
                   "ler o inventário. A tela não inventa dado de conta.",
        )
    return base, chave


def _fonte_de_vinculo() -> Any:
    """A escrita de vínculo. Mesma credencial da leitura do inventário.

    Fica atrás de função pelo mesmo motivo da fonte de leitura: o router não
    guarda credencial em módulo, e o teste troca a fonte sem tocar em variável
    de ambiente.
    """
    from app.trafego import persistencia  # noqa: PLC0415

    if _FONTE_DE_VINCULO is not None:
        return _FONTE_DE_VINCULO
    base, chave = _credenciais()
    return persistencia.FonteDeReconciliacao(base, chave)


#: A forma de `volc_campaign_id`, espelhando o CHECK da v9_01. Serve para
#: recusar um endereço impossível antes de ele virar consulta.
_CHAVE_DE_CAMPANHA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")

#: `vinculo_id` é `uuid` no schema. Recusar aqui evita transformar um erro do
#: pedido num 502 que culpa o Supabase.
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _e_conflito_de_unicidade(exc: Exception) -> bool:
    """O índice `trafego_vinculo_ativo_por_campanha_ux` recusou.

    Ele é único sobre `volc_campaign_id WHERE desfeito_em IS NULL`: no máximo um
    vínculo vivo por campanha. Bater nele não é erro de servidor — é a resposta
    correta a um pedido que a tela precisa saber tratar, e por isso vira 409 e
    não 502.

    A detecção é por texto porque o `httpx` não expõe o `SQLSTATE` do Postgres
    através do PostgREST. É frágil de propósito declarado: se a mensagem mudar,
    o caso vira 502 — que é o comportamento antigo, não um comportamento pior.
    """
    texto = f"{exc}".lower()
    return ("409" in texto
            or "duplicate key" in texto
            or "23505" in texto
            or "already exists" in texto)

_FONTE_DE_VINCULO: Optional[Any] = None


def definir_fonte_de_vinculo(fonte: Optional[Any]) -> None:
    """Ponto de troca para o teste. `None` volta ao real."""
    global _FONTE_DE_VINCULO  # noqa: PLW0603
    _FONTE_DE_VINCULO = fonte


def _fonte() -> inv.FonteDeInventario:
    if _FONTE is not None:
        return _FONTE
    base, chave = _credenciais()
    try:
        return inv.fabricar_fonte(base, chave)
    except inv.PersistenciaAusente as exc:
        # ⚠️ Ponto de integração com a Frente A. Enquanto
        # `app/trafego/persistencia.py` não existir, esta rota responde 503 com
        # o nome do arquivo que falta — em vez de 404 do PostgREST sobre uma
        # tabela que ninguém criou, que era o comportamento anterior.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _fonte_de_alertas() -> Any:
    from app.trafego import alertas as alr  # noqa: PLC0415

    if _FONTE_DE_ALERTAS is not None:
        return _FONTE_DE_ALERTAS
    base, chave = _credenciais()
    try:
        return alr.fabricar_fonte(base, chave)
    except inv.PersistenciaAusente as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _repo() -> Any:
    from app.trafego import sincronizador as sinc  # noqa: PLC0415

    base, chave = _credenciais()
    try:
        return sinc.fabricar_repositorio(base, chave)
    except inv.PersistenciaAusente as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


_REPO_INJETADO: Optional[Any] = None
_BUSCA_INJETADA: Optional[Any] = None


def definir_varredura(repo: Optional[Any], fabrica_de_busca: Optional[Any]) -> None:
    """Injeta o repositório e o leitor da conta. Dublê no teste, real fora dele.

    Existe porque a alternativa seria um teste que fala com a conta de anúncios
    de verdade — e a suíte não pode depender de rede nem gastar quota de quota
    alheia para provar que o portão de admin funciona.
    """
    global _REPO_INJETADO, _BUSCA_INJETADA
    _REPO_INJETADO, _BUSCA_INJETADA = repo, fabrica_de_busca


# ── GET /inventario ─────────────────────────────────────────────────────────


@router.get("/inventario")
async def inventario_operacional(
    busca: Optional[str] = Query(
        None, max_length=120,
        description="texto livre: casa com o nome da campanha ou com o id externo"),
    conta: Optional[List[str]] = Query(None, description="customer_id; repetível"),
    projeto: Optional[List[int]] = Query(None),
    canal: Optional[List[str]] = Query(None, description="vocabulário do ADR-18"),
    estado_externo: Optional[List[str]] = Query(None, description="ENABLED, PAUSED…"),
    presenca: Optional[List[str]] = Query(None),
    frescor: Optional[List[str]] = Query(None),
    procedencia: Optional[List[str]] = Query(None),
    atencao: Optional[bool] = Query(None),
    vinculado: Optional[bool] = Query(None),
    incluir_historico: bool = Query(
        False,
        description=("inclui o histórico removido na listagem. O padrão é "
                     "`false`: das 84 campanhas das contas da casa, 79 estão "
                     "REMOVED, e abrir o Hub em história é abrir em ruído. "
                     "Filtrar explicitamente por `estado_externo=REMOVED` ou "
                     "`presenca=removida` também liga o histórico — pedir o "
                     "que o padrão esconde e receber vazio seria mentira.")),
    limite: int = Query(inv.LIMITE_PADRAO, ge=1, le=inv.LIMITE_MAXIMO),
    cursor: Optional[str] = Query(None, description="opaco; nunca offset"),
) -> Any:
    """O que existe nas contas, em que estado, e quão recente é a informação.

    Leitura do SNAPSHOT. Zero consultas ao Google Ads — é o requisito que faz o
    Layout e o sino pararem de custar rede externa a cada render.
    """
    try:
        filtros = inv.normalizar_filtros({
            "busca": busca,
            "conta": conta or (), "projeto": projeto or (), "canal": canal or (),
            "estado_externo": estado_externo or (), "presenca": presenca or (),
            "frescor": frescor or (), "procedencia": procedencia or (),
            "atencao": atencao, "vinculado": vinculado,
            "incluir_historico": incluir_historico,
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        resposta = await inv.montar_inventario(_fonte(), filtros,
                                               limite=limite, cursor=cursor)
    except inv.CursorInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # O snapshot fora do ar é 503, não 200 com lista vazia: lista vazia é um
        # fato (`vazio_confirmado`) e confundir os dois é a definição de
        # "parece que está tudo bem".
        log.exception("leitura do snapshot falhou")
        raise HTTPException(
            status_code=503,
            detail=f"não consegui ler o snapshot do inventário: {exc}"[:300],
        ) from exc

    return resposta.json()


@router.get("/inventario/alertas")
async def quadro_de_alertas() -> Any:
    """Campanhas ligadas que não gastaram — do SNAPSHOT, sem uma consulta GAQL.

    ## Por que esta rota existe ao lado de `/api/trafego/alertas`

    A rota antiga (`routers/trafego.py`) chama `volc_ads.entrega`, que roda ~5
    GAQL por conta EM TEMPO DE RENDER. O `Layout` monta o sino em toda página do
    produto, então abrir o Pautador custa rede para o Google — três contas,
    quinze consultas, cada navegação.

    Esta responde a mesma pergunta lendo Postgres. Ela vive num caminho novo em
    vez de substituir a antiga porque `routers/trafego.py`, `src/lib/pautadorApi.ts`
    e `src/hooks/useNotificacoes.ts` são de outra frente: reapontar o sino é uma
    linha, e ela está no pedido ao integrador. Enquanto o sino não for
    reapontado, o gate NÃO está fechado em produção — só está disponível.

    ## O que muda no corpo, e por que

    Três acréscimos, todos por regra A (nenhum número sem frescor):

    · `frescor` e `leitura` no envelope — o quadro antigo era calculado na hora e
      por construção era do instante em que aparecia; lido do snapshot, deixa de
      ser, e a idade tem de estar visível;
    · `leitura` em cada alerta, pela mesma razão, por linha;
    · `nao_sabemos`, dizendo quais campos o snapshot não tem como responder.

    E dois campos passam a poder sair `null`: `aprovacao_do_anuncio` (vive numa
    entidade filha que a varredura comum não lê) e `alteracoes[].origem/quem`
    (quem mexeu vive no histórico da conta). `null` e não um texto genérico: a
    tela precisa poder dizer que não sabe.
    """
    from app.trafego import alertas as alr  # noqa: PLC0415

    try:
        quadro = await alr.montar_quadro(_fonte_de_alertas())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # 503 e nunca 200 com `alertas: []`. Lista vazia significa "nenhuma
        # campanha ligada está parada" — a melhor notícia possível — e emiti-la
        # quando a causa é o snapshot fora do ar é a definição de alerta
        # quebrado indistinguível de "está tudo bem".
        log.exception("leitura do quadro de alertas falhou")
        raise HTTPException(
            status_code=503,
            detail=f"não consegui ler o snapshot dos alertas: {exc}"[:300],
        ) from exc

    return quadro.json()


@router.get("/inventario/vocabulario")
async def vocabulario() -> Any:
    """Os valores fechados do contrato, servidos pela fonte que os aplica.

    Existe para que a tela não mantenha uma segunda cópia da lista: divergência
    de vocabulário entre front e back é o defeito do E-21, medido em cinco
    lugares diferentes.
    """
    return {
        "versao": inv.VERSAO_INVENTARIO,
        "presenca": list(inv.ESTADOS_DE_PRESENCA),
        "frescor": list(inv.FRESCORES),
        "procedencia": list(inv.PROCEDENCIAS),
        "canal": list(inv.CANAIS),
        "apelidos_de_canal": dict(inv.APELIDOS_DE_CANAL),
        "estrategia": list(inv.ESTRATEGIAS),
        "segundos_para_velho": inv.SEGUNDOS_PARA_VELHO,
        # ── o que o Hub SABE FAZER, por plataforma e por canal ──────────────
        #
        # A tela deriva cada ação daqui, e não da lista de canais. Quatro canais
        # não são quatro botões de "criar": existe um único construtor de
        # campanha, e oferecer os outros por simetria visual faz o operador
        # descobrir a ausência depois de montar o pedido inteiro.
        #
        # `indisponibilidades` viaja junto porque é a diferença entre um botão
        # cinza sem explicação e uma recusa que ensina.
        "plataformas": list(plat.PLATAFORMAS),
        "manifestos": [m.json() for p_ in plat.PLATAFORMAS
                       for m in plat.manifestos_de(p_)],
        "estados_de_reconciliacao": list(recon.ESTADOS),
    }


# ── GET /campanhas/{volc_campaign_id} — a página canônica (H0) ──────────────
#
# A rota que a ADR-02 declarou canônica: uma instância, 1:1 com uma campanha
# externa, endereçada pela identidade INTERNA.
#
# ⚠️ **Ela não resolve `campaign_id` externo, e a recusa é o ponto.** O id
# externo do Google não é único no VOLC O.S.: ele é único DENTRO de uma conta, e
# a partir da H0 a identidade externa é uma trinca (plataforma, conta, id). Uma
# rota que aceitasse o id externo teria de adivinhar as outras duas pontas — e
# adivinhar errado leva o operador à campanha de outro cliente com a URL certa
# na barra de endereço.
#
# A rota legada `/dashboard/campaign/:campaignId` continua existindo e continua
# sendo compatibilidade. Ela só redireciona para cá quando conta + plataforma +
# id externo levarem a UMA identidade interna — e isso é trabalho de outra
# fatia, com prova própria.


@router.get("/campanhas/{volc_campaign_id}")
async def uma_campanha(volc_campaign_id: str) -> Any:
    """Tudo o que se sabe de UMA campanha. Leitura do snapshot, sem Google.

    Devolve identidade (interna e externa), plataforma, canal, conta, estado
    externo, frescor da leitura, vínculo e o manifesto de capacidades do canal.

    O manifesto viaja junto de propósito: é dele que a tela deriva o que pode
    oferecer. Sem ele, a página teria de manter uma segunda cópia da tabela de
    capacidades — e no dia em que um canal ganhasse construtor, a tela
    continuaria escondendo, ou pior, oferecendo o que não existe.

    ⚠️ Zero consulta ao Google Ads. Zero mutação. Zero varredura paginada.
    """
    chave = str(volc_campaign_id or "").strip()
    if not chave or not _CHAVE_DE_CAMPANHA.match(chave):
        # 404 e não 400: um id fora do formato é um endereço que não existe, e
        # dizer "formato inválido" ensinaria a forma da chave a quem está
        # tentando adivinhá-la.
        raise HTTPException(status_code=404,
                            detail="campanha não encontrada.")

    try:
        linha = await _fonte_de_vinculo().uma_campanha(chave)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("leitura da campanha canônica falhou")
        raise HTTPException(
            status_code=503,
            detail="não consegui ler o snapshot desta campanha.") from exc

    if linha is None:
        raise HTTPException(status_code=404,
                            detail="campanha não encontrada.")

    agora = datetime.now(timezone.utc)
    conta_falhou = str(linha.get("tentativa_resultado") or "") == "falhou"
    projetada = inv.campanha_projetada(linha, conta_falhou=conta_falhou,
                                       agora=agora)

    canal = projetada.canal
    manifesto = plat.manifesto(plat.GOOGLE_ADS, canal) if canal else None

    return {
        "versao": inv.VERSAO_INVENTARIO,
        "campanha": dataclasses.asdict(projetada),
        # A identidade externa é a TRINCA da H0, e não mais o par. Ver
        # `plataforma.IdentidadeDeCampanha`.
        "identidade": {
            "volc_campaign_id": projetada.volc_campaign_id,
            "campaign_lineage_id": projetada.campaign_lineage_id,
            "plataforma": plat.GOOGLE_ADS,
            "conta_externa": projetada.externa.customer_id,
            "id_externo": projetada.externa.campaign_id,
        },
        "conta": {
            "customer_id": linha.get("customer_id"),
            # O frescor da CONTA, que é o que carimba os números da campanha.
            # Vem de `inventario.frescor_da_conta`, que é a mesma função que a
            # listagem usa — duas definições de frescor fariam a mesma conta
            # aparecer recente na lista e velha no detalhe.
            "frescor": inv.frescor_da_conta(
                inv.normalizar_linha_de_conta({
                    "customer_id": linha.get("customer_id"),
                    "tentativa_resultado": linha.get("tentativa_resultado"),
                    "tentativa_em": linha.get("tentativa_em"),
                    "leitura_boa_em": linha.get("leitura_boa_em"),
                }), agora),
            "tentativa_resultado": linha.get("tentativa_resultado"),
        },
        # `null` quando o canal não tem manifesto — Vídeo e Shopping aparecem no
        # inventário e o Hub não os opera. Nulo diz isso; um manifesto vazio
        # diria "não pode nada", que é outra afirmação.
        "manifesto": manifesto.json() if manifesto else None,
    }


# ── GET /campanhas/{id}/correspondencias — de quem é esta campanha? ─────────
#
# A pergunta do INVENTÁRIO, que é o inverso da pergunta do quadro.
#
# O quadro pergunta "este funil já tem campanha?" — quem chega ali quer saber se
# pode montar. Aqui o operador está olhando uma campanha que a varredura
# encontrou na conta e precisa decidir **de quem ela é**.
#
# ⚠️ Esta rota SUGERE. Ela não grava nada, e a sugestão não vira vínculo por
# passar do tempo, por ser a única ou por ser forte: quem responde é
# `POST /vinculos`, e a resposta leva quem confirmou, quando e com que regra
# (ADR-09). Uma correspondência provável apresentada como vínculo é exatamente
# o defeito que a confirmação humana existe para impedir.
#
# Zero Google Ads: tudo sai do snapshot e das tabelas do VOLC.


async def _funis_da_conta(supa: Any, customer_id: str) -> tuple:
    """Os funis publicados dos projetos QUE USAM esta conta, e o legado por run.

    ⚠️ Só os projetos desta conta. A conta é pré-requisito da prova (ADR-03):
    comparar URL entre contas diferentes casaria a campanha de um cliente com o
    funil de outro, e o erro seria silencioso — as URLs de dois portais de
    utilidade pública se parecem.
    """
    projetos = await supa.select("projects", {
        "select": "id,google_ads_customer_id",
        "google_ads_customer_id": f"eq.{customer_id}"})
    ids = sorted({int(p["id"]) for p in (projetos or [])
                  if p.get("id") is not None})
    if not ids:
        return (), {}

    runs = await supa.select("pautador_funnel_runs", {
        "select": "id,opportunity_id,project_id,status,lp_url,paginas_publicadas",
        "project_id": f"in.({','.join(str(i) for i in ids)})"})

    funis = []
    numeros_de_run = []
    for r in (runs or []):
        # Um funil só entra se publicou página: sem URL no ar não há destino
        # para comparar, e um rascunho casaria por acaso com o que estiver perto.
        publicadas = r.get("paginas_publicadas") or []
        if r.get("status") != "done" or not publicadas:
            continue
        if r.get("opportunity_id") is None:
            continue
        urls = tuple(str(pg.get("url_wp") or "")
                     for pg in publicadas
                     if isinstance(pg, dict) and pg.get("url_wp"))
        projeto = r.get("project_id")
        funis.append(recon.Funil(
            opportunity_id=int(r["opportunity_id"]),
            run_id=int(r["id"]) if r.get("id") is not None else None,
            project_id=int(projeto) if projeto is not None else None,
            customer_id=customer_id,
            lp_url=r.get("lp_url"),
            urls_publicadas=urls,
        ))
        if r.get("id") is not None:
            numeros_de_run.append(int(r["id"]))

    # A tabela legada entra como SINAL, com a força de uma declaração nossa —
    # nunca como autoridade sobre existência (ADR-01).
    legado: Dict[int, set] = {}
    if numeros_de_run:
        for l in (await supa.select("campaigns", {
                "select": "funnel_run_id,campaign_id",
                "funnel_run_id": f"in.({','.join(str(r) for r in numeros_de_run)})"}) or []):
            rid, cid = l.get("funnel_run_id"), l.get("campaign_id")
            if rid is not None and cid:
                legado.setdefault(int(rid), set()).add(str(cid))

    return tuple(funis), legado


def _conhecida(l: Dict[str, Any]) -> recon.CampanhaConhecida:
    """Uma linha da view virando o tipo do motor. Lista fechada de colunas."""
    return recon.CampanhaConhecida(
        volc_campaign_id=str(l.get("volc_campaign_id") or ""),
        campaign_id=str(l.get("campaign_id") or ""),
        customer_id=(str(l["customer_id"]) if l.get("customer_id") else None),
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
                                if l.get("opportunity_id") is not None else None),
        vinculo_run_id=(int(l["funnel_run_id"])
                        if l.get("funnel_run_id") is not None else None),
    )


@router.get("/campanhas/{volc_campaign_id}/correspondencias")
async def correspondencias_da_campanha(volc_campaign_id: str) -> Any:
    """Que funis internos casam com esta campanha, e com que força cada sinal.

    Devolve o que a superfície de revisão precisa mostrar antes de o operador
    decidir: o candidato, a regra que o trouxe, a força dela, o que impediu de
    comparar e se outra campanha disputa o mesmo funil.

    ⚠️ Nada aqui grava. E a força NÃO é inflada: a URL lida da conta vale
    `historica`, e não `forte`, porque o espelho não guarda quando ela foi lida
    (ver `reconciliacao._sinais_da_campanha`). Apresentá-la como observação de
    agora seria oferecer como prova recente um valor que pode ter três semanas.
    """
    chave = str(volc_campaign_id or "").strip()
    if not chave or not _CHAVE_DE_CAMPANHA.match(chave):
        raise HTTPException(status_code=404, detail="campanha não encontrada.")

    fonte = _fonte_de_vinculo()
    try:
        linha = await fonte.uma_campanha(chave)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("leitura da campanha para correspondências falhou")
        raise HTTPException(
            status_code=503,
            detail="não consegui ler o snapshot desta campanha.") from exc
    if linha is None:
        raise HTTPException(status_code=404, detail="campanha não encontrada.")

    alvo = _conhecida(linha)

    if not alvo.customer_id:
        # Sem conta não há onde procurar. O motor devolve `nao_apurada` e diz o
        # porquê — e essa resposta é útil, não um erro a esconder.
        return recon.correspondencias_da_campanha(alvo, (), (alvo,)).json()

    from app.services.supabase_service import SupabaseService  # noqa: PLC0415

    supa = SupabaseService(get_settings())
    try:
        universo = [_conhecida(l)
                    for l in await fonte.campanhas_conhecidas([alvo.customer_id])]
        funis, legado = await _funis_da_conta(supa, alvo.customer_id)
    except Exception as exc:  # noqa: BLE001
        # ⚠️ 503 e não uma lista vazia. Uma lista vazia diria "comparei e nada
        # casou", que é a frase que libera o operador a tratar a campanha como
        # órfã. Falha de leitura precisa parecer falha de leitura.
        log.exception("não consegui montar o universo de correspondências")
        raise HTTPException(
            status_code=503,
            detail="não consegui comparar esta campanha com os funis agora.") from exc

    # A campanha alvo PRECISA estar no universo — o motor recusa o contrário. A
    # view a inclui por construção, mas uma leitura parcial poderia não incluir,
    # e aí a resposta seria "sem correspondência" por ausência de dado.
    if not any(c.volc_campaign_id == alvo.volc_campaign_id for c in universo):
        universo.append(alvo)

    revisao = recon.correspondencias_da_campanha(
        alvo, funis, universo, legado_por_run=legado)
    return revisao.json()


# ── vínculo campanha ↔ funil — a decisão humana da reconciliação ────────────
#
# A reconciliação SUGERE; estas duas rotas são onde o operador RESPONDE.
#
# Portão: `exigir_usuario`, e não `exigir_admin`. Vincular é o trabalho do
# operador, não administração — e o vínculo é reversível, auditável e não gasta
# um centavo. Exigir ADMIN aqui deixaria a reconciliação parada esperando por
# quem não está na tela, e a fila de sugestões sem resposta é o modo como uma
# reconciliação morre.
#
# O que NÃO vem do corpo: quem confirmou. `confirmado_por` sai do token, sempre.
# Aceitar do corpo permitiria a qualquer usuário assinar a decisão com o nome de
# outro — numa tabela cujo propósito inteiro é dizer quem decidiu o quê.


class PedidoDeVinculo(BaseModel):
    volc_campaign_id: str = Field(..., min_length=1, max_length=120)
    opportunity_id: Optional[int] = None
    project_id: Optional[int] = None
    funnel_run_id: Optional[int] = None
    #: Qual regra casou. A tabela a recusa vazia, e a razão é o ADR-09: um
    #: vínculo sem regra visível é uma caixa-preta que o operador não tem como
    #: contestar depois.
    regra: str = Field(..., min_length=1, max_length=200)
    evidencia: Dict[str, Any] = Field(default_factory=dict)
    #: O vínculo que este substitui, quando há. É o que permite reconstruir a
    #: cadeia inteira de decisões sobre a mesma campanha.
    vinculo_anterior: Optional[str] = None


@router.post("/vinculos", status_code=201)
async def confirmar_vinculo(corpo: PedidoDeVinculo = Body(...),
                            quem: Identidade = Depends(exigir_usuario)) -> Any:
    """Grava a confirmação humana de um vínculo campanha ↔ funil.

    ⚠️ Um vínculo errado contamina a atribuição de receita de forma permanente e
    silenciosa (ADR-09). O custo de confirmar recai sobre o operador, e isso é
    deliberado — o sistema sugere, ele decide.
    """
    if (corpo.opportunity_id is None and corpo.project_id is None
            and corpo.funnel_run_id is None):
        raise HTTPException(
            status_code=400,
            detail="vínculo precisa apontar para alguma coisa: informe "
                   "`opportunity_id`, `project_id` ou `funnel_run_id`.")

    # ── autorização, e não só identidade ───────────────────────────────────
    #
    # ⚠️ `exigir_usuario` prova QUEM é; ele não prova que a pessoa tem papel.
    # `volc_role_of` devolve string vazia para quem teve o papel revogado, e a
    # revogação vale no ato — mas a sessão do Supabase continua válida até o
    # token expirar. Sem esta linha, alguém removido da operação continuaria
    # gravando vínculo, e a linha nasceria assinada com o nome dele.
    #
    # Vincular não gasta dinheiro, mas contamina atribuição de receita de forma
    # permanente (ADR-09) — e a linha é imutável: só dá para desfazer, nunca
    # corrigir.
    if not str(quem.papel or "").strip():
        raise HTTPException(
            status_code=403,
            detail="sem papel ativo para confirmar vínculo. Se o seu acesso foi "
                   "revogado, ele vale desde já — o token continua válido até "
                   "expirar, mas a autorização não.")

    fonte = _fonte_de_vinculo()

    # ── a campanha precisa existir ─────────────────────────────────────────
    #
    # Sem esta conferência, um `volc_campaign_id` inexistente viola a FK e volta
    # como 502 — atribuindo ao Supabase um erro que é do pedido, e sem dizer o
    # que estava errado.
    try:
        alvo = await fonte.uma_campanha(corpo.volc_campaign_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("não consegui conferir a campanha do vínculo")
        raise HTTPException(
            status_code=503,
            detail="não consegui conferir a campanha antes de vincular.") from exc
    if alvo is None:
        raise HTTPException(
            status_code=404,
            detail="não há campanha com essa identidade interna.")

    try:
        linha = await fonte.confirmar_vinculo({
            "volc_campaign_id": corpo.volc_campaign_id,
            "opportunity_id": corpo.opportunity_id,
            "project_id": corpo.project_id,
            "funnel_run_id": corpo.funnel_run_id,
            "regra": corpo.regra,
            "evidencia": corpo.evidencia,
            "confirmado_por": quem.email or quem.sub,
            "vinculo_anterior": corpo.vinculo_anterior,
        })
    except Exception as exc:  # noqa: BLE001
        # ⚠️ A mensagem NÃO carrega o texto cru da exceção.
        #
        # `httpx` põe a URL do PostgREST no `str(exc)` — endpoint interno,
        # tabela e colunas —, e isso ia inteiro para qualquer usuário
        # autenticado que provocasse um 400. O detalhe fica no log do servidor,
        # onde ele serve para investigar; a resposta diz o que fazer.
        log.exception("não consegui gravar o vínculo")
        if _e_conflito_de_unicidade(exc):
            raise HTTPException(
                status_code=409,
                detail="esta campanha já tem um vínculo vivo. Desfaça o "
                       "vínculo atual antes de confirmar outro — a linha "
                       "antiga fica no histórico, com quem a confirmou e "
                       "quando.") from exc
        raise HTTPException(
            status_code=502,
            detail="o vínculo não foi gravado. O detalhe está no log do "
                   "servidor.") from exc
    return {"vinculo": linha}


class PedidoDeDesvinculo(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=500)


@router.post("/vinculos/{vinculo_id}/desfazer")
async def desfazer_vinculo(vinculo_id: str,
                           corpo: PedidoDeDesvinculo = Body(default=None),
                           quem: Identidade = Depends(exigir_usuario)) -> Any:
    """Desvincular é operação de primeira classe, não exceção (ADR-09).

    ⚠️ A linha NÃO é apagada. Ela guarda quem vinculou, quando, com que regra e
    por que foi desfeito. Apagar deixaria a campanha sem vínculo e sem rastro de
    que houve um — indistinguível de uma que nunca foi vinculada.
    """
    if not str(quem.papel or "").strip():
        raise HTTPException(
            status_code=403,
            detail="sem papel ativo para desfazer vínculo.")

    # Um id fora do formato é um endereço que não existe. Sem esta conferência
    # ele virava um 400 do PostgREST e voltava como 502 — atribuindo ao Supabase
    # um erro que é do pedido.
    if not _UUID.match(str(vinculo_id or "")):
        raise HTTPException(status_code=404,
                            detail="não há vínculo vivo com esse id.")

    try:
        linha = await _fonte_de_vinculo().desfazer_vinculo(
            vinculo_id, por=(quem.email or quem.sub),
            motivo=(corpo.motivo if corpo else None))
    except Exception as exc:  # noqa: BLE001
        log.exception("não consegui desfazer o vínculo")
        raise HTTPException(
            status_code=502,
            detail="o vínculo não foi desfeito. O detalhe está no log do "
                   "servidor.") from exc
    if not linha:
        raise HTTPException(
            status_code=404,
            detail="não há vínculo vivo com esse id. Ele pode já ter sido "
                   "desfeito — e nesse caso a linha continua no histórico.")
    return {"vinculo": linha}


# ── POST /inventario/atualizar — uma conta, admin, com custo declarado ───────


class PedidoDeAtualizacao(BaseModel):
    customer_id: str = Field(..., description="uma conta por vez, sempre")
    janela: str = Field(default="LAST_30_DAYS")


@router.post("/inventario/atualizar", dependencies=[Depends(exigir_admin)])
async def atualizar_uma_conta(corpo: PedidoDeAtualizacao = Body(...)) -> Any:
    """Varredura sob demanda de UMA conta. Somente leitura, com limite de taxa.

    Admin porque gasta quota da conta do cliente, e uma conta por vez porque
    "atualizar tudo" é o botão que alguém aperta três vezes quando a tela não
    muda na hora. A resposta declara o custo — quantas consultas foram feitas e
    quanto demorou —, que é o que o SPEC §3.4 chama de "custo declarado".
    """
    from app.trafego import sincronizador as sinc  # noqa: PLC0415

    cid, _ = _no_escopo(corpo.customer_id)
    if corpo.janela not in sinc.JANELAS:
        raise HTTPException(
            status_code=400,
            detail=f"janela {corpo.janela!r} não existe. As janelas são: "
                   f"{', '.join(sinc.JANELAS)}.",
        )

    repo = _REPO_INJETADO or _repo()
    conta = await _conta_da_casa(cid)

    # O limite consulta o REGISTRO, não um contador de processo: com dois
    # workers, um contador em memória libera o dobro das varreduras e nada
    # denuncia. Como `exigir()` é síncrono, o carimbo é buscado antes.
    ultimas = {cid: await repo.ultima_tentativa(cid)}
    limite = sinc.LimiteDeTaxa(ultimas.get, intervalos=sinc.INTERVALO_MINIMO_S)

    fabrica = _BUSCA_INJETADA or _fabrica_real
    try:
        resultado = await sinc.sincronizar_conta(
            conta, repo, buscar=fabrica(conta), janela=corpo.janela,
            origem="manual", limite=limite)
    except sinc.LimiteExcedido as exc:
        raise HTTPException(
            status_code=429,
            detail={"mensagem": str(exc), "customer_id": cid,
                    "proxima_em": exc.proxima_em.isoformat(),
                    "intervalo_s": exc.intervalo_s},
        ) from exc

    return {
        "escopo": {"customer_id": cid, "nome": conta.get("nome"),
                   "janela": corpo.janela, "contas": 1},
        "custo": {"consultas_gaql": resultado.consultas,
                  "duracao_ms": resultado.duracao_ms},
        "resultado": resultado.json(),
        "escrita_permitida": False,
    }


# ── POST /inventario/sincronizacoes — contrato para scheduler/n8n ────────────


class PedidoDeSincronizacao(BaseModel):
    """O que o agendador manda. Nenhuma decisão viaja aqui.

    O n8n é periferia (ADR-05): ele DISPARA um contrato interno autenticado e
    não contém lógica. Por isso o corpo só nomeia contas e janela — não há
    limiar, regra nem ação. Se um dia aparecer um campo de decisão neste modelo,
    a fronteira vazou.
    """

    contas: Optional[List[str]] = Field(default=None,
                                        description="vazio = todas as da casa")
    janela: str = Field(default="LAST_30_DAYS")
    chave_idempotencia: Optional[str] = Field(
        default=None, description="repetir a mesma chave não custa quota")


@router_servico.post("/inventario/sincronizacoes")
async def sincronizar_agendado(corpo: PedidoDeSincronizacao = Body(...)) -> Any:
    """Varredura agendada. Credencial de SERVIÇO, nunca sessão de navegador.

    Sem `chave_idempotencia`, a chave é derivada do balde de 15 minutos do
    relógio — o mesmo ciclo que o SPEC §4.4 dimensiona. Efeito prático: dois
    disparos no mesmo balde são a mesma intenção e o segundo não custa quota.
    Quem precisar forçar manda a própria chave.
    """
    from app.trafego import sincronizador as sinc  # noqa: PLC0415

    if corpo.janela not in sinc.JANELAS:
        raise HTTPException(
            status_code=400,
            detail=f"janela {corpo.janela!r} não existe. As janelas são: "
                   f"{', '.join(sinc.JANELAS)}.",
        )

    repo = _REPO_INJETADO or _repo()
    if corpo.contas:
        contas = [await _conta_da_casa(_no_escopo(c)[0]) for c in corpo.contas]
    else:
        contas = await _contas_da_casa()

    chave = corpo.chave_idempotencia or sinc.chave_de_janela(
        "rodada", corpo.janela, datetime.now(timezone.utc))

    ultimas: Dict[str, Optional[datetime]] = {}
    for c in contas:
        alvo = escopo.so_digitos(c.get("customer_id"))
        ultimas[alvo] = await repo.ultima_tentativa(alvo)
    limite = sinc.LimiteDeTaxa(ultimas.get, intervalos=sinc.INTERVALO_MINIMO_S)

    saida = await sinc.sincronizar(
        contas, repo, fabrica_de_busca=(_BUSCA_INJETADA or _fabrica_real),
        janela=corpo.janela, origem="agendado", chave_idempotencia=chave,
        limite=limite)
    saida["escrita_permitida"] = False
    return saida


# ── apoio ───────────────────────────────────────────────────────────────────


def _no_escopo(customer_id: Any) -> tuple[str, str]:
    """O portão da casa, traduzido para HTTP. Não faz rede.

    403 e não 409: não é conflito de estado, é uma fronteira que não se negocia.
    A credencial alcança 39 contas anunciáveis e 36 delas são de cliente.
    """
    try:
        return escopo.exigir_escopo(customer_id, escopo.MCC_DA_CASA)
    except escopo.ForaDoEscopo as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


#: Contas injetáveis para o teste não precisar da árvore real do MCC.
_CONTAS_INJETADAS: Optional[List[Dict[str, Any]]] = None


def definir_contas(contas: Optional[List[Dict[str, Any]]]) -> None:
    global _CONTAS_INJETADAS
    _CONTAS_INJETADAS = contas


async def _contas_da_casa() -> List[Dict[str, Any]]:
    import asyncio  # noqa: PLC0415

    if _CONTAS_INJETADAS is not None:
        return list(_CONTAS_INJETADAS)
    try:
        casa = await asyncio.to_thread(escopo.mapa)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail=f"não consegui listar as contas da casa: "
                                   f"{exc}"[:300]) from exc
    return list(casa.get("contas") or [])


async def _conta_da_casa(customer_id: str) -> Dict[str, Any]:
    for c in await _contas_da_casa():
        if escopo.so_digitos(c.get("customer_id")) == customer_id:
            return c
    raise HTTPException(
        status_code=403,
        detail=f"a conta {customer_id} não está entre as contas anunciáveis do "
               f"MCC {escopo.MCC_DA_CASA}.",
    )


def _fabrica_real(conta: Dict[str, Any]):
    """O leitor de verdade. Import tardio: o backend sobe sem o SDK."""
    from app.trafego.sincronizador import leitor_google_ads  # noqa: PLC0415

    return leitor_google_ads(escopo.so_digitos(conta.get("customer_id")),
                             login_customer_id=escopo.MCC_DA_CASA)
