"""Perfil de publicação de cada projeto — onde o redator vai publicar.

## A regra que organiza este arquivo

**O Application Password nunca volta para o browser.** Nenhuma rota aqui
devolve `wp_app_password`, nem mascarado a ponto de ser reconstruível, nem em
mensagem de erro, nem em log. O que a tela recebe é o suficiente para o operador
saber o que está configurado e se funciona:

    { configurado: true, wp_username: "volc-redator",
      senha_mascarada: "••••••••••••••••••••UVWX",
      conexao: { ok: true, em: "...", detalhe: "Editor · pode publicar" } }

Quem quiser trocar a credencial ESCREVE uma nova. Não existe leitura. É por isso
que `PUT` trata `wp_app_password` como opcional: campo ausente significa "mantém
a que está", e não "apaga".

## Por que o teste de conexão existe

Sem ele, a única forma de saber se a credencial funciona é rodar o redator
inteiro e ver falhar no último passo, depois de já ter gasto dólar em LLM. O
`GET /wp-json/wp/v2/users/me` custa nada, responde em ~300 ms e diz três coisas
que importam: se a senha vale, quem é o usuário, e se ele tem permissão de
publicar. O resultado fica gravado com data — a tela mostra "testado em 15/08"
em vez de pedir fé.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import get_settings
from app.seguranca import (
    CofreSemChave,
    SegredoCorrompido,
    cifrar,
    cofre_configurado,
    decifrar,
    mascara,
)
from app.services.supabase_service import SupabaseService

log = logging.getLogger("volc.publicacao")

# Referência forte para as tarefas de run em andamento. Sem isto o asyncio pode
# coletar a task no meio de um run de 45 minutos — o processo do motor
# continuaria vivo, mas ninguém estaria acompanhando para gravar o desfecho.
_TAREFAS: set = set()

from app.seguranca.identidade import exigir_admin, exigir_usuario

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
router = APIRouter(prefix="/api/publicacao", tags=["publicacao"], dependencies=[Depends(exigir_usuario)])

TABELA = "project_wordpress"

# ⚠️ Medido em 18/08/2026 na LP do run 7: o print de página inteira com
# rolagem levou ~20 s e produziu 760 kB. O teto é generoso porque a rolagem
# do lazy-load é proporcional ao tamanho da página — e porque estourar aqui
# não gasta nada além de tempo: o print não cria nem altera coisa alguma.
TIMEOUT_PRINT_S = 120.0


# ── contratos ──────────────────────────────────────────────────────────────

class PerfilEntrada(BaseModel):
    """O que a tela manda. `wp_app_password` ausente = mantém a atual.

    Não tem CNPJ, autor nem lista de cross-funnel: o CNPJ e a assinatura saem do
    TEMA do site, e a saída cross-funnel o engine resolve lendo o sitemap real
    (`adapters/sitemap_http.py`). Cadastrar de novo aqui seria pedir manutenção
    manual de dado que o site já publica.
    """
    wp_url: str
    wp_username: str
    wp_app_password: Optional[str] = None
    post_type: str = "rec"
    lp_post_type: str = "r"


class Conexao(BaseModel):
    ok: Optional[bool] = None
    em: Optional[str] = None
    detalhe: Optional[str] = None


class PerfilSaida(BaseModel):
    """O que a tela recebe. Repare no que NÃO está aqui: a senha."""
    project_id: int
    configurado: bool
    cofre_pronto: bool
    wp_url: Optional[str] = None
    wp_username: Optional[str] = None
    senha_mascarada: str = "—"
    post_type: str = "rec"
    lp_post_type: str = "r"
    conexao: Conexao = Field(default_factory=Conexao)


# ── leitura ────────────────────────────────────────────────────────────────

def _para_saida(project_id: int, linha: Optional[Dict[str, Any]]) -> PerfilSaida:
    pronto = cofre_configurado()
    if not linha:
        return PerfilSaida(project_id=project_id, configurado=False, cofre_pronto=pronto)

    # A máscara é derivada do valor DECIFRADO, então ela some se a chave mudar —
    # o que é o comportamento certo: melhor a tela dizer "—" do que fingir que a
    # credencial está lá quando ela virou ilegível.
    mascarada = "—"
    cifrado = linha.get("wp_app_password_enc")
    tem_senha = bool(cifrado)
    if tem_senha:
        try:
            mascarada = mascara(decifrar(cifrado))
        except (SegredoCorrompido, CofreSemChave):
            mascarada = "ilegível — recadastre"

    return PerfilSaida(
        project_id=project_id,
        configurado=tem_senha,
        cofre_pronto=pronto,
        wp_url=linha.get("wp_url"),
        wp_username=linha.get("wp_username"),
        senha_mascarada=mascarada,
        post_type=linha.get("post_type") or "rec",
        lp_post_type=linha.get("lp_post_type") or "r",
        conexao=Conexao(
            ok=linha.get("conexao_ok"),
            em=linha.get("conexao_em"),
            detalhe=linha.get("conexao_detalhe"),
        ),
    )


async def _buscar(supa: SupabaseService, project_id: int) -> Optional[Dict[str, Any]]:
    linhas = await supa.select(TABELA, {"project_id": f"eq.{project_id}", "limit": 1})
    return linhas[0] if linhas else None


def _supa() -> SupabaseService:
    supa = SupabaseService(get_settings())
    if not supa.enabled:
        raise HTTPException(
            status_code=503,
            detail="Supabase não configurado no backend — sem onde guardar o perfil.",
        )
    return supa


async def _titulo_do_card(opportunity_id: int) -> str:
    """O nome que o operador reconhece, para um card.

    A cadeia de recuo importa mais que o campo preferido: `display_title` está
    NULO em todos os cards de hoje, e quem tem o nome bom é a entidade
    (`canonical_name`, ex.: "Maquininha de Cartão"). Faltando ela, o título da
    primeira página do plano é o texto mais humano que existe no card.

    ⚠️ A chave do plano é `page_title`. `h1_title` não existe — e o recuo que a
    usava ficou morto em silêncio, porque `.get` devolve `None` sem reclamar.
    """
    supa = _supa()
    cards = await supa.select("pautador_entity_opportunities",
                              {"id": f"eq.{opportunity_id}", "limit": 1})
    if not cards:
        return f"card #{opportunity_id}"
    c = cards[0]

    if c.get("display_title"):
        return str(c["display_title"])

    ent_id = c.get("entity_id")
    if ent_id:
        ents = await supa.select("pautador_entities",
                                 {"id": f"eq.{ent_id}", "limit": 1})
        if ents:
            nome = ents[0].get("canonical_name") or ents[0].get("full_name")
            if nome:
                return str(nome)

    paginas = ((c.get("funnel_architecture") or {}).get("pages") or [])
    if paginas and paginas[0].get("page_title"):
        return str(paginas[0]["page_title"])
    return f"card #{opportunity_id}"


@router.get("/projetos/{project_id}/wordpress", response_model=PerfilSaida, dependencies=[Depends(exigir_admin)])
async def obter_perfil(project_id: int) -> PerfilSaida:
    return _para_saida(project_id, await _buscar(_supa(), project_id))


# ── escrita ────────────────────────────────────────────────────────────────

@router.put("/projetos/{project_id}/wordpress", response_model=PerfilSaida, dependencies=[Depends(exigir_admin)])
async def salvar_perfil(project_id: int, body: PerfilEntrada = Body(...)) -> PerfilSaida:
    supa = _supa()
    atual = await _buscar(supa, project_id)

    valores: Dict[str, Any] = {
        "project_id": project_id,
        "wp_url": body.wp_url.rstrip("/"),
        "wp_username": body.wp_username.strip(),
        "post_type": body.post_type.strip() or "rec",
        "lp_post_type": body.lp_post_type.strip() or "r",
    }

    # Senha só entra no update quando veio de verdade. Campo vazio na tela
    # significa "não mexi nela" — apagar por omissão seria a forma mais fácil de
    # derrubar a publicação sem ninguém entender por quê.
    if body.wp_app_password:
        try:
            valores["wp_app_password_enc"] = cifrar(body.wp_app_password.strip())
        except CofreSemChave as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # Credencial nova invalida o teste anterior: ele era sobre a senha antiga.
        valores.update(conexao_ok=None, conexao_em=None, conexao_detalhe=None)

    from datetime import datetime, timezone
    valores["updated_at"] = datetime.now(timezone.utc).isoformat()

    if atual:
        await supa.patch(TABELA, {"project_id": f"eq.{project_id}"}, valores)
    else:
        await supa.insert(TABELA, [valores])

    return _para_saida(project_id, await _buscar(supa, project_id))


# ── teste de conexão ───────────────────────────────────────────────────────

class ResultadoTeste(BaseModel):
    ok: bool
    detalhe: str
    usuario: Optional[str] = None
    pode_publicar: Optional[bool] = None
    post_types_ok: Optional[Dict[str, bool]] = None


@router.post("/projetos/{project_id}/wordpress/testar", response_model=ResultadoTeste, dependencies=[Depends(exigir_admin)])
async def testar_conexao(project_id: int) -> ResultadoTeste:
    """Bate no WordPress do projeto e diz se a credencial serve para publicar.

    Só faz GET. Não cria, não edita e não apaga nada no site — o teste não pode
    ser uma escrita disfarçada.
    """
    supa = _supa()
    linha = await _buscar(supa, project_id)
    if not linha or not linha.get("wp_app_password_enc"):
        raise HTTPException(status_code=404, detail="Este projeto ainda não tem credencial cadastrada.")

    try:
        senha = decifrar(linha["wp_app_password_enc"])
    except (SegredoCorrompido, CofreSemChave) as exc:
        return await _gravar_teste(supa, project_id, ResultadoTeste(ok=False, detalhe=str(exc)))

    base = (linha.get("wp_url") or "").rstrip("/")
    usuario = linha.get("wp_username") or ""
    cred = base64.b64encode(f"{usuario}:{senha}".encode()).decode()
    cabecalhos = {"Authorization": f"Basic {cred}"}

    resultado = await _sondar(base, cabecalhos, linha.get("post_type") or "rec",
                              linha.get("lp_post_type") or "r")
    return await _gravar_teste(supa, project_id, resultado)


async def _sondar(base: str, cabecalhos: Dict[str, str], post_type: str,
                  lp_post_type: str) -> ResultadoTeste:
    """Sonda o site por CAPACIDADE, não por identidade.

    ## Por que não `/wp/v2/users/me`

    Era a sonda óbvia e ela quebra em site endurecido. O `creditoup.com.br`
    devolve **410 Gone** nesse endpoint — plugin de segurança bloqueando
    enumeração de usuário, prática comum e correta. Um teste que reprova a
    credencial porque o site é bem configurado é um teste errado.

    ## O que se sonda no lugar

    `GET /wp/v2/<post_type>?context=edit` — `context=edit` **exige autenticação
    com permissão de edição** naquele post type. É exatamente a pergunta que
    importa ("esta credencial consegue escrever aqui?"), e a resposta separa os
    casos sozinha:

        200  autenticou E pode editar        -> é o que o redator precisa
        401  credencial inválida             -> senha ou usuário errado
        403  autenticou, sem permissão       -> usuário existe, papel insuficiente
        404  post type não existe no REST    -> falta registrar `rec`/`r`

    A identidade do usuário vira um extra: tenta-se `users/me`, e se o site
    bloquear, o teste segue e só não mostra o nome. Bloqueio de enumeração não
    é falha de credencial.
    """
    tipos: Dict[str, bool] = {}
    nome: Optional[str] = None
    problemas: List[str] = []

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as c:
            # A REST responde nesta URL? Sem auth, só para separar "site errado"
            # de "credencial errada" — sem isso os dois viram a mesma mensagem.
            raiz = await c.get(f"{base}/wp-json/")
            if raiz.status_code >= 400:
                return ResultadoTeste(
                    ok=False,
                    detalhe=f"A REST API do WordPress não respondeu em {base}/wp-json/ "
                            f"(HTTP {raiz.status_code}). Confira a URL do site.",
                )

            for t in sorted({post_type, lp_post_type}):
                r = await c.get(f"{base}/wp-json/wp/v2/{t}", headers=cabecalhos,
                                params={"context": "edit", "per_page": 1})
                tipos[t] = r.status_code == 200
                if r.status_code == 401:
                    problemas.append(f"`{t}`: 401 — usuário ou Application Password inválido")
                elif r.status_code == 403:
                    problemas.append(f"`{t}`: 403 — autenticou, mas esse usuário não pode editar")
                elif r.status_code == 404:
                    problemas.append(f"`{t}`: 404 — post type não existe ou não está exposto ao REST")
                elif r.status_code != 200:
                    problemas.append(f"`{t}`: HTTP {r.status_code}")

            # Identidade é bônus: site que bloqueia enumeração continua válido.
            try:
                eu = await c.get(f"{base}/wp-json/wp/v2/users/me", headers=cabecalhos)
                if eu.status_code == 200:
                    d = eu.json()
                    nome = d.get("name") or d.get("slug")
            except httpx.HTTPError:
                pass
    except httpx.HTTPError as exc:
        return ResultadoTeste(ok=False, detalhe=f"Falha de rede ao falar com o site: {str(exc)[:160]}")
    except Exception as exc:  # noqa: BLE001
        return ResultadoTeste(ok=False, detalhe=f"Resposta inesperada do site: {str(exc)[:160]}")

    if problemas:
        return ResultadoTeste(ok=False, usuario=nome, pode_publicar=False,
                              post_types_ok=tipos, detalhe=" · ".join(problemas))

    quem = f"como {nome} " if nome else ""
    return ResultadoTeste(
        ok=True, usuario=nome, pode_publicar=True, post_types_ok=tipos,
        detalhe=f"Conectado {quem}· pode editar os post types {', '.join(sorted(tipos))}.".replace("  ", " "),
    )


async def _gravar_teste(supa: SupabaseService, project_id: int,
                        r: ResultadoTeste) -> ResultadoTeste:
    from datetime import datetime, timezone
    try:
        await supa.patch(TABELA, {"project_id": f"eq.{project_id}"}, {
            "conexao_ok": r.ok,
            "conexao_em": datetime.now(timezone.utc).isoformat(),
            "conexao_detalhe": r.detalhe[:400],
        })
    except Exception as exc:  # noqa: BLE001 — gravar o resultado é acessório ao teste
        log.warning("não gravei o resultado do teste do projeto %s: %s", project_id, str(exc)[:160])
    return r


# ── a lista que o popup do Pautador consome ────────────────────────────────

class ProjetoDestino(BaseModel):
    """Um site candidato a receber o funil, com o motivo de estar apto ou não."""
    project_id: int
    nome: str
    dominio: Optional[str] = None
    apto: bool
    motivo: str


@router.get("/destinos", response_model=List[ProjetoDestino])
async def listar_destinos() -> List[ProjetoDestino]:
    """Os projetos, marcados por aptidão para receber uma publicação.

    O popup mostra TODOS, inclusive os inaptos — com o motivo. Esconder o
    projeto sem credencial faria o operador procurar um site que "sumiu"; dizer
    "falta cadastrar o WordPress" manda ele direto ao lugar certo.
    """
    supa = _supa()
    projetos = await supa.select("projects", {"select": "id,project_name,domain,main_url,visible",
                                              "order": "id.asc", "limit": 200})
    perfis = {int(p["project_id"]): p
              for p in await supa.select(TABELA, {"select": "*", "limit": 200})}

    saida: List[ProjetoDestino] = []
    for p in projetos:
        pid = int(p["id"])
        perfil = perfis.get(pid)
        if not perfil:
            apto, motivo = False, "WordPress não configurado neste projeto"
        elif not perfil.get("wp_app_password_enc"):
            apto, motivo = False, "falta o Application Password"
        elif perfil.get("conexao_ok") is False:
            apto, motivo = False, "o último teste de conexão falhou"
        elif perfil.get("conexao_ok") is None:
            # Deixou de ser apto quando o modo "só gerar" saiu: agora todo
            # disparo publica, e publicar exige teste verde. Marcar como apto
            # aqui deixaria o operador escolher um site que o disparo recusa.
            apto, motivo = False, "conexão ainda não testada"
        else:
            apto, motivo = True, "pronto"
        saida.append(ProjetoDestino(
            project_id=pid,
            nome=p.get("project_name") or f"projeto {pid}",
            dominio=p.get("domain") or p.get("main_url"),
            apto=apto, motivo=motivo,
        ))
    return saida


# ── o gatilho do redator ───────────────────────────────────────────────────
#
# Esta é a fronteira entre o Pautador e o motor redator. O que ela faz HOJE é
# enfileirar: valida que o disparo faz sentido e grava uma linha em
# `pautador_funnel_runs`. Quem executa é a próxima etapa do projeto.
#
# A fila existir ANTES do motor não é adiamento — é o contrato. A linha do run é
# o que dá ao motor uma entrada bem definida (card + site + modo), ao operador um
# histórico com custo, e a esta tela um estado para mostrar. Se o gatilho
# chamasse o motor direto, não haveria onde registrar um run que falhou no meio.

TABELA_RUNS = "pautador_funnel_runs"


class DispararEntrada(BaseModel):
    """Disparo do redator. Não há escolha de modo — ver abaixo.

    ## Por que o modo "só gerar" saiu

    Ele parecia o modo seguro e não era. Os dois modos rodavam o pipeline
    INTEIRO e gastavam exatamente o mesmo: `publish` só é consultado em
    `pipeline.py:267`, no fim do laço de cada página, depois de research, write,
    judge, seo, imagem e widget já terem faturado. "Só gerar" não era ensaio
    barato — era o mesmo run com o último passo desligado.

    E ele entregava MENOS capacidade de revisão, não mais: os artefatos ficavam
    em `runs/<run_id>/` no disco do servidor, sem tela para olhá-los. O rascunho
    do WordPress é a superfície de revisão de verdade — página renderizada, com
    o tema, invisível para o público, e desfazer é apagar o rascunho.

    Sobra um modo só, e ele sempre publica como DRAFT do WordPress. O engine
    fixa isso com `set_status` como ÚLTIMA escrita, porque gravação de meta do
    Elementor ou do Yoast vira draft em publicado em algumas instalações.
    """
    opportunity_id: int
    project_id: int
    # Tetos de gasto DESTE run. `None` usa o padrão do motor (config.yaml), que
    # hoje é folgado de propósito — o teto existe para matar laço de retentativa
    # em fuga, não para reprovar trabalho bom. Medido em campo: ~US$ 2,10 num
    # funil de 5 páginas, ~US$ 0,45 por página.
    teto_usd: Optional[float] = None
    teto_pagina_usd: Optional[float] = None


class RunDoRedator(BaseModel):
    id: int
    opportunity_id: int
    project_id: int
    run_id: Optional[str] = None
    status: str
    modo: str
    custo_usd: Optional[float] = None
    paginas_planejadas: Optional[int] = None
    paginas_geradas: Optional[int] = None
    erro: Optional[str] = None
    criado_em: Optional[str] = None


class DispararSaida(BaseModel):
    """O run enfileirado, mais o estado honesto do motor.

    `motor_conectado=False` é o estado de hoje: o funnelforge ainda não está
    ligado. A tela mostra isso em vez de fingir que o funil está sendo escrito —
    uma barra de progresso que nunca anda é pior que um aviso claro.
    """
    run: RunDoRedator
    motor_conectado: bool
    aviso: Optional[str] = None


def _run_para_saida(r: Dict[str, Any]) -> RunDoRedator:
    return RunDoRedator(
        id=int(r["id"]),
        opportunity_id=int(r["opportunity_id"]),
        project_id=int(r["project_id"]),
        run_id=r.get("run_id"),
        status=r.get("status") or "queued",
        modo=r.get("modo") or "rascunho",
        custo_usd=float(r["custo_usd"]) if r.get("custo_usd") is not None else None,
        paginas_planejadas=r.get("paginas_planejadas"),
        paginas_geradas=r.get("paginas_geradas"),
        erro=r.get("erro"),
        criado_em=r.get("criado_em"),
    )


@router.post("/redator/disparar", response_model=DispararSaida, dependencies=[Depends(exigir_admin)])
async def disparar_redator(body: DispararEntrada = Body(...)) -> DispararSaida:
    """Enfileira a escrita de um funil para um site.

    Tudo que pode ser checado ANTES de gastar dólar é checado aqui: o card tem
    arquitetura? o site tem credencial? a credencial funcionou? já existe um run
    andando para esse par? Cada uma dessas descobertas custaria uma execução
    inteira se ficasse para o motor descobrir.
    """
    supa = _supa()

    # 1 · o card existe e tem funil arquitetado?
    opps = await supa.select(
        "pautador_entity_opportunities",
        {"id": f"eq.{body.opportunity_id}", "select": "id,status,funnel_architecture", "limit": 1},
    )
    if not opps:
        raise HTTPException(status_code=404, detail="Card não encontrado.")
    arq = opps[0].get("funnel_architecture") or {}
    paginas = arq.get("pages") or []
    if not paginas:
        raise HTTPException(
            status_code=409,
            detail="Este card ainda não tem arquitetura de funil. Passe por 'Em funil' antes.",
        )

    # 2 · o site aceita publicação?
    perfil = await _buscar(supa, body.project_id)
    if not perfil:
        raise HTTPException(status_code=409, detail="Este projeto não tem WordPress configurado.")
    if not perfil.get("wp_app_password_enc"):
        raise HTTPException(status_code=409, detail="Este projeto não tem Application Password cadastrado.")
    if perfil.get("conexao_ok") is not True:
        # Sem teste verde não há disparo. Antes existia o modo "rascunho" como
        # saída para site não testado; sem ele, o teste vira pré-requisito — e é
        # o certo: descobrir uma senha errada no último passo de um run pago é o
        # jeito mais caro possível de descobrir.
        raise HTTPException(
            status_code=409,
            detail="Teste a conexão deste site antes de gerar o funil (engrenagem na página do projeto).",
        )

    # 3 · já tem um run andando para esse par?
    andando = await supa.select(TABELA_RUNS, {
        "opportunity_id": f"eq.{body.opportunity_id}",
        "project_id": f"eq.{body.project_id}",
        "status": "in.(queued,running)",
        "limit": 1,
    })
    if andando:
        return DispararSaida(
            run=_run_para_saida(andando[0]),
            motor_conectado=False,
            aviso="Já existe uma execução na fila para este card neste site.",
        )

    criado = await supa.insert(TABELA_RUNS, [{
        "opportunity_id": body.opportunity_id,
        "project_id": body.project_id,
        "status": "queued",
        # Único modo hoje. A coluna fica porque um run é registro histórico do
        # que ELE fez — se um dia existir "publicar no ar", o espaço já existe.
        "modo": "publicado",
        "paginas_planejadas": len(paginas),
        # Os tetos DESTE run ficam na linha. Sem eles a régua de custo da tela
        # não teria contra o que comparar o gasto — e "US$ 1,87" sozinho não diz
        # se está tranquilo ou a um passo de ser cortado.
        "teto_usd": body.teto_usd,
        "teto_pagina_usd": body.teto_pagina_usd,
    }])
    if not criado:
        raise HTTPException(status_code=500, detail="Não consegui gravar a execução.")

    # ── e agora o motor roda de verdade ───────────────────────────────────
    #
    # O perfil é montado AQUI, na requisição, porque é aqui que as validações
    # acabaram de acontecer e o operador ainda está olhando: credencial ilegível
    # ou card sem arquitetura viram 409 com o motivo, e não um run que falha
    # dez segundos depois numa tela que ninguém está vendo.
    from app.redator import PerfilIncompleto, montar_perfil
    from app.redator import worker as w

    entidade = None
    if opps[0].get("entity_id"):
        ent = await supa.select("pautador_entities",
                                {"id": f"eq.{opps[0]['entity_id']}", "limit": 1})
        entidade = ent[0] if ent else None

    try:
        perfil_do_run = montar_perfil(
            perfil_wp=perfil, arquitetura=arq, entidade=entidade,
            teto_usd=body.teto_usd, teto_pagina_usd=body.teto_pagina_usd)
    except PerfilIncompleto as exc:
        await supa.patch(TABELA_RUNS, {"id": f"eq.{criado[0]['id']}"},
                         {"status": "failed", "erro": str(exc)})
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # `create_task` e não `BackgroundTasks`: um run dura ~45 min e não pode ficar
    # amarrado ao ciclo de vida de uma requisição. A referência é guardada porque
    # o asyncio descarta task sem referência forte no meio do caminho.
    tarefa = asyncio.create_task(w.executar(
        supa=supa, run_row_id=int(criado[0]["id"]),
        arquitetura=arq, perfil=perfil_do_run, publicar=True))
    _TAREFAS.add(tarefa)
    tarefa.add_done_callback(_TAREFAS.discard)

    return DispararSaida(
        run=_run_para_saida(criado[0]),
        motor_conectado=True,
        aviso="O motor começou. O funil sobe como rascunho do WordPress; "
              "acompanhe o andamento na execução.",
    )


@router.post("/redator/runs/{run_row_id}/cancelar")
async def cancelar_run(run_row_id: int) -> Dict[str, Any]:
    """Encerra um run em andamento.

    Duas coisas acontecem, e as duas importam: o PROCESSO do motor é encerrado
    (senão ele segue gastando até o timeout de 3h) e a LINHA é fechada (senão o
    card fica preso, porque o disparo recusa duplicata enquanto houver run
    aberto).

    A linha é fechada mesmo quando o processo não está neste backend — é o caso
    de um run herdado de um reinício, e aí cancelar é justamente o que destrava.
    """
    from app.redator import worker as w

    supa = _supa()
    linhas = await supa.select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    if linhas[0].get("status") not in ("queued", "running"):
        return {"cancelado": False, "motivo": "esta execução já tinha terminado"}

    matou_o_processo = await w.cancelar(run_row_id)
    from datetime import datetime, timezone
    await supa.patch(TABELA_RUNS, {"id": f"eq.{run_row_id}"}, {
        "status": "cancelled",
        "erro": "Cancelado pelo operador."
                + ("" if matou_o_processo else " (o processo não estava neste backend)"),
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    })
    return {"cancelado": True, "processo_encerrado": matou_o_processo}


@router.get("/redator/runs", response_model=List[RunDoRedator])
async def listar_runs(opportunity_id: Optional[int] = None) -> List[RunDoRedator]:
    """O histórico de execuções, do mais novo para o mais velho.

    Com `opportunity_id`: as execuções daquele card — é o que o drawer do
    Pautador pede. Sem: as últimas de todos os cards, que é o que a página
    `/redator` precisa para ter porta de entrada. Um run é caro (~US$ 2 e ~45
    min); exigir que o operador saiba de cor o número do card para reencontrá-lo
    seria esconder trabalho que já foi pago.
    """
    filtro: Dict[str, Any] = {"order": "criado_em.desc", "limit": 50}
    if opportunity_id is not None:
        filtro["opportunity_id"] = f"eq.{opportunity_id}"
    return [_run_para_saida(r) for r in await _supa().select(TABELA_RUNS, filtro)]


@router.delete("/redator/runs/{run_row_id}")
async def excluir_run(run_row_id: int) -> Dict[str, Any]:
    """Tira uma execução encerrada do quadro.

    ## Duas regras, e as duas protegem dinheiro

    **Não apaga run em andamento.** Cancelar mata o processo; excluir só some com
    a linha. Apagar a linha de um run vivo deixaria o motor gastando sem nada no
    banco apontando para ele — e sem a linha, nem `cancelar` acha mais o PID.

    **Não apaga run que publicou.** As páginas continuam no WordPress e a linha
    é o único lugar onde `paginas_publicadas` guarda o `post_id` e a URL que o
    WP devolveu. Sem ela, ninguém sabe mais quais rascunhos vieram deste funil —
    e a atribuição de receita depende de casar essa URL exata.

    O que sobra é o caso comum: tentativa fracassada, sem nada no ar. Esta é a
    que polui o quadro, e apagá-la não perde nada que exista noutro lugar (os
    artefatos ficam na pasta do run).
    """
    supa = _supa()
    linhas = await supa.select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    r = linhas[0]

    if r.get("status") in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail="Esta execução ainda está em andamento. Cancele antes de excluir.")

    publicadas = r.get("paginas_publicadas") or []
    if publicadas:
        raise HTTPException(
            status_code=409,
            detail=f"Esta execução publicou {len(publicadas)} página(s) no WordPress. "
                   "A linha é o único registro de quais rascunhos vieram dela — "
                   "apague os rascunhos no site antes, se quiser descartá-la.")

    await supa.delete(TABELA_RUNS, {"id": f"eq.{run_row_id}"})
    return {"excluido": True, "custo_perdido_usd": float(r.get("custo_usd") or 0)}


class ProvaVisualSaida(BaseModel):
    page_number: int
    arquivo: str
    url: str
    status_http: Optional[int] = None
    parece_erro: bool = False
    bytes: int = 0
    resumo: str


@router.post("/redator/runs/{run_row_id}/prova-visual/{page_number}",
             response_model=ProvaVisualSaida)
async def prova_visual(run_row_id: int, page_number: int) -> ProvaVisualSaida:
    """Fotografa a página publicada, inteira, rolando — e guarda no run.

    ## A pergunta que só o olho responde

    Os portões provam FATO e FORMA: o número tem fonte, o HTML tem contrato.
    Nenhum deles vê o tema montar a página. Um bloco que o tema não conhece, uma
    imagem que não carregou, um acordeão que não abre — nada disso reprova em
    validador, e tudo isso o leitor que a gente PAGOU para trazer vê primeiro.

    ## Rolar antes de fotografar não é detalhe

    `full_page` sozinho fotografa a página inteira com os blocos de baixo em
    branco, porque o lazy-load nunca foi acionado. O `scroll=True` do
    `PlaywrightScreenshotProvider` percorre a página antes do clique — e é o que
    faz a foto valer como prova em vez de parecer defeito de conteúdo.

    ⚠️ O print vale para o estado ATUAL. Ele é a foto do que está no ar agora,
    não um artefato do run: reeditar a página no WordPress invalida a foto sem
    que nada aqui mude, e por isso o arquivo é sobrescrito a cada chamada em vez
    de acumular versões que ninguém sabe datar.
    """
    from app.redator import worker as w

    supa = _supa()
    linhas = await supa.select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    run = linhas[0]

    pagina = next((p for p in (run.get("paginas_publicadas") or [])
                   if int(p.get("page_number") or 0) == page_number), None)
    if pagina is None:
        raise HTTPException(
            status_code=409,
            detail=f"A página {page_number} não foi publicada por esta execução — "
                   f"não há endereço para fotografar.")

    # ⚠️ RASCUNHO NÃO SE FOTOGRAFA, E O ERRO DISSO ERA UM DIAGNÓSTICO ERRADO.
    #
    # Rascunho no WordPress só é visível para quem tem SESSÃO logada, e
    # Application Password autentica requisição REST — não carregamento normal
    # de página (`wp_authenticate_application_password` só roda para REST e
    # XML-RPC). O Chromium recebe a tela de "não encontrado", e a versão
    # anterior desta rota devolvia "a página parece um erro (título ou corpo de
    # 404)" — mandando o operador conferir um conteúdo que está intacto.
    #
    # Recusar antes de abrir o browser é mais honesto e mais barato: o print de
    # uma página inacessível não prova nada sobre ela.
    if pagina.get("status_wp") != "publish":
        raise HTTPException(
            status_code=409,
            detail=f"A página {page_number} ainda está como "
                   f"`{pagina.get('status_wp') or 'sem status'}` no WordPress, e "
                   f"rascunho só é visível para quem está logado — o print sairia "
                   f"da tela de 'não encontrado', não da página. Publique e releia "
                   f"do WordPress; aí o print vale.")

    url = str(pagina.get("url_wp") or "")
    if not url.startswith("https://"):
        raise HTTPException(
            status_code=409,
            detail=f"O endereço da página não é https ({url!r}). O provedor de "
                   f"print exige https antes de abrir o browser.")

    pasta = _pasta_do_run(run)
    if pasta is None or not pasta.exists():
        raise HTTPException(
            status_code=409,
            detail="A pasta desta execução não existe mais no disco — sem onde "
                   "guardar o print.")

    # ⚠️ O nome PRECISA casar com `paginas._ARQUIVO_SERVIVEL` (`^p\d+...\.png$`),
    # senão a rota que serve artefatos recusa o arquivo que acabamos de gravar —
    # e o operador vê "artefato não encontrado" logo depois de um print bem
    # sucedido.
    arquivo = f"p{page_number}-prova-visual.png"
    destino = pasta / arquivo

    try:
        exe = w._executavel()
    except w.MotorIndisponivel as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    proc = await asyncio.create_subprocess_exec(
        str(exe), "print-url", url, str(destino),
        cwd=str(w.raiz_do_motor()),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        saida, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_PRINT_S)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(
            status_code=504,
            detail=f"O print passou de {int(TIMEOUT_PRINT_S)}s. Página muito "
                   f"pesada, ou o site não respondeu.") from None

    texto = (saida or b"").decode("utf-8", "replace")
    if proc.returncode != 0 or not destino.exists():
        raise HTTPException(
            status_code=502,
            detail=f"O print falhou: {texto.strip()[-400:] or 'sem saída'}")

    # A última linha é o JSON do comando; o resto é ruído de browser.
    dados: Dict[str, Any] = {}
    for linha in reversed(texto.strip().splitlines()):
        try:
            dados = json.loads(linha)
            break
        except ValueError:
            continue

    parece_erro = bool(dados.get("is_error_page"))
    status_http = dados.get("status")
    if parece_erro:
        # A página é publicada (a rota já barrou rascunho acima), então erro aqui
        # é erro de verdade: permalink trocado, post removido, tema quebrado.
        resumo = ("A foto saiu, mas a página parece um erro (título ou corpo de "
                  "404) — e ela está publicada, então isso não é falta de acesso.")
    else:
        resumo = "Foto da página no ar, inteira, com o lazy-load acionado."

    return ProvaVisualSaida(
        page_number=page_number, arquivo=arquivo, url=url,
        status_http=status_http if isinstance(status_http, int) else None,
        parece_erro=parece_erro, bytes=int(dados.get("bytes") or destino.stat().st_size),
        resumo=resumo,
    )


class ReconciliacaoSaida(BaseModel):
    run_row_id: int
    status_antes: str
    status_agora: str
    motor_vivo: bool
    paginas_publicadas: int
    custo_usd: float
    resumo: str


@router.post("/redator/runs/{run_row_id}/reconciliar", response_model=ReconciliacaoSaida)
async def reconciliar_run(run_row_id: int) -> ReconciliacaoSaida:
    """Recupera do disco um run cujo acompanhamento morreu.

    ## O defeito que ela conserta

    O motor roda como subprocesso e quem escreve no banco é uma tarefa asyncio
    DENTRO do uvicorn. Reiniciar o backend mata a tarefa — e não mata o
    subprocesso. O motor segue escrevendo e publicando no WordPress, e a linha
    do run fica `running` para sempre, com o custo e as páginas congelados no
    instante do reinício.

    Medido em 18/08/2026, run #7: o backend foi reiniciado 17 min depois do
    disparo; a linha parou em 4 passos e US$ 0,23, e o `state.json` do motor já
    registrava 3 páginas publicadas. Sem esta rota, o único caminho seria SQL na
    mão — ou refazer um funil já pago.

    ## De onde vem a verdade

    Do `state.json` que o motor grava a cada etapa, com escrita atômica. É a
    mesma fonte que o acompanhamento vivo lê; muda só quem pergunta.

    ⚠️ Ela NÃO ressuscita o acompanhamento. Enquanto o motor estiver vivo e sem
    quem o observe, cada chamada traz o estado daquele instante — e a resposta
    diz `motor_vivo` para a tela não fingir que voltou ao normal.
    """
    from app.redator import worker as w

    supa = _supa()
    linhas = await supa.select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    run = linhas[0]

    artefatos = run.get("artefatos") or {}
    carimbo = artefatos.get("carimbo")
    if not carimbo:
        raise HTTPException(
            status_code=409,
            detail="Esta execução não registrou o carimbo do motor — não há pasta "
                   "de run para reconciliar.")

    raiz = w.raiz_do_motor()
    run_dir = w._achar_run_dir(raiz, str(carimbo))
    if run_dir is None:
        raise HTTPException(
            status_code=409,
            detail=f"Não achei a pasta do run `{carimbo}` em {raiz / 'runs'}. "
                   f"O motor pode não ter chegado a criá-la.")

    estado = w._ler_estado(run_dir)
    if not estado:
        raise HTTPException(
            status_code=409,
            detail="A pasta do run existe, mas o `state.json` ainda não foi escrito.")

    # O PID decide o STATUS, e só ele. O `state.json` diz o que já aconteceu;
    # ele não sabe dizer se ainda vai acontecer mais coisa.
    pid = artefatos.get("pid")
    vivo = False
    if isinstance(pid, int):
        try:
            os.kill(pid, 0)
            vivo = True
        except (OSError, ProcessLookupError):
            vivo = False

    resumo = w.resumo_do_estado(estado, w._flags(raiz, True))
    antes = str(run.get("status") or "")

    # ⚠️ FILTRAR POR `_COLUNAS` NÃO É ZELO, É OBRIGATÓRIO.
    #
    # `resumo_do_estado()` devolve mais chaves do que a tabela tem — é o mesmo
    # dicionário que alimenta a matriz da tela. Mandar tudo para o PostgREST
    # devolve **400 Bad Request** com uma mensagem sobre a primeira coluna
    # desconhecida, e o run continua órfão. O worker filtra na linha 285; aqui
    # tem de filtrar igual, pela MESMA constante, senão os dois divergem no dia
    # em que alguém acrescentar uma coluna.
    patch: Dict[str, Any] = {k: v for k, v in resumo.items() if k in w._COLUNAS}

    # ⚠️ O ESTADO DO MOTOR NÃO É DONO DO `status_wp`. O WORDPRESS É.
    #
    # `state.json` congela o que o motor VIU no instante em que publicou — e o
    # motor publica sempre como rascunho (`publish_status: draft`). Quem publica
    # de verdade é o humano, no WP, e quem descobre isso é `/reler-wp`.
    #
    # Sem esta costura, reconciliar DESFAZIA a releitura: medido em 18/08/2026,
    # o run 7 tinha a LP em `publish` com o permalink
    # `/r/maquininha-de-cartao-menor-taxa/`, e uma reconciliação a devolveu para
    # `draft` com `?post_type=r&p=2163`. O Hub de Tráfego barra LP em rascunho —
    # então o operador publicava, o sistema destravava, e o clique seguinte em
    # "reconciliar" travava tudo de novo sem dizer nada.
    #
    # A posse é por CAMPO: o motor sabe QUAIS páginas existem e o `post_id` de
    # cada uma; o WordPress sabe em que estado elas estão.
    por_post = {p.get("post_id"): p for p in (run.get("paginas_publicadas") or [])}
    costuradas = []
    for pagina in (patch.get("paginas_publicadas") or []):
        antiga = por_post.get(pagina.get("post_id"))
        if antiga and antiga.get("status_wp") == "publish":
            pagina = {**pagina, "status_wp": "publish", "url_wp": antiga.get("url_wp")}
        costuradas.append(pagina)
    if costuradas:
        patch["paginas_publicadas"] = costuradas
        lp = next((p for p in costuradas if str(p.get("role") or "").upper() == "LP"), None)
        if lp and lp.get("status_wp") == "publish":
            patch["lp_url"] = lp.get("url_wp")
    if vivo:
        # Continua `running`: fechar como `done` um motor que ainda escreve
        # faria a tela liberar o card para a próxima etapa com páginas faltando.
        patch["status"] = "running"
    else:
        falhou = bool(resumo.get("erro"))
        patch["status"] = "error" if falhou else "done"

    await supa.patch(TABELA_RUNS, {"id": f"eq.{run_row_id}"}, patch)

    publicadas = len(patch.get("paginas_publicadas") or [])
    custo = float(patch.get("custo_usd") or 0.0)
    if vivo:
        texto = (f"O motor ainda está rodando (pid {pid}) e ninguém o acompanha. "
                 f"Até agora: {publicadas} página(s), US$ {custo:.2f}. "
                 f"Chame de novo para atualizar.")
    else:
        texto = (f"O motor terminou. {publicadas} página(s) publicada(s), "
                 f"US$ {custo:.2f}.")

    return ReconciliacaoSaida(
        run_row_id=run_row_id, status_antes=antes, status_agora=str(patch["status"]),
        motor_vivo=vivo, paginas_publicadas=publicadas, custo_usd=round(custo, 6),
        resumo=texto,
    )


class PaginaRelida(BaseModel):
    post_id: int
    post_type: str
    role: str
    status_antes: str
    status_agora: str
    url_antes: str
    url_agora: str
    mudou: bool
    erro: Optional[str] = None


class ReleituraSaida(BaseModel):
    run_row_id: int
    paginas: List[PaginaRelida]
    mudaram: int
    lp_url_antes: Optional[str] = None
    lp_url_agora: Optional[str] = None
    no_ar: int
    resumo: str


@router.post("/redator/runs/{run_row_id}/reler-wp", response_model=ReleituraSaida, dependencies=[Depends(exigir_admin)])
async def reler_do_wordpress(run_row_id: int) -> ReleituraSaida:
    """Relê no WordPress o estado real das páginas deste run.

    ## O elo que faltava para o ciclo fechar

    `status_wp` e `lp_url` são gravados UMA VEZ, pelo worker, no instante da
    escrita — e o motor sobe tudo como rascunho de propósito
    (`engine/config.yaml: publish_status: draft`, "generate → draft → human
    reviews and clicks publish"). Ninguém relê o WordPress depois.

    A consequência era travar o ciclo inteiro: o operador publicava a LP no WP,
    o permalink definitivo nascia, e o run continuava dizendo `draft` com
    `?post_type=r&p=2152`. O Hub de Tráfego barra LP em rascunho e URL
    provisória — corretamente, e para sempre, porque o dado nunca se atualizava.

    ## O que ela toca

    **Lê** o WordPress (`GET`, `context=edit`) e **escreve só na nossa tabela**.
    Nada é publicado, editado ou apagado no site: quem clica em publicar é o
    humano, no WP, que é o desenho do motor e não um acidente.

    ⚠️ Página apagada no WP volta 404 e é RELATADA, não removida da linha.
    `paginas_publicadas` é o único registro de qual rascunho veio de qual run —
    é dele que a atribuição de receita depende. Sumir com a linha resolveria a
    tela e destruiria a rastreabilidade.
    """
    supa = _supa()
    linhas = await supa.select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    run = linhas[0]

    paginas = list(run.get("paginas_publicadas") or [])
    if not paginas:
        raise HTTPException(
            status_code=409,
            detail="Esta execução não publicou nenhuma página — não há o que reler.")

    perfil = await _buscar(supa, int(run["project_id"]))
    if not perfil or not perfil.get("wp_app_password_enc"):
        raise HTTPException(
            status_code=409,
            detail="O projeto desta execução não tem credencial de WordPress cadastrada.")

    try:
        senha = decifrar(perfil["wp_app_password_enc"])
    except (SegredoCorrompido, CofreSemChave) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    base = (perfil.get("wp_url") or "").rstrip("/")
    usuario = perfil.get("wp_username") or ""
    cred = base64.b64encode(f"{usuario}:{senha}".encode()).decode()
    cabecalhos = {"Authorization": f"Basic {cred}"}

    relidas: List[PaginaRelida] = []
    novas: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as c:
        for p in paginas:
            nova = dict(p)
            post_id = p.get("post_id")
            tipo = p.get("post_type") or "post"
            antes_status = str(p.get("status_wp") or "")
            antes_url = str(p.get("url_wp") or "")
            erro: Optional[str] = None
            agora_status, agora_url = antes_status, antes_url

            if not post_id:
                erro = "linha sem post_id — nada a consultar"
            else:
                try:
                    r = await c.get(f"{base}/wp-json/wp/v2/{tipo}/{post_id}",
                                    params={"context": "edit"}, headers=cabecalhos)
                    if r.status_code == 200:
                        d = r.json()
                        agora_status = str(d.get("status") or antes_status)
                        # ⚠️ `link` é o permalink de verdade. Enquanto o post é
                        # rascunho ele vem como `?post_type=x&p=123`; publicado,
                        # vira o endereço final. É essa troca que destrava o
                        # Tráfego, e é por isso que a URL é relida junto do
                        # status: atualizar um sem o outro deixaria uma campanha
                        # apontando para o endereço antigo.
                        agora_url = str(d.get("link") or antes_url)
                    elif r.status_code == 404:
                        erro = "não existe mais no WordPress (404)"
                    elif r.status_code in (401, 403):
                        erro = f"credencial sem permissão de leitura ({r.status_code})"
                    else:
                        erro = f"HTTP {r.status_code}"
                except httpx.HTTPError as exc:  # noqa: PERF203
                    erro = f"falha de rede: {type(exc).__name__}"

            if erro is None:
                nova["status_wp"] = agora_status
                nova["url_wp"] = agora_url
            novas.append(nova)
            relidas.append(PaginaRelida(
                post_id=int(post_id or 0), post_type=str(tipo),
                role=str(p.get("role") or ""),
                status_antes=antes_status, status_agora=agora_status,
                url_antes=antes_url, url_agora=agora_url,
                mudou=(agora_status != antes_status or agora_url != antes_url),
                erro=erro,
            ))

    # A LP é a que o Tráfego usa como destino do anúncio. `role` é gravado em
    # caixa alta pelo worker ("LP"), e comparar sem normalizar deixaria a
    # `lp_url` velha numa linha que mudou — o defeito exato que esta rota existe
    # para consertar.
    lp = next((n for n in novas if str(n.get("role") or "").upper() == "LP"), None)
    lp_antes = run.get("lp_url")
    lp_agora = str(lp.get("url_wp")) if lp else lp_antes

    patch: Dict[str, Any] = {"paginas_publicadas": novas}
    if lp_agora and lp_agora != lp_antes:
        patch["lp_url"] = lp_agora
    await supa.patch(TABELA_RUNS, {"id": f"eq.{run_row_id}"}, patch)

    mudaram = sum(1 for r in relidas if r.mudou)
    no_ar = sum(1 for r in relidas if r.status_agora == "publish")
    if mudaram == 0:
        resumo = (f"Nada mudou: as {len(relidas)} páginas seguem como estavam. "
                  f"Publique no WordPress e releia.")
    else:
        resumo = (f"{mudaram} de {len(relidas)} página(s) mudaram · "
                  f"{no_ar} no ar (`publish`).")

    return ReleituraSaida(
        run_row_id=run_row_id, paginas=relidas, mudaram=mudaram,
        lp_url_antes=lp_antes, lp_url_agora=lp_agora, no_ar=no_ar, resumo=resumo,
    )


@router.get("/redator/configuracao")
async def configuracao_do_redator() -> Any:
    """A doutrina, os prompts e os modelos — o que o motor diz e com o que.

    Somente leitura, e isso é decisão declarada, não pendência esquecida: ver
    `app/redator/configuracao.py`.
    """
    from app.redator import configuracao as cfg
    from app.redator import worker as w

    try:
        raiz = w.raiz_do_motor()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return cfg.ler(raiz)


@router.get("/redator/quadro")
async def quadro_do_redator() -> Any:
    """O posto de comando: onde cada funil está no ciclo.

    ## Por que isto não é a lista de runs

    A lista responde "que execuções existiram". O quadro responde a pergunta que
    o operador realmente tem: **o que está pronto para ser escrito, o que está
    sendo escrito agora, e o que já virou rascunho esperando revisão.**

    A diferença que importa é a primeira coluna. Ela não vem desta tabela: são os
    cards do Pautador que chegaram a `ready` COM arquitetura de funil e que ainda
    não tiveram um run bem-sucedido. Sem ela, a única forma de disparar um funil
    é voltar ao Pautador, achar o card e arrastá-lo — e o operador que abriu o
    Redator para trabalhar não tem por onde começar.

    ## O que conta como "já escrito"

    Um card com run `done` sai da fila. Um com run `failed` VOLTA — porque
    falhou é justamente o caso em que se quer tentar de novo, agora sabendo o
    que já foi pago (a tela do funil mostra isso).
    """
    supa = _supa()

    runs = await supa.select(TABELA_RUNS, {"order": "criado_em.desc", "limit": 100})
    # Não só os `ready`: um card que já rodou pode ter voltado a outro estado, e
    # o quadro precisa saber o título dele para não escrever "card #73".
    cards = await supa.select("pautador_entity_opportunities",
                              {"order": "updated_at.desc", "limit": 200})
    projetos = await supa.select("project_wordpress", {"limit": 100})
    entidades = await supa.select("pautador_entities", {"limit": 300})

    # ⚠️ A coluna é `wp_url`. `wp_base_url` não existe — e como `.get` devolve
    # `None` em silêncio, o domínio saía vazio em toda linha sem nenhum erro.
    nome_do_projeto = {int(p["project_id"]): (p.get("wp_url") or "")
                       .replace("https://", "").replace("http://", "").rstrip("/")
                       for p in projetos}
    nome_da_entidade = {int(e["id"]): (e.get("canonical_name") or e.get("full_name") or "")
                        for e in entidades}

    def titulo_de(c: Dict[str, Any]) -> str:
        """O nome que o operador reconhece.

        `display_title` está NULO em todos os cards de hoje, então a cadeia de
        recuo importa mais que o campo preferido: a entidade tem o nome
        canônico ("Cartão para Negativado") e, faltando ela, o H1 da LP é o
        título mais humano que existe no card.
        """
        if c.get("display_title"):
            return str(c["display_title"])
        ent = nome_da_entidade.get(int(c.get("entity_id") or 0), "")
        if ent:
            return ent
        # ⚠️ A CHAVE É `page_title`, NÃO `h1_title`.
        #
        # Este recuo estava MORTO: `funnel_architecture.pages[]` grava
        # `page_title`, e `h1_title` não existe em lugar nenhum do plano. Como
        # `.get` devolve `None` em silêncio, o ramo nunca disparava e todo card
        # sem entidade caía em "card #N" — sem erro, sem log, sem sintoma.
        paginas = ((c.get("funnel_architecture") or {}).get("pages") or [])
        if paginas and paginas[0].get("page_title"):
            return str(paginas[0]["page_title"])
        return f"card #{c['id']}"

    # Um card sai da fila quando tem run vivo ou concluído. `failed` NÃO tira:
    # é o caso em que se quer tentar de novo.
    ocupados = {int(r["opportunity_id"]) for r in runs
                if r.get("status") in ("queued", "running", "done")}

    prontos = []
    for c in cards:
        paginas = ((c.get("funnel_architecture") or {}).get("pages") or [])
        # `ready` + arquitetura é o que define "pronto para escrever". Um card
        # em `validating` tem arquitetura mas ainda não passou pelo julgamento
        # humano — disparar US$ 2 nele seria pagar por uma decisão não tomada.
        if c.get("status") != "ready" or not paginas or int(c["id"]) in ocupados:
            continue
        prontos.append({
            "opportunity_id": int(c["id"]),
            "titulo": titulo_de(c),
            "paginas": len(paginas),
            "score": c.get("score"),
            "cpc_max": c.get("cpc_max"),
            "ecpm_band": c.get("ecpm_band"),
            "estimated_volume": c.get("estimated_volume"),
            "atualizado_em": c.get("updated_at"),
        })

    titulo_do_card = {int(c["id"]): titulo_de(c) for c in cards}

    def enfeitar(r: Dict[str, Any]) -> Dict[str, Any]:
        pubs = r.get("paginas_publicadas") or []
        return {
            **_run_para_saida(r).model_dump(),
            "titulo": titulo_do_card.get(int(r["opportunity_id"]),
                                         f"card #{r['opportunity_id']}"),
            "dominio": nome_do_projeto.get(int(r["project_id"]), ""),
            "paginas_publicadas": len(pubs),
            "lp_url": r.get("lp_url"),
            # Quantas etapas o motor já registrou — é o que dá sinal de vida a um
            # card na coluna "escrevendo" sem precisar abrir o funil.
            "etapas": len(r.get("passos") or {}),
        }

    escrevendo = [enfeitar(r) for r in runs if r.get("status") in ("queued", "running")]
    escritos = [enfeitar(r) for r in runs if r.get("status") == "done"]
    interrompidos = [enfeitar(r) for r in runs
                     if r.get("status") in ("failed", "cancelled")]

    return {
        "prontos": prontos,
        "escrevendo": escrevendo,
        "escritos": escritos,
        "interrompidos": interrompidos,
        "totais": {
            # O gasto acumulado inclui os runs que falharam — dinheiro gasto é
            # dinheiro gasto, e escondê-lo nos relatórios é como o custo de um
            # funil deixa de ser confrontado com a receita dele.
            "gasto_usd": round(sum(float(r.get("custo_usd") or 0) for r in runs), 4),
            "runs": len(runs),
            "paginas_no_ar": sum(len(r.get("paginas_publicadas") or []) for r in runs),
        },
    }


def _pasta_do_run(linha: Dict[str, Any]):
    """A pasta de artefatos deste run, se ela ainda existe no disco.

    ## ⚠️ `artefatos` tem DOIS formatos na mesma tabela

    Medido em 19/08/2026:

        run 7  {"carimbo": "20260818-112043"}
        run 9  {"pasta": "fgts-saque-aniversario-20260819-135623", "arquivos": [32 nomes]}

    Esta função só conhecia `carimbo`. Para o run 9 ela devolvia `None`, a rota
    concluía "os arquivos deste run não estão no disco deste servidor" — e o
    desenho do funil sumia da tela **com os 32 artefatos ali, incluindo 11 kB de
    HTML da p3 e 13 kB da p4**. O operador viu "não posso perder o que já foi
    escrito"; nada tinha se perdido, a tela é que não achava.

    Ler os dois formatos é o conserto barato. O caro — unificar o que o worker
    grava — fica para quando alguém tocar no worker, e até lá esta função é a
    tradutora.
    """
    from app.redator import worker as w

    arte = (linha.get("artefatos") or {}) or {}
    try:
        raiz = w.raiz_do_motor()
    except Exception:  # noqa: BLE001 — motor ausente não pode derrubar a tela
        return None

    # Formato novo: o nome da pasta, inteiro. É o mais direto — sem varredura.
    pasta = arte.get("pasta")
    if pasta:
        cand = raiz / "runs" / str(pasta)
        if cand.is_dir():
            return cand

    # Formato antigo: só o carimbo; acha a pasta que termina nele.
    carimbo = arte.get("carimbo")
    if carimbo:
        try:
            return w._achar_run_dir(raiz, str(carimbo))
        except Exception:  # noqa: BLE001
            return None

    # Último recurso: o `run_id` da linha carrega `<slug>-<carimbo>` e é o mesmo
    # nome da pasta. Vale para runs gravados antes de qualquer um dos dois.
    rid = linha.get("run_id")
    if rid:
        cand = raiz / "runs" / str(rid)
        if cand.is_dir():
            return cand
    return None


@router.get("/redator/runs/{run_row_id}/paginas")
async def paginas_do_run(run_row_id: int) -> Any:
    """O funil ESCRITO: uma entrada por página, com o texto, o SEO, a imagem, os
    links oficiais e os prints.

    Separado da matriz de propósito. A matriz é telemetria — pesa ~11 kB e muda
    a cada 3 s durante o run. Isto é conteúdo: pesa mais, muda pouco, e continua
    valendo depois que o run acabou. Juntar os dois faria o polling arrastar o
    texto das cinco páginas 900 vezes.
    """
    linhas = await _supa().select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    r = linhas[0]

    from app.redator import paginas as pgs
    from app.redator import worker as w

    run_dir = _pasta_do_run(r)
    estado = w._ler_estado(run_dir) if run_dir else None
    if not estado:
        # A linha existe mas os artefatos não — run antigo, disco limpo, ou
        # backend em outra máquina. Dizer isso é melhor que devolver [] e deixar
        # a tela parecer um funil vazio.
        return {"paginas": [], "sem_artefatos": True,
                "motivo": "Os arquivos deste run não estão no disco deste servidor."}

    return {
        "paginas": pgs.montar(estado, run_dir=run_dir,
                              publicadas=r.get("paginas_publicadas") or []),
        "sem_artefatos": False,
        "avatar": (estado.get("plan") or {}).get("avatar_summary") or "",
        "tom": (estado.get("plan") or {}).get("tone_voice") or "",
    }


@router.get("/redator/runs/{run_row_id}/arquivo/{nome}")
async def artefato_do_run(run_row_id: int, nome: str):
    """Serve uma imagem gerada pelo motor.

    Lista branca de nome + confinamento ao `run_dir` ficam em
    `paginas.caminho_de_artefato` — a pasta também guarda o `state.json` com o
    briefing inteiro, e um path traversal aqui vazaria o plano do funil.
    """
    from fastapi.responses import FileResponse

    from app.redator import paginas as pgs

    linhas = await _supa().select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    caminho = pgs.caminho_de_artefato(_pasta_do_run(linhas[0]), nome)
    if caminho is None:
        raise HTTPException(status_code=404, detail="Artefato não encontrado.")
    # Imutável: o motor nunca reescreve um artefato de run encerrado.
    return FileResponse(caminho, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/redator/runs/{run_row_id}/matriz")
async def matriz_do_run(run_row_id: int, request: Request, resposta: Response) -> Any:
    """A grade páginas × etapas de um run, para a tela do redator.

    ## O 304 não é otimização, é a condição de existir o polling

    A tela pergunta a cada 3 s durante ~45 min: são ~900 requisições por run. A
    grade completa de um funil de 5 páginas tem 63 células e ~40 kB de JSON —
    trafegá-la 900 vezes seriam ~36 MB para mostrar, na esmagadora maioria das
    vezes, exatamente o que já estava na tela.

    `passos_hash` muda quando e somente quando alguma etapa muda de estado. Com
    ele, a resposta cara sai uma vez por etapa concluída (~30 por run) e as
    outras ~870 são um 304 vazio.

    ⚠️ O ETag tem de incluir o STATUS da linha, não só o hash dos passos: o
    último `patch` de um run que termina muda `status` de `running` para `done`
    sem tocar em nenhuma etapa. Com um ETag só de `passos_hash`, a tela ficaria
    para sempre mostrando "em andamento" num run já encerrado.
    """
    linhas = await _supa().select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    r = linhas[0]

    # ⚠️ `VERSAO_MATRIZ` NÃO É CERIMÔNIA — SEM ELA, CAMPO NOVO NUNCA CHEGA.
    #
    # O ETag é derivado do ESTADO DO RUN, não do conteúdo da resposta. Num run
    # `done` o `passos_hash` está congelado para sempre, então todo browser com
    # cache quente recebe 304 e reusa o corpo que baixou ANTES — e um campo
    # acrescentado ao payload fica invisível eternamente.
    #
    # Medido em 18/08/2026: o campo `titulo` foi acrescentado para a manchete
    # parar de escrever `card #74`, o servidor passou a devolvê-lo, e a tela
    # continuou mostrando `card #74`. O conserto estava certo e não chegava.
    #
    # Ao MUDAR A FORMA desta resposta, incremente este número.
    VERSAO_MATRIZ = 2
    etiqueta = 'W/"{}-{}-v{}"'.format(
        r.get("passos_hash") or "vazio", r.get("status") or "?", VERSAO_MATRIZ)
    resposta.headers["ETag"] = etiqueta
    # Sem isto um proxy pode servir a grade de 30 s atrás como se fosse a de agora.
    resposta.headers["Cache-Control"] = "no-cache"
    if request.headers.get("if-none-match") == etiqueta:
        return Response(status_code=304, headers=dict(resposta.headers))

    from app.redator import matriz as mz

    grade = mz.montar({"step_status": r.get("passos") or {}})
    return {
        "run": _run_para_saida(r),
        # ⚠️ O TÍTULO VEM DAQUI, e não do `opportunity_id`.
        #
        # A tela do funil escrevia `card #74` na manchete — o número da linha do
        # banco como nome de um funil de seis páginas. O nome existe: está em
        # `pautador_entities.canonical_name` ("Maquininha de Cartão"), e o
        # quadro do redator já sabia resolvê-lo. Faltava alguém trazer.
        #
        # Ele viaja só no caminho 200: com o ETag, a resposta cara sai ~30 vezes
        # por run (não ~900), então as duas leituras extras não pesam no polling.
        "titulo": await _titulo_do_card(int(r["opportunity_id"])),
        "colunas": mz.COLUNAS,
        # A máscara e as linhas foram calculadas pelo WORKER, no instante em que
        # ele tinha o `state.json` e o `config.yaml` na mão. Recalculá-las aqui
        # exigiria reler o disco do motor a cada polling — e daria resposta
        # diferente se alguém editasse o config.yaml no meio do run.
        "paginas": r.get("paginas") or [],
        "celulas": grade["celulas"],
        "faixa": grade["faixa"],
        "custo_total": grade["custo_total"],
        "custo_maior_celula": grade["custo_maior_celula"],
        "subestimado": grade["subestimado"],
        "publicadas": r.get("paginas_publicadas") or [],
        "lp_url": r.get("lp_url"),
        "teto_usd": float(r["teto_usd"]) if r.get("teto_usd") is not None else None,
        "teto_pagina_usd": (float(r["teto_pagina_usd"])
                            if r.get("teto_pagina_usd") is not None else None),
        "artefatos": r.get("artefatos") or {},
    }


class PublicarPaginaSaida(BaseModel):
    ok: bool
    publicada: Optional[Dict[str, Any]] = None
    erro: Optional[str] = None
    aviso: Optional[str] = None


@router.post("/redator/runs/{run_row_id}/publicar/{page_number}",
             response_model=PublicarPaginaSaida, dependencies=[Depends(exigir_admin)])
async def publicar_pagina_do_run(run_row_id: int, page_number: int) -> PublicarPaginaSaida:
    """Envia ao WordPress UMA página deste run que ficou escrita e parada.

    ## O buraco que esta rota fecha

    O motor publicava tudo ou nada: `run-volc --publish` no disparo, e ponto. Uma
    página que caísse num portão e fosse consertada depois não tinha caminho
    nenhum de volta — nem pela tela, nem pela API. Só terminal.

    Medido em 19/08/2026, run 9: p2, p3 e p4 ficaram escritas, aprovadas nos
    portões e paradas no disco. O funil tinha duas páginas no ar e três órfãs — e
    funil pela metade não é meio funil: os links internos apontam para páginas
    que não existem, e a sessão comprada morre no primeiro salto.

    ## As travas, e por que cada uma

    Isto ESCREVE num site de verdade. As cinco recusas abaixo acontecem ANTES de
    o motor ser chamado, e cada uma existe por um motivo diferente:

    1. **Já publicada** → 409. Publicar de novo criaria um SEGUNDO post no
       WordPress para a mesma página. O WP não recusa duplicata: ele aceita, dá
       outro `post_id` e acrescenta `-2` ao slug — e a atribuição de receita, que
       casa `url_wp` com `campaign_funnel_urls` por igualdade de string exata,
       passa a apontar para o post errado, em silêncio.
    2. **Run em andamento** → 409. Dois processos escrevendo o mesmo
       `state.json` se sobrescrevem; o último a fechar o arquivo vence, e o
       trabalho do outro some.
    3. **Página barrada** → 409. Portão reprovado é conteúdo que a casa decidiu
       não publicar. A rota não é um caminho para contornar o portão.
    4. **Sem artigo** → 409. Sem rascunho no disco não há o que enviar.
    5. **Credencial ausente ou não testada** → 409, com o mesmo texto do
       disparo: o operador precisa reconhecer o erro que já conhece.
    """
    supa = _supa()
    linhas = await supa.select(TABELA_RUNS, {"id": f"eq.{run_row_id}", "limit": 1})
    if not linhas:
        raise HTTPException(status_code=404, detail="Execução não encontrada.")
    run = linhas[0]

    if run.get("status") in ("running", "queued"):
        raise HTTPException(
            status_code=409,
            detail="Esta execução ainda está rodando. Espere ela terminar — dois "
                   "processos escrevendo o mesmo estado se sobrescrevem.")

    ja = next((p for p in (run.get("paginas_publicadas") or [])
               if int(p.get("page_number") or 0) == page_number), None)
    if ja:
        raise HTTPException(
            status_code=409,
            detail=f"A página {page_number} já está no WordPress (post "
                   f"#{ja.get('post_id')}). Enviar de novo criaria um segundo "
                   f"post para a mesma página.")

    run_id = (run.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=409,
                            detail="Esta execução não gravou o identificador do motor.")

    # O estado no disco é a verdade sobre o que existe para enviar.
    from app.redator import worker as w

    run_dir = _pasta_do_run(run)
    estado = w._ler_estado(run_dir) if run_dir else None
    if not estado:
        raise HTTPException(
            status_code=409,
            detail="Os arquivos deste run não estão no disco deste servidor.")

    passos = estado.get("step_status") or {}
    if (passos.get(f"blocked_p{page_number}") or {}).get("status") == "FAILED":
        raise HTTPException(
            status_code=409,
            detail=f"A página {page_number} foi barrada por um portão do motor e "
                   f"não pode ser publicada por aqui.")
    rascunho = (estado.get("drafts") or {}).get(str(page_number)) \
        or (estado.get("drafts") or {}).get(page_number)
    if not (rascunho or {}).get("content"):
        raise HTTPException(
            status_code=409,
            detail=f"A página {page_number} não tem artigo escrito no disco.")

    perfil_wp = await _buscar(supa, int(run.get("project_id") or 0))
    if not perfil_wp or not perfil_wp.get("wp_app_password_enc"):
        raise HTTPException(status_code=409,
                            detail="Este projeto não tem Application Password cadastrado.")
    if perfil_wp.get("conexao_ok") is not True:
        raise HTTPException(
            status_code=409,
            detail="Teste a conexão deste site antes de publicar (engrenagem na "
                   "página do projeto).")

    # A arquitetura vem do card, como no disparo: `montar_perfil` a exige para o
    # tema e recusa card sem funil.
    arq: Dict[str, Any] = {}
    entidade = None
    opps = await supa.select("pautador_opportunities",
                             {"id": f"eq.{run.get('opportunity_id')}", "limit": 1})
    if opps:
        arq = opps[0].get("funnel_architecture") or {}
        if opps[0].get("entity_id"):
            ent = await supa.select("pautador_entities",
                                    {"id": f"eq.{opps[0]['entity_id']}", "limit": 1})
            entidade = ent[0] if ent else None
    if not (arq.get("pages") or []):
        # O motor só precisa da arquitetura para o TEMA na retomada — o plano
        # já está gravado no `state.json`. Um esqueleto satisfaz `montar_perfil`
        # sem inventar conteúdo nenhum.
        arq = {"pages": (estado.get("plan") or {}).get("pages") or [{}]}

    from app.redator import PerfilIncompleto, montar_perfil

    try:
        perfil_do_run = montar_perfil(perfil_wp=perfil_wp, arquitetura=arq,
                                      entidade=entidade)
    except PerfilIncompleto as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    resultado = await w.publicar_pagina(
        supa=supa, run_row_id=run_row_id, run_id=run_id,
        page_number=page_number, perfil=perfil_do_run)

    if not resultado.get("ok"):
        return PublicarPaginaSaida(ok=False, erro=resultado.get("erro"))

    pub = resultado.get("publicada") or {}
    return PublicarPaginaSaida(
        ok=True, publicada=pub,
        aviso=("A página subiu como RASCUNHO — é assim que o motor trabalha. "
               "Publique de verdade no WordPress e releia aqui para trazer o "
               "permalink." if pub.get("status_wp") != "publish" else None),
    )
