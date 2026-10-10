"""O BUCKET TEMPORÁRIO do run: cada documento é baixado UMA vez e fica com recibo.

São três partes, e só a primeira mora aqui:

a) documentos extraídos — `runs/<id>/bucket/documentos/<id>.json`;
b) índice de evidências — `dossie.indice_de_evidencias`, derivado do dossiê e
   destes documentos (`runs/<id>/bucket/indice_de_evidencias.json`);
c) pacote de cada página — `pacotes.json` (`inteligencia.congelar_pacotes`).

A leitura continua sendo `pesquisa_plano.ler_documento` (UA honesto, PDF,
charset). Este módulo só impede a segunda viagem. Antes dele, a mesma página
oficial era lida na conferência de cada rodada de pesquisa, de novo na
proveniência, e a sonda de anúncio e a busca do link profundo abriam um
Chromium por URL a cada recálculo do dossiê.

- memória do run, com espera de quem já está baixando a mesma URL;
- cache compartilhado entre runs, com validade; só leitura bem-sucedida entra;
- cópia no run, que não expira com o cache: é o material para reproduzir a
  execução.

Não há score, selo nem interpretação aqui: documento é o que a fonte devolveu.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from funnelforge.adapters.pesquisa_plano import canonica, ler_documento

VALIDADE_DO_CACHE_H = 24.0
LIMITE_DE_TEXTO = 400_000          # caracteres guardados por documento
ESPERA_MAXIMA_S = 120.0


def id_do_documento(url: str) -> str:
    return hashlib.sha256(canonica(url).rstrip("/").encode("utf-8")).hexdigest()[:16]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class BucketDoRun:
    """Documentos e operações de rede do run, deduplicados e com recibo."""

    def __init__(self, *, cache: Path | None = None,
                 validade_h: float = VALIDADE_DO_CACHE_H,
                 ler: Callable[[str], dict] = ler_documento,
                 agora: Callable[[], datetime] = _agora) -> None:
        self.cache, self.validade = cache, timedelta(hours=validade_h)
        self._ler, self._agora = ler, agora
        self._trava = threading.RLock()
        self._docs: dict[str, dict] = {}
        self._em_voo: dict[str, threading.Event] = {}
        self._memo: dict[tuple[str, str], Any] = {}
        self._memo_em_voo: dict[tuple[str, str], threading.Event] = {}
        self.contagem: dict[str, dict[str, int]] = {}
        self.por_url: dict[str, dict[str, int]] = {}

    # -- contagem -----------------------------------------------------------
    def _contar(self, operacao: str, origem: str, url: str) -> None:
        with self._trava:
            op = self.contagem.setdefault(operacao, {})
            op[origem] = op.get(origem, 0) + 1
            u = self.por_url.setdefault(url, {})
            chave = f"{operacao}:{origem}"
            u[chave] = u.get(chave, 0) + 1

    # -- documentos ---------------------------------------------------------
    def _do_cache(self, chave: str) -> dict | None:
        if self.cache is None:
            return None
        arquivo = self.cache / f"{chave}.json"
        try:
            doc = json.loads(arquivo.read_text(encoding="utf-8"))
            coletado = datetime.fromisoformat(doc["coletado_em"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not doc.get("ok") or self._agora() - coletado > self.validade:
            return None
        return doc

    def _para_o_cache(self, chave: str, doc: dict) -> None:
        if self.cache is None or not doc.get("ok"):
            return
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            (self.cache / f"{chave}.json").write_text(
                json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass                                   # cache é otimização, nunca falha o run

    def documento(self, url: str) -> dict:
        """O documento da URL: memória, cache válido ou rede, nesta ordem."""
        chave = id_do_documento(url)
        with self._trava:
            if chave in self._docs:
                self._contar("documento", "memoria", url)
                return self._docs[chave]
            evento = self._em_voo.get(chave)
            dono = evento is None
            if dono:
                self._em_voo[chave] = threading.Event()
        if not dono:
            evento.wait(ESPERA_MAXIMA_S)
            with self._trava:
                self._contar("documento", "memoria", url)
                return self._docs.get(chave) or {"ok": False, "motivo": "leitura concorrente "
                                                 "sem resultado", "url": url, "id": chave}
        try:
            doc = self._do_cache(chave)
            origem = "cache_compartilhado"
            if doc is None:
                origem = "rede"
                bruto = dict(self._ler(url))
                texto = str(bruto.get("texto") or "")
                doc = {**bruto, "url": url, "id": chave,
                       "coletado_em": self._agora().isoformat(timespec="seconds"),
                       "texto": texto[:LIMITE_DE_TEXTO],
                       "texto_truncado": len(texto) > LIMITE_DE_TEXTO}
                self._para_o_cache(chave, doc)
            doc = {**doc, "origem": origem}
        except Exception as exc:  # noqa: BLE001 - leitura falha vira documento sem ok
            origem = "rede"
            doc = {"ok": False, "motivo": f"página não lida ({type(exc).__name__})",
                   "url": url, "id": chave, "origem": origem,
                   "coletado_em": self._agora().isoformat(timespec="seconds")}
        with self._trava:
            self._docs[chave] = doc
            self._contar("documento", origem if doc.get("ok") or origem != "rede"
                         else "rede_falhou", url)
            self._em_voo.pop(chave).set()
        return doc

    def ler_pagina(self, url: str) -> tuple[str, str]:
        """O contrato de `pesquisa_plano.ler_pagina`: (texto, motivo)."""
        doc = self.documento(url)
        return (doc.get("texto", ""), "") if doc.get("ok") else ("", doc.get("motivo", ""))

    def ja_lido(self, url: str) -> dict | None:
        """O documento SE já foi lido neste run. Nunca baixa."""
        with self._trava:
            return self._docs.get(id_do_documento(url))

    # -- outras operações de rede (sonda de anúncio, links da raiz) ----------
    def memo(self, operacao: str, url: str, fn: Callable[[], Any]) -> Any:
        """Resultado de uma operação de rede por URL, uma vez por run."""
        chave = (operacao, canonica(url).rstrip("/"))
        with self._trava:
            if chave in self._memo:
                self._contar(operacao, "memoria", url)
                return self._memo[chave]
            evento = self._memo_em_voo.get(chave)
            dono = evento is None
            if dono:
                self._memo_em_voo[chave] = threading.Event()
        if not dono:
            evento.wait(ESPERA_MAXIMA_S)
            with self._trava:
                self._contar(operacao, "memoria", url)
                return self._memo.get(chave)
        try:
            valor = fn()
        except Exception:  # noqa: BLE001 - quem chama já trata o "não sei"
            valor = None
        with self._trava:
            self._memo[chave] = valor
            self._contar(operacao, "rede", url)
            self._memo_em_voo.pop(chave).set()
        return valor

    # -- recibo e cópia no run ------------------------------------------------
    def recibo(self) -> dict:
        with self._trava:
            docs = list(self._docs.values())
            pedidos = {op: sum(c.values()) for op, c in self.contagem.items()}
            rede = {op: c.get("rede", 0) + c.get("rede_falhou", 0)
                    for op, c in self.contagem.items()}
            return {
                "documentos": len(docs),
                "documentos_ok": sum(1 for d in docs if d.get("ok")),
                "por_operacao": {op: dict(c) for op, c in self.contagem.items()},
                "leituras_pedidas": pedidos,
                "idas_a_rede": rede,
                "repeticoes_evitadas": {op: pedidos[op] - rede.get(op, 0) for op in pedidos},
                "por_url": {u: dict(c) for u, c in self.por_url.items()},
            }

    def gravar(self, pasta: Path) -> None:
        """Copia no run os documentos ainda não gravados e o recibo de rede."""
        destino = pasta / "bucket" / "documentos"
        try:
            destino.mkdir(parents=True, exist_ok=True)
            with self._trava:
                docs = list(self._docs.items())
            for chave, doc in docs:
                arquivo = destino / f"{chave}.json"
                if not arquivo.exists():
                    arquivo.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
            (pasta / "bucket" / "recibo_de_rede.json").write_text(
                json.dumps(self.recibo(), ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass                                    # recibo não derruba o run
