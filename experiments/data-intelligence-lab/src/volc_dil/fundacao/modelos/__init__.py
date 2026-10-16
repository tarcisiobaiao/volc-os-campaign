"""Model Lab da Fundação Data Intelligence (worker F, missão 2026-10-16).

Funções PURAS e documentadas, para o shadow (worker D) chamar sobre snapshots ``as_of``. Nada aqui
lê rede, banco, segredo ou produção; tudo foi exercitado só em simulação (teto de estado:
"testado com sintético"). Documento: ``docs/data-intelligence/fundacao-20261016/08-MODEL-LAB.md``.

Reuso do herdado (sem duplicar): ``volc_dil.statlab`` (maturação chain-ladder e guarda, EB, CS, BH),
``volc_dil.replay.politicas`` (regra proporcional e repartição exata), ``volc_dil.fundacao.simulador``
(registros, ``visao_as_of``, mundo com verdade só para avaliação).

API principal::

    from volc_dil.fundacao.modelos import (
        TabelaVersoes,                               # painéis as_of vetorizados (= visao_as_of)
        triangulo_de_tabela, nowcast, maturar, monitor_maturacao, curva_intradiaria,   # maturação
        encolher_taxa, encolher_media, vencedores_por_sorte,                           # EB
        detectar_quebra, calibrar_limiar,                                              # mudança
        eprocesso_media_limitada, e_bh,                                                # sequencial/FDR
        did_painel, tendencias_paralelas, placebo_temporal, controle_sintetico,         # causal
        rodar, ips, snips, dr, PropensaoAusente,                                       # bandits/OPE
        intervalo_conformal, aci,                                                      # conformal
        detectar_anomalias, zero_implausivel,                                          # anomalia
        ajustar_resposta, alocar_orcamento, limites, verificar_restricoes,              # alocação
        checar_vazamento, features_no_corte,                                           # tabular
        Achado,
    )
"""
from .alocacao import (
    CurvaResposta,
    ajustar_resposta,
    alocar_guloso,
    alocar_igual,
    alocar_orcamento,
    alocar_proporcional,
    limites,
    lucro_esperado,
    para_micros,
    projetar,
    verificar_restricoes,
)
from .anomalia import detectar_anomalias, escores, nulo_como_zero, precisao_recall, zero_implausivel
from .bandits import (
    POLITICAS,
    Gulosa,
    LinUCB,
    Log,
    PropensaoAusente,
    ThompsonLinear,
    Uniforme,
    dr,
    ips,
    medias_por_contexto,
    pseudo_regret,
    q_tabular_cruzado,
    rodar,
    snips,
    valor_verdadeiro,
)
from .base import VERSAO_MODELOS, Achado, ResultadoInsuficiente, ic_bootstrap_media
from .causal import (
    controle_sintetico,
    controle_sintetico_placebo,
    did_painel,
    placebo_temporal,
    placebo_unidades,
    tendencias_paralelas,
)
from .conformal import aci, cobertura, escores_escalados, intervalo_conformal, quantil_conformal
from .dados import TabelaVersoes, dias_iso, epoch, ids_campanhas, instante_local
from .eb import encolher_media, encolher_taxa, vencedores_por_sorte
from .maturacao import (
    ConfigMonitor,
    ConfigNowcast,
    curva_intradiaria,
    fator_congelado,
    maturar,
    monitor_maturacao,
    nowcast,
    nowcast_intradiario,
    regime_vigente,
    paineis_diarios,
    paineis_intradiarios,
    triangulo_de_tabela,
)
from .mudanca import bocpd, bocpd_posterior, calibrar_limiar, cusum, detectar_quebra, media_movel
from .sequencial import ForaDoSuporte, bh, cs_prpl_eb, e_bh, eprocesso_media_limitada, normalizar_por_limite, p_binomial_unilateral
from .tabular import FeatureMeta, ModeloAjustado, ajustar, ajustar_e_prever, checar_vazamento, features_no_corte, vazamento_empirico

__all__ = [
    "Achado", "bh", "cs_prpl_eb", "ConfigMonitor", "ConfigNowcast", "CurvaResposta", "FeatureMeta", "ForaDoSuporte", "Gulosa", "LinUCB",
    "Log", "POLITICAS", "PropensaoAusente", "ResultadoInsuficiente", "TabelaVersoes", "ThompsonLinear", "Uniforme",
    "VERSAO_MODELOS", "aci", "ModeloAjustado", "ajustar", "ajustar_e_prever", "ajustar_resposta", "alocar_guloso", "alocar_igual", "alocar_orcamento",
    "alocar_proporcional", "bocpd", "bocpd_posterior", "calibrar_limiar", "checar_vazamento", "cobertura", "controle_sintetico",
    "controle_sintetico_placebo", "curva_intradiaria", "cusum", "detectar_anomalias", "detectar_quebra", "dias_iso",
    "did_painel", "dr", "e_bh", "encolher_media", "encolher_taxa", "eprocesso_media_limitada", "epoch", "escores",
    "escores_escalados", "fator_congelado", "features_no_corte", "ic_bootstrap_media", "ids_campanhas",
    "instante_local", "intervalo_conformal", "ips", "limites", "lucro_esperado", "maturar", "media_movel",
    "medias_por_contexto", "monitor_maturacao", "normalizar_por_limite", "nowcast", "nowcast_intradiario",
    "nulo_como_zero", "p_binomial_unilateral", "paineis_diarios", "paineis_intradiarios", "para_micros",
    "placebo_temporal", "placebo_unidades", "precisao_recall", "projetar", "pseudo_regret", "q_tabular_cruzado", "regime_vigente",
    "quantil_conformal", "rodar", "snips", "tendencias_paralelas", "triangulo_de_tabela", "valor_verdadeiro",
    "vazamento_empirico", "vencedores_por_sorte", "verificar_restricoes", "zero_implausivel",
]
