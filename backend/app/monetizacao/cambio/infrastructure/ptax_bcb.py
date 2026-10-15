"""PTAX do Banco Central do Brasil (dados abertos, sem chave).

Fonte documentada: serviço OData "PTAX" do Olinda/BCB,
https://dadosabertos.bcb.gov.br/dataset/dolar-americano-usd-todos-os-boletins-diarios
Recurso `CotacaoDolarPeriodo(dataInicial, dataFinalCotacao)`: um registro por
dia útil com o fechamento PTAX (`cotacaoCompra`, `cotacaoVenda`,
`dataHoraCotacao` no horário de Brasília). Datas da URL em MM-DD-AAAA.

Usamos `cotacaoVenda`: é a taxa de referência que contratos e balanços usam
para converter USD em BRL. A taxa de compra vai na proveniência.

O HTTP é injetável (`obter`): os testes passam uma resposta gravada e nada sai
para a rede. Esta classe não grava nada.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, List, Optional
from zoneinfo import ZoneInfo

from ..domain import Cotacao, CotacaoInvalida

BASE = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"
FUSO_BCB = ZoneInfo("America/Sao_Paulo")
NOME = "bcb_ptax"
PAR = "USD/BRL"


def montar_url(inicio: date, fim: date) -> str:
    return (f"{BASE}/CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
            f"?@dataInicial='{inicio:%m-%d-%Y}'&@dataFinalCotacao='{fim:%m-%d-%Y}'"
            "&$format=json&$select=cotacaoCompra,cotacaoVenda,dataHoraCotacao")


def _obter_http(url: str) -> bytes:
    import httpx  # noqa: PLC0415 — o módulo importa sem rede

    r = httpx.get(url, timeout=30.0)
    r.raise_for_status()
    return r.content


def interpretar(corpo: bytes, url: str) -> List[Cotacao]:
    """Resposta do OData → cotações. Recusa o lote inteiro se um registro não fecha."""
    try:
        doc = json.loads(corpo)
        registros = doc["value"]
    except (ValueError, KeyError, TypeError) as e:
        raise CotacaoInvalida(f"resposta PTAX sem 'value': {e}") from e
    if not isinstance(registros, list):
        raise CotacaoInvalida("resposta PTAX: 'value' não é lista")
    resposta_sha = hashlib.sha256(corpo).hexdigest()
    saida: List[Cotacao] = []
    for i, r in enumerate(registros):
        try:
            instante = datetime.fromisoformat(str(r["dataHoraCotacao"])).replace(tzinfo=FUSO_BCB)
            venda = Decimal(str(r["cotacaoVenda"]))
            compra = r.get("cotacaoCompra")
        except (KeyError, ValueError, InvalidOperation, TypeError) as e:
            raise CotacaoInvalida(f"registro PTAX {i} ilegível: {e}") from e
        saida.append(Cotacao(
            par=PAR, data_referencia=instante.date(), taxa=venda, fonte=NOME, as_of=instante,
            proveniencia={"url": url, "resposta_sha256": resposta_sha, "campo": "cotacaoVenda",
                          "cotacao_compra": None if compra is None else str(compra),
                          "data_hora_cotacao": str(r["dataHoraCotacao"])}))
    return saida


class FontePtaxBcb:
    nome = NOME
    par = PAR

    def __init__(self, obter: Optional[Callable[[str], bytes]] = None) -> None:
        self._obter = obter or _obter_http

    def buscar(self, inicio: date, fim: date) -> List[Cotacao]:
        url = montar_url(inicio, fim)
        return interpretar(self._obter(url), url)
