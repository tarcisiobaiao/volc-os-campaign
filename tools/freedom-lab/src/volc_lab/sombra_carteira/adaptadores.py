"""Adaptadores das portas de custo e receita.

- `SnapshotCusto` / `SnapshotReceita`: leem um JSON `{"lido_em", "fonte",
  "linhas": [...]}` exportado das tabelas do contrato. É o caminho do replay e
  dos testes, e é como a nuvem roda sem dado real.
- `PostgrestSoLeitura`: lê `google_ads_campanha_dia`, `receita_as_of()` e
  `cambio_resolver()` pelo PostgREST do Supabase oficial com a service_role do
  AMBIENTE (nunca do repositório). Só faz GET na tabela e POST nas duas RPCs
  STABLE; qualquer outro caminho é recusado antes da rede. Este adaptador não
  roda na nuvem: a prova dele é no Mac/Hetzner.

Paginação por CHAVE (ciclo corretivo 2): `id`/`fato_id` maior que o último lido,
em ordem crescente, até uma página vazia. Offset perdia a linha seguinte quando
uma versão nova de receita entrava entre páginas, e um `db-max-rows` menor que
a página truncava em silêncio. Por chave, nenhuma linha some e o tamanho da
página que o servidor devolve não importa. A versão nova que aparece depois
da antiga já lida fica com o maior `id` por (tabela, chave), a mesma regra do
`DISTINCT ON` da `receita_as_of`.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from volc_lab.sombra_carteira.portas import ContratoQuebrado, CustoDia, Leitura, ReceitaObservada

AUTORIDADE_SUPABASE = "database.agenciavolc.com.br"
PAGINA = 1000


def _ler_snapshot(caminho: Path) -> dict[str, Any]:
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("linhas"), list) or not doc.get("lido_em"):
        raise ContratoQuebrado(f"{caminho.name}: snapshot sem lido_em ou sem linhas")
    return doc


@dataclass(frozen=True)
class SnapshotCusto:
    caminho: Path

    def custo_campanha_dia(self, conta: str, inicio: date, fim: date) -> Leitura:
        doc = _ler_snapshot(self.caminho)
        return Leitura(tuple(doc["linhas"]), str(doc["lido_em"]),
                       str(doc.get("fonte") or f"snapshot {self.caminho.name}"))


@dataclass(frozen=True)
class SnapshotReceita:
    caminho: Path

    def receita_vigente(self, inicio: date, fim: date) -> Leitura:
        doc = _ler_snapshot(self.caminho)
        return Leitura(tuple(doc["linhas"]), str(doc["lido_em"]),
                       str(doc.get("fonte") or f"snapshot {self.caminho.name}"))


@dataclass(frozen=True)
class SnapshotCambio:
    """Respostas de `cambio_resolver` já exportadas. Dia sem linha = sem_cotacao."""

    caminho: Path

    def cotacoes(self, pedidos: Sequence[tuple[str, date]], conhecido_ate: str,
                 max_defasagem_dias: int) -> Leitura:
        doc = _ler_snapshot(self.caminho)
        return Leitura(tuple(doc["linhas"]), str(doc["lido_em"]),
                       str(doc.get("fonte") or f"snapshot {self.caminho.name}"))


Transporte = Callable[[str, str, Mapping[str, str], Optional[bytes]], tuple[int, bytes]]


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Um 3xx levaria a service_role a outro host; vira erro, não redireciona."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_ABRIDOR = urllib.request.build_opener(_SemRedirecionar())


def _transporte_urllib(metodo: str, url: str, cabecalhos: Mapping[str, str],
                       corpo: Optional[bytes]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=dict(cabecalhos))
    try:
        with _ABRIDOR.open(req, timeout=60) as resp:  # noqa: S310 (URL validada no init)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        # 3xx (não seguido), 4xx e 5xx viram status: o chamador recusa com o código.
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ContratoQuebrado(f"leitura sem resposta: {exc}") from exc


@dataclass
class PostgrestSoLeitura:
    """Leitura do contrato pelo PostgREST. Recusa tudo que não seja leitura."""

    url_base: str
    chave_service_role: str
    transporte: Transporte = field(default=_transporte_urllib)
    chamadas: list[tuple[str, str]] = field(default_factory=list)

    _PERMITIDOS = {
        ("GET", "/rest/v1/google_ads_campanha_dia"),
        ("POST", "/rest/v1/rpc/receita_as_of"),
        ("POST", "/rest/v1/rpc/cambio_resolver"),
    }

    def __post_init__(self) -> None:
        partes = urllib.parse.urlsplit(self.url_base)
        if partes.scheme != "https" or partes.hostname != AUTORIDADE_SUPABASE:
            # ADR-SUPABASE-AUTORIDADE-OPERACIONAL: o único Supabase operacional.
            raise ValueError(f"Supabase fora da autoridade operacional: {partes.hostname!r}")
        if not self.chave_service_role:
            raise ValueError("service_role ausente no ambiente")

    def _uma(self, metodo: str, caminho: str, consulta: dict[str, str],
             corpo: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        """Uma requisição; devolve a lista de linhas."""
        if (metodo, caminho) not in self._PERMITIDOS:
            raise PermissionError(f"{metodo} {caminho} não é leitura do contrato")
        url = self.url_base.rstrip("/") + caminho
        if consulta:
            url += "?" + urllib.parse.urlencode(consulta, safe="(),.:*")
        cab = {"apikey": self.chave_service_role,
               "Authorization": f"Bearer {self.chave_service_role}",
               "Accept": "application/json",
               "x-volc-proveniencia": "volc_lab.sombra_carteira"}
        dados = None
        if corpo is not None:
            cab["Content-Type"] = "application/json"
            dados = json.dumps(corpo).encode()
        self.chamadas.append((metodo, caminho))
        status, bruto = self.transporte(metodo, url, cab, dados)
        if status != 200:
            raise ContratoQuebrado(f"{caminho}: HTTP {status}")
        try:
            pagina = json.loads(bruto)
        except ValueError as exc:
            raise ContratoQuebrado(f"{caminho}: resposta não é JSON") from exc
        if not isinstance(pagina, list):
            raise ContratoQuebrado(f"{caminho}: resposta não é lista")
        return pagina

    def _pedir(self, metodo: str, caminho: str, consulta: dict[str, str],
               corpo: Optional[dict[str, Any]] = None, *, chave: str) -> list[dict[str, Any]]:
        """Paginação por chave crescente até uma página vazia."""
        linhas: list[dict[str, Any]] = []
        ultima: Optional[str] = None
        while True:
            q = {**consulta, "order": f"{chave}.asc", "limit": str(PAGINA)}
            if ultima is not None:
                q[chave] = f"gt.{ultima}"
            pagina = self._uma(metodo, caminho, q, corpo)
            if not pagina:
                return linhas
            valores = [str(l.get(chave)) if isinstance(l, dict) else None for l in pagina]
            if any(v in (None, "None") for v in valores):
                raise ContratoQuebrado(f"{caminho}: linha sem {chave}; não dá para paginar sem perder linha")
            if ultima is not None and _menor_ou_igual(valores[0], ultima, chave):
                raise ContratoQuebrado(f"{caminho}: página fora de ordem por {chave}")
            linhas.extend(pagina)
            ultima = valores[-1]

    def custo_campanha_dia(self, conta: str, inicio: date, fim: date) -> Leitura:
        lido_em = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        linhas = self._pedir("GET", "/rest/v1/google_ads_campanha_dia", {
            "select": ",".join(("fato_id",) + CustoDia.CAMPOS),
            "customer_id": f"eq.{conta}",
            "and": f"(metric_date.gte.{inicio.isoformat()},metric_date.lte.{fim.isoformat()})",
        }, chave="fato_id")
        return Leitura(tuple(linhas), lido_em, "PostgREST google_ads_campanha_dia (v12_04), paginação por fato_id")

    def receita_vigente(self, inicio: date, fim: date) -> Leitura:
        lido_em = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # O instante da leitura vira o conhecido_ate: o replay pede o mesmo corte.
        brutas = self._pedir("POST", "/rest/v1/rpc/receita_as_of", {
            "select": ",".join(("id", "tabela_origem") + ReceitaObservada.CAMPOS),
            "and": f"(data_referencia.gte.{inicio.isoformat()},data_referencia.lte.{fim.isoformat()})",
        }, {"p_conhecido_ate": lido_em, "p_fonte": None}, chave="id")
        linhas, recolhidas = vigentes_por_chave(brutas)
        return Leitura(tuple(linhas), lido_em,
                       f"PostgREST receita_as_of(conhecido_ate={lido_em}) (v23_01), paginação por id"
                       + (f"; {recolhidas} versão(ões) antiga(s) entre páginas descartada(s)" if recolhidas else ""))

    def cotacoes(self, pedidos: Sequence[tuple[str, date]], conhecido_ate: str,
                 max_defasagem_dias: int) -> Leitura:
        lido_em = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        linhas = []
        for par, dia in pedidos:
            resposta = self._uma("POST", "/rest/v1/rpc/cambio_resolver", {}, {
                "p_data": dia.isoformat(), "p_par": par,
                "p_max_defasagem_dias": max_defasagem_dias, "p_conhecido_ate": conhecido_ate})
            if len(resposta) != 1 or not isinstance(resposta[0], dict):
                raise ContratoQuebrado(f"cambio_resolver: {len(resposta)} linhas para {par} {dia}")
            r = resposta[0]
            linhas.append({"par": par, "data": dia.isoformat(), "modo": r.get("modo"), "taxa": r.get("taxa"),
                           "data_cotacao": r.get("data_cotacao"), "defasagem_dias": r.get("defasagem_dias"),
                           "cotacao_id": r.get("cotacao_id"), "fonte": r.get("fonte")})
        return Leitura(tuple(linhas), lido_em,
                       f"PostgREST cambio_resolver(conhecido_ate={conhecido_ate}, max_defasagem={max_defasagem_dias}) (v23_01)")


def _menor_ou_igual(a: str, b: str, chave: str) -> bool:
    if chave == "id":
        return int(a) <= int(b)
    return a <= b


def vigentes_por_chave(linhas: Sequence[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Uma linha por (tabela_origem, chave): a de maior id.

    Entre duas páginas pode entrar uma versão nova de uma chave já lida (a
    transação começou antes do conhecido_ate e commitou depois). Ficam as duas
    na leitura por chave; vale a mais nova, como no DISTINCT ON da RPC.
    """
    por_chave: dict[str, dict[str, Any]] = {}
    for l in linhas:
        k = json.dumps([l.get("tabela_origem"), l.get("chave")], sort_keys=True)
        if k not in por_chave or int(l["id"]) > int(por_chave[k]["id"]):
            por_chave[k] = l
    ficam = sorted(por_chave.values(), key=lambda l: int(l["id"]))
    return ficam, len(linhas) - len(ficam)
