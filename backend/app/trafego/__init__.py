"""Hub de Tráfego — a terceira etapa do ciclo PAUTA → FUNIL → CAMPANHA.

O Pautador acha o tema e minera as keywords. O Redator escreve o funil e sobe os
rascunhos. Este módulo **compra o clique** que leva alguém até lá.

## O que ele NÃO é

Não é dashboard de performance, e a decisão é de fato: `metrics.` tem **zero
ocorrências** em todo o `volc_ads/`. Não existe camada de métrica, receita nem
executor de ajuste. Uma tela com ROAS e curva de gasto seria ficção desenhada.

O que existe — e é muito — é uma **mesa de prova**: um engine que monta a
campanha inteira num mutate atômico e a valida contra a conta real antes de
criar nada.

## Search primeiro, e só Search

O `Brief` foi desenhado para servir todos os canais e a taxonomia já nomeia os
quatro (SEARCH, DISPLAY, DEMAND_GEN, PERFORMANCE_MAX). Mas existe **um**
construtor: `campanha/search.py`.

Não há despachante de canal aqui, e isso é deliberado. Um dispatcher com uma
implementação só é generalidade especulativa: ele fixa a forma da abstração
antes de existir o segundo caso que a justificaria, e o segundo caso é sempre o
que revela que a forma estava errada. Quando o construtor de Demand Gen existir,
`preparar()` ganha o parâmetro de canal — a costura é de uma linha, e ela fica
óbvia justamente por não ter sido pré-construída.
"""
