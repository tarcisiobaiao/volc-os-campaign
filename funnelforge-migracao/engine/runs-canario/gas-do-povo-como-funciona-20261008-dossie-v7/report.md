# Relatório de execução -- gas-do-povo-como-funciona-20261008-dossie-v7

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
- `engajamento`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
- `research_p1`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 2 fato(s) verificado(s) do dossiê 24e58e41738e
- `dossie_p1`: OK (tentativas=0, modelo=review)
  - [revisao_humana_por_evidencia] requisito da promessa central sem evidência: a página é escrita, mas não publica sem decisão humana
  - [evidencia_unsupported] entrega_visual_1: não há evidência suficiente sobre 'fatos e regras que permitem entregar este bloco sem extrapolar: H2: Como é feita a concessão: botijão físico ou dinheiro na conta? Diferenciar o formato de repasse financeiro do fornecimento direto de recarga do botijão.': omita a afirmação; não diga que o leitor tem direito, não cite número nem prazo
- `research_p2`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 3 fato(s) verificado(s) do dossiê 24e58e41738e
- `dossie_p2`: OK (tentativas=0, modelo=ready)
- `research_p3`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 2 fato(s) verificado(s) do dossiê 24e58e41738e
- `dossie_p3`: OK (tentativas=0, modelo=review)
  - [revisao_humana_por_evidencia] requisito da promessa central sem evidência: a página é escrita, mas não publica sem decisão humana
  - [evidencia_unsupported] entrega_visual_1: não há evidência suficiente sobre 'fatos e regras que permitem entregar este bloco sem extrapolar: H2: Por que você não precisa de voucher pelo Caixa Tem Destacar em alerta que não existe opção de gerar voucher no aplicativo e evitar busca por telas falsas.': omita a afirmação; não diga que o leitor tem direito, não cite número nem prazo
- `research_p4`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 2 fato(s) verificado(s) do dossiê 24e58e41738e
- `dossie_p4`: OK (tentativas=0, modelo=review)
  - [revisao_humana_por_evidencia] requisito da promessa central sem evidência: a página é escrita, mas não publica sem decisão humana
  - [evidencia_unsupported] entrega_visual_1: não há evidência suficiente sobre 'fatos e regras que permitem entregar este bloco sem extrapolar: H2: A revendedora pode cobrar taxa de entrega? O que diz a regra Contrastar retirada no balcão (custo zero obrigatório) com entrega a domicílio (serviço opcional cobrável).': omita a afirmação; não diga que o leitor tem direito, não cite número nem prazo
- `research_p5`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 2 fato(s) verificado(s) do dossiê 24e58e41738e
- `dossie_p5`: OK (tentativas=0, modelo=review)
  - [revisao_humana_por_evidencia] requisito da promessa central sem evidência: a página é escrita, mas não publica sem decisão humana
  - [evidencia_unavailable] entrega_visual_2: a fonte de 'fatos e regras que permitem entregar este bloco sem extrapolar: H2: Prazos e ciclos de atualização do sistema para liberação do benefício Explicar a linha do tempo entre entrevista no CRAS, processamento Dataprev e disponibilidade do botijão no depósito.' está indisponível agora (não quer dizer que é falso): não afirme valor, prazo nem precisão sobre isso; explique só o que está comprovado e diga onde o leitor confere na fonte oficial
- `dossie`: OK (tentativas=2, modelo=gpt-6.1-sol)
  - [dossie_portao] 5 página(s) liberada(s), 0 bloqueada(s); 14 fato(s), 1 rodada(s), 6 consulta(s) de busca do grounding; auth_mode chatgpt_plan: custo NÃO informado pelo servidor (quota do plano); sha256 24e58e41738e

## Custos e telemetria (COGS)
- Custo total (USD): 0.000000
- Teto por run/página (USD): 12.00 / 2.50
- Gasto debitado do teto (USD): 0.000000
- Tokens prompt/completion: 38903/4349
- Páginas alcançáveis no grafo: 5
- Páginas por sessão: não medidas (nenhum evento de sessão neste relatório).
- Passos no plano ChatGPT (uso do plano, sem custo de API): 2 — o custo em USD acima é só o faturado por API.

### Custo por página

| Página | Slug | Custo USD | % do run | Tokens | Situação |
|---|---|---|---|---|---|
| p1 | gas-do-povo-como-funciona | 0.000000 | 0.0% | 0 | gerada (sem publish) |
| p2 | gas-do-povo-quem-tem-direito-consulta-pr | 0.000000 | 0.0% | 0 | gerada (sem publish) |
| p3 | como-validar-retirada-gas-do-povo-cpf-p1 | 0.000000 | 0.0% | 0 | gerada (sem publish) |
| p4 | onde-retirar-botijao-revendedoras-credenciadas-p2 | 0.000000 | 0.0% | 0 | gerada (sem publish) |
| p5 | atualizacao-cadunico-desbloqueio-gas-do-povo-p3 | 0.000000 | 0.0% | 0 | gerada (sem publish) |

### Custo por tipo de passo

| Tipo | Chamadas | Custo USD | % do run |
|---|---|---|---|
| revisao_esqueleto | 1 | 0.000000 | 0.0% |
| engajamento | 1 | 0.000000 | 0.0% |
| research | 5 | 0.000000 | 0.0% |
| dossie | 6 | 0.000000 | 0.0% |

### Desperdício e custo por página útil

- Gasto em páginas REPROVADAS: US$ 0.000000 (0.0% do run) — nenhuma
- Custo médio por página que sobreviveu: US$ 0.000000

### Verificação de URL (ao vivo)

- URLs visitadas: 3 · visitas evitadas pelo cache: 4
- Verificadas OK: 3 · recusadas: 0 · inconclusivas (bloqueio/timeout): 0

| Passo | Prompt tok | Completion tok | Custo USD | Latência ms |
|---|---|---|---|---|
| revisao_esqueleto | 0 | 0 | 0.000000 | 0 |
| engajamento | 1179 | 325 | 0.000000 | 10595 |
| research_p1 | 0 | 0 | 0.000000 | 0 |
| dossie_p1 | 0 | 0 | 0.000000 | 0 |
| research_p2 | 0 | 0 | 0.000000 | 0 |
| dossie_p2 | 0 | 0 | 0.000000 | 0 |
| research_p3 | 0 | 0 | 0.000000 | 0 |
| dossie_p3 | 0 | 0 | 0.000000 | 0 |
| research_p4 | 0 | 0 | 0.000000 | 0 |
| dossie_p4 | 0 | 0 | 0.000000 | 0 |
| research_p5 | 0 | 0 | 0.000000 | 0 |
| dossie_p5 | 0 | 0 | 0.000000 | 0 |
| dossie | 37724 | 4024 | 0.000000 | 112816 |

## Jornada do leitor

- Revisão do esqueleto (antes do gasto): aprovada, 4 aviso(s).
- Revisão global do funil pronto: não rodou — 0 achado(s) material(is), 0 aviso(s). Nenhum texto alterado.
- Saídas oficiais: visao_geral=nao_aplicavel, elegibilidade_consulta=nao_aplicavel, validacao_retirada=nao_aplicavel, locais_retirada=nao_aplicavel, atualizacao_cadunico=boa
- Contrato de medição: medicao.json (29 sinais previstos, 0 observação(ões) real(is)). Proposta de nova versão exige aprovação humana; nada é publicado ou reescrito por código.
