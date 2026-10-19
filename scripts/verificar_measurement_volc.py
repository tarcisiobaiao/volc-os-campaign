#!/usr/bin/env python3
"""Prova read-only de drift e heartbeat do VOLC Measurement.

O comando compara a versao live do GTM com os fontes versionados e confirma a
fronteira ``GTM -> volc-ingest -> raw_events`` sem publicar tags, alterar o
banco ou imprimir credenciais. O exit code e diferente de zero quando um gate
critico falha, para que o mesmo contrato possa ser usado por um monitor.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


RAIZ = Path(__file__).resolve().parents[1]
MANIFESTO_PADRAO = RAIZ / "measurement" / "gtm" / "manifest.json"
OAUTH_PADRAO = Path.home() / ".config" / "volc" / "google-oauth.json"


class FalhaDeProva(RuntimeError):
    """Falha operacional que pode ser apresentada sem dados sensiveis."""


def _normalizar_html(valor: str) -> str:
    # O editor do GTM preserva linhas vazias como um espaco. Isso nao altera o
    # JavaScript e nao deve produzir um falso drift; espacos dentro da linha
    # continuam significativos e seguem sendo comparados.
    linhas = valor.replace("\r\n", "\n").splitlines()
    return "\n".join(linha.rstrip() for linha in linhas).strip()


def _sha256_texto(valor: str) -> str:
    return hashlib.sha256(_normalizar_html(valor).encode("utf-8")).hexdigest()


def _ler_env(caminhos: list[Path]) -> dict[str, str]:
    resultado = dict(os.environ)
    for caminho in caminhos:
        if not caminho.is_file():
            continue
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            resultado.setdefault(chave, valor.strip().strip('"').strip("'"))
    return resultado


def _json_http(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    statuses: set[int] | None = None,
) -> tuple[int, dict[str, Any] | list[Any], dict[str, str]]:
    esperado = statuses or {200}
    requisicao = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            status = resposta.status
            corpo = resposta.read()
            cabecalhos = {k.lower(): v for k, v in resposta.headers.items()}
    except urllib.error.HTTPError as erro:
        status = erro.code
        corpo = erro.read()
        cabecalhos = {k.lower(): v for k, v in erro.headers.items()}
    if status not in esperado:
        detalhe = corpo[:300].decode("utf-8", errors="replace")
        raise FalhaDeProva(f"HTTP {status} em {url}: {detalhe}")
    if not corpo:
        payload: dict[str, Any] | list[Any] = {}
    else:
        try:
            payload = json.loads(corpo)
        except json.JSONDecodeError as erro:
            raise FalhaDeProva(f"resposta nao JSON em {url}") from erro
    return status, payload, cabecalhos


def _token_google(caminho: Path) -> str:
    if not caminho.is_file():
        raise FalhaDeProva(f"credencial OAuth ausente: {caminho}")
    credencial = json.loads(caminho.read_text(encoding="utf-8"))
    obrigatorios = ("client_id", "client_secret", "refresh_token")
    if any(not credencial.get(campo) for campo in obrigatorios):
        raise FalhaDeProva("credencial OAuth incompleta")
    dados = urllib.parse.urlencode(
        {
            "client_id": credencial["client_id"],
            "client_secret": credencial["client_secret"],
            "refresh_token": credencial["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    _, resposta, _ = _json_http(
        "https://oauth2.googleapis.com/token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=dados,
    )
    if not isinstance(resposta, dict) or not resposta.get("access_token"):
        raise FalhaDeProva("Google nao devolveu access_token")
    return str(resposta["access_token"])


def _consentimentos(tag: dict[str, Any]) -> list[str]:
    lista = (
        tag.get("consentSettings", {})
        .get("consentType", {})
        .get("list", [])
    )
    return sorted(
        str(item.get("value"))
        for item in lista
        if isinstance(item, dict) and item.get("value")
    )


def _html_da_tag(tag: dict[str, Any]) -> str:
    for parametro in tag.get("parameter", []):
        if parametro.get("key") == "html":
            return str(parametro.get("value") or "")
    return ""


def _provar_gtm(manifesto: dict[str, Any], token: str) -> dict[str, Any]:
    parent = f"accounts/{manifesto['account_id']}/containers/{manifesto['container_id']}"
    _, live, _ = _json_http(
        "https://tagmanager.googleapis.com/tagmanager/v2/" + parent + "/versions:live",
        headers={"Authorization": "Bearer " + token},
    )
    if not isinstance(live, dict):
        raise FalhaDeProva("versao live do GTM nao e um objeto")
    triggers = {
        str(trigger.get("triggerId")): str(trigger.get("name"))
        for trigger in live.get("trigger", [])
    }
    por_nome = {str(tag.get("name")): tag for tag in live.get("tag", [])}
    provas: list[dict[str, Any]] = []
    for esperado in manifesto["tags"]:
        nome = esperado["name"]
        tag = por_nome.get(nome)
        if not tag:
            provas.append({"tag": nome, "ok": False, "erro": "ausente_na_live"})
            continue
        fonte = (RAIZ / esperado["source"]).read_text(encoding="utf-8")
        html = _html_da_tag(tag)
        ids = sorted(str(item) for item in tag.get("firingTriggerId", []))
        nomes = sorted(triggers.get(item, item) for item in ids)
        consentimentos = _consentimentos(tag)
        problemas: list[str] = []
        if bool(tag.get("paused", False)) != bool(esperado["paused"]):
            problemas.append("estado_paused_divergente")
        if _normalizar_html(html) != _normalizar_html(fonte):
            problemas.append("html_divergente")
        if consentimentos != sorted(esperado["consent"]):
            problemas.append("consentimento_divergente")
        ids_esperados = sorted(esperado.get("firing_trigger_ids", []))
        if ids_esperados and ids != ids_esperados:
            problemas.append("trigger_id_divergente")
        nomes_esperados = sorted(esperado.get("firing_trigger_names", []))
        if nomes_esperados and nomes != nomes_esperados:
            problemas.append("trigger_nome_divergente")
        provas.append(
            {
                "tag": nome,
                "ok": not problemas,
                "paused": bool(tag.get("paused", False)),
                "consent": consentimentos,
                "triggers": nomes,
                "html_sha256": _sha256_texto(html),
                "problemas": problemas,
            }
        )
    versao_ok = str(live.get("containerVersionId")) == str(manifesto["live_version_id"])
    nome_ok = str(live.get("name")) == str(manifesto["live_version_name"])
    return {
        "ok": versao_ok and nome_ok and all(prova["ok"] for prova in provas),
        "version_id": live.get("containerVersionId"),
        "version_name": live.get("name"),
        "version_expected": manifesto["live_version_id"],
        "version_name_expected": manifesto["live_version_name"],
        "tags": provas,
    }


def _parse_data(valor: str) -> dt.datetime:
    data = dt.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if data.tzinfo is None:
        data = data.replace(tzinfo=dt.timezone.utc)
    return data.astimezone(dt.timezone.utc)


def _provar_supabase(
    manifesto: dict[str, Any],
    env: dict[str, str],
    max_heartbeat_horas: float,
) -> dict[str, Any]:
    base = (env.get("SUPABASE_URL") or env.get("VITE_SUPABASE_URL") or "").rstrip("/")
    service_role = env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    anon = env.get("VITE_SUPABASE_ANON_KEY", "")
    if base != "https://database.agenciavolc.com.br":
        raise FalhaDeProva("SUPABASE_URL nao aponta para a autoridade operacional")
    if not service_role:
        raise FalhaDeProva("SUPABASE_SERVICE_ROLE_KEY ausente")

    filtros = urllib.parse.urlencode(
        {
            "select": "event_name,v,ts,host,path",
            "event_name": "eq." + manifesto["heartbeat_event"],
            "order": "ts.desc",
            "limit": "1",
        }
    )
    _, linhas, _ = _json_http(
        base + "/rest/v1/raw_events?" + filtros,
        headers={"apikey": service_role, "Authorization": "Bearer " + service_role},
    )
    if not isinstance(linhas, list) or not linhas:
        raise FalhaDeProva("raw_events nao devolveu heartbeat")
    ultima = linhas[0]
    idade = (dt.datetime.now(dt.timezone.utc) - _parse_data(str(ultima["ts"]))).total_seconds() / 3600
    heartbeat_ok = (
        idade <= max_heartbeat_horas
        and ultima.get("v") == manifesto["measurement_version"]
        and ultima.get("host") in manifesto["allowed_hosts"]
    )

    anon_bloqueado: bool | None = None
    anon_status: int | None = None
    if anon:
        anon_status, _, _ = _json_http(
            base + "/rest/v1/raw_events?select=id&limit=1",
            headers={"apikey": anon, "Authorization": "Bearer " + anon},
            statuses={200, 401, 403},
        )
        anon_bloqueado = anon_status in {401, 403}

    endpoint = manifesto["ingest_url"]
    options_status, _, _ = _json_http(
        endpoint,
        method="OPTIONS",
        headers={
            "Origin": "https://creditoup.com.br",
            "Access-Control-Request-Method": "POST",
        },
        statuses={200, 204},
    )
    origem_status, origem_resposta, _ = _json_http(
        endpoint,
        method="POST",
        headers={"Origin": "https://origem-invalida.example", "Content-Type": "text/plain"},
        data=b"{}",
        statuses={403},
    )
    origem_bloqueada = (
        origem_status == 403
        and isinstance(origem_resposta, dict)
        and origem_resposta.get("error") == "origin_not_allowed"
    )
    return {
        "ok": heartbeat_ok and origem_bloqueada and anon_bloqueado is not False,
        "heartbeat": {
            "ok": heartbeat_ok,
            "ts": ultima.get("ts"),
            "age_hours": round(idade, 3),
            "version": ultima.get("v"),
            "host": ultima.get("host"),
            "path": ultima.get("path"),
        },
        "anon_raw_events_blocked": anon_bloqueado,
        "anon_status": anon_status,
        "options_status": options_status,
        "invalid_origin_blocked": origem_bloqueada,
    }


def _argumentos(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFESTO_PADRAO)
    parser.add_argument("--oauth-file", type=Path, default=OAUTH_PADRAO)
    parser.add_argument("--env-file", action="append", type=Path, default=[])
    parser.add_argument("--max-heartbeat-hours", type=float, default=48.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv or sys.argv[1:])
    try:
        manifesto = json.loads(args.manifest.read_text(encoding="utf-8"))
        caminhos_env = args.env_file or [RAIZ / ".env", RAIZ / ".env.local", RAIZ / ".env.server"]
        env = _ler_env(caminhos_env)
        gtm = _provar_gtm(manifesto, _token_google(args.oauth_file))
        supabase = _provar_supabase(manifesto, env, args.max_heartbeat_hours)
        relatorio = {"ok": bool(gtm["ok"] and supabase["ok"]), "gtm": gtm, "supabase": supabase}
    except (FalhaDeProva, OSError, KeyError, ValueError, json.JSONDecodeError) as erro:
        relatorio = {"ok": False, "erro": str(erro)}
    print(json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if relatorio["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
