"""Contrato canônico de observação append-only, fonte-agnóstico (Fundação DIL, thread A).

Domínio puro (stdlib + `volc_dil.contracts`). Ver
`docs/data-intelligence/fundacao-20261016/02-CONTRATO-DE-DADOS.md`.
Espelho em banco: `experiments/data-intelligence-lab/migrations_candidatas/dil_obs_0001_*.sql`.
"""
from .adaptadores import AdaptacaoImpossivel, adaptar_google_ads_v21, adaptar_joinads_v2
from .asof import AgregadoObservacao, agregar_observacoes, as_of, latest, para_contrato_economico
from .chaves import chave_base, chave_natural, chave_reafirmacao, instante_canonico
from .modelo import CAMPOS_JSON, Coletor, EntidadeRef, Observacao, ObservacaoInvalida
from .normalizador import (
    CampoMetrica,
    ContextoLeitura,
    EsquemaPayload,
    PayloadBruto,
    Rejeicao,
    ResultadoNormalizacao,
    normalizar,
    observacoes_sem_dado,
)
from .registro import ConflitoIdempotencia, Registro, ResultadoRegistro, TipoRegistro, VersaoRegistrada
from .vocab import MAPA_ESTADO_HERDADO, StatusObservacao, Unidade

__all__ = [
    "AdaptacaoImpossivel", "adaptar_google_ads_v21", "adaptar_joinads_v2", "AgregadoObservacao", "CAMPOS_JSON", "CampoMetrica", "Coletor", "ConflitoIdempotencia", "ContextoLeitura",
    "EntidadeRef", "EsquemaPayload", "MAPA_ESTADO_HERDADO", "Observacao", "ObservacaoInvalida", "PayloadBruto",
    "Registro", "Rejeicao", "ResultadoNormalizacao", "ResultadoRegistro", "StatusObservacao", "TipoRegistro",
    "Unidade", "VersaoRegistrada", "agregar_observacoes", "as_of", "chave_base", "chave_natural",
    "chave_reafirmacao", "instante_canonico", "latest", "normalizar", "observacoes_sem_dado",
    "para_contrato_economico",
]
