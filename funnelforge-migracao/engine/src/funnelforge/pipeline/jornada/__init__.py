"""A JORNADA DO FUNIL: régua determinística do mapa e do funil pronto.

Quatro limites, um módulo cada:

- `esqueleto`      — antes de qualquer chamada paga (alimenta o `funnel_graph`);
- `contexto`       — o que redator, juiz, briefing e revisor recebem, e a
                     política da saída oficial que o roteador obedece;
- `revisao_global` — o funil pronto, antes da publicação, só páginas aprovadas;
- `medicao`        — o contrato de medição (sem tracking novo).

`_comum` guarda o que os quatro dividem (termos, grafo, saída oficial e o
estado do leitor POR CAMINHO). Nenhum número da apresentação Pubx ou da
simulação MiroFish vira limiar aqui.
"""
from funnelforge.pipeline.jornada._comum import (
    EstadoDoLeitor,
    classificar_saida_oficial,
    cta_do_link,
    estado_do_leitor,
    tem_jornada,
)
from funnelforge.pipeline.jornada.contexto import (
    PoliticaDaSaidaOficial,
    alvo_da_proxima_duvida,
    ativos_validos,
    contexto_de_jornada,
    politica_da_saida_oficial,
)
from funnelforge.pipeline.jornada.esqueleto import RevisaoDoEsqueleto, revisar_esqueleto
from funnelforge.pipeline.jornada.medicao import contrato_de_medicao
from funnelforge.pipeline.jornada.revisao_global import pagina_aprovada, revisar_funil_pronto

__all__ = [
    "EstadoDoLeitor", "PoliticaDaSaidaOficial", "RevisaoDoEsqueleto",
    "alvo_da_proxima_duvida", "ativos_validos", "classificar_saida_oficial", "cta_do_link",
    "contexto_de_jornada", "contrato_de_medicao", "estado_do_leitor",
    "pagina_aprovada", "politica_da_saida_oficial", "revisar_esqueleto",
    "revisar_funil_pronto", "tem_jornada",
]
