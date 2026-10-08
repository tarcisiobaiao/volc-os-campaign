"""Dublês da gestão: o ledger v10_02 em memória e uma conta Google de mentira.

Não é módulo de teste (o pytest não o coleta): é usado por
`test_trafego_gestao.py` e pela prova no banco descartável, que REPRODUZ as
escritas registradas aqui (`LedgerEmMemoria.ops`) como SQL dentro de
BEGIN…ROLLBACK — é assim que se prova que as linhas que o caso de uso monta
passam nas CHECKs e gatilhos reais.

O ledger em memória espelha só as invariantes que mudam o fluxo dos casos de
uso (chave única, decisão única, aprovação exigida, carência, fecha-uma-vez).
Ele NÃO é a prova de que o banco aceita — a prova é a reprodução no Postgres.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.trafego import escopo, intencao
from app.trafego.gestao.application.erros import BancoRecusou

CASA = "5478096539"          # Crédito Up — filha direta do MCC da casa (medido 08/10)
FORA = "5838529870"          # IESDE — outro MCC
CAMPANHA = "24278665189"
BUDGET = 15886629542


def agora() -> datetime:
    return datetime.now(timezone.utc)


def regra_padrao(**sobre: Any) -> Dict[str, Any]:
    """A regra de gestão manual como o banco a devolveria (linha de `trafego_regra_vigente`)."""
    r = {
        "regra_id": str(uuid.uuid4()), "chave": "gestao_manual_google", "versao": 1,
        "titulo": "Gestão manual de campanhas Google Ads",
        "objetivo": "Limitar e registrar ajustes pedidos por humano em campanhas no ar",
        "plataformas": ["GOOGLE_ADS"], "canais": ["*"],
        "janela_minima_dias": 7, "atraso_conversao_dias": 0, "frescor_maximo_horas": 6,
        "amostra_minima_cliques": None, "amostra_minima_impressoes": 0,
        "amostra_minima_conversoes": None,
        "dados_obrigatorios": ["impressoes", "custo_micros"],
        "teto_orcamento_micros": 500_000_000, "teto_orcamento_moeda": "BRL",
        "limite_alteracao_pct": 30, "limite_alteracao_absoluto_micros": None,
        "cooldown_horas": 24, "confianca_minima": 0.5,
        "condicao_rollback": "o operador declara piora no acompanhamento",
        "rollback_janela_horas": 72, "responsavel": "dono-da-operacao",
        "nivel_autonomia": "T1", "deteccao": {"tipo": "pedido_humano"},
        "acao": {"tipo": "gestao_manual"}, "declarada_por": "prova", "fonte": "humano",
        "declarada_em": agora().isoformat(), "vigente_desde": agora().isoformat(),
        "retirada_em": None, "retirada_por": None, "retirada_motivo": None,
    }
    r.update(sobre)
    return r


#: A declaração `operacoes_sem_delta` da regra de REFERÊNCIA (v17_03): os 13
#: tipos sem delta, com tetos conservadores de exemplo. É a mesma que está em
#: comentário no fim da migration e no contrato (§4) — um teste confere as três.
OPERACOES_SEM_DELTA_REFERENCIA: Dict[str, Any] = {
    "status": {"status_permitidos": ["PAUSED", "ENABLED"],
               "niveis": ["campanha", "grupo", "anuncio", "asset_group"]},
    "lance.estrategia": {"estrategias": ["MANUAL_CPC", "TARGET_SPEND", "MAXIMIZE_CONVERSIONS",
                                         "MAXIMIZE_CONVERSION_VALUE"],
                         "teto_micros": 50_000_000},
    "ajuste.dispositivo": {"modificador_min": 0.5, "modificador_max": 1.5},
    "ajuste.horario": {"modificador_min": 0.5, "modificador_max": 1.5},
    "negativa.keyword": {"max_itens": 50, "escopos": ["campanha", "grupo"]},
    "exclusao.placement": {"max_itens": 50, "escopos": ["campanha", "conta"]},
    "exclusao.ip": {"max_itens": 20, "escopos": ["campanha", "conta"]},
    "programacao.anuncios": {"max_itens": 42, "modificador_min": 0.5, "modificador_max": 1.5},
    "lista.criar": {"max_itens": 100, "max_campanhas": 10},
    "lista.adicionar": {"max_itens": 100},
    "lista.anexar": {"max_itens": 10},
    "recomendacao.aplicar": {"tipos_permitidos": ["SITELINK_ASSET", "CALLOUT_ASSET", "CALL_ASSET",
                                                  "RESPONSIVE_SEARCH_AD_ASSET"]},
    "recomendacao.dispensar": {},
}


def regra_referencia(**sobre: Any) -> Dict[str, Any]:
    """`gestao_manual_google` como a v17_03 a propõe: os 15 tipos cobertos."""
    return regra_padrao(operacoes_sem_delta=copy.deepcopy(OPERACOES_SEM_DELTA_REFERENCIA),
                        **sobre)


def _sem_none(linha: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in linha.items() if v is not None}


class LedgerEmMemoria:
    """Implementa `portas.Ledger` em dicionários, com o log das escritas."""

    def __init__(self, regras: Sequence[Mapping[str, Any]] = ()) -> None:
        self.regras: Dict[str, Dict[str, Any]] = {r["regra_id"]: dict(r) for r in regras}
        self.campanhas: Dict[str, Dict[str, Any]] = {}
        self.evidencias: Dict[str, Dict[str, Any]] = {}
        self.diagnosticos: Dict[str, Dict[str, Any]] = {}
        self.propostas: Dict[str, Dict[str, Any]] = {}
        self.aprovacoes: Dict[str, Dict[str, Any]] = {}
        self.aplicacoes: Dict[str, Dict[str, Any]] = {}
        self.acompanhamentos: Dict[str, Dict[str, Any]] = {}
        self.reversoes: Dict[str, Dict[str, Any]] = {}
        self.cooldowns: List[Dict[str, Any]] = []
        #: ("insert", tabela, linha_enviada+id) | ("update", tabela, pk, id, filtro, patch)
        self.ops: List[tuple] = []

    # utilidades
    def _ins(self, tabela: str, pk: str, destino: Dict[str, Dict[str, Any]],
             linha: Mapping[str, Any], defaults: Mapping[str, Any]) -> Dict[str, Any]:
        enviada = _sem_none(linha)
        ident = str(enviada.get(pk) or uuid.uuid4())
        self.ops.append(("insert", tabela, {**enviada, pk: ident}))
        gravada = {**defaults, **copy.deepcopy(enviada), pk: ident}
        destino[ident] = gravada
        return copy.deepcopy(gravada)

    def _upd(self, tabela: str, pk: str, ident: str, linha: Dict[str, Any],
             filtro: Mapping[str, Any], patch: Mapping[str, Any]) -> Dict[str, Any]:
        self.ops.append(("update", tabela, pk, ident, dict(filtro), dict(patch)))
        linha.update(copy.deepcopy(dict(patch)))
        return copy.deepcopy(linha)

    # regra e identidade
    async def regra_vigente(self, chave: str):
        for r in self.regras.values():
            if r["chave"] == chave and r.get("vigente_desde") and not r.get("retirada_em"):
                return copy.deepcopy(r)
        return None

    async def regra(self, regra_id: str):
        return copy.deepcopy(self.regras.get(regra_id))

    async def identidade_campanha(self, customer_id: str, campaign_id: str):
        for c in self.campanhas.values():
            if c.get("customer_id") == customer_id and c.get("campaign_id") == campaign_id:
                return copy.deepcopy(c)
        return None

    async def declarar_identidade(self, linha):
        self.ops.append(("insert", "trafego_campanha", _sem_none(linha)))
        self.campanhas[linha["volc_campaign_id"]] = {**_sem_none(linha)}
        return copy.deepcopy(self.campanhas[linha["volc_campaign_id"]])

    async def resolver_procedencia(self, volc_campaign_id, patch):
        c = self.campanhas[volc_campaign_id]
        return self._upd("trafego_campanha", "volc_campaign_id", volc_campaign_id, c,
                         {"procedencia": "desconhecida"}, patch)

    # proposta
    async def proposta_por_chave(self, chave):
        for p in self.propostas.values():
            if p["idempotency_key"] == chave:
                return copy.deepcopy(p)
        return None

    async def inserir_evidencia(self, linha):
        return self._ins("trafego_evidencia", "evidencia_id", self.evidencias, linha, {})

    async def inserir_diagnostico(self, linha):
        return self._ins("trafego_diagnostico", "diagnostico_id", self.diagnosticos, linha, {})

    async def diagnostico(self, diagnostico_id):
        return copy.deepcopy(self.diagnosticos.get(diagnostico_id))

    async def inserir_proposta(self, linha):
        if any(p["idempotency_key"] == linha["idempotency_key"] for p in self.propostas.values()):
            raise BancoRecusou("duplicate key trafego_proposta_chave_ux",
                               detalhe={"sqlstate": "23505"})
        return self._ins("trafego_proposta", "proposta_id", self.propostas, linha,
                         {"estado": "aguardando_aprovacao", "criada_em": agora().isoformat()})

    async def proposta(self, proposta_id):
        return copy.deepcopy(self.propostas.get(proposta_id))

    async def atualizar_estado_proposta(self, proposta_id, de, para):
        p = self.propostas.get(proposta_id)
        if not p or p["estado"] not in de:
            return None
        return self._upd("trafego_proposta", "proposta_id", proposta_id, p,
                         {"estado": list(de)}, {"estado": para})

    async def aprovacao_da_proposta(self, proposta_id):
        for a in self.aprovacoes.values():
            if a["proposta_id"] == proposta_id:
                return copy.deepcopy(a)
        return None

    async def inserir_aprovacao(self, linha):
        if await self.aprovacao_da_proposta(linha["proposta_id"]):
            raise BancoRecusou("duplicate key trafego_aprovacao_proposta_ux",
                               detalhe={"sqlstate": "23505"})
        return self._ins("trafego_aprovacao", "aprovacao_id", self.aprovacoes, linha,
                         {"decidida_em": agora().isoformat()})

    # aplicação
    async def aplicacoes_da_proposta(self, proposta_id):
        return sorted((copy.deepcopy(a) for a in self.aplicacoes.values()
                       if a["proposta_id"] == proposta_id), key=lambda a: a["tentativa"])

    async def aplicacao(self, aplicacao_id):
        return copy.deepcopy(self.aplicacoes.get(aplicacao_id))

    async def inserir_aplicacao(self, linha):
        ap = self.aprovacoes.get(linha["aprovacao_id"]) or {}
        if ap.get("proposta_id") != linha["proposta_id"] or ap.get("decisao") != "aprovada":
            raise BancoRecusou("trafego_aplicacao: exige aprovação", detalhe={"sqlstate": "23001"})
        p = self.propostas[linha["proposta_id"]]
        chave = self.regras[p["regra_id"]]["chave"]
        if await self.cooldown_ativo(chave, p["alvo_chave"]):
            raise BancoRecusou("trafego_aplicacao: em carência", detalhe={"sqlstate": "23001"})
        if any(a["proposta_id"] == linha["proposta_id"] and a["tentativa"] == linha["tentativa"]
               for a in self.aplicacoes.values()):
            raise BancoRecusou("duplicate key trafego_aplicacao_tentativa_ux",
                               detalhe={"sqlstate": "23505"})
        return self._ins("trafego_aplicacao", "aplicacao_id", self.aplicacoes, linha,
                         {"desfecho": "em_voo"})

    async def fechar_aplicacao(self, aplicacao_id, patch):
        a = self.aplicacoes.get(aplicacao_id)
        if not a or a["desfecho"] != "em_voo":
            return None
        if patch.get("desfecho") == "sucesso" and any(
                o["idempotency_key"] == a["idempotency_key"] and o["desfecho"] == "sucesso"
                for o in self.aplicacoes.values()):
            raise BancoRecusou("duplicate key trafego_aplicacao_sucesso_unico_ux",
                               detalhe={"sqlstate": "23505"})
        saida = self._upd("trafego_aplicacao", "aplicacao_id", aplicacao_id, a,
                          {"desfecho": "em_voo"}, patch)
        if patch.get("desfecho") == "sucesso":  # o gatilho trafego_aplicacao_abre_cooldown
            p = self.propostas[a["proposta_id"]]
            r = self.regras[p["regra_id"]]
            ini = datetime.fromisoformat(patch["respondido_em"])
            self.cooldowns.append({"regra_chave": r["chave"], "alvo_chave": p["alvo_chave"],
                                   "aplicacao_id": aplicacao_id, "iniciado_em": ini.isoformat(),
                                   "expira_em": (ini + timedelta(hours=r["cooldown_horas"]))
                                   .isoformat()})
        return saida

    async def cooldown_ativo(self, regra_chave, alvo_chave):
        vivos = [c for c in self.cooldowns if c["regra_chave"] == regra_chave
                 and c["alvo_chave"] == alvo_chave
                 and datetime.fromisoformat(c["expira_em"]) > agora()]
        return copy.deepcopy(max(vivos, key=lambda c: c["expira_em"])) if vivos else None

    async def inserir_acompanhamento(self, linha):
        return self._ins("trafego_acompanhamento", "acompanhamento_id", self.acompanhamentos,
                         linha, {"gatilho_de_rollback": False})

    async def acompanhamentos_da_aplicacao(self, aplicacao_id):
        return [copy.deepcopy(a) for a in self.acompanhamentos.values()
                if a["aplicacao_id"] == aplicacao_id]

    async def reversao_da_aplicacao(self, aplicacao_id):
        for r in self.reversoes.values():
            if r["aplicacao_id"] == aplicacao_id:
                return copy.deepcopy(r)
        return None

    async def inserir_reversao(self, linha):
        if await self.reversao_da_aplicacao(linha["aplicacao_id"]):
            raise BancoRecusou("duplicate key trafego_reversao_aplicacao_ux",
                               detalhe={"sqlstate": "23505"})
        return self._ins("trafego_atuacao_reversao", "reversao_id", self.reversoes, linha,
                         {"desfecho": "pendente", "acionado_em": agora().isoformat()})

    async def fechar_reversao(self, reversao_id, patch):
        r = self.reversoes.get(reversao_id)
        if not r or r["desfecho"] != "pendente":
            return None
        return self._upd("trafego_atuacao_reversao", "reversao_id", reversao_id, r,
                         {"desfecho": "pendente"}, patch)

    async def painel(self, customer_id, *, estado=None, limite=50):
        saida = []
        for p in sorted(self.propostas.values(), key=lambda p: p["criada_em"], reverse=True):
            if not p["alvo_chave"].startswith(f"google_ads:{customer_id}:"):
                continue
            if estado and p["estado"] != estado:
                continue
            a = await self.aprovacao_da_proposta(p["proposta_id"])
            aps = await self.aplicacoes_da_proposta(p["proposta_id"])
            ult = aps[-1] if aps else {}
            linha = {**p, "aprovacao_decisao": (a or {}).get("decisao"),
                     "aplicacao_id": ult.get("aplicacao_id"),
                     "aplicacao_desfecho": ult.get("desfecho")}
            linha["proximo_passo"] = intencao.proximo_passo_da_proposta(linha)
            saida.append(linha)
        return saida[:limite]


# ── a conta ─────────────────────────────────────────────────────────────────


def antes_orcamento(verba: int = 30_000_000, **sobre: Any) -> Dict[str, Any]:
    d = {"existe": True, "campaign_id": int(CAMPANHA), "budget_id": BUDGET,
         "verba_diaria_micros": verba, "total_micros": None, "periodo": "DAILY",
         "compartilhado": False, "campanhas_no_orcamento": 1, "moeda": "BRL"}
    d.update(sobre)
    return d


class ContaFalsa:
    """`portas.ContaGoogle` em memória. Muta o "mundo" quando aplica — sem rede."""

    def __init__(self) -> None:
        #: (tipo, alvo_id) → dados do "antes"
        self.mundo: Dict[tuple, Dict[str, Any]] = {
            ("orcamento.diario", CAMPANHA): antes_orcamento(),
            ("status", CAMPANHA): {"existe": True, "status": "ENABLED"},
        }
        self.metricas: Dict[str, Any] = {"impressoes": 1200, "cliques": 80,
                                         "custo_micros": 95_000_000, "conversoes": 3.0,
                                         "valor_conversao_micros": 0, "moeda": "BRL",
                                         "sem_linhas": False}
        self.campanhas: Dict[str, Dict[str, Any]] = {
            CAMPANHA: {"campaign_id": CAMPANHA, "nome": "Crédito Up | Search",
                       "status": "ENABLED", "canal": "SEARCH", "moeda": "BRL"}}
        self.validacao_ok = True
        self.trava_fechada = False
        self.explodir_na_escrita = False
        self.chamadas: List[tuple] = []

    def ler_antes(self, customer_id, acao, *, conferir):
        self.chamadas.append(("ler_antes", acao.tipo, conferir))
        chave = (acao.tipo, str(acao.alvo_id))
        if chave not in self.mundo and acao.tipo.startswith("reverso"):
            chave = ("orcamento.diario", CAMPANHA)
        dados = copy.deepcopy(self.mundo.get(chave, {"existe": False}))
        if conferir:
            acao.conferir(dados)
        return SimpleNamespace(acao=acao, dados=dados, lido_em=agora(), consultas=())

    def ler_metricas(self, customer_id, nivel, alvo_id, inicio, fim):
        self.chamadas.append(("ler_metricas", nivel, alvo_id, inicio, fim))
        return dict(self.metricas)

    def ler_campanha(self, customer_id, campaign_id):
        self.chamadas.append(("ler_campanha", campaign_id))
        return copy.deepcopy(self.campanhas.get(str(campaign_id)))

    def _lote(self, acoes, desfecho="ok", validate_only=True):
        from volc_ads.gads.errors import ErroGads  # noqa: PLC0415
        from volc_ads.gestao.lote import ResultadoAcao, ResultadoLote  # noqa: PLC0415

        erros = () if desfecho == "ok" else (
            ErroGads("range_error", "TOO_LOW", "abaixo do mínimo", indice_operacao=0),)
        return ResultadoLote(CASA, validate_only,
                             tuple(ResultadoAcao(a, desfecho, erros, (), (i, i + 1))
                                   for i, a in enumerate(acoes)), (), "req-falso")

    def validar(self, customer_id, acoes):
        self.chamadas.append(("validar", [a.tipo for a in acoes]))
        return self._lote(acoes, "ok" if self.validacao_ok else "falhou")

    def _efeito(self, acao) -> None:
        from volc_ads.gestao import acoes as A  # noqa: PLC0415

        if isinstance(acao, A.AlterarOrcamento):
            self.mundo[(acao.tipo, str(acao.campaign_id))]["verba_diaria_micros"] = \
                acao.amount_micros
        elif isinstance(acao, A.AlterarStatus):
            self.mundo[(acao.tipo, acao.ident)]["status"] = acao.status

    def aplicar(self, customer_id, acoes, motivo):
        from volc_ads.gads.modo import EscritaBloqueada  # noqa: PLC0415

        self.chamadas.append(("aplicar", [a.tipo for a in acoes], motivo))
        ensaio = self._lote(acoes, "ok" if self.validacao_ok else "falhou")
        if not self.validacao_ok:
            return ensaio, None
        if self.trava_fechada:
            raise EscritaBloqueada("FORGE_PERMITIR_ESCRITA não está definido como '1'")
        if self.explodir_na_escrita:
            raise RuntimeError("DEADLINE_EXCEEDED")
        for a in acoes:
            self._efeito(a)
        return ensaio, self._lote(acoes, "ok", validate_only=False)

    def aplicar_recomendacoes(self, customer_id, acoes, motivo):
        self.chamadas.append(("aplicar_recomendacoes", [a.tipo for a in acoes]))
        return {"aplicar": self._lote(acoes, "ok", validate_only=False)}

    def recomendacoes(self, customer_id):
        self.chamadas.append(("recomendacoes", customer_id))
        rn = f"customers/{customer_id}/recommendations/abc123"
        return [{"recurso": rn, "tipo": "CAMPAIGN_BUDGET", "dispensada": False,
                 "acoes": [{"tipo": "recomendacao.aplicar", "recurso": rn}]}]


def portao_falso(customer_id: str) -> Dict[str, Any]:
    """`escopo.conta_da_casa` sem rede: só a Crédito Up é da casa."""
    if customer_id != CASA:
        raise escopo.ForaDoEscopo(f"A conta {customer_id} não está entre as contas do MCC")
    return {"customer_id": CASA}


def gestao_de_teste(*, regras: Optional[Sequence[Mapping[str, Any]]] = None,
                    escrita: bool = True, importada: bool = True):
    """(gestao, ledger, conta) prontos: regra vigente, campanha importada, escrita ligada."""
    from app.trafego.gestao.application.casos_de_uso import Gestao  # noqa: PLC0415
    from app.trafego.sincronizador import volc_campaign_id  # noqa: PLC0415

    ledger = LedgerEmMemoria([regra_padrao()] if regras is None else regras)
    if importada:
        vid = volc_campaign_id(CASA, CAMPANHA)
        ledger.campanhas[vid] = {"volc_campaign_id": vid, "customer_id": CASA,
                                 "campaign_id": CAMPANHA, "procedencia": "descoberta",
                                 "procedencia_declarada_por": "prova",
                                 "procedencia_declarada_em": agora().isoformat(),
                                 "criada_por": "prova"}
    conta = ContaFalsa()
    g = Gestao(ledger, conta, escrita_habilitada=lambda: escrita, portao=portao_falso)
    return g, ledger, conta
