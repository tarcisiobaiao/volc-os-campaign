#!/usr/bin/env python3
"""Autoriza o app de desktop do Google Cloud nos escopos que a casa precisa.

## Por que este script existe

A credencial que já fala com o Google Ads e a que falha no Tag Manager são a
MESMA — mesmo `client_id`, mesmo `client_secret`, projeto `n8n-works-464416`.
Medido em 19/08/2026. O que separa uma da outra é o conjunto de escopos com que
o `refresh_token` foi emitido: o atual carrega só `adwords`, e por isso GTM e
GA4 devolvem `403 insufficient authentication scopes`.

O `gcloud` resolveria isso, mas não está instalado nesta máquina. Como o cliente
OAuth é do tipo `installed` (app de desktop, redirect `http://localhost`), dá
para rodar o fluxo aqui mesmo, sem dependência nenhuma além da biblioteca padrão.

## O que ele NÃO faz

Não sobrescreve `~/google-ads.yaml` nem a ADC do gcloud. O token novo é gravado
num arquivo à parte e o script diz onde. Emitir um `refresh_token` novo **não
invalida** os anteriores — o Google Ads continua funcionando exatamente como
está, com o token que ele já usa.

## O que ele prova

Depois de autorizar, ele CHAMA as três APIs e mostra o veredito de cada uma.
É assim que se descobre se a Tag Manager API está apenas sem escopo ou também
desabilitada no projeto: com escopo em mãos, o erro muda de
`insufficient authentication scopes` para `SERVICE_DISABLED`, e aí o conserto é
no console, não aqui.

Uso:
    backend/.venv/bin/python scripts/autorizar-google.py [caminho/do/client_secret.json]
"""
from __future__ import annotations

import http.server
import json
import pathlib
import secrets
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

# O que a casa precisa, e por quê. Leitura primeiro: escrita em GTM e GA4 não
# entra sem pedido explícito, pela mesma razão que a trava de escrita do
# Google Ads existe.
ESCOPOS = [
    # Sem este, a ADC nova perderia o Google Ads. Mantenha-o SEMPRE.
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/tagmanager.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
]

DESTINO = pathlib.Path.home() / ".config" / "volc" / "google-oauth.json"


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _esperar_codigo(porta: int, estado: str) -> str:
    """Sobe um servidor de um tiro só para capturar o `code` do redirect."""
    capturado: dict[str, str] = {}

    class Alça(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nome exigido pela stdlib)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            # O `state` é a defesa contra alguém injetar um code de outra sessão.
            if q.get("state", [""])[0] != estado:
                self.send_response(400)
                self.end_headers()
                self.wfile.write("estado nao confere".encode())
                return
            capturado["code"] = q.get("code", [""])[0]
            capturado["erro"] = q.get("error", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h2>Pode fechar esta aba.</h2>"
                "<p>Volte para o terminal.</p>".encode("utf-8"))

        def log_message(self, *a):  # silencia o log da stdlib
            pass

    srv = http.server.HTTPServer(("127.0.0.1", porta), Alça)
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    t.join(timeout=300)
    srv.server_close()
    if capturado.get("erro"):
        raise SystemExit(f"O Google recusou: {capturado['erro']}")
    if not capturado.get("code"):
        raise SystemExit("Nenhum código recebido em 5 minutos.")
    return capturado["code"]


def _post(url: str, dados: dict) -> dict:
    corpo = urllib.parse.urlencode(dados).encode()
    req = urllib.request.Request(url, data=corpo)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Troca de código falhou: {(e.read() or b'').decode()[:300]}")


def _sondar(rotulo: str, url: str, token: str, extra: dict | None = None) -> None:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read() or b"{}")
            # Conta o que veio, sem despejar o conteúdo na tela.
            n = next((len(v) for v in d.values() if isinstance(v, list)), 0)
            print(f"  ✅ {rotulo}: HTTP {r.status} · {n} item(ns)")
    except urllib.error.HTTPError as e:
        det = json.loads(e.read() or b"{}").get("error", {})
        msg = det.get("message", "") if isinstance(det, dict) else str(det)
        estado = det.get("status", "") if isinstance(det, dict) else ""
        print(f"  ❌ {rotulo}: HTTP {e.code} {estado} — {msg[:150]}")
        if "SERVICE_DISABLED" in str(det) or "has not been used in project" in msg:
            print("     ↳ agora é escopo OK e API DESABILITADA: habilite no "
                  "console do projeto e rode de novo.")


def main() -> None:
    padrao = ("/Users/mac/Library/CloudStorage/GoogleDrive-tarcisio@agenciavolc.com.br/"
              "Drives compartilhados/VOLC/VOLC/SECURITY/CREDENCIAL GOOGLE CLOUD/"
              "APP GOOGLE ADS COMPUTADR/"
              "client_secret_891119529554-qp053mpvh5jkun5eu2o8dt1uanqgp92d."
              "apps.googleusercontent.com.json")
    caminho = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else padrao)
    if not caminho.exists():
        raise SystemExit(f"Não achei o client secret em {caminho}")

    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    tipo = next(iter(bruto))
    if tipo != "installed":
        raise SystemExit(f"Cliente do tipo {tipo!r}; este fluxo exige 'installed'.")
    cli = bruto[tipo]

    porta = _porta_livre()
    estado = secrets.token_urlsafe(24)
    redirect = f"http://localhost:{porta}"
    url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({
        "client_id": cli["client_id"],
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(ESCOPOS),
        # `offline` + `consent` garantem um refresh_token novo mesmo se este
        # usuário já autorizou o app antes.
        "access_type": "offline",
        "prompt": "consent",
        "state": estado,
    })

    print("Escopos que vou pedir:")
    for e in ESCOPOS:
        print("   ", e)
    print(f"\nAbrindo o navegador. Se não abrir, cole esta URL:\n\n{url}\n")
    webbrowser.open(url)

    code = _esperar_codigo(porta, estado)
    tok = _post("https://oauth2.googleapis.com/token", {
        "code": code,
        "client_id": cli["client_id"],
        "client_secret": cli["client_secret"],
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    })
    concedidos = tok.get("scope", "").split()
    print("\nEscopos CONCEDIDOS:")
    for e in sorted(concedidos):
        print("   ", e)
    faltando = [e for e in ESCOPOS if e not in concedidos]
    if faltando:
        print("\n⚠️  Não vieram:", ", ".join(faltando))

    print("\n── provando cada API com o token novo ──")
    _sondar("Google Tag Manager v2",
            "https://tagmanager.googleapis.com/tagmanager/v2/accounts", tok["access_token"])
    _sondar("GA4 Admin",
            "https://analyticsadmin.googleapis.com/v1beta/accountSummaries", tok["access_token"])
    _sondar("Google Ads v25",
            "https://googleads.googleapis.com/v25/customers:listAccessibleCustomers",
            tok["access_token"], {
                "developer-token": _ler_env("GOOGLE_ADS_DEVELOPER_TOKEN"),
                "login-customer-id": _ler_env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
            })

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(json.dumps({
        "type": "authorized_user",
        "client_id": cli["client_id"],
        "client_secret": cli["client_secret"],
        "refresh_token": tok["refresh_token"],
        "scopes": concedidos,
    }, indent=2), encoding="utf-8")
    DESTINO.chmod(0o600)
    print(f"\nGravado em {DESTINO} (chmod 600).")
    print("Nada foi sobrescrito: ~/google-ads.yaml e a ADC do gcloud seguem intactos.")


def _ler_env(chave: str) -> str:
    raiz = pathlib.Path(__file__).resolve().parents[1]
    for linha in (raiz / ".env").read_text(encoding="utf-8").splitlines():
        if linha.startswith(f"{chave}="):
            return linha.partition("=")[2].strip()
    return ""


if __name__ == "__main__":
    main()
