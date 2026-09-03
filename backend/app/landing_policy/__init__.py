"""Política do DESTINO — o contrato que separa página editorial de destino pago.

Ponto de entrada único do pacote. Quem integra o portão importa daqui; a divisão
interna (`contrato`/`varredura`/`portao`/`recibo`) é detalhe deste pacote.

    from app.landing_policy import (
        PaginaObservada, PapelDestino, PontoDePortao, avaliar, emitir_recibo,
    )
"""
from app.landing_policy.contrato import (
    CARIMBO_DETERMINISTICO,
    JANELA_DE_FRESCOR_PADRAO_S,
    POLICY_CONTRACT_VERSION,
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
from app.landing_policy.plano import (
    PlanoDaPagina,
    avaliar_plano,
    documento_do_plano,
    pagina_do_plano,
)
from app.landing_policy.registro import (
    CHAVE_DO_RECIBO,
    anexar_recibo,
    gravar_recibo_local,
    nome_do_recibo,
    recibo_da_url,
    url_canonica,
)
from app.landing_policy.portao import (
    Avaliacao,
    PapelRelaxadoPeloCliente,
    avaliar,
    elegibilidade_de_destino_de_campanha,
    papel_do_servidor,
    sem_fonte_oficial,
)
from app.landing_policy.recibo import (
    emitir as emitir_recibo,
    impressao_do_recibo,
    json_deterministico,
)
from app.landing_policy.varredura import (
    PaginaObservada,
    impressao_canonica,
    texto_visivel,
)

__all__ = [
    "Achado",
    "Avaliacao",
    "CHAVE_DO_RECIBO",
    "PapelRelaxadoPeloCliente",
    "PlanoDaPagina",
    "CARIMBO_DETERMINISTICO",
    "JANELA_DE_FRESCOR_PADRAO_S",
    "POLICY_CONTRACT_VERSION",
    "PaginaObservada",
    "PapelDestino",
    "PontoDePortao",
    "SCHEMA_VERSION",
    "Veredito",
    "Verificacao",
    "anexar_recibo",
    "avaliar",
    "avaliar_plano",
    "carregar_fontes",
    "codigos_conhecidos",
    "elegibilidade_de_destino_de_campanha",
    "documento_do_plano",
    "emitir_recibo",
    "fonte_do_codigo",
    "gravar_recibo_local",
    "nome_do_recibo",
    "impressao",
    "impressao_canonica",
    "impressao_do_recibo",
    "json_deterministico",
    "pagina_do_plano",
    "papel_do_servidor",
    "recibo_da_url",
    "sem_fonte_oficial",
    "severidade",
    "texto_visivel",
    "url_canonica",
    "versao_da_fonte",
]
