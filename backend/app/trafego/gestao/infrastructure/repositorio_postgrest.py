"""O ledger v10_02 sobre o PostgREST, com `service_role`. Só transporte.

Herda o transporte de `persistencia._Cliente` (mesmos cabeçalhos, mesmo
`raise_for_status`) em vez de criar o quarto cliente HTTP deste backend — três
clientes com três tratamentos de erro é como uma recusa vira 409 numa rota e
503 noutra.

## O que este módulo traduz, e só isso

· tabela/coluna/filtro → query param do PostgREST;
· `httpx.HTTPStatusError` → `BancoRecusou` (gatilho/CHECK/único: SQLSTATE
  classe 23, P0001, P0002, 22023 — o mesmo predicado de `ledger.py` e
  `persistencia.py`) ou `Indisponivel` (o resto). Os gatilhos da v10_02 levantam
  `restrict_violation` (23001), que cai na primeira família.

## As escritas que são UPDATE, e o filtro que as protege

`trafego_proposta.estado`, o fechamento de `trafego_aplicacao` e o de
`trafego_atuacao_reversao` são os únicos UPDATEs. Cada um vai com o estado de
origem NO FILTRO (`desfecho=eq.em_voo`, `estado=in.(...)`): duas requisições
que correm para fechar a mesma linha não se sobrescrevem — a segunda atualiza
zero linhas e recebe `None`, e quem chamou decide. O gatilho
`trafego_aplicacao_fecha_uma_vez` recusaria de todo modo; o filtro só faz a
corrida perder em silêncio em vez de em exceção.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.trafego.persistencia import _Cliente

from ..application.erros import BancoRecusou, Indisponivel

T_REGRA = "trafego_regra_otimizacao"
V_REGRA_VIGENTE = "trafego_regra_vigente"
T_CAMPANHA = "trafego_campanha"
T_EVIDENCIA = "trafego_evidencia"
T_DIAGNOSTICO = "trafego_diagnostico"
T_PROPOSTA = "trafego_proposta"
T_APROVACAO = "trafego_aprovacao"
T_APLICACAO = "trafego_aplicacao"
T_ACOMPANHAMENTO = "trafego_acompanhamento"
T_REVERSAO = "trafego_atuacao_reversao"
V_COOLDOWN_ATIVO = "trafego_cooldown_ativo"
V_PAINEL = "trafego_proposta_painel"

_RETORNAR = "return=representation"


def _e_recusa_de_regra(codigo: str) -> bool:
    return bool(codigo) and (codigo in ("P0001", "P0002", "22023") or codigo.startswith("23"))


def traduzir_erro(exc: Any) -> Exception:
    """`httpx.HTTPStatusError` do PostgREST → exceção da gestão. Pura e testável."""
    resposta = getattr(exc, "response", None)
    status = getattr(resposta, "status_code", 0)
    codigo, mensagem = "", ""
    if resposta is not None:
        try:
            corpo = resposta.json()
        except Exception:  # noqa: BLE001
            corpo = None
        if isinstance(corpo, dict):
            codigo = str(corpo.get("code") or "")
            mensagem = str(corpo.get("message") or "")[:2000]
        else:
            mensagem = str(getattr(resposta, "text", "") or exc)[:500]
    if _e_recusa_de_regra(codigo):
        return BancoRecusou(mensagem or str(exc), detalhe={"sqlstate": codigo})
    return Indisponivel(f"o ledger respondeu {status}: {mensagem or exc}",
                        detalhe={"sqlstate": codigo or None, "http": status})


def _um(linhas: Any) -> Optional[Dict[str, Any]]:
    if isinstance(linhas, list):
        return dict(linhas[0]) if linhas else None
    return dict(linhas) if isinstance(linhas, dict) else None


class RepositorioGestaoPostgrest(_Cliente):
    """Implementa `application.portas.Ledger`."""

    async def _chamar(self, metodo: str, alvo: str, **kw: Any) -> Any:
        import httpx  # noqa: PLC0415 — mantém o módulo importável sem rede

        if not self.habilitado:
            raise Indisponivel("o ledger não está configurado neste processo "
                               "(SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY ausentes). Nada foi "
                               "registrado e nada foi enviado.")
        try:
            return await self._req(metodo, alvo, **kw)
        except httpx.HTTPStatusError as exc:
            raise traduzir_erro(exc) from exc
        except httpx.HTTPError as exc:
            raise Indisponivel(f"o ledger não respondeu: {exc}") from exc

    async def _ler(self, alvo: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        return list(await self._chamar("GET", alvo, headers=self._headers(),
                                       params=params) or [])

    async def _inserir(self, tabela: str, linha: Mapping[str, Any]) -> Dict[str, Any]:
        # `None` é omitido: mandar a chave com null sobrescreve o DEFAULT da
        # coluna (`estado`, `criada_em`, `desfecho`), e alguns DEFAULTs não são NULL.
        corpo = {k: v for k, v in linha.items() if v is not None}
        saida = _um(await self._chamar("POST", tabela, headers=self._headers(_RETORNAR),
                                       json=corpo))
        if saida is None:
            raise Indisponivel(f"o INSERT em {tabela} não devolveu a linha gravada")
        return saida

    async def _atualizar(self, tabela: str, filtro: Dict[str, Any],
                         patch: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        return _um(await self._chamar("PATCH", tabela, headers=self._headers(_RETORNAR),
                                      params=filtro, json=dict(patch)))

    async def _primeira(self, alvo: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return _um(await self._ler(alvo, {"select": "*", "limit": 1, **params}))

    # ── regra e identidade ──────────────────────────────────────────────────

    async def regra_vigente(self, chave: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(V_REGRA_VIGENTE, {"chave": f"eq.{chave}"})

    async def regra(self, regra_id: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(T_REGRA, {"regra_id": f"eq.{regra_id}"})

    async def identidade_campanha(self, customer_id: str,
                                  campaign_id: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(T_CAMPANHA, {"customer_id": f"eq.{customer_id}",
                                                 "campaign_id": f"eq.{campaign_id}"})

    async def declarar_identidade(self, linha: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._inserir(T_CAMPANHA, linha)

    async def resolver_procedencia(self, volc_campaign_id: str,
                                   patch: Mapping[str, Any]) -> Dict[str, Any]:
        linha = await self._atualizar(
            T_CAMPANHA, {"volc_campaign_id": f"eq.{volc_campaign_id}",
                         "procedencia": "eq.desconhecida"}, patch)
        return linha or (await self._primeira(
            T_CAMPANHA, {"volc_campaign_id": f"eq.{volc_campaign_id}"})) or {}

    # ── proposta e satélites ────────────────────────────────────────────────

    async def proposta_por_chave(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(T_PROPOSTA, {"idempotency_key": f"eq.{idempotency_key}"})

    async def inserir_evidencia(self, linha: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._inserir(T_EVIDENCIA, linha)

    async def inserir_diagnostico(self, linha: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._inserir(T_DIAGNOSTICO, linha)

    async def diagnostico(self, diagnostico_id: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(T_DIAGNOSTICO, {"diagnostico_id": f"eq.{diagnostico_id}"})

    async def inserir_proposta(self, linha: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._inserir(T_PROPOSTA, linha)

    async def proposta(self, proposta_id: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(T_PROPOSTA, {"proposta_id": f"eq.{proposta_id}"})

    async def atualizar_estado_proposta(self, proposta_id: str, de: Sequence[str],
                                        para: str) -> Optional[Dict[str, Any]]:
        return await self._atualizar(
            T_PROPOSTA, {"proposta_id": f"eq.{proposta_id}",
                         "estado": f"in.({','.join(de)})"}, {"estado": para})

    async def aprovacao_da_proposta(self, proposta_id: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(T_APROVACAO, {"proposta_id": f"eq.{proposta_id}"})

    async def inserir_aprovacao(self, linha: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._inserir(T_APROVACAO, linha)

    # ── aplicação, acompanhamento, reversão ─────────────────────────────────

    async def aplicacoes_da_proposta(self, proposta_id: str) -> List[Dict[str, Any]]:
        return await self._ler(T_APLICACAO, {"select": "*", "proposta_id": f"eq.{proposta_id}",
                                             "order": "tentativa.asc"})

    async def aplicacao(self, aplicacao_id: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(T_APLICACAO, {"aplicacao_id": f"eq.{aplicacao_id}"})

    async def inserir_aplicacao(self, linha: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._inserir(T_APLICACAO, linha)

    async def fechar_aplicacao(self, aplicacao_id: str,
                               patch: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        return await self._atualizar(T_APLICACAO, {"aplicacao_id": f"eq.{aplicacao_id}",
                                                   "desfecho": "eq.em_voo"}, patch)

    async def cooldown_ativo(self, regra_chave: str,
                             alvo_chave: str) -> Optional[Dict[str, Any]]:
        return _um(await self._ler(V_COOLDOWN_ATIVO, {
            "select": "*", "regra_chave": f"eq.{regra_chave}",
            "alvo_chave": f"eq.{alvo_chave}", "order": "expira_em.desc", "limit": 1}))

    async def inserir_acompanhamento(self, linha: Mapping[str, Any]) -> Dict[str, Any]:
        # `confere` é tri-estado e o `False` não pode sumir com o filtro de None.
        return await self._inserir(T_ACOMPANHAMENTO, linha)

    async def acompanhamentos_da_aplicacao(self, aplicacao_id: str) -> List[Dict[str, Any]]:
        return await self._ler(T_ACOMPANHAMENTO, {"select": "*",
                                                  "aplicacao_id": f"eq.{aplicacao_id}",
                                                  "order": "observado_em.asc"})

    async def reversao_da_aplicacao(self, aplicacao_id: str) -> Optional[Dict[str, Any]]:
        return await self._primeira(T_REVERSAO, {"aplicacao_id": f"eq.{aplicacao_id}"})

    async def inserir_reversao(self, linha: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._inserir(T_REVERSAO, linha)

    async def fechar_reversao(self, reversao_id: str,
                              patch: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        return await self._atualizar(T_REVERSAO, {"reversao_id": f"eq.{reversao_id}",
                                                  "desfecho": "eq.pendente"}, patch)

    # ── painel ──────────────────────────────────────────────────────────────

    async def painel(self, customer_id: str, *, estado: Optional[str] = None,
                     limite: int = 50) -> List[Dict[str, Any]]:
        """A view `trafego_proposta_painel`, da conta pedida.

        A view não tem `customer_id`; a conta mora em `alvo_chave`
        (`google_ads:<conta>:…`), e o `like` com prefixo é exato porque a conta
        é só dígito e o separador é `:`.
        """
        params: Dict[str, Any] = {"select": "*",
                                  "alvo_chave": f"like.google_ads:{customer_id}:*",
                                  "order": "criada_em.desc", "limit": limite}
        if estado:
            params["estado"] = f"eq.{estado}"
        return await self._ler(V_PAINEL, params)
