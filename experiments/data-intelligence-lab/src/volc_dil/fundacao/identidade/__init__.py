"""`volc_dil.fundacao.identidade` — identidade e atribuição honesta (thread C, 2026-10-16).

Puro (stdlib + `volc_dil.contracts`), sem rede. Ver
`docs/data-intelligence/fundacao-20261016/03-MATRIZ-DE-ATRIBUICAO.md`.
"""
from .chave_campanha import (
    ChaveCampanha,
    MotivoRecusa,
    OrigemValor,
    interpretar_campanha_da_sessao,
    interpretar_chave_campanha,
    sobrevive_ao_sensor,
)
from .colisao import (
    Colisao,
    Gravidade,
    TipoColisao,
    colisoes_de_normalizacao,
    detectar_colisoes_registro,
    detectar_custom_key_substituida,
)
from .graos import (
    MATRIZ,
    Capacidade,
    Confianca,
    Fonte,
    Grao,
    GraoNaoSuportado,
    GraoTempo,
    capacidade,
    exigir_grao,
    receita_por_sessao,
    suportados_hoje,
)
from .juncao import (
    GRAOS_RECEITA_CAMPANHA,
    Cobertura,
    ContratoDeEntrada,
    FuturoNaJuncao,
    GraoMistoNaReceita,
    LinhaDuplicada,
    CustoCampanhaDia,
    EventoSensorReady,
    LinhaCampanhaDia,
    Medida,
    ReceitaChaveDia,
    ReceitaDominioDia,
    ResultadoJuncao,
    SessaoResolvida,
    juntar_campanha_dia,
    para_json,
    sessoes_de_eventos,
)
from .normalizacao import (
    LIMITE_CHECAGEM_PII,
    LIMITE_VALOR_UTM,
    MotivoDescarte,
    UtmSessao,
    chave_sem_corte_sensor_v3,
    diagnosticar_utm_sensor_v3,
    limpar_utm_ingest,
    normalizar_utm_sensor_v3,
    normalizar_valor_wrapper_v2,
    parse_query_urlsearchparams,
    utm_da_pagina_sensor_v3,
)
from .resolvedor import (
    CampanhaRegistrada,
    RegistroCampanhas,
    Resolucao,
    TemplateCampanha,
    normalizar_host,
    registro_de,
)

__all__ = [
    "ContratoDeEntrada", "FuturoNaJuncao", "GRAOS_RECEITA_CAMPANHA", "GraoMistoNaReceita", "LinhaDuplicada",
    "normalizar_host",
    "CampanhaRegistrada", "Capacidade", "ChaveCampanha", "Cobertura", "Colisao", "Confianca",
    "CustoCampanhaDia", "EventoSensorReady", "Fonte", "Grao", "GraoNaoSuportado", "GraoTempo",
    "Gravidade", "LIMITE_CHECAGEM_PII", "LIMITE_VALOR_UTM", "LinhaCampanhaDia", "MATRIZ", "Medida",
    "MotivoDescarte", "MotivoRecusa", "OrigemValor", "ReceitaChaveDia", "ReceitaDominioDia",
    "RegistroCampanhas", "Resolucao", "ResultadoJuncao", "SessaoResolvida", "TemplateCampanha",
    "TipoColisao", "UtmSessao", "capacidade", "chave_sem_corte_sensor_v3", "colisoes_de_normalizacao",
    "detectar_colisoes_registro", "detectar_custom_key_substituida", "diagnosticar_utm_sensor_v3",
    "exigir_grao", "interpretar_campanha_da_sessao", "interpretar_chave_campanha", "juntar_campanha_dia",
    "limpar_utm_ingest", "normalizar_utm_sensor_v3", "normalizar_valor_wrapper_v2",
    "para_json", "parse_query_urlsearchparams", "receita_por_sessao", "registro_de",
    "sessoes_de_eventos", "sobrevive_ao_sensor", "suportados_hoje", "utm_da_pagina_sensor_v3",
]
