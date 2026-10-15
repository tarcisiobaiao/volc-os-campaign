# Relatório de execução -- gas-do-povo-como-funciona-20261008-dossie-v6

Total de páginas no plano: 5

| Página | Tipo | Slug | Palavras | Status | Modelo |
|---|---|---|---|---|---|
| 1 | LANDING PAGE | gas-do-povo-como-funciona | 0 | SKIPPED |  |
| 2 | HUB | gas-do-povo-quem-tem-direito-consulta-pr | 0 | SKIPPED |  |
| 3 | SOLUTION | como-validar-retirada-gas-do-povo-cpf-p1 | 0 | SKIPPED |  |
| 4 | SOLUTION | onde-retirar-botijao-revendedoras-credenciadas-p2 | 0 | SKIPPED |  |
| 5 | SOLUTION | atualizacao-cadunico-desbloqueio-gas-do-povo-p3 | 0 | SKIPPED |  |

## Detalhe dos passos
- `revisao_esqueleto`: OK (tentativas=0, modelo=n/a)
  - [bloco_sem_entrega_correspondente] [visao_geral] plano_visual[1] (H2: Principais etapas para ter acesso ao botijão de 13kg): 'passo_a_passo' não corresponde a nenhuma entrega declarada (comparacao, decisao_pratica, resposta_direta).
  - [bloco_sem_entrega_correspondente] [locais_retirada] plano_visual[1] (H2: Como proceder se o estabelecimento recusar o atendimento ou alegar falta de cota): 'proximos_passos' não corresponde a nenhuma entrega declarada (checklist, comparacao, resposta_direta).
  - [checkpoint_sem_conclusao] o checkpoint 'elegibilidade_consulta' não declara condição terminal nem saída oficial boa.
  - [coorte_fria_sem_resposta_direta] [coorte:discover] tráfego frio com profundidade guiada: quem chega sem tarefa decide em um ou dois olhares.
- `engajamento`: OK (tentativas=1, modelo=gemini-3.5-flash)

## Custos e telemetria (COGS)
- Custo total (USD): 0.025752
- Teto por run/página (USD): 12.00 / 2.50
- Gasto debitado do teto (USD): 0.025752
- Tokens prompt/completion: 1250/2653
- Páginas alcançáveis no grafo: 5
- Páginas por sessão: não medidas (nenhum evento de sessão neste relatório).

### Custo por página

| Página | Slug | Custo USD | % do run | Tokens | Situação |
|---|---|---|---|---|---|

### Custo por tipo de passo

| Tipo | Chamadas | Custo USD | % do run |
|---|---|---|---|
| engajamento | 1 | 0.025752 | 100.0% |
| revisao_esqueleto | 1 | 0.000000 | 0.0% |

### Desperdício e custo por página útil

- Gasto em páginas REPROVADAS: US$ 0.000000 (0.0% do run) — nenhuma
- Custo médio por página que sobreviveu: US$ 0.000000

### Verificação de URL (ao vivo)

- URLs visitadas: 0 · visitas evitadas pelo cache: 0
- Verificadas OK: 0 · recusadas: 0 · inconclusivas (bloqueio/timeout): 0

| Passo | Prompt tok | Completion tok | Custo USD | Latência ms |
|---|---|---|---|---|
| revisao_esqueleto | 0 | 0 | 0.000000 | 0 |
| engajamento | 1250 | 2653 | 0.025752 | 18954 |

## Jornada do leitor

- Revisão do esqueleto (antes do gasto): aprovada, 4 aviso(s).
- Revisão global do funil pronto: não rodou — 0 achado(s) material(is), 0 aviso(s). Nenhum texto alterado.
- Saídas oficiais: visao_geral=nao_aplicavel, elegibilidade_consulta=nao_aplicavel, validacao_retirada=nao_aplicavel, locais_retirada=nao_aplicavel, atualizacao_cadunico=boa
- Contrato de medição: medicao.json (29 sinais previstos, 0 observação(ões) real(is)). Proposta de nova versão exige aprovação humana; nada é publicado ou reescrito por código.
