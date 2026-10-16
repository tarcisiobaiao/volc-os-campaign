"""Portão de viabilidade do surrogate index (Fase 6).

Antes de qualquer modelo, o portão responde se existe base identificável:

1. o grão-alvo precisa ser o grão do rótulo ou um grão DERIVÁVEL dele por soma
   (reticulado explícito, não ordem linear) → senão `nao_identificavel`;
2. features circulares saem pela regra única do contrato (`origens_circulares`, vocabulário
   fechado de fontes); features sem instante de disponibilidade, ou disponíveis depois do
   fechamento do período, saem como vazamento/não verificáveis;
3. contam só unidades com PROFUNDIDADE suficiente em treino e teste fora do tempo
   (um painel 1×1200 + 19×1 não equivale a 20×60) → senão `dados_insuficientes`;
4. só então `viavel_para_teste` — que ainda exige o modelo superar o ingênuo fora do tempo.

Os mínimos são PARÂMETROS calibrados por simulação (`experiment.py`), não regra.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Mapping, Optional, Sequence

from volc_dil.contracts import familia_de_fonte, origens_circulares

# grão do rótulo -> grãos-alvo derivados por soma SEM ratear (inclui ele mesmo).
# URL não está aninhada em campanha/keyword: só agrega para conta.
DERIVAVEL: Mapping[str, frozenset[str]] = {
    "account_day": frozenset({"account_day"}),
    "campaign_day": frozenset({"campaign_day", "account_day"}),
    "ad_group_day": frozenset({"ad_group_day", "campaign_day", "account_day"}),
    "keyword_day": frozenset({"keyword_day", "ad_group_day", "campaign_day", "account_day"}),
    "url_day": frozenset({"url_day", "account_day"}),
    "session": frozenset({"session", "account_day"}),
    "click": frozenset({"click", "session", "account_day"}),
}


class Veredito(str, enum.Enum):
    VIAVEL_PARA_TESTE = "viavel_para_teste"
    NAO_IDENTIFICAVEL = "nao_identificavel"
    DADOS_INSUFICIENTES = "dados_insuficientes"


@dataclass(frozen=True)
class Feature:
    valor: Optional[float]
    origem: str  # família de fonte (vocabulário fechado do contrato)
    disponivel_em: Optional[datetime] = None  # quando a feature passou a ser conhecida


@dataclass(frozen=True)
class LinhaRotulada:
    unidade_id: str
    periodo: date
    grao: str
    rotulo: Optional[float]  # None = sem rótulo econômico (null != 0)
    rotulo_maduro: bool
    origem_rotulo: str
    features: Mapping[str, Feature] = field(default_factory=dict)


@dataclass(frozen=True)
class ParametrosPortao:
    # Calibrado em results/surrogate (sinal fraco, força 0.25, painel balanceado): menor grade com
    # P(skill > 1%) >= 0.8 foi 50 unidades × 90 períodos (63 treino / 27 teste); sob sinal nulo a
    # mesma grade dá 0,0. Reavaliar com dado real.
    min_unidades: int = 50
    min_periodos_treino_por_unidade: int = 63
    min_periodos_teste_por_unidade: int = 27
    min_linhas_maduras: int = 4500
    fracao_teste: float = 0.3
    # horizonte de decisão: a feature precisa estar disponível até D+1 do período; a receita
    # que ela antecipa matura só em ~D+3. Parâmetro, não regra.
    tolerancia_disponibilidade: timedelta = timedelta(days=1)


@dataclass
class ResultadoPortao:
    veredito: Veredito
    motivos: list[str]
    contagens: dict
    features_validas: list[str]
    features_circulares: list[str]
    features_vazamento: list[str] = field(default_factory=list)

    def para_json(self) -> dict:
        return {
            "veredito": self.veredito.value,
            "motivos": self.motivos,
            "contagens": self.contagens,
            "features_validas": self.features_validas,
            "features_circulares": self.features_circulares,
            "features_vazamento_ou_sem_as_of": self.features_vazamento,
        }


def _fim_do_periodo(p: date) -> datetime:
    return datetime(p.year, p.month, p.day, tzinfo=timezone.utc) + timedelta(days=1)


def avaliar_viabilidade(
    linhas: Sequence[LinhaRotulada],
    *,
    grao_alvo: str,
    parametros: ParametrosPortao = ParametrosPortao(),
) -> ResultadoPortao:
    motivos: list[str] = []
    graos_rotulo = {l.grao for l in linhas}
    contagens: dict = {"linhas": len(linhas), "graos_do_rotulo": sorted(graos_rotulo)}
    if grao_alvo not in DERIVAVEL:
        raise ValueError(f"grão desconhecido: {grao_alvo}")

    if not linhas:
        return ResultadoPortao(Veredito.DADOS_INSUFICIENTES, ["nenhuma linha"], contagens, [], [])
    if len(graos_rotulo) != 1:
        return ResultadoPortao(Veredito.NAO_IDENTIFICAVEL, [f"rótulos em grãos misturados: {sorted(graos_rotulo)}"], contagens, [], [])
    grao_rotulo = graos_rotulo.pop()
    if grao_rotulo not in DERIVAVEL:
        raise ValueError(f"grão desconhecido: {grao_rotulo}")
    if grao_alvo not in DERIVAVEL[grao_rotulo]:
        return ResultadoPortao(
            Veredito.NAO_IDENTIFICAVEL,
            [f"alvo '{grao_alvo}' não é derivável por soma do rótulo em '{grao_rotulo}' (exigiria ratear ou inventar identidade)"],
            contagens, [], [],
        )

    origens_rotulo = {l.origem_rotulo for l in linhas}
    for o in origens_rotulo:
        familia_de_fonte(o)  # origem de rótulo fora do vocabulário é erro
    nomes = sorted({n for l in linhas for n in l.features})
    circulares: set[str] = set()
    vazamento: set[str] = set()
    for l in linhas:
        for n, f in l.features.items():
            if any(origens_circulares(f.origem, o) for o in origens_rotulo):
                circulares.add(n)
            elif f.disponivel_em is None or f.disponivel_em > _fim_do_periodo(l.periodo) + parametros.tolerancia_disponibilidade:
                vazamento.add(n)
    validas = [n for n in nomes if n not in circulares and n not in vazamento]
    if circulares:
        motivos.append(f"features circulares removidas (mesma família de fonte do rótulo): {sorted(circulares)}")
    if vazamento:
        motivos.append(f"features sem as_of verificável ou disponíveis após o período, removidas: {sorted(vazamento)}")
    if not validas:
        motivos.append("nenhuma feature não circular com as_of verificável")

    maduras = [l for l in linhas if l.rotulo is not None and l.rotulo_maduro]
    periodos = sorted({l.periodo for l in maduras})
    n_teste = max(1, round(len(periodos) * parametros.fracao_teste)) if periodos else 0
    corte = periodos[-n_teste] if periodos else None
    profundidade: dict[str, list[int]] = {}
    for l in maduras:
        tr_te = profundidade.setdefault(l.unidade_id, [0, 0])
        tr_te[0 if l.periodo < corte else 1] += 1
    p = parametros
    profundas = [u for u, (tr, te) in profundidade.items()
                 if tr >= p.min_periodos_treino_por_unidade and te >= p.min_periodos_teste_por_unidade]
    contagens.update(
        {
            "grao_rotulo": grao_rotulo,
            "linhas_maduras": len(maduras),
            "linhas_sem_rotulo_ou_imaturas": len(linhas) - len(maduras),
            "unidades_com_rotulo": len(profundidade),
            "unidades_com_profundidade": len(profundas),
            "periodos_com_rotulo": len(periodos),
            "periodos_treino_oot": len(periodos) - n_teste,
            "periodos_teste_oot": n_teste,
        }
    )
    if len(profundas) < p.min_unidades:
        motivos.append(
            f"unidades com ≥{p.min_periodos_treino_por_unidade} períodos de treino e ≥{p.min_periodos_teste_por_unidade} "
            f"de teste: {len(profundas)} < {p.min_unidades}"
        )
    if len(maduras) < p.min_linhas_maduras:
        motivos.append(f"linhas maduras {len(maduras)} < {p.min_linhas_maduras}")

    insuficiente = (not validas) or len(profundas) < p.min_unidades or len(maduras) < p.min_linhas_maduras
    veredito = Veredito.DADOS_INSUFICIENTES if insuficiente else Veredito.VIAVEL_PARA_TESTE
    return ResultadoPortao(veredito, motivos, contagens, validas, sorted(circulares), sorted(vazamento))
