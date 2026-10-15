"""Broker Google Ads: leitura GAQL e validate_only, com recibo sanitizado.

Reaproveita `volc_ads.gads` (cliente, trava de escrita, captura de request-id) e a
impressão canônica de `volc_ads.subir._impressao`, para que o hash do recibo do
laboratório bata com o de /provar. Não expõe mutar, lote.aplicar, enviar real
nem aplicar_recomendacoes, e não importa modo.destravar.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .recibos import agora_utc, gravar, mascarar


class TravaAberta(RuntimeError):
    pass


def _trava() -> dict:
    from volc_ads.gads import modo

    if modo.escrita_permitida():
        raise TravaAberta("broker do lab recusa rodar com a trava de escrita aberta")
    return {k: v for k, v in modo.estado().items() if k != "motivo"}


def ler(customer_id: str, gaql: str, *, login_customer_id: str, destino_recibo: Path) -> list[Any]:
    """Executa uma GAQL de leitura e registra recibo (customer mascarado, hash da consulta)."""
    from volc_ads.gads import client as gads

    trava = _trava()
    if not gaql.lstrip().upper().startswith("SELECT"):
        raise ValueError("broker de leitura aceita só GAQL SELECT")
    linhas = list(gads.buscar(str(customer_id), gaql, login_customer_id=login_customer_id))
    gravar({
        "broker": "google_ads", "operacao": "leitura:gaql",
        "customer": mascarar(customer_id),
        "payload_sha256": hashlib.sha256(gaql.encode("utf-8")).hexdigest(),
        "request_ids": [],  # search_stream não captura request-id neste cliente; vazio ≠ inventado
        "resultado": f"lido:{len(linhas)}", "versao_api": gads.VERSAO_API,
        "trava": trava, "em": agora_utc(),
    }, destino_recibo)
    return linhas


def validar(customer_id: str, operacoes: list, *, login_customer_id: str, destino_recibo: Path) -> dict:
    """Único verbo de 'escrita' do broker: validate_only. Nunca chama mutar()."""
    from volc_ads import subir
    from volc_ads.gads import client as gads

    trava = _trava()
    ids: list[str] = []
    falha = gads.validar_mutacoes(str(customer_id), operacoes,
                                  login_customer_id=login_customer_id, request_ids=ids)
    if falha is not None and getattr(falha, "request_id", ""):
        ids.append(falha.request_id)
    return gravar({
        "broker": "google_ads", "operacao": "validate_only",
        "customer": mascarar(customer_id),
        "payload_sha256": subir._impressao(operacoes),
        "n_operacoes": len(operacoes),
        "request_ids": sorted(set(ids)),
        "resultado": "aceito" if falha is None else f"recusado:{falha.classe.value}",
        "versao_api": gads.VERSAO_API, "trava": trava, "em": agora_utc(),
    }, destino_recibo)
