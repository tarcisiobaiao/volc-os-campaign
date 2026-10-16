"""Observabilidade e Data Quality da Fundação DIL (thread G).

Puro: nenhuma checagem faz I/O, rede ou envio. Entradas = protocolo mínimo (`ObservacaoDQ`,
`RunDQ`, `CoberturaSensorDia`) ou linhas exportadas das tabelas reais (adaptadores), ou o contrato
de A via `ponte_observacao`. Saída = `Achado` tipado (regra, severidade, fonte, grão, janela,
evidência). Views SQL equivalentes: `migrations_candidatas/views_qualidade/`.
Doc: `docs/data-intelligence/fundacao-20261016/09-OBSERVABILIDADE.md`.
"""
from .agenda import LIMIARES_PADRAO, SLA, SLA_PADRAO, horas_de_cron
from .alertas import POLITICAS_PADRAO, Alerta, PoliticaAlerta, decidir_alertas, despachar
from .deriva import checar_deriva, detectar_deriva, medir_falso_alarme, medir_poder
from .integridade import (
    avaliar_cobertura_atribuicao,
    campos_de_payload,
    checar_cobertura_atribuicao,
    checar_deriva_esquema,
    checar_substituicao_fonte,
)
from .leituras import (
    CelulaEsperada,
    checar_completude_grade,
    checar_duplicacao,
    checar_zero_sintetizado,
    classificar_celula,
    classificar_duplicacao,
    classificar_zero,
    medir_zero_sintetizado,
)
from .modelo import Achado, CoberturaSensorDia, ObservacaoDQ, RunDQ, Severidade, StatusDado, StatusRun
from .motor import ConjuntoSaude, avaliar_saude, view_da_regra
from .ponte_observacao import checar_dead_letter, checar_latencia_ingestao, de_observacoes, runs_de_run_coleta
from .reconciliacao import (
    LinhaReceitaDia,
    agregar_receita_joinads,
    avaliar_reconciliacao_custo,
    avaliar_reconciliacao_receita,
    checar_reconciliacao_custo,
    checar_reconciliacao_receita,
    joinads_latest,
)
from .runs import (
    avaliar_completude_slots,
    avaliar_frescor,
    avaliar_runs_orfaos,
    checar_completude_slots,
    checar_falha_silenciosa,
    checar_frescor,
    checar_runs_orfaos,
)

__all__ = [
    "Achado", "Alerta", "CelulaEsperada", "CoberturaSensorDia", "ConjuntoSaude", "LIMIARES_PADRAO",
    "LinhaReceitaDia", "ObservacaoDQ", "POLITICAS_PADRAO", "PoliticaAlerta", "RunDQ", "SLA", "SLA_PADRAO",
    "Severidade", "StatusDado", "StatusRun", "agregar_receita_joinads", "avaliar_cobertura_atribuicao",
    "avaliar_completude_slots", "avaliar_frescor", "avaliar_reconciliacao_custo", "avaliar_reconciliacao_receita",
    "avaliar_runs_orfaos", "avaliar_saude", "campos_de_payload", "checar_cobertura_atribuicao",
    "checar_completude_grade", "checar_completude_slots", "checar_dead_letter", "checar_deriva",
    "checar_deriva_esquema", "checar_duplicacao", "checar_falha_silenciosa", "checar_frescor",
    "checar_latencia_ingestao", "checar_reconciliacao_custo", "checar_reconciliacao_receita",
    "checar_runs_orfaos", "checar_substituicao_fonte", "checar_zero_sintetizado", "classificar_celula",
    "classificar_duplicacao", "classificar_zero", "de_observacoes", "decidir_alertas", "despachar",
    "detectar_deriva", "horas_de_cron", "joinads_latest", "medir_falso_alarme", "medir_poder",
    "medir_zero_sintetizado", "runs_de_run_coleta", "view_da_regra",
]
