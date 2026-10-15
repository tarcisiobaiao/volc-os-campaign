"""Custo Google Ads do período pelo fato canônico: `GET /api/trafego/custo`.

Router próprio, e não mais uma rota em `trafego_inventario.py`: o inventário
lê o espelho `LAST_30_DAYS` do sincronizador, e esta rota lê
`google_ads_campanha_dia` (v12_04) com o ledger. São fontes diferentes, e o
consumidor (o herói do Hub) precisa saber de qual veio o número.

Leitura pura: zero consulta ao Google Ads, zero escrita. Sessão obrigatória
(`exigir_usuario` no nível do router, para que rota nova nasça fechada).

Contrato da resposta: `app.trafego.custo_canonico.montar_custo`.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.seguranca.identidade import exigir_usuario
from app.trafego import custo_canonico as cc

log = logging.getLogger("volc.trafego.rotas.custo")

router = APIRouter(prefix="/api/trafego", tags=["trafego"],
                   dependencies=[Depends(exigir_usuario)])

#: As contas da casa operam em São Paulo; "ontem" do período padrão é de lá.
FUSO_PADRAO = "America/Sao_Paulo"
_CONTA = re.compile(r"^[0-9]{6,12}$")

_FONTE: Optional[Any] = None


def definir_fonte(fonte: Optional[Any]) -> None:
    """Dublê no teste, PostgREST real fora dele."""
    global _FONTE
    _FONTE = fonte


def _fonte() -> Any:
    if _FONTE is not None:
        return _FONTE
    from app.routers.trafego_inventario import _credenciais  # noqa: PLC0415
    from app.trafego.custo_canonico_fonte import FonteDeCustoCanonico  # noqa: PLC0415

    base, chave = _credenciais()
    return FonteDeCustoCanonico(base, chave)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/custo")
async def custo_do_periodo(
    conta: Optional[List[str]] = Query(
        None, description="customer_id (só dígitos, sem hífen); repetível. Sem ele, as "
                          "contas são inferidas do fato e do ledger, e a resposta avisa."),
    inicio: Optional[date] = Query(None, description="YYYY-MM-DD; padrão: hoje-30 em São Paulo"),
    fim: Optional[date] = Query(None, description="YYYY-MM-DD; padrão: ontem em São Paulo"),
) -> Any:
    contas = [c.replace("-", "").strip() for c in (conta or [])]
    ruins = [c for c in contas if not _CONTA.match(c)]
    if ruins:
        raise HTTPException(status_code=400, detail=f"conta inválida: {ruins[:3]}")

    agora = _agora()
    hoje = agora.astimezone(ZoneInfo(FUSO_PADRAO)).date()
    try:
        if inicio is None and fim is None:
            periodo = cc.periodo_padrao(hoje)
        elif inicio is None or fim is None:
            raise cc.PeriodoInvalido("informe `inicio` e `fim` juntos, ou nenhum dos dois")
        else:
            periodo = cc.Periodo(inicio, fim)
        if periodo.fim > hoje:
            raise cc.PeriodoInvalido("`fim` no futuro: não há custo de amanhã")
    except cc.PeriodoInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fonte = _fonte()
    try:
        # ⚠️ Ledger ANTES do fato. A RPC grava as linhas antes do fechamento, na
        # mesma transação: todo fechamento já visível tem as linhas visíveis.
        # Na ordem inversa, um D-1 que commita entre as duas leituras faria um
        # dia "fechado" carregar o valor D0 lido antes — número errado como real.
        fechos = await fonte.fechamentos(contas or None, periodo)
        linhas = await fonte.linhas_do_fato(contas or None, periodo)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        # Fonte fora do ar é 503, nunca 200 com custo zero ou "sem coleta":
        # quem não conseguiu olhar não pode dizer que não houve coleta.
        log.exception("leitura do fato canônico falhou")
        raise HTTPException(status_code=503,
                            detail=f"não consegui ler o fato canônico de custo: {exc}"[:300]) from exc

    try:
        return cc.montar_custo(linhas, fechos, contas=contas or None, periodo=periodo, agora=agora)
    except ValueError as exc:
        # Dado do banco fora do contrato (ex.: custo_micros não inteiro).
        log.exception("fato canônico fora do contrato")
        raise HTTPException(status_code=502, detail=f"fato canônico fora do contrato: {exc}"[:300]) from exc
