"""Sessão Google com token REDUZIDO aos escopos pedidos.

Lê ~/.config/volc/google-oauth.json dentro do google-auth. O refresh token guardado
carrega `adwords` completo; por isso o refresh pede só o escopo readonly do serviço
(down-scoping) e recusa qualquer token que volte com escopo a mais. A sessão
devolvida carrega SÓ o access token já reduzido (sem refresh_token nem
client_secret): quem a recebe não consegue emitir outro token. Não reautoriza,
não grava nada.

Limite honesto: o broker é biblioteca no mesmo processo do agente, não fronteira
de processo. Código hostil no mesmo processo pode ler o arquivo por conta própria;
a contenção real disso é rodar o broker em processo/usuário separado (pendente).
"""
from __future__ import annotations

import os
from pathlib import Path

ARQUIVO_PADRAO = Path.home() / ".config" / "volc" / "google-oauth.json"


class CredencialIndisponivel(RuntimeError):
    pass


def _arquivo() -> Path:
    return Path(os.environ.get("VOLC_GOOGLE_OAUTH_FILE", str(ARQUIVO_PADRAO)))


def verificar_arquivo(caminho: Path | None = None) -> Path:
    caminho = caminho or _arquivo()
    if not caminho.exists():
        raise CredencialIndisponivel("google-oauth.json ausente; OAuth novo é decisão humana")
    if caminho.stat().st_mode & 0o077:
        raise CredencialIndisponivel("google-oauth.json com permissão aberta; esperado 600")
    return caminho


def conferir_escopos(concedidos: frozenset[str], pedidos: frozenset[str]) -> None:
    if not concedidos:
        raise CredencialIndisponivel("token sem escopos declarados; recusado por precaução")
    excesso = concedidos - pedidos
    if excesso:
        raise CredencialIndisponivel(f"token veio com escopos a mais: {sorted(excesso)}")


def sessao(escopos: frozenset[str]):
    """AuthorizedSession com token cujo escopo é subconjunto de `escopos`."""
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials

    caminho = verificar_arquivo()
    cred = Credentials.from_authorized_user_file(str(caminho), scopes=sorted(escopos))
    # Escopo pedido e não concedido NÃO levanta no google-auth 2.56 (só loga aviso);
    # por isso a conferência abaixo, sobre o que o token de fato trouxe.
    cred.refresh(Request())
    concedidos = frozenset(getattr(cred, "granted_scopes", None) or ())
    conferir_escopos(concedidos, escopos)
    if not concedidos:
        raise CredencialIndisponivel("token sem escopo concedido")
    # Só o access token reduzido sai daqui; refresh_token e client_secret ficam para trás.
    s = AuthorizedSession(Credentials(token=cred.token, scopes=sorted(concedidos)))
    del cred
    s.escopos_efetivos = concedidos  # nomes de escopo não são segredo
    return s
