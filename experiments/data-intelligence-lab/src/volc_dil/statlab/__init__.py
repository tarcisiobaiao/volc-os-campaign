"""Stat Lab do VOLC Data Intelligence Lab (worker D, Fase 4).

Bancada de SIMULAÇÃO com seed para tentar refutar métodos estatísticos antes de
qualquer uso operacional:

- ``maturacao``: nowcasting de coortes com atraso de reporte (fator de maturação
  empírico, guarda de maturidade, intervalos, mudança de regime);
- ``shrinkage``: Empirical Bayes Beta-Binomial / Gamma-Poisson e alternativa
  hurdle para receita monetária zero-inflada;
- ``sequencias_confianca``: confidence sequence anytime-valid para média de
  outcome limitado em [0, 1] (PrPl-EB de Waudby-Smith & Ramdas) vs. Wald com peeking;
- ``fdr``: Benjamini-Hochberg (própria e statsmodels), Bonferroni, peeking.

Nada aqui lê dado real, rede, Supabase ou segredo. Resultados são "demonstrado em
simulação" no máximo — nunca "validado".
"""

from volc_dil.statlab.base import VERSAO_STATLAB, ResultadoInsuficiente

__all__ = ["VERSAO_STATLAB", "ResultadoInsuficiente"]
