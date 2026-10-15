"""`volc_get_campaign_context` — o contexto de UMA campanha, só leitura.

## De onde vem cada número (serviços canônicos, nenhum SQL próprio)

- identidade, canal, estado e frescor do snapshot: a MESMA leitura e a MESMA
  projeção de `GET /api/trafego/campanhas/{id}` (`FonteDeReconciliacao.uma_campanha`
  + `inventario.campanha_projetada` + `inventario.frescor_da_conta`);
- custo: o fato canônico campanha-dia pelo MESMO domínio do Hub
  (`custo_canonico.montar_custo`, ledger lido ANTES do fato), filtrado pela
  campanha. Total só quando todo dia da janela está fechado;
- conversões oficiais: coluna `conversoes` do mesmo fato (Google
  `metrics.conversions`, ações primárias), na MESMA régua de dias do custo;
- receita: **nula**. Não há serviço aplicado que reconcilie receita por
  campanha (v17_04 não aplicada; ADR-CICLO-ECONOMICO-COMPRA-MONETIZACAO);
- lucro: **nulo**, pelo mesmo motivo e porque a granularidade economicamente
  válida é a coorte, não a campanha-janela.

## O que esta capacidade se recusa a fazer

Escrever em qualquer lugar, chamar o Google Ads, aceitar data livre (só as
janelas enumeradas, fechadas até ontem), aceitar id externo cru, estimar
receita/lucro, ou devolver número sem frescor.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Literal, Mapping, Optional, Protocol, Sequence
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from app.agente_bia.gateway.catalogo import Capacidade
from app.seguranca.identidade import Identidade
from app.trafego import custo_canonico as cc

NOME = "volc_get_campaign_context"
FUSO = "America/Sao_Paulo"

#: Mesmo formato aceito por `GET /api/trafego/campanhas/{id}`.
PADRAO_REF = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$"

JANELAS: Dict[str, int] = {"ultimos_7_dias": 7, "ultimos_14_dias": 14, "ultimos_30_dias": 30}

#: Snapshot do inventário mais velho que isto é sinalizado como defasado.
HORAS_SNAPSHOT_DEFASADO = 24

FONTES = (
    "trafego_inventario_campanha (snapshot do inventário, mesma leitura de /api/trafego/campanhas/{id})",
    "google_ads_campanha_dia (fato canônico campanha-dia, v12_04)",
    "trafego_coleta_execucao (ledger de fechamento da coleta)",
)
LIMITACOES_FIXAS = (
    "Receita por campanha não é reconciliada por nenhum serviço aplicado (v17_04 não aplicada): "
    "receita fica nula.",
    "Lucro não é calculado: a granularidade economicamente válida é a coorte, e falta receita "
    "reconciliada e custos além da mídia.",
    "Conversões são as do Google Ads (ações primárias, metrics.conversions), não vendas confirmadas.",
    "Alertas do quadro operacional completo não estão incluídos na V1; os alertas abaixo são "
    "derivados só desta leitura.",
)


# ── contrato ────────────────────────────────────────────────────────────────

class EntradaContextoCampanha(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    campaign_ref: str = Field(pattern=PADRAO_REF, description="volc_campaign_id (identidade interna)")
    janela: Literal["ultimos_7_dias", "ultimos_14_dias", "ultimos_30_dias"] = "ultimos_7_dias"


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identificacao(_Estrito):
    campaign_ref_mascarado: str
    nome: Optional[str]
    plataforma: str
    conta_mascarada: Optional[str]
    id_externo_mascarado: Optional[str]


class Situacao(_Estrito):
    canal: Optional[str]
    estado_externo: Optional[str]
    veiculacao: Optional[str]


class Janela(_Estrito):
    nome: str
    inicio: str
    fim: str
    dias: int


class Medida(_Estrito):
    valor: Optional[float]
    valor_coberto: Optional[float]
    verdade: Literal["real", "parcial", "indisponivel"]
    unidade: str


class Nulo(_Estrito):
    valor: None = None
    estado: str
    motivo: str


class Frescor(_Estrito):
    avaliado_em: str
    estado: Literal["fresco", "defasado", "desconhecido"]
    snapshot_inventario: Optional[str]
    fato_ultima_colhida_em: Optional[str]
    fato_ultimo_fechamento_em: Optional[str]
    fato_idade_horas: Optional[float]


class Cobertura(_Estrito):
    dias_total: int
    dias_fechados: int
    dias_por_estado: Dict[str, int]


class ContextoDeCampanha(_Estrito):
    capacidade: Literal["volc_get_campaign_context"] = NOME
    efeito: Literal["leitura"] = "leitura"
    identificacao: Identificacao
    situacao: Situacao
    janela: Janela
    custo: Medida
    conversoes_oficiais: Medida
    receita: Nulo
    lucro: Nulo
    frescor: Frescor
    cobertura: Cobertura
    fontes: List[str]
    limitacoes: List[str]
    alertas: List[str]


# ── portas ──────────────────────────────────────────────────────────────────

class FonteDoContexto(Protocol):
    async def uma_campanha(self, volc_campaign_id: str) -> Optional[Dict[str, Any]]: ...

    async def fechamentos(self, contas: Sequence[str], periodo: cc.Periodo) -> List[Dict[str, Any]]: ...

    async def linhas_da_campanha(self, customer_id: str, campaign_id: str,
                                 periodo: cc.Periodo) -> List[Dict[str, Any]]: ...


class CampanhaNaoEncontrada(LookupError):
    pass


# ── domínio da capacidade (puro) ────────────────────────────────────────────

def mascarar(valor: Any) -> Optional[str]:
    texto = str(valor or "").strip()
    if not texto:
        return None
    return "••••" + texto[-4:]


def periodo_da_janela(nome: str, agora: datetime) -> cc.Periodo:
    hoje = agora.astimezone(ZoneInfo(FUSO)).date()
    return cc.periodo_padrao(hoje, JANELAS[nome])


def _numero(v: Any) -> Optional[Decimal]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _conversoes(linhas: Sequence[Mapping[str, Any]], serie: Sequence[Mapping[str, Any]],
                verdade_custo: str) -> Medida:
    """Conversões na régua do custo: dia sem coleta é nulo, total só se tudo fechado."""
    estado_do_dia = {s["data"]: s["estado"] for s in serie}
    por_dia: Dict[str, Decimal] = {}
    sem_medida: set = set()
    for l in linhas:
        d = str(l.get("metric_date") or "")[:10]
        if d not in estado_do_dia:
            continue
        n = _numero(l.get("conversoes"))
        if n is None:
            sem_medida.add(d)
        else:
            por_dia[d] = por_dia.get(d, Decimal(0)) + n
    coberto = Decimal(0)
    algum = False
    for d, e in estado_do_dia.items():
        if e == cc.SEM_COLETA or d in sem_medida:
            continue
        if d in por_dia:
            coberto += por_dia[d]
            algum = True
        elif e in (cc.FECHADO, cc.INTRADIA):
            algum = True  # zero medido
    verdade = verdade_custo if not sem_medida else ("parcial" if verdade_custo != "indisponivel"
                                                    else "indisponivel")
    return Medida(
        valor=float(coberto) if verdade == "real" else None,
        valor_coberto=float(coberto) if algum else None,
        verdade=verdade,
        unidade="conversões (Google Ads, ações primárias)",
    )


def montar_contexto(*, ref: str, janela_nome: str, linha: Mapping[str, Any],
                    fechamentos: Sequence[Mapping[str, Any]], linhas: Sequence[Mapping[str, Any]],
                    periodo: cc.Periodo, agora: datetime) -> ContextoDeCampanha:
    from app.trafego import inventario as inv  # tarde: o módulo é grande e só a leitura o usa

    conta_falhou = str(linha.get("tentativa_resultado") or "") == "falhou"
    projetada = inv.campanha_projetada(dict(linha), conta_falhou=conta_falhou, agora=agora)
    frescor_snapshot = inv.frescor_da_conta(inv.normalizar_linha_de_conta({
        "customer_id": linha.get("customer_id"),
        "tentativa_resultado": linha.get("tentativa_resultado"),
        "tentativa_em": linha.get("tentativa_em"),
        "leitura_boa_em": linha.get("leitura_boa_em"),
    }), agora)

    customer_id = str(projetada.externa.customer_id or linha.get("customer_id") or "")
    custo = cc.montar_custo(linhas, fechamentos, contas=[customer_id] if customer_id else None,
                            periodo=periodo, agora=agora)
    conta = (custo.get("contas") or [{}])[0] if custo.get("contas") else {}
    serie = conta.get("dias") or []
    verdade_custo = str(conta.get("verdade") or "indisponivel")
    moeda = conta.get("moeda")

    def _moeda(micros: Optional[int]) -> Optional[float]:
        return None if micros is None else round(micros / 1_000_000, 2)

    por_estado: Dict[str, int] = {}
    for s in serie:
        por_estado[s["estado"]] = por_estado.get(s["estado"], 0) + 1
    fechados = por_estado.get(cc.FECHADO, 0)

    fr = conta.get("frescor") or {}
    idade = fr.get("ultima_colhida_em")
    alertas: List[str] = []
    if frescor_snapshot != "recente":
        alertas.append(f"Snapshot do inventário desta conta está '{frescor_snapshot}'.")
    if verdade_custo == "parcial":
        alertas.append("Custo parcial: nem todos os dias da janela estão fechados no ledger.")
    if verdade_custo == "indisponivel":
        alertas.append("Custo indisponível: nenhum dia da janela foi comprovadamente coletado.")
    for m in conta.get("motivos") or []:
        alertas.append(f"Custo: {m}.")
    if not customer_id:
        alertas.append("Campanha sem conta externa no snapshot: custo não pôde ser lido.")

    if fr.get("ultima_colhida_em") is None and fr.get("ultimo_fechamento_em") is None:
        estado_frescor = "desconhecido"
        alertas.append("Frescor do fato de custo desconhecido: sem coleta registrada na janela.")
    elif frescor_snapshot in ("recente",) and verdade_custo == "real":
        estado_frescor = "fresco"
    else:
        estado_frescor = "defasado"

    nome = projetada.nome
    if isinstance(nome, str):
        # Nome é texto de fora (conta de anúncio): cortado e tratado como dado.
        nome = re.sub(r"[\x00-\x1f\x7f]", " ", nome)[:120]

    return ContextoDeCampanha(
        identificacao=Identificacao(
            campaign_ref_mascarado=mascarar(ref) or "••••",
            nome=nome,
            plataforma="google_ads",
            conta_mascarada=mascarar(customer_id),
            id_externo_mascarado=mascarar(projetada.externa.campaign_id),
        ),
        situacao=Situacao(canal=projetada.canal, estado_externo=projetada.estado_externo,
                          veiculacao=projetada.veiculacao),
        janela=Janela(nome=janela_nome, inicio=periodo.inicio.isoformat(),
                      fim=periodo.fim.isoformat(), dias=periodo.dias),
        custo=Medida(valor=_moeda(conta.get("custo_micros")),
                     valor_coberto=_moeda(conta.get("custo_micros_coberto")),
                     verdade=verdade_custo if verdade_custo in ("real", "parcial", "indisponivel")
                     else "indisponivel",
                     unidade=f"moeda da conta ({moeda})" if moeda else "moeda da conta (desconhecida)"),
        conversoes_oficiais=_conversoes(linhas, serie, verdade_custo),
        receita=Nulo(estado="nao_reconciliada",
                     motivo="Sem serviço aplicado que reconcilie receita por campanha."),
        lucro=Nulo(estado="nao_calculado",
                   motivo="Sem receita reconciliada; granularidade válida é a coorte."),
        frescor=Frescor(
            avaliado_em=agora.astimezone(timezone.utc).isoformat(),
            estado=estado_frescor,
            snapshot_inventario=frescor_snapshot,
            fato_ultima_colhida_em=idade,
            fato_ultimo_fechamento_em=fr.get("ultimo_fechamento_em"),
            fato_idade_horas=fr.get("idade_horas"),
        ),
        cobertura=Cobertura(dias_total=len(serie), dias_fechados=fechados, dias_por_estado=por_estado),
        fontes=list(FONTES),
        limitacoes=list(LIMITACOES_FIXAS),
        alertas=alertas,
    )


# ── a capacidade ────────────────────────────────────────────────────────────

def capacidade(fonte_factory, *, relogio=None) -> Capacidade:
    """Monta a capacidade com a fonte injetada (real ou de teste)."""

    async def executar(identidade: Identidade, entrada: BaseModel) -> ContextoDeCampanha:
        assert isinstance(entrada, EntradaContextoCampanha)
        agora = (relogio or (lambda: datetime.now(timezone.utc)))()
        periodo = periodo_da_janela(entrada.janela, agora)
        fonte: FonteDoContexto = fonte_factory()
        linha = await fonte.uma_campanha(entrada.campaign_ref)
        if linha is None:
            raise CampanhaNaoEncontrada(entrada.campaign_ref)
        customer_id = str(linha.get("customer_id") or "")
        campaign_id = str(linha.get("campaign_id") or "")
        fechos: List[Dict[str, Any]] = []
        linhas: List[Dict[str, Any]] = []
        if customer_id and campaign_id:
            # Ledger ANTES do fato (mesma razão de routers/trafego_custo.py).
            fechos = await fonte.fechamentos([customer_id], periodo)
            linhas = await fonte.linhas_da_campanha(customer_id, campaign_id, periodo)
        return montar_contexto(ref=entrada.campaign_ref, janela_nome=entrada.janela, linha=linha,
                               fechamentos=fechos, linhas=linhas, periodo=periodo, agora=agora)

    return Capacidade(
        nome=NOME,
        descricao=("Contexto somente leitura de UMA campanha VOLC: identificação mascarada, canal, "
                   "estado, custo e conversões oficiais na janela, frescor, cobertura, fontes, "
                   "limitações e alertas. Receita e lucro ficam nulos até haver reconciliação."),
        efeito="leitura",
        papel_minimo="ADMIN",
        entrada=EntradaContextoCampanha,
        saida=ContextoDeCampanha,
        executar=executar,
    )


def resumo_para_recibo(ctx: Mapping[str, Any]) -> Dict[str, Any]:
    """O que vai ao evento `contexto_lido`: sem nome, sem número, sem id cru."""
    return {
        "capacidade": NOME,
        "campanha": (ctx.get("identificacao") or {}).get("campaign_ref_mascarado"),
        "janela": (ctx.get("janela") or {}).get("nome"),
        "frescor": (ctx.get("frescor") or {}).get("estado"),
        "verdade_custo": (ctx.get("custo") or {}).get("verdade"),
        "alertas": len(ctx.get("alertas") or []),
    }

