"""Registro de conversões offline sobre a v25_01, pelo PostgREST.

Fino como `app/trafego/ledger.py`: a regra (no máximo um envio real vivo,
validação aceita antes do real, transições fechadas) mora no banco. Aqui só se
traduz chamada em `POST /rest/v1/...` e a recusa do banco em exceção tipada.

O cliente chega pronto (URL base `.../rest/v1`, `apikey` e `Authorization`
da service_role); este módulo não lê ambiente nem segredo.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import httpx

from ..application import portas
from ..application.enviar import JaEnviado, ValidacaoAusente
from ..domain.valor import Coorte


class RegistroRecusou(RuntimeError):
    def __init__(self, status: int, corpo: Mapping[str, Any]):
        self.status = status
        self.corpo = dict(corpo)
        super().__init__(f"registro recusou ({status}): {corpo.get('code')} {corpo.get('message')}")


def _erro(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        corpo = resp.json()
    except ValueError:
        corpo = {"message": resp.text[:500]}
    if not isinstance(corpo, dict):
        corpo = {"message": str(corpo)[:500]}
    codigo = corpo.get("code")
    if codigo == "23505":
        raise JaEnviado(f"o banco recusou um segundo envio real vivo: {corpo.get('message')}")
    if codigo == "55000" and "abrir_lote" in str(corpo.get("message", "")):
        raise ValidacaoAusente(str(corpo.get("message")))
    raise RegistroRecusou(resp.status_code, corpo)


class RegistroPostgrest:
    def __init__(self, cliente: httpx.Client) -> None:
        self._c = cliente

    def envios_reais_vivos(self, *, operating_account_id: str, product_destination_id: str,
                           transaction_ids: Sequence[str]) -> Mapping[str, portas.EnvioAnterior]:
        achados: Dict[str, portas.EnvioAnterior] = {}
        ids = list(dict.fromkeys(transaction_ids))
        for i in range(0, len(ids), 200):  # URL curta: 200 por leitura
            fatia = ids[i:i + 200]
            resp = self._c.get("/conversao_offline_item", params={
                "select": "lote_id,estado,valor_impressao,transaction_id",
                "modo": "eq.real",
                "operating_account_id": f"eq.{operating_account_id}",
                "product_destination_id": f"eq.{product_destination_id}",
                "estado": f"in.({','.join(portas.ESTADOS_VIVOS)})",
                "transaction_id": f"in.({','.join(fatia)})",
            })
            _erro(resp)
            for linha in resp.json():
                achados[linha["transaction_id"]] = portas.EnvioAnterior(
                    lote_id=int(linha["lote_id"]), estado=linha["estado"],
                    valor_impressao=linha["valor_impressao"])
        return achados

    def envios_reais_por_coorte(self, *, operating_account_id: str, product_destination_id: str,
                                coortes: Sequence[Coorte]) -> Mapping[Coorte, portas.EnvioDaCoorte]:
        achados: Dict[Coorte, portas.EnvioDaCoorte] = {}
        for coorte in dict.fromkeys(coortes):  # poucas por rodada: uma leitura cada
            resp = self._c.get("/conversao_offline_envio_por_coorte", params={
                "select": "itens_vivos,soma_valor",
                "operating_account_id": f"eq.{operating_account_id}",
                "product_destination_id": f"eq.{product_destination_id}",
                "coorte_data": f"eq.{coorte.data_referencia.isoformat()}",
                "coorte_campanha": f"eq.{coorte.utm_campaign_value}",
                "coorte_dominio": f"eq.{coorte.dominio}",
            })
            _erro(resp)
            for linha in resp.json():
                if int(linha["itens_vivos"]) > 0:
                    achados[coorte] = portas.EnvioDaCoorte(
                        itens=int(linha["itens_vivos"]), soma=Decimal(str(linha["soma_valor"])))
        return achados

    def registrar_decisoes(self, *, rodada: str, customer_id: str,
                           operating_account_id: str, product_destination_id: str,
                           decisoes: Sequence[Dict[str, Any]]) -> None:
        if not decisoes:
            return
        linhas = []
        for d in decisoes:
            linhas.append({
                "rodada": rodada, "customer_id": customer_id,
                "operating_account_id": operating_account_id,
                "product_destination_id": product_destination_id,
                "transaction_id": d["transaction_id"], "visita_ref": d["visita_ref"],
                "clique_tipo": d["clique_tipo"], "clique_sha256": d["clique_sha256"],
                "ocorrido_em": d["ocorrido_em"], "estado": d["estado"],
                "coorte_data": d["coorte_data"], "coorte_campanha": d["coorte_campanha"],
                "coorte_dominio": d["coorte_dominio"],
                "motivo": d["motivo"], "detalhe": d["detalhe"],
                "valor": d["valor"], "moeda": d["moeda"], "estimado": d["estimado"],
                "valor_impressao": d["valor_impressao"], "proveniencia": d["proveniencia"],
            })
        resp = self._c.post(
            "/conversao_offline_decisao", json=linhas,
            # ⚠️ Sem ignore-duplicates: reusar a rodada com conteúdo diferente
            # descartaria a decisão nova em silêncio (revisão W14, achado 8).
            # A rodada é por execução; repeti-la é erro (23505), não no-op.
            headers={"Prefer": "return=minimal"})
        _erro(resp)

    def abrir_lote(self, *, modo: str, impressao: str, customer_id: str,
                   login_customer_id: str, operating_account_id: str,
                   product_destination_id: str, itens: Sequence[Tuple[str, str]],
                   aprovacao: Optional[Mapping[str, Any]] = None,
                   validacao_lote_id: Optional[int] = None) -> portas.LoteRegistrado:
        p = {
            "modo": modo, "impressao": impressao, "customer_id": customer_id,
            "login_customer_id": login_customer_id,
            "operating_account_id": operating_account_id,
            "product_destination_id": product_destination_id,
            "itens": [{"transaction_id": t, "valor_impressao": v} for t, v in itens],
            "aprovacao": None if aprovacao is None else dict(aprovacao),
            "validacao_lote_id": validacao_lote_id,
        }
        resp = self._c.post("/rpc/conversao_offline_abrir_lote", json={"p": p})
        _erro(resp)
        return portas.LoteRegistrado(lote_id=int(resp.json()), impressao=impressao,
                                     modo=modo, estado="em_voo")

    def ler_lote(self, lote_id: int) -> Optional[portas.LoteRegistrado]:
        resp = self._c.get("/conversao_offline_lote", params={
            "select": "id,impressao,modo,estado,request_id", "id": f"eq.{int(lote_id)}"})
        _erro(resp)
        linhas = resp.json()
        if not linhas:
            return None
        l = linhas[0]
        return portas.LoteRegistrado(lote_id=int(l["id"]), impressao=l["impressao"],
                                     modo=l["modo"], estado=l["estado"],
                                     request_id=l.get("request_id"))

    def fechar_lote(self, *, lote_id: int, estado: str, request_id: Optional[str],
                    resposta: Mapping[str, Any]) -> None:
        resp = self._c.post("/rpc/conversao_offline_fechar_lote", json={
            "p_lote_id": int(lote_id), "p_estado": estado,
            "p_request_id": request_id, "p_resposta": dict(resposta)})
        _erro(resp)
