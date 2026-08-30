"""Quem está do outro lado da requisição — e o que essa pessoa pode fazer.

## Por que este módulo existe

Medido em 24/08/2026, antes desta camada: as 17 rotas de `/api/trafego/*` não
tinham uma única checagem de identidade (`grep -c "Depends"` = 0), e duas delas
(`POST /subir`, `POST /remover`) mutam a conta real de anúncios. O único portão
do backend era `deps.require_api_key`, com dois defeitos que o tornam inútil
como autenticação de navegador:

1. **Falha ABERTA.** `if not expected: return` — sem `PAUTADOR_API_KEY` no
   ambiente, o portão simplesmente não existe. Um deploy com credenciais reais
   e essa variável esquecida fica aberto e parece protegido.
2. **A chave viaja para o browser.** O front a envia como `X-API-Key` lendo
   `VITE_PAUTADOR_API_KEY` (`src/lib/pautadorApi.ts:37`), e tudo que é `VITE_*`
   é embutido no bundle. Um segredo compartilhado com o navegador é público.

Daí as **duas vias separadas por origem**, que é a regra desta casa:

    navegador  → sessão do Supabase (JWT), validada CONTRA o Supabase
    serviço    → credencial própria, que NUNCA chega ao navegador

## O que este módulo se recusa a fazer

**Não lê papel de `user_metadata`.** Esse campo é editável pelo próprio usuário
pela API de auth: usá-lo como autorização é deixar o visitante assinar o próprio
crachá. **Não lê de `app_metadata` tampouco** — ali o usuário não escreve, mas o
valor viaja dentro do token e só muda quando um token novo é emitido; uma
revogação de papel levaria até a expiração para valer. Para operação que gasta
dinheiro isso é tarde demais.

O papel vem de **consulta server-side, pelo `sub` do token**, numa fonte
dedicada e protegida — ver `supabase/migrations/` do Sprint 1A. É mais uma ida
ao banco por requisição, e é o preço de a revogação valer no ato.

## Falha fechada, sempre

Se a configuração de segurança estiver ausente ou quebrada, toda dependência
aqui responde **503** e nada passa. O oposto — abrir o portão porque a
configuração falhou — é exatamente o defeito que este módulo corrige.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Optional

import httpx
from fastapi import Depends, Header, HTTPException

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

#: A ÚNICA porta pela qual este módulo descobre o papel de alguém.
#:
#: É uma RPC de propósito único (`public.volc_role_of(uuid) -> text`), não uma
#: tabela. A fonte real é `app_auth.user_roles`, que tem RLS forçada e ALL
#: revogado de todos os papéis do Data API — inclusive `service_role`. Expor a
#: tabela de papéis como recurso REST devolveria ao Data API exatamente o poder
#: que este sprint tirou dos proxies genéricos.
#:
#: ⚠️ NÃO é `public.users`: aquela tabela tinha RLS desabilitada, zero policies e
#: `anon` com UPDATE em 24/08/2026 — seu `role` era gravável por qualquer um.
#:
#: ⚠️ Uma versão anterior deste arquivo consultava a tabela `hub_autorizacao`,
#: que nunca existiu em migration nenhuma: a camada de identidade e o schema
#: foram escritos em paralelo e ninguém reconciliou os dois. O efeito seria
#: 503 em toda requisição autenticada, DEPOIS de aplicar a migration — o tipo de
#: defeito que só aparece em integração. O contrato agora é uma função nomeada,
#: e o teste de integração a exercita contra um Postgres de verdade.
RPC_PAPEL = "volc_role_of"

PAPEL_ADMIN = "ADMIN"

#: Quanto esperamos o Supabase responder sobre o token. Curto de propósito: esta
#: chamada está no caminho de TODA requisição autenticada, e um auth lento que
#: pendura a API é indistinguível de uma API fora do ar.
TIMEOUT_AUTH_S = 5.0


@dataclass(frozen=True)
class Identidade:
    """Quem está chamando. Imutável: nada abaixo pode reescrever o papel."""

    sub: str
    email: str
    papel: str
    origem: Literal["sessao", "servico"]

    @property
    def e_admin(self) -> bool:
        return self.papel == PAPEL_ADMIN


def _config_ou_503(settings: Settings) -> None:
    """A porta fecha quando a configuração falta. Nunca o contrário."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        log.error("autenticação indisponível: SUPABASE_URL/SERVICE_ROLE_KEY ausentes")
        raise HTTPException(
            status_code=503,
            detail="Autenticação indisponível: o servidor está sem configuração de "
                   "segurança. Nenhuma requisição é aceita neste estado.",
        )


def _token_do_cabecalho(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Credencial ausente.")
    partes = authorization.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer" or not partes[1].strip():
        raise HTTPException(status_code=401, detail="Credencial malformada.")
    return partes[1].strip()


async def _usuario_do_token(settings: Settings, token: str) -> dict:
    """Valida o token PERGUNTANDO AO SUPABASE.

    Poderíamos verificar a assinatura localmente com o JWT secret. Não o
    fazemos: verificação local aceita token de sessão já revogada até a
    expiração, e obriga o backend a guardar mais um segredo. O `/auth/v1/user`
    responde 200 só enquanto a sessão vale — que é a pergunta real.
    """
    url = settings.supabase_url.rstrip("/") + "/auth/v1/user"
    cabecalhos = {
        "Authorization": f"Bearer {token}",
        # O PostgREST/GoTrue exige `apikey`; a service role serve e não sai daqui.
        "apikey": settings.supabase_service_role_key,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_AUTH_S) as cliente:
            resposta = await cliente.get(url, headers=cabecalhos)
    except httpx.HTTPError as exc:
        # Indisponibilidade do auth NÃO vira permissão. 503, e o portão fecha.
        log.warning("falha ao validar token no Supabase: %s", exc)
        raise HTTPException(status_code=503, detail="Não foi possível validar a credencial.") from exc

    if resposta.status_code == 401:
        raise HTTPException(status_code=401, detail="Credencial inválida ou expirada.")
    if resposta.status_code >= 400:
        log.warning("resposta inesperada do auth: %s", resposta.status_code)
        raise HTTPException(status_code=503, detail="Não foi possível validar a credencial.")

    corpo = resposta.json()
    if not corpo.get("id"):
        raise HTTPException(status_code=401, detail="Credencial sem sujeito.")
    return corpo


async def _papel_do_sub(settings: Settings, sub: str) -> str:
    """O papel, perguntado ao banco pelo `sub` — nunca lido do token.

    Chama a RPC, não uma tabela: ver `RPC_PAPEL`. Devolve string vazia quando
    não há papel ativo, e é `volc_role_of` que já resolve a revogação — ela
    filtra `revoked_at IS NULL` a cada chamada, e é por isso que tirar o papel
    de alguém vale no ato, sem esperar o token expirar.
    """
    url = settings.supabase_url.rstrip("/") + f"/rest/v1/rpc/{RPC_PAPEL}"
    cabecalhos = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_AUTH_S) as cliente:
            resposta = await cliente.post(url, headers=cabecalhos,
                                          json={"p_auth_user_id": sub})
    except httpx.HTTPError as exc:
        log.warning("falha ao ler autorização de %s: %s", sub, exc)
        raise HTTPException(status_code=503, detail="Não foi possível apurar a autorização.") from exc

    if resposta.status_code == 404:
        # A migration não foi aplicada. Falhar fechado e DIZER o porquê: um 503
        # mudo aqui mandaria o próximo a investigar procurar rede, não schema.
        log.error("RPC %s não existe no banco — a migration de autorização não foi aplicada", RPC_PAPEL)
        raise HTTPException(
            status_code=503,
            detail="Fonte de autorização indisponível no banco.",
        )
    if resposta.status_code >= 400:
        log.warning("resposta inesperada da autorização: %s", resposta.status_code)
        raise HTTPException(status_code=503, detail="Não foi possível apurar a autorização.")

    corpo = resposta.json()
    # PostgREST devolve o escalar puro para função que retorna text.
    if corpo is None:
        return ""
    if isinstance(corpo, list):
        corpo = corpo[0] if corpo else ""
    if isinstance(corpo, dict):
        corpo = corpo.get(RPC_PAPEL, "")
    return str(corpo or "")


# ── as três dependências ────────────────────────────────────────────────────

async def exigir_usuario(
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Identidade:
    """Sessão válida do navegador. 401 quando não há ou não vale."""
    _config_ou_503(settings)
    token = _token_do_cabecalho(authorization)
    usuario = await _usuario_do_token(settings, token)
    sub = str(usuario["id"])
    papel = await _papel_do_sub(settings, sub)
    return Identidade(
        sub=sub,
        email=str(usuario.get("email") or ""),
        papel=papel,
        origem="sessao",
    )


async def exigir_admin(
    identidade: Identidade = Depends(exigir_usuario),
) -> Identidade:
    """Papel administrativo. 403 — a identidade é válida, a permissão é que não.

    A distinção importa para quem opera: 401 manda entrar de novo, 403 manda
    pedir acesso. Colapsar os dois faz o operador tentar o login errado.
    """
    if not identidade.e_admin:
        raise HTTPException(
            status_code=403,
            detail="Esta operação exige papel administrativo.",
        )
    return identidade


async def exigir_servico(
    x_volc_service_key: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Identidade:
    """Credencial de serviço, para n8n, cron e integrações internas.

    ⚠️ Esta credencial NUNCA pode ser exposta ao navegador. Ela não tem
    equivalente `VITE_*`, e não deve ganhar um — foi assim que a
    `PAUTADOR_API_KEY` deixou de ser segredo.

    Falha fechada por construção: sem `VOLC_SERVICE_KEY` no ambiente, nenhuma
    chamada de serviço é aceita. É o oposto de `deps.require_api_key`, que
    liberava tudo quando a variável faltava.
    """
    _config_ou_503(settings)
    esperado = (getattr(settings, "volc_service_key", None) or "").strip()
    if not esperado:
        log.error("credencial de serviço não configurada; recusando chamada interna")
        raise HTTPException(
            status_code=503,
            detail="Credencial de serviço não configurada no servidor.",
        )
    enviado = (x_volc_service_key or "").strip()
    if not enviado:
        raise HTTPException(status_code=401, detail="Credencial de serviço ausente.")

    # Comparação em tempo constante: comparar segredo com `!=` vaza o tamanho do
    # prefixo correto por diferença de tempo.
    import hmac

    if not hmac.compare_digest(enviado, esperado):
        raise HTTPException(status_code=401, detail="Credencial de serviço inválida.")

    return Identidade(sub="servico-interno", email="", papel="SERVICO", origem="servico")
