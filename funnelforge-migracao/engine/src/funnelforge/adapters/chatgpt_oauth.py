"""SIGN IN WITH CHATGPT — OAuth Authorization Code + PKCE (doc oficial OpenAI).

Endpoints, parâmetros e escopo transcritos de
https://developers.openai.com/siwc/token-sharing-open-source/sign-in
(consultado em 07/10/2026). Nada aqui é inventado: o que a doc não define
(revogação remota, por exemplo) não é implementado.

- O VOLC usa o PRÓPRIO `client_id` (`oaiapp_...`). Ele é público, mora em
  `config.yaml` (`openai.client_id`) e nunca é segredo.
- Primeiro registro (opcional, decisão do operador): `client_id=
  dynamic_agent_client` + `agent_name_hint` + `ext_agent_host_id` gerado por
  host; o callback devolve o `client_id` emitido para o VOLC.
- Callback só em `http://127.0.0.1:<porta>/auth/callback` (a doc proíbe trocar
  por `localhost` e exige o caminho exato).
- Tokens são OPACOS para este código: nunca decodificados, nunca impressos,
  nunca logados. O `TokenSet` mascara a si mesmo em `repr`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.server
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse

AUTHORIZE_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
ESCOPO = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
ESCOPO_DO_PLANO = "chatgpt.tokens.use.direct"
RECURSO = "https://api.openai.com/v1"
CLIENTE_DE_REGISTRO = "dynamic_agent_client"
EMISSOR = "https://auth.openai.com"
#: Metadado OIDC público do emissor (confere com os endpoints da doc e dá o JWKS).
DESCOBERTA_OIDC = "https://auth.openai.com/.well-known/openid-configuration"
CAMINHO_DO_CALLBACK = "/auth/callback"
NOME_DO_APP = "VOLC FunnelForge"

#: Códigos de erro da doc "errors and recovery" que significam "faça login de novo".
CODIGOS_DE_SESSAO_PERDIDA = frozenset({
    "invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
    "refresh_token_invalidated", "refresh_token_reused",
})

# post(url, form) -> (status_http, corpo_json). Injetável: teste não usa rede.
Post = Callable[[str, dict[str, str]], tuple[int, dict]]


class ErroDeAutenticacao(RuntimeError):
    """Erro com mensagem para PESSOA. Nunca carrega token."""
    codigo = "erro_de_autenticacao"
    retentavel = False

    def __init__(self, mensagem: str, codigo: str | None = None) -> None:
        super().__init__(mensagem)
        if codigo:
            self.codigo = codigo


class SessaoExpirada(ErroDeAutenticacao):
    codigo = "sessao_expirada"


class EscopoAusente(ErroDeAutenticacao):
    codigo = "escopo_ausente"


class PlanoInelegivel(ErroDeAutenticacao):
    codigo = "subscription_sharing_user_not_eligible"


class LimiteDoPlano(ErroDeAutenticacao):
    codigo = "subscription_sharing_usage_limit_exceeded"


class ClienteInvalido(ErroDeAutenticacao):
    codigo = "invalid_client"


class CallbackInvalido(ErroDeAutenticacao):
    codigo = "callback_invalido"


@dataclass
class TokenSet:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: float
    scope: str
    client_id: str
    id_token: str = field(default="", repr=False)
    earliest_refresh_at: float | None = None
    obtido_em: float = 0.0
    # Conta identificada de forma MASCARADA (ex.: "ta***@ag***.br"), do ID token.
    conta: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, dados: dict) -> "TokenSet":
        campos = {k: dados.get(k) for k in cls.__dataclass_fields__ if k in dados}
        return cls(**campos)

    def tem_escopo_do_plano(self) -> bool:
        return ESCOPO_DO_PLANO in (self.scope or "").split()

    def expira_em(self, agora: float) -> float:
        return self.expires_at - agora


def _b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def gerar_pkce() -> tuple[str, str]:
    """(verifier, challenge S256). Verifier com 64 bytes aleatórios (86 chars,
    dentro dos 43-128 do RFC 7636)."""
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def gerar_state() -> str:
    return secrets.token_urlsafe(32)


def redirect_uri(porta: int) -> str:
    return f"http://127.0.0.1:{porta}{CAMINHO_DO_CALLBACK}"


def url_de_autorizacao(*, client_id: str, redirect: str, state: str, nonce: str,
                       challenge: str, host_id: str | None = None,
                       login_hint: str | None = None) -> str:
    """URL de consentimento. Com `host_id` é o PRIMEIRO registro dinâmico
    (client_id de registro + nome do app + id do host); sem ele, é o login de
    quem já tem o `client_id` emitido."""
    if not client_id and not host_id:
        raise ErroDeAutenticacao("client_id do VOLC ausente: configure openai.client_id "
                                 "ou use o registro dinâmico explícito.")
    if host_id and not re.fullmatch(
            r"urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", host_id):
        raise ErroDeAutenticacao("ext_agent_host_id fora do formato oficial urn:uuid:<UUID>.")
    params = {
        "client_id": CLIENTE_DE_REGISTRO if host_id else client_id,
        "response_type": "code",
        "redirect_uri": redirect,
        "scope": ESCOPO,
        "resource": RECURSO,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    if host_id:
        params["agent_name_hint"] = NOME_DO_APP
        params["ext_agent_host_id"] = host_id
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def validar_callback(query: str, state_esperado: str, *, registrando: bool) -> dict[str, str]:
    """Confere o callback: erro do provedor, state (comparação em tempo
    constante), code presente e — no registro — o client_id emitido."""
    q = {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}
    if q.get("error"):
        raise CallbackInvalido(f"Consentimento recusado ou falhou: {q.get('error')} "
                               f"{q.get('error_description', '')}".strip(), q.get("error"))
    if not hmac.compare_digest(q.get("state", ""), state_esperado):
        raise CallbackInvalido("state do callback não confere: tentativa descartada.")
    if not q.get("code"):
        raise CallbackInvalido("callback sem code.")
    emitido = q.get("client_id", "")
    if registrando and not emitido.startswith("oaiapp_"):
        # Só os NOMES dos parâmetros recebidos: valor nenhum vai para a mensagem.
        raise CallbackInvalido("registro dinâmico sem client_id emitido (oaiapp_...) no "
                               f"callback; parâmetros recebidos: {sorted(q)}.")
    return {"code": q["code"], "client_id": emitido}


def esperar_callback(porta: int, state: str, *, registrando: bool,
                     timeout_s: float = 300.0) -> dict[str, str]:
    """Servidor de UMA requisição em 127.0.0.1. Caminho diferente de
    `/auth/callback` recebe 404 e não encerra a espera. Nada é logado."""
    resultado: dict[str, Any] = {}
    pronto = threading.Event()

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - nome do BaseHTTPRequestHandler
            partes = urlparse(self.path)
            if partes.path != CAMINHO_DO_CALLBACK:
                self.send_response(404)
                self.end_headers()
                return
            try:
                resultado["ok"] = validar_callback(partes.query, state, registrando=registrando)
                corpo = "Conectado. Pode fechar esta aba e voltar ao terminal."
                self.send_response(200)
            except CallbackInvalido as exc:
                resultado["erro"] = exc
                corpo = "Falha no login. Volte ao terminal."
                self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(corpo.encode("utf-8"))
            pronto.set()

        def log_message(self, *args: Any) -> None:  # silencia: a query tem o code
            return

    servidor = http.server.HTTPServer(("127.0.0.1", porta), _Handler)
    servidor.timeout = 1.0
    limite = time.monotonic() + timeout_s
    try:
        while not pronto.is_set():
            if time.monotonic() > limite:
                raise CallbackInvalido(f"tempo esgotado ({int(timeout_s)} s) esperando o "
                                       "consentimento no navegador.", "timeout")
            servidor.handle_request()
    finally:
        servidor.server_close()
    if "erro" in resultado:
        raise resultado["erro"]
    return resultado["ok"]


def _post_httpx(url: str, form: dict[str, str]) -> tuple[int, dict]:
    import httpx
    resp = httpx.post(url, data=form, timeout=30.0)
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {}
    return resp.status_code, corpo


def _token_set(corpo: dict, client_id: str, agora: float) -> TokenSet:
    if not corpo.get("access_token") or not corpo.get("refresh_token"):
        raise ErroDeAutenticacao("resposta de token sem access_token/refresh_token.")
    ts = TokenSet(
        access_token=corpo["access_token"], refresh_token=corpo["refresh_token"],
        id_token=corpo.get("id_token", ""), scope=corpo.get("scope", ""),
        expires_at=agora + float(corpo.get("expires_in") or 0), client_id=client_id,
        earliest_refresh_at=(float(corpo["earliest_refresh_at"])
                             if corpo.get("earliest_refresh_at") is not None else None),
        obtido_em=agora)
    if not ts.tem_escopo_do_plano():
        raise EscopoAusente(f"o consentimento não concedeu '{ESCOPO_DO_PLANO}': sem "
                            "permissão para usar o plano ChatGPT. Refaça o login e aceite "
                            "o uso do plano.")
    return ts


def _erro_de_token(status: int, corpo: dict) -> ErroDeAutenticacao:
    codigo = str(corpo.get("error") or corpo.get("code") or f"http_{status}")
    if codigo in CODIGOS_DE_SESSAO_PERDIDA:
        return SessaoExpirada("sessão do ChatGPT expirada ou revogada: rode "
                              "`funnelforge auth login --provider chatgpt`.", codigo)
    if codigo == "invalid_client":
        return ClienteInvalido("client_id do VOLC recusado pelo provedor: confira "
                               "openai.client_id.", codigo)
    return ErroDeAutenticacao(f"troca de token falhou ({codigo}).", codigo)


def trocar_codigo(*, client_id: str, code: str, verifier: str, redirect: str,
                  post: Post = _post_httpx, agora: Callable[[], float] = time.time) -> TokenSet:
    status, corpo = post(TOKEN_URL, {
        "grant_type": "authorization_code", "client_id": client_id, "code": code,
        "code_verifier": verifier, "redirect_uri": redirect, "resource": RECURSO})
    if status != 200:
        raise _erro_de_token(status, corpo)
    return _token_set(corpo, client_id, agora())


def renovar(token: TokenSet, *, post: Post = _post_httpx,
            agora: Callable[[], float] = time.time) -> TokenSet:
    """Refresh rotativo: a resposta traz um refresh_token NOVO; o antigo deixa
    de valer. Quem chama grava o resultado atomicamente."""
    status, corpo = post(TOKEN_URL, {
        # Só os parâmetros padrão do refresh: a doc não lista `resource` aqui.
        "grant_type": "refresh_token", "client_id": token.client_id,
        "refresh_token": token.refresh_token})
    if status != 200:
        raise _erro_de_token(status, corpo)
    return _token_set(corpo, token.client_id, agora())


def mascarar_conta(email: str, sub: str = "") -> str:
    if "@" in (email or ""):
        nome, dominio = email.split("@", 1)
        base, _, tld = dominio.rpartition(".")
        return f"{nome[:2]}***@{(base or dominio)[:2]}***.{tld or ''}".rstrip(".")
    return f"sub:{hashlib.sha256((sub or '').encode()).hexdigest()[:10]}" if sub else "?"


def _jwks_httpx() -> dict:
    """O JWKS do emissor via httpx (certifi). O `PyJWKClient` usa `urllib`, que
    neste Python não tem pacote de CAs e falha com CERTIFICATE_VERIFY_FAILED."""
    import httpx
    jwks_uri = httpx.get(DESCOBERTA_OIDC, timeout=15.0).json()["jwks_uri"]
    return httpx.get(jwks_uri, timeout=15.0).json()


def validar_id_token(id_token: str, *, client_id: str, nonce: str,
                     jwks: dict | None = None) -> dict:
    """Assinatura (JWKS do emissor, RS256, chave pelo `kid`), issuer, audience =
    client_id emitido, nonce desta tentativa e expiração. Devolve as claims;
    quem chama só guarda a conta MASCARADA."""
    import jwt  # PyJWT
    if not id_token:
        raise ErroDeAutenticacao("resposta de token sem id_token: não dá para validar a conta.")
    try:
        conjunto = jwt.PyJWKSet.from_dict(jwks if jwks is not None else _jwks_httpx())
        kid = jwt.get_unverified_header(id_token).get("kid")
        candidatas = [k for k in conjunto.keys if kid is None or k.key_id == kid]
        if not candidatas:
            raise jwt.InvalidKeyError(f"kid {kid!r} ausente do JWKS do emissor")
        chave = candidatas[0].key
        claims = jwt.decode(id_token, chave, algorithms=["RS256"], audience=client_id,
                            issuer=EMISSOR, options={"require": ["exp", "iat", "iss", "aud"]},
                            leeway=60)
    except jwt.PyJWTError as exc:
        raise ErroDeAutenticacao(f"ID token recusado na validação: {type(exc).__name__}.",
                                 "id_token_invalido") from exc
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ErroDeAutenticacao("nonce do ID token não confere: login descartado.",
                                 "nonce_invalido")
    return claims
