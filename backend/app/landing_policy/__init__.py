"""Política do DESTINO — o contrato que separa página editorial de destino pago.

Ponto de entrada único do pacote. Quem integra o portão importa daqui; a divisão
interna (`contrato`/`varredura`/`portao`/`recibo`) é detalhe deste pacote.

    from app.landing_policy import (
        PaginaObservada, PapelDestino, PontoDePortao, avaliar, emitir_recibo,
    )
"""
from app.landing_policy.contrato import (
    CARIMBO_DETERMINISTICO,
    SCHEMA_VERSION,
    Achado,
    PapelDestino,
    PontoDePortao,
    Veredito,
    Verificacao,
    carregar_fontes,
    codigos_conhecidos,
    fonte_do_codigo,
    impressao,
    severidade,
    versao_da_fonte,
)
from app.landing_policy.portao import (
    Avaliacao,
    avaliar,
    elegibilidade_de_destino_de_campanha,
    sem_fonte_oficial,
)
from app.landing_policy.recibo import (
    emitir as emitir_recibo,
    impressao_do_recibo,
    json_deterministico,
)
from app.landing_policy.varredura import PaginaObservada, texto_visivel

__all__ = [
    "Achado",
    "Avaliacao",
    "CARIMBO_DETERMINISTICO",
    "PaginaObservada",
    "PapelDestino",
    "PontoDePortao",
    "SCHEMA_VERSION",
    "Veredito",
    "Verificacao",
    "avaliar",
    "carregar_fontes",
    "codigos_conhecidos",
    "elegibilidade_de_destino_de_campanha",
    "emitir_recibo",
    "fonte_do_codigo",
    "impressao",
    "impressao_do_recibo",
    "json_deterministico",
    "sem_fonte_oficial",
    "severidade",
    "texto_visivel",
    "versao_da_fonte",
]
