"""Contratos tipados do Predictive Core V1.

Todo registro carrega identidade, conta/campanha quando aplicável, instante,
janela, horizonte, versão, hash de inputs, procedência, estado semântico e
chave de idempotência. Nenhum contrato autoriza mutação de campanha.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Tuple

from .constantes import (
    ALVO_ROAS,
    ALVOS_DERIVADOS,
    ALVOS_PONTO,
    CENARIO_OBSERVADO,
    CENARIO_PLANNED_SPEND,
    CENARIOS,
    DATASET_KINDS,
    DATASET_SINTETICO,
    DEFINICOES_ALVO,
    FUSO_NEGOCIO,
    HORIZONTE_PADRAO_DIAS,
    IDENTIFICACAO_PLANNED_SPEND,
    MOEDA,
    UNIDADE_MONETARIA,
)
from .excecoes import ContratoInvalido, MoedaOuFusoIncompativel
from .hashes import hash_canonico, pair_id_d1
from .relogio import (
    civil_de_instante,
    exigir_target_d1,
    parse_civil,
    parse_instante,
    recusar_instante_futuro,
)
from .semantica import EstadoSemantico


def _exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise ContratoInvalido(mensagem)


@dataclass(frozen=True)
class SourceReceipt:
    recibo_id: str
    origem: str
    dataset_kind: str
    entra_em_contagens_reais: bool
    extraido_em: str
    hash_fonte: str
    notas: Tuple[str, ...] = ()
    fuso: str = FUSO_NEGOCIO
    moeda: str = MOEDA
    unidade: str = UNIDADE_MONETARIA

    def __post_init__(self) -> None:
        _exigir(bool(self.recibo_id), "SourceReceipt sem recibo_id")
        _exigir(bool(self.origem), "SourceReceipt sem origem")
        _exigir(bool(self.hash_fonte), "SourceReceipt sem hash_fonte")
        _exigir(isinstance(self.entra_em_contagens_reais, bool), "flag de contagem real não booleana")
        _exigir(
            self.fuso == FUSO_NEGOCIO and self.moeda == MOEDA and self.unidade == UNIDADE_MONETARIA,
            "SourceReceipt fora de fuso/moeda/unidade canônicos",
        )
        _exigir(self.dataset_kind in DATASET_KINDS, "dataset_kind inválido")
        parse_instante(self.extraido_em)
        marcador = " ".join((self.recibo_id, self.origem, *self.notas)).casefold()
        declarado_sintetico = any(
            token in marcador
            for token in (
                "sintetic",
                "sintétic",
                "synthetic",
                "fixture_sint",
                "fixture-sint",
            )
        )
        if declarado_sintetico:
            _exigir(
                self.dataset_kind == DATASET_SINTETICO,
                "fixture sintética não pode se declarar dataset real",
            )
        if self.dataset_kind == DATASET_SINTETICO:
            _exigir(
                self.entra_em_contagens_reais is False,
                "fixture sintética não pode entrar em contagens reais",
            )

    def serializar(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelVersion:
    version_id: str
    papel: str
    alvo: str
    feature_set_id: str
    code_hash: str
    artifact_hash: str
    criado_em: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    parent_version_id: Optional[str] = None
    notas: Tuple[str, ...] = ()
    mutacao_campanha: bool = False

    def __post_init__(self) -> None:
        _exigir(self.papel in ("candidate", "challenger", "champion", "retired"), "papel inválido")
        _exigir(self.mutacao_campanha is False, "ModelVersion não muta campanha")
        _exigir(bool(self.version_id and self.feature_set_id), "ModelVersion sem identidade")
        _exigir(self.alvo in DEFINICOES_ALVO, "ModelVersion com alvo inválido")
        _exigir(bool(self.code_hash and self.artifact_hash), "hashes de modelo obrigatórios")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        return dados


@dataclass(frozen=True)
class FeatureSnapshot:
    snapshot_id: str
    campanha_id: str
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    alvo: str
    feature_set_id: str
    features: Mapping[str, Optional[float]]
    feature_estados: Mapping[str, EstadoSemantico]
    feature_as_of: Mapping[str, Optional[str]]
    feature_unidades: Mapping[str, str]
    conta_id: Optional[str] = None
    origin_date: str = ""
    target_date: str = ""
    cutoff_em: str = ""
    cenario: str = CENARIO_OBSERVADO
    target_definition: str = ""
    feature_civil_dates: Mapping[str, Optional[str]] = field(default_factory=dict)
    codigo_hash: str = ""
    max_data_usada: str = ""
    max_instante_usado: str = ""

    def __post_init__(self) -> None:
        _exigir(bool(self.snapshot_id and self.campanha_id), "FeatureSnapshot sem identidade")
        _exigir(bool(self.conta_id), "FeatureSnapshot sem conta_id")
        _exigir(self.cenario in CENARIOS, "cenário inválido no snapshot")
        _exigir(bool(self.codigo_hash), "FeatureSnapshot sem codigo_hash")
        _exigir(self.origin_date == self.janela_fim, "origin_date difere da janela_fim")
        exigir_target_d1(self.origin_date, self.target_date, self.horizonte_dias)
        _exigir(
            self.target_definition == DEFINICOES_ALVO.get(self.alvo),
            "definição do alvo não corresponde ao alvo do snapshot",
        )
        _exigir(parse_civil(self.max_data_usada) <= parse_civil(self.origin_date), "max_data_usada posterior à origem")
        parse_instante(self.cutoff_em)
        parse_instante(self.max_instante_usado)
        recusar_instante_futuro(self.max_instante_usado, self.cutoff_em, "max_instante_usado")
        _exigir(
            set(self.features)
            == set(self.feature_estados)
            == set(self.feature_as_of)
            == set(self.feature_unidades)
            == set(self.feature_civil_dates),
            "features desalinhadas",
        )
        for nome, estado in self.feature_estados.items():
            valor = self.features[nome]
            quando = self.feature_as_of[nome]
            civil = self.feature_civil_dates[nome]
            if quando is not None:
                recusar_instante_futuro(quando, self.cutoff_em, f"feature {nome}")
            if civil is not None:
                _exigir(parse_civil(civil) <= parse_civil(self.origin_date), f"feature {nome} usa data futura")
            if estado in (
                EstadoSemantico.AUSENTE,
                EstadoSemantico.FALHA,
                EstadoSemantico.ANTIGO,
                EstadoSemantico.NAO_APLICAVEL,
            ):
                _exigir(valor is None, f"{estado.value} de {nome} não pode alimentar o modelo")
            if estado is EstadoSemantico.ZERO_MEDIDO:
                _exigir(valor == 0, f"zero medido de {nome} deve ser 0, não {valor}")
            if estado is EstadoSemantico.MEDIDO:
                _exigir(valor is not None, f"medido de {nome} exige valor")
            if estado is EstadoSemantico.HIPOTESE:
                _exigir(valor is not None, f"hipótese de {nome} exige valor")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        dados["feature_estados"] = {k: v.value for k, v in self.feature_estados.items()}
        dados["features"] = dict(self.features)
        dados["feature_as_of"] = dict(self.feature_as_of)
        dados["feature_unidades"] = dict(self.feature_unidades)
        dados["feature_civil_dates"] = dict(self.feature_civil_dates)
        return dados


@dataclass(frozen=True)
class PredictionRequest:
    request_id: str
    campanha_id: str
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    alvos: Tuple[str, ...]
    cenario: str = "observado"
    planned_spend_micros: Optional[int] = None
    conta_id: Optional[str] = None
    fuso: str = FUSO_NEGOCIO
    moeda: str = MOEDA
    unidade: str = UNIDADE_MONETARIA
    mutacao_campanha: bool = False
    identificacao_cenario: Optional[str] = None
    cutoff_em: Optional[str] = None

    def __post_init__(self) -> None:
        _exigir(self.mutacao_campanha is False, "previsão não executa mudança em campanha")
        _exigir(bool(self.request_id and self.campanha_id and self.conta_id), "request sem identidade conta/campanha")
        _exigir(self.moeda == MOEDA and self.unidade == UNIDADE_MONETARIA, "moeda/unidade fora do contrato")
        _exigir(self.fuso == FUSO_NEGOCIO, "fuso fora do contrato de negócio")
        _exigir(self.cenario in CENARIOS, "cenário de previsão inválido")
        _exigir(self.horizonte_dias == HORIZONTE_PADRAO_DIAS, "Core V1 só aceita request D+1")
        _exigir(parse_civil(self.janela_inicio) <= parse_civil(self.janela_fim), "janela invertida")
        parse_instante(self.observado_em)
        recusar_instante_futuro(self.procedencia.extraido_em, self.observado_em, "procedência do request")
        if self.cutoff_em is not None:
            parse_instante(self.cutoff_em)
            recusar_instante_futuro(self.cutoff_em, self.observado_em, "cutoff point-in-time do request")
        _exigir(bool(self.hash_inputs and self.chave_idempotencia), "request sem hash/idempotência")
        _exigir(bool(self.alvos) and len(set(self.alvos)) == len(self.alvos), "alvos vazios ou duplicados")
        _exigir(set(self.alvos).issubset(set(ALVOS_PONTO + ALVOS_DERIVADOS)), "alvo fora do contrato")
        if self.cenario == CENARIO_PLANNED_SPEND:
            _exigir(self.planned_spend_micros is not None, "cenário planned_spend sem valor")
            _exigir(self.planned_spend_micros >= 0, "planned_spend não pode ser negativo")
            _exigir(
                self.identificacao_cenario == IDENTIFICACAO_PLANNED_SPEND,
                "planned_spend precisa declarar ausência de identificação causal",
            )
        else:
            _exigir(self.planned_spend_micros is None, "cenário observado não aceita planned_spend")
            _exigir(self.identificacao_cenario is None, "cenário observado não aceita identificação de hipótese")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        return dados


@dataclass(frozen=True)
class PredictionInterval:
    interval_id: str
    campanha_id: str
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    alvo: str
    nominal: float
    lower_micros: Optional[int]
    upper_micros: Optional[int]
    metodo: str
    calibrado_fora_da_amostra: bool
    n_calibracao: int
    conta_id: Optional[str] = None
    pair_id: str = ""
    cenario: str = CENARIO_OBSERVADO
    artifact_hash: str = ""

    def __post_init__(self) -> None:
        _exigir(bool(self.conta_id and self.campanha_id and self.pair_id), "intervalo sem identidade completa")
        _exigir(self.cenario in CENARIOS, "intervalo com cenário inválido")
        _exigir(bool(self.artifact_hash), "intervalo sem hash de artefato")
        _exigir(0.0 < self.nominal < 1.0, "nominal do intervalo inválido")
        _exigir(self.n_calibracao >= 1, "intervalo sem amostra de calibração")
        _exigir(self.calibrado_fora_da_amostra, "intervalo não pode alegar calibração in-sample")
        _exigir(
            self.lower_micros is not None
            and self.upper_micros is not None
            and 0 <= self.lower_micros <= self.upper_micros,
            "limites do intervalo inválidos",
        )

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        return dados


@dataclass(frozen=True)
class Confidence:
    confidence_id: str
    campanha_id: str
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    cobertura_empirica: Optional[float]
    cobertura_nominal: float
    n_avaliacao: int
    evidencia_suficiente: bool
    conta_id: Optional[str] = None
    notas: Tuple[str, ...] = ()

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        return dados


@dataclass(frozen=True)
class Prediction:
    previsao_id: str
    campanha_id: str
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    alvo: str
    target_date: str
    ponto_micros: Optional[int]
    ponto_bruto_micros: Optional[int]
    intervalo: Optional[PredictionInterval]
    confianca: Optional[Confidence]
    snapshot_id: str
    cenario: str
    pair_id: str
    origin_date: str
    target_definition: str
    artifact_hash: str
    mutacao_campanha: bool = False
    conta_id: Optional[str] = None
    moeda: str = MOEDA
    unidade: str = UNIDADE_MONETARIA
    fuso: str = FUSO_NEGOCIO
    disponivel: bool = True
    motivo_indisponivel: Optional[str] = None

    def __post_init__(self) -> None:
        _exigir(self.mutacao_campanha is False, "Prediction não muta campanha")
        _exigir(bool(self.conta_id and self.campanha_id), "Prediction sem identidade conta/campanha")
        _exigir(self.cenario in CENARIOS, "Prediction com cenário inválido")
        _exigir(self.origin_date == self.janela_fim, "Prediction origin_date difere da janela_fim")
        exigir_target_d1(self.origin_date, self.target_date, self.horizonte_dias)
        _exigir(
            self.target_definition == DEFINICOES_ALVO.get(self.alvo),
            "Prediction mistura alvo e definição",
        )
        esperado_pair = pair_id_d1(
            conta_id=self.conta_id,
            campanha_id=self.campanha_id,
            origin_date=self.origin_date,
            target_date=self.target_date,
            alvo=self.alvo,
            cenario=self.cenario,
            target_definition=self.target_definition,
        )
        _exigir(self.pair_id == esperado_pair, "pair_id da Prediction não corresponde ao D+1")
        _exigir(bool(self.artifact_hash), "Prediction sem artifact_hash")
        if self.alvo == ALVO_ROAS:
            _exigir(self.unidade == "fracao_x_1e6", "ROAS usa fracao_x_1e6, não micros de moeda")
        else:
            _exigir(self.moeda == MOEDA and self.unidade == UNIDADE_MONETARIA, "moeda/unidade inválida")
        _exigir(self.fuso == FUSO_NEGOCIO, "fuso inválido")
        if not self.disponivel:
            _exigir(self.ponto_micros is None, "indisponível não pode carregar ponto")
            _exigir(
                self.estado_semantico
                in (
                    EstadoSemantico.AUSENTE,
                    EstadoSemantico.FALHA,
                    EstadoSemantico.ANTIGO,
                    EstadoSemantico.NAO_APLICAVEL,
                ),
                "indisponível exige estado não numérico",
            )
        else:
            _exigir(self.ponto_micros is not None, "Prediction disponível exige ponto")
        if self.estado_semantico in (
            EstadoSemantico.AUSENTE,
            EstadoSemantico.FALHA,
            EstadoSemantico.ANTIGO,
            EstadoSemantico.NAO_APLICAVEL,
        ):
            _exigir(self.ponto_micros is None, f"{self.estado_semantico.value} não vira ponto")
        if self.estado_semantico is EstadoSemantico.ZERO_MEDIDO:
            _exigir(self.ponto_micros == 0, "Prediction ZERO_MEDIDO contraditória")
        if self.intervalo is not None:
            _exigir(self.intervalo.pair_id == self.pair_id, "intervalo pertence a outro pair_id")
            _exigir(self.intervalo.artifact_hash == self.artifact_hash, "intervalo pertence a outro artefato")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        dados["intervalo"] = self.intervalo.serializar() if self.intervalo else None
        dados["confianca"] = self.confianca.serializar() if self.confianca else None
        return dados


@dataclass(frozen=True)
class ObservedOutcome:
    outcome_id: str
    campanha_id: str
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    alvo: str
    target_date: str
    valor_micros: Optional[int]
    pair_id: str
    origin_date: str
    target_definition: str
    cenario: str
    previsao_id: Optional[str] = None
    conta_id: Optional[str] = None
    moeda: str = MOEDA
    unidade: str = UNIDADE_MONETARIA
    fuso: str = FUSO_NEGOCIO
    watermark_fechado_ate: Optional[str] = None
    fechado: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        dia_observado = civil_de_instante(self.observado_em)
        watermark = (
            parse_civil(self.watermark_fechado_ate)
            if self.watermark_fechado_ate is not None
            else None
        )
        if watermark is not None:
            _exigir(
                watermark <= dia_observado,
                "watermark de actual não pode superar a data observada",
            )
        fechado_derivado = parse_civil(self.target_date) < dia_observado or (
            watermark is not None and parse_civil(self.target_date) <= watermark
        )
        _exigir(
            fechado_derivado,
            "data do actual ainda não está fechada por data civil ou watermark",
        )
        object.__setattr__(self, "fechado", True)
        _exigir(bool(self.conta_id and self.campanha_id), "outcome sem identidade conta/campanha")
        _exigir(self.cenario == CENARIO_OBSERVADO, "actual só existe no cenário observado")
        exigir_target_d1(self.origin_date, self.target_date, self.horizonte_dias)
        _exigir(self.janela_inicio == self.target_date == self.janela_fim, "janela do outcome não é o target")
        _exigir(
            self.target_definition == DEFINICOES_ALVO.get(self.alvo),
            "outcome mistura alvo e definição",
        )
        esperado_pair = pair_id_d1(
            conta_id=self.conta_id,
            campanha_id=self.campanha_id,
            origin_date=self.origin_date,
            target_date=self.target_date,
            alvo=self.alvo,
            cenario=self.cenario,
            target_definition=self.target_definition,
        )
        _exigir(self.pair_id == esperado_pair, "pair_id do outcome não corresponde ao D+1")
        if self.moeda != MOEDA or self.unidade != UNIDADE_MONETARIA:
            raise MoedaOuFusoIncompativel("outcome em unidade não canônica")
        if self.fuso != FUSO_NEGOCIO:
            raise MoedaOuFusoIncompativel("outcome em fuso não canônico")
        if self.estado_semantico in (
            EstadoSemantico.AUSENTE,
            EstadoSemantico.FALHA,
            EstadoSemantico.ANTIGO,
            EstadoSemantico.NAO_APLICAVEL,
        ):
            _exigir(self.valor_micros is None, f"outcome {self.estado_semantico.value} não carrega número")
        if self.estado_semantico is EstadoSemantico.ZERO_MEDIDO:
            _exigir(self.valor_micros == 0, "zero medido deve ser 0")
        if self.estado_semantico is EstadoSemantico.MEDIDO:
            _exigir(self.valor_micros is not None and self.valor_micros != 0, "outcome MEDIDO contraditório")
        _exigir(self.estado_semantico is not EstadoSemantico.HIPOTESE, "actual não pode ser hipótese")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        return dados


@dataclass(frozen=True)
class EvaluationWindow:
    window_id: str
    campanha_id: Optional[str]
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    conta_id: Optional[str] = None
    n_pares: int = 0
    completa: bool = False
    split: str = "walk_forward_temporal"
    cenario: str = CENARIO_OBSERVADO
    population_hash: str = ""

    def __post_init__(self) -> None:
        _exigir(self.split != "aleatorio", "split aleatório é leakage em série temporal")
        _exigir(self.horizonte_dias == HORIZONTE_PADRAO_DIAS, "janela de avaliação não é D+1")
        _exigir(self.cenario == CENARIO_OBSERVADO, "avaliação de actual exige cenário observado")
        _exigir(bool(self.conta_id and self.campanha_id), "janela sem conta/campanha")
        _exigir(bool(self.population_hash), "janela sem identidade de população")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        return dados


@dataclass(frozen=True)
class MetricasAvaliacao:
    n: int
    mae: Optional[float]
    wape: Optional[float]
    rmse: Optional[float]
    bias: Optional[float]
    cobertura: Optional[float]
    largura_media: Optional[float]
    winkler: Optional[float]
    evidencia_suficiente: bool
    dataset_kind: str
    entra_em_contagens_reais: bool
    pair_ids: Tuple[str, ...] = ()
    n_intervalos: int = 0

    def __post_init__(self) -> None:
        _exigir(self.n == len(self.pair_ids), "n de métricas difere dos pair_ids")
        _exigir(len(set(self.pair_ids)) == len(self.pair_ids), "pair_id duplicado infla métricas")
        _exigir(0 <= self.n_intervalos <= self.n, "denominador de intervalos inválido")
        _exigir(self.dataset_kind in DATASET_KINDS, "métricas com dataset_kind inválido")
        if self.dataset_kind == DATASET_SINTETICO:
            _exigir(self.entra_em_contagens_reais is False, "métrica sintética marcada como real")

    def serializar(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    result_id: str
    campanha_id: Optional[str]
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    janela: EvaluationWindow
    metricas_por_alvo: Mapping[str, MetricasAvaliacao]
    naive_por_alvo: Mapping[str, MetricasAvaliacao]
    falhas_parciais: Tuple[Mapping[str, str], ...]
    leakage_detectado: bool
    conta_id: Optional[str] = None
    dataset_kind: str = "sintetico"
    entra_em_contagens_reais: bool = False
    n_total: int = 0
    pair_ids_por_alvo: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    population_hash: str = ""
    cenario: str = CENARIO_OBSERVADO

    def __post_init__(self) -> None:
        _exigir(self.leakage_detectado is False, "resultado com leakage não é avaliável")
        _exigir(self.dataset_kind == self.procedencia.dataset_kind, "backtest diverge da procedência")
        _exigir(self.entra_em_contagens_reais == self.procedencia.entra_em_contagens_reais, "backtest diverge da procedência real")
        _exigir(self.cenario == CENARIO_OBSERVADO, "backtest de actual só aceita cenário observado")
        _exigir(bool(self.conta_id and self.campanha_id), "backtest sem conta/campanha")
        _exigir(bool(self.population_hash), "backtest sem population_hash")
        _exigir(self.population_hash == self.janela.population_hash, "janela e backtest usam populações distintas")
        for campo in (
            "conta_id",
            "campanha_id",
            "janela_inicio",
            "janela_fim",
            "horizonte_dias",
            "versao_modelo",
            "cenario",
        ):
            _exigir(
                getattr(self, campo) == getattr(self.janela, campo),
                f"janela e backtest divergem em {campo}",
            )
        _exigir(
            self.janela.procedencia.dataset_kind == self.dataset_kind,
            "janela e backtest divergem em dataset_kind",
        )
        _exigir(
            self.janela.procedencia.hash_fonte == self.procedencia.hash_fonte,
            "janela e backtest divergem em fonte",
        )
        _exigir(self.janela.n_pares == self.n_total, "janela.n_pares infla/contradiz n_total")
        _exigir(
            set(self.metricas_por_alvo)
            == set(self.naive_por_alvo)
            == set(self.pair_ids_por_alvo),
            "alvos de métricas/baseline/população desalinhados",
        )
        tamanhos: list[int] = []
        for alvo, metricas in self.metricas_por_alvo.items():
            ids = tuple(self.pair_ids_por_alvo.get(alvo, ()))
            _exigir(metricas.pair_ids == ids, f"métricas {alvo} fora da população declarada")
            _exigir(metricas.n == len(ids), f"n de {alvo} não corresponde à população")
            naive = self.naive_por_alvo.get(alvo)
            _exigir(naive is not None and naive.pair_ids == ids, f"baseline {alvo} não está pareado")
            _exigir(
                metricas.dataset_kind == naive.dataset_kind == self.dataset_kind,
                f"dataset_kind de {alvo} desalinhado",
            )
            _exigir(
                metricas.entra_em_contagens_reais
                == naive.entra_em_contagens_reais
                == self.entra_em_contagens_reais,
                f"flag real de {alvo} desalinhada",
            )
            tamanhos.append(len(ids))
        esperado_n = min(tamanhos) if tamanhos else 0
        _exigir(self.n_total == esperado_n, "n_total deve ser população mínima por alvo, não soma")
        if self.dataset_kind == DATASET_SINTETICO:
            _exigir(self.entra_em_contagens_reais is False, "sintético não afirma performance real")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        dados["janela"] = self.janela.serializar()
        dados["metricas_por_alvo"] = {k: v.serializar() for k, v in self.metricas_por_alvo.items()}
        dados["naive_por_alvo"] = {k: v.serializar() for k, v in self.naive_por_alvo.items()}
        dados["falhas_parciais"] = [dict(f) for f in self.falhas_parciais]
        dados["pair_ids_por_alvo"] = {k: list(v) for k, v in self.pair_ids_por_alvo.items()}
        return dados


@dataclass(frozen=True)
class DriftSignal:
    signal_id: str
    campanha_id: Optional[str]
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    tipo: str
    feature: Optional[str]
    mag: Optional[float]
    evidencia_suficiente: bool
    acao: str
    conta_id: Optional[str] = None
    notas: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.campanha_id is not None:
            _exigir(bool(self.conta_id), "drift de campanha sem conta_id")
        _exigir(self.acao in ("nenhuma", "suspender_influencia", "usar_baseline", "indisponivel"), "ação de drift inválida")
        _exigir(self.acao != "imputar_zero", "drift não imputa zero")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        return dados


@dataclass(frozen=True)
class ChampionChallengerDecision:
    decision_id: str
    campanha_id: Optional[str]
    observado_em: str
    janela_inicio: str
    janela_fim: str
    horizonte_dias: int
    versao_modelo: str
    hash_inputs: str
    procedencia: SourceReceipt
    estado_semantico: EstadoSemantico
    chave_idempotencia: str
    champion_id: Optional[str]
    challenger_id: str
    veredito: str
    promocao: str
    explicacao: Tuple[str, ...]
    metricas_consideradas: Tuple[str, ...]
    n_pares: int
    janela_completa: bool
    previous_champion_id: Optional[str] = None
    conta_id: Optional[str] = None
    politica_id: str = "orakul-cc-policy/v1"
    mutacao_campanha: bool = False
    population_hash: str = ""
    pair_ids_hash: str = ""
    cenario: str = CENARIO_OBSERVADO

    def __post_init__(self) -> None:
        _exigir(self.promocao in ("proposta", "preservar", "rollback_proposto"), "promoção automática proibida")
        _exigir(self.mutacao_campanha is False, "CC não muta campanha")
        _exigir(bool(self.conta_id and self.campanha_id), "decisão CC sem conta/campanha")
        _exigir(bool(self.population_hash and self.pair_ids_hash), "decisão CC sem população pareada")
        _exigir(self.cenario == CENARIO_OBSERVADO, "CC só compara actual observado")
        _exigir(self.veredito in (
            "propor_promocao",
            "preservar_champion",
            "evidencia_insuficiente",
            "empate",
            "regressao_critica",
            "propor_rollback",
            "champion_inicial_proposto",
        ), "veredito inválido")
        if self.veredito == "propor_promocao":
            _exigir(self.promocao == "proposta", "promoção é proposta, nunca ação")
            _exigir(len(self.metricas_consideradas) >= 2, "uma métrica só não promove")

    def serializar(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["procedencia"] = self.procedencia.serializar()
        dados["estado_semantico"] = self.estado_semantico.value
        return dados


def recibo_sintetico(tag: str, extraido_em: str) -> SourceReceipt:
    return SourceReceipt(
        recibo_id=f"recibo:{tag}",
        origem="fixture_sintetica",
        dataset_kind="sintetico",
        entra_em_contagens_reais=False,
        extraido_em=extraido_em,
        hash_fonte=hash_canonico({"tag": tag, "extraido_em": extraido_em}),
        notas=("SYNTHETIC_FIXTURE", "nao_afirmar_performance_real"),
    )
