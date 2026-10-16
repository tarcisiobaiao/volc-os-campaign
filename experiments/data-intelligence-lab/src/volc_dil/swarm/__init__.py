"""Swarm Lab do VOLC Data Intelligence Lab (worker E, Fase 5).

Bancada de SIMULAÇÃO com seed para tentar refutar políticas de alocação de
orçamento entre "células" sintéticas (canal × ângulo × objetivo × device são só
rótulos): equal budget, random, greedy conservador, Successive Halving, ASHA,
Thompson sampling (extensão) e um oráculo que conhece o valor verdadeiro (só para
calcular regret).

Regras do módulo:
- toda célula/braço é SINTÉTICA; não existe caminho de código para mutação real,
  rede, Google Ads, Supabase ou segredo;
- resultado aqui é no máximo "demonstrado em simulação", nunca "validado";
- fronteira de dinheiro: alocação, gasto e receita observada são ``int`` em micros
  (BRL sintético, sem câmbio). Valor ESPERADO (float64) existe só como métrica
  interna de simulação (regret, oráculo) e nunca é registro de alocação.
"""

from volc_dil.swarm.cenario import (
    MICROS,
    CenarioRealizado,
    ParametrosCenario,
    gerar_cenario,
)
from volc_dil.swarm.simulador import (
    Observacao,
    ResultadoExecucao,
    ViolacaoOrcamento,
    inteirizar,
    simular,
)
from volc_dil.swarm.politicas import (
    ASHA,
    EqualBudget,
    GreedyConservador,
    Oraculo,
    SuccessiveHalving,
    ThompsonTopN,
)

VERSAO_SWARM = "0.1.0"

__all__ = [
    "ASHA", "CenarioRealizado", "EqualBudget", "GreedyConservador", "MICROS", "Observacao",
    "Oraculo", "ParametrosCenario", "ResultadoExecucao", "SuccessiveHalving", "ThompsonTopN",
    "VERSAO_SWARM", "ViolacaoOrcamento", "gerar_cenario", "inteirizar", "simular",
]
