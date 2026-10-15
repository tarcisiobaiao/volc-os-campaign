# Relatório de execução -- programa-gas-do-povo-como-funciona-20261008-dossie-v5

Total de páginas no plano: 5

| Página | Tipo | Slug | Palavras | Status | Modelo |
|---|---|---|---|---|---|
| 1 | LANDING PAGE | programa-gas-do-povo-como-funciona | 0 | SKIPPED |  |
| 2 | HUB | gas-do-povo-quem-tem-direito-consulta-pr | 0 | SKIPPED |  |
| 3 | SOLUTION | gas-do-povo-onde-retirar-revendedoras-p1 | 0 | SKIPPED |  |
| 4 | SOLUTION | gas-do-povo-validacao-cpf-sms-retirada-p2 | 0 | SKIPPED |  |
| 5 | SOLUTION | gas-do-povo-bloqueio-cadunico-atualizacao-p3 | 0 | SKIPPED |  |

## Detalhe dos passos
- `funnel_graph`: FAILED (tentativas=0, modelo=n/a)
  - [loop_sem_ganho] ciclo atualizacao_cadunico → validacao_retirada → atualizacao_cadunico sem ganho de informação: o clique devolve o leitor a uma dúvida que ele já resolveu. Declare `retornos_justificados` ou tire uma das arestas.
- `revisao_esqueleto`: FAILED (tentativas=0, modelo=n/a)
  - [loop_sem_ganho] ciclo atualizacao_cadunico → validacao_retirada → atualizacao_cadunico sem ganho de informação: o clique devolve o leitor a uma dúvida que ele já resolveu. Declare `retornos_justificados` ou tire uma das arestas.
  - [cta_contextual] [elegibilidade_consulta] 'validacao_retirada' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [cta_contextual] [elegibilidade_consulta] 'atualizacao_cadunico' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [cta_contextual] [locais_retirada] 'validacao_retirada' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [cta_contextual] [validacao_retirada] 'atualizacao_cadunico' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [cta_contextual] [validacao_retirada] 'locais_retirada' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [cta_contextual] [atualizacao_cadunico] 'elegibilidade_consulta' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [cta_contextual] [atualizacao_cadunico] 'validacao_retirada' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [retorno_justificado] ciclo atualizacao_cadunico → elegibilidade_consulta → atualizacao_cadunico mantido com justificativa: Permite ao leitor reconfirmar a faixa de renda per capita antes de comparecer ao CRAS..
  - [retorno_justificado] ciclo atualizacao_cadunico → elegibilidade_consulta → validacao_retirada → atualizacao_cadunico mantido com justificativa: Permite ao leitor reconfirmar a faixa de renda per capita antes de comparecer ao CRAS..
  - [retorno_justificado] ciclo locais_retirada → validacao_retirada → locais_retirada mantido com justificativa: Permite ao usuário consultar onde levar o botijão assim que entender como comprovar seus dados..
  - [checkpoint_sem_conclusao] o checkpoint 'elegibilidade_consulta' não declara condição terminal nem saída oficial boa.

## Custos e telemetria (COGS)
- Custo total (USD): 0.000000
- Teto por run/página (USD): 12.00 / 2.50
- Gasto debitado do teto (USD): 0.000000
- Tokens prompt/completion: 0/0
- Páginas alcançáveis no grafo: 5
- Páginas por sessão: não medidas (nenhum evento de sessão neste relatório).

### Custo por página

| Página | Slug | Custo USD | % do run | Tokens | Situação |
|---|---|---|---|---|---|

### Custo por tipo de passo

| Tipo | Chamadas | Custo USD | % do run |
|---|---|---|---|
| funnel_graph | 1 | 0.000000 | 0.0% |
| revisao_esqueleto | 1 | 0.000000 | 0.0% |

### Desperdício e custo por página útil

- Gasto em páginas REPROVADAS: US$ 0.000000 (0.0% do run) — nenhuma
- Custo médio por página que sobreviveu: US$ 0.000000

### Verificação de URL (ao vivo)

- URLs visitadas: 0 · visitas evitadas pelo cache: 0
- Verificadas OK: 0 · recusadas: 0 · inconclusivas (bloqueio/timeout): 0

| Passo | Prompt tok | Completion tok | Custo USD | Latência ms |
|---|---|---|---|---|
| funnel_graph | 0 | 0 | 0.000000 | 0 |
| revisao_esqueleto | 0 | 0 | 0.000000 | 0 |
