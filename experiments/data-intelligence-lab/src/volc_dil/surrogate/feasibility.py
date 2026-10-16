"""Portão de viabilidade do surrogate index (Fase 6).

Antes de qualquer modelo, o portão responde se existe base identificável:

1. o rótulo é econômico (reconciliado e maduro) e está no MESMO grão das features,
   ou o grão-alvo é mais fino que o rótulo → `nao_identificavel`;
2. features que compartilham origem com o rótulo (ex.: impressões/eCPM da mesma fonte
   que produz a receita) são CIRCULARES e saem antes de contar qualquer coisa;
3. sobram unidades, períodos e linhas maduras suficientes para validação fora do tempo
   → senão `dados_insuficientes`;
4. só então `viavel_para_teste` — que ainda exige o modelo superar o baseline ingênuo
   fora do tempo, com intervalo (ver `experiment.py`).

Os mínimos são PARÂMETROS calibrados por simulação de poder (`experiment.py`), não regra.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional, Sequence

# Ordem do mais grosso para o mais fino. Um alvo mais fino que o rótulo não é identificável
# sem chave compartilhada (e alocar receita agregada por sessão é inventar identidade).
ORDEM_GRAO = ("account_day", "campaign_day", "ad_group_day", "keyword_day", "url_day", "session", "click")


class Veredito(str, enum.Enum):
    VIAVEL_PARA_TESTE = "viavel_para_teste"
    NAO_IDENTIFICAVEL = "nao_identificavel"
    DADOS_INSUFICIENTES = "dados_insuficientes"


@dataclass(frozen=True)
class Feature:
    valor: Optional[float]
    origem: str  # fonte/coleta que produziu o número


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
    # Calibrado em results/surrogate (sinal fraco, força 0.25): menor grade com
    # P(skill>0) >= 0.8 e IC95 inferior > 0 foi 20 unidades × 60 períodos. Reavaliar com dado real.
    min_unidades: int = 20
    min_periodos_treino: int = 42
    min_periodos_teste: int = 18
    min_linhas_maduras: int = 1200
    fracao_teste: float = 0.3


@dataclass
class ResultadoPortao:
    veredito: Veredito
    motivos: list[str]
    contagens: dict
    features_validas: list[str]
    features_circulares: list[str]

    def para_json(self) -> dict:
        return {
            "veredito": self.veredito.value,
            "motivos": self.motivos,
            "contagens": self.contagens,
            "features_validas": self.features_validas,
            "features_circulares": self.features_circulares,
        }


def _indice_grao(g: str) -> int:
    if g not in ORDEM_GRAO:
        raise ValueError(f"grão desconhecido: {g}")
    return ORDEM_GRAO.index(g)


def avaliar_viabilidade(
    linhas: Sequence[LinhaRotulada],
    *,
    grao_alvo: str,
    parametros: ParametrosPortao = ParametrosPortao(),
) -> ResultadoPortao:
    motivos: list[str] = []
    graos_rotulo = {l.grao for l in linhas}
    contagens: dict = {"linhas": len(linhas), "graos_do_rotulo": sorted(graos_rotulo)}

    if not linhas:
        return ResultadoPortao(Veredito.DADOS_INSUFICIENTES, ["nenhuma linha"], contagens, [], [])
    if len(graos_rotulo) != 1:
        return ResultadoPortao(Veredito.NAO_IDENTIFICAVEL, [f"rótulos em grãos misturados: {sorted(graos_rotulo)}"], contagens, [], [])
    grao_rotulo = graos_rotulo.pop()
    if _indice_grao(grao_alvo) > _indice_grao(grao_rotulo):
        return ResultadoPortao(
            Veredito.NAO_IDENTIFICAVEL,
            [f"alvo em '{grao_alvo}' é mais fino que o rótulo em '{grao_rotulo}': exigiria ratear receita agregada"],
            contagens, [], [],
        )

    origens_rotulo = {l.origem_rotulo for l in linhas}
    nomes = sorted({n for l in linhas for n in l.features})
    circulares = sorted({n for l in linhas for n, f in l.features.items() if f.origem in origens_rotulo})
    validas = [n for n in nomes if n not in circulares]
    if circulares:
        motivos.append(f"features circulares removidas (mesma origem do rótulo): {circulares}")
    if not validas:
        motivos.append("nenhuma feature não circular")

    maduras = [l for l in linhas if l.rotulo is not None and l.rotulo_maduro]
    periodos = sorted({l.periodo for l in maduras})
    unidades = {l.unidade_id for l in maduras}
    n_teste = max(1, round(len(periodos) * parametros.fracao_teste)) if periodos else 0
    n_treino = len(periodos) - n_teste
    contagens.update(
        {
            "grao_rotulo": grao_rotulo,
            "linhas_maduras": len(maduras),
            "linhas_sem_rotulo_ou_imaturas": len(linhas) - len(maduras),
            "unidades_com_rotulo": len(unidades),
            "periodos_com_rotulo": len(periodos),
            "periodos_treino_oot": n_treino,
            "periodos_teste_oot": n_teste,
        }
    )
    p = parametros
    if len(unidades) < p.min_unidades:
        motivos.append(f"unidades com rótulo {len(unidades)} < {p.min_unidades}")
    if n_treino < p.min_periodos_treino:
        motivos.append(f"períodos de treino fora do tempo {n_treino} < {p.min_periodos_treino}")
    if n_teste < p.min_periodos_teste:
        motivos.append(f"períodos de teste fora do tempo {n_teste} < {p.min_periodos_teste}")
    if len(maduras) < p.min_linhas_maduras:
        motivos.append(f"linhas maduras {len(maduras)} < {p.min_linhas_maduras}")

    insuficiente = [m for m in motivos if not m.startswith("features circulares")]
    veredito = Veredito.DADOS_INSUFICIENTES if insuficiente else Veredito.VIAVEL_PARA_TESTE
    return ResultadoPortao(veredito, motivos, contagens, validas, circulares)
