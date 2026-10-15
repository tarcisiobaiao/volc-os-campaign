# Relatório de execução -- tarifa-social-energia-eletrica-20261010-canario-copy

Total de páginas no plano: 7

| Página | Tipo | Slug | Palavras | Status | Modelo |
|---|---|---|---|---|---|
| 1 | LANDING PAGE | tarifa-social-energia-eletrica | 723 | OK | chatgpt/gpt-6-sol |
| 2 | HUB | quem-tem-direito-tarifa-social-pr | 893 | OK | chatgpt/gpt-6-sol |
| 3 | SOLUTION | como-obter-tarifa-social-p1 | 743 | OK | chatgpt/gpt-6-sol |
| 4 | SOLUTION | tarifa-social-por-distribuidora-p2 | 744 | OK | chatgpt/gpt-6-sol |
| 5 | SOLUTION | como-saber-se-tarifa-social-esta-na-conta-p3 | 477 | OK | chatgpt/gpt-6-sol |
| 6 | SOLUTION | quanto-paga-tarifa-social-p4 | 1133 | OK | chatgpt/gpt-6-sol |
| 7 | SOLUTION | desconto-social-conta-de-luz-p5 | 599 | OK | chatgpt/gpt-6-sol |

## Detalhe dos passos
- `inteligencia`: OK (tentativas=0, modelo=n/a)
  - [paa] {"perguntas": ["Quem tem 60 anos tem desconto na conta de luz?", "Quem tem direito à tarifa social de energia elétrica em 2026?", "Como saber se minha energia está cadastrada no baixa renda?", "Quanto paga de luz na tarifa social?"], "cabeca": "Quem tem 60 anos tem desconto na conta de luz?", "recibo": {"paa_disponivel": true, "paa_perguntas": ["Quem tem 60 anos tem desconto na conta de luz?", "Quem tem direito à tarifa social de energia elétrica em 2026?", "Como saber se minha energia está cadastrada no baixa renda?", "Quanto paga de luz na tarifa social?"], "regra_editorial": "primeira pergunta do PAA — nenhuma delas tem volume medido", "volume_editorial": 0}, "origem": "cache_serp_recente", "erro": ""}
  - [pesquisa_pelo_esqueleto_aprovado] sem pesquisa antecipada: a primeira pesquisa é a do dossiê, pelos requisitos das páginas aprovadas
- `extract`: OK (tentativas=0, modelo=n/a)
  - [arquitetura_aprovada_preservada] 7 páginas do plano aprovado; sem chamada ao arquiteto
- `revisao_esqueleto`: OK (tentativas=0, modelo=n/a)
  - [cta_sem_correspondencia_no_destino] [como_obter] 'Confira como a Neoenergia indica baixa renda' não ecoa nada do que 'confirmar_aplicacao' entrega: confira se o destino cumpre a promessa do botão.
  - [cta_contextual] [por_distribuidora] 'confirmar_aplicacao' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [cta_contextual] [confirmar_aplicacao] 'por_distribuidora' está resolvida só em parte dos caminhos (há entrada direta aqui): mantenha o CTA como secundário e condicional, nunca como principal.
  - [bloco_sem_entrega_correspondente] [confirmar_aplicacao] plano_visual[2] (Como confirmar a situação com a empresa da conta?): 'prova_oficial' não corresponde a nenhuma entrega declarada (checklist, decisao_pratica, proximo_passo_concreto).
  - [bloco_sem_entrega_correspondente] [desconto_social] plano_visual[2] (Como conferir uma modalidade já identificada na fatura?): 'prova_oficial' não corresponde a nenhuma entrega declarada (comparacao, decisao_pratica, tabela).
  - [loop_sem_ganho] ciclo confirmar_aplicacao → por_distribuidora → confirmar_aplicacao sem ganho de informação: o clique devolve o leitor a uma dúvida que ele já resolveu. Declare `retornos_justificados` ou tire uma das arestas.
  - [coorte_fria_sem_resposta_direta] [coorte:discover] tráfego frio com profundidade guiada: quem chega sem tarefa decide em um ou dois olhares.
  - [coorte_fria_sem_resposta_direta] [coorte:social] tráfego frio com profundidade guiada: quem chega sem tarefa decide em um ou dois olhares.
  - [coorte_fria_sem_resposta_direta] [coorte:display] tráfego frio com profundidade guiada: quem chega sem tarefa decide em um ou dois olhares.
- `research_p1`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 7 fato(s) verificado(s) do dossiê cc429d677a39
- `dossie_p1`: OK (tentativas=0, modelo=ready)
- `research_p2`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 5 fato(s) verificado(s) do dossiê cc429d677a39
- `dossie_p2`: OK (tentativas=0, modelo=review)
  - [revisao_humana_por_evidencia] requisito da promessa central sem evidência: a página é escrita, mas não publica sem decisão humana
  - [evidencia_unavailable] criterios.renda_per_capita: nenhum fato foi vinculado a 'Confirmar para quais hipóteses a renda por pessoa é apurada pela renda familiar considerada dividida pelo número de integrantes considerados, e definir esses termos.' porque a fonte que o tratava está indisponível agora (não quer dizer que é falso). Diga tudo o que os FATOS desta página sustentam, com os números deles; não acrescente valor, prazo ou precisão que não esteja nos fatos, e não troque a falta por ressalvas
  - [evidencia_unavailable] criterios.salario_minimo_vigente: nenhum fato foi vinculado a 'Confirmar o valor e a vigência do salário-mínimo usado para expressar em reais o limite citado, sem incorporá-lo à calculadora.' porque a fonte que o tratava está indisponível agora (não quer dizer que é falso). Diga tudo o que os FATOS desta página sustentam, com os números deles; não acrescente valor, prazo ou precisão que não esteja nos fatos, e não troque a falta por ressalvas
  - [evidencia_unsupported] ativo:Calcule a renda por pessoa da família: a calculadora faz só a conta; sem fonte verificada para a regra ou o valor vigente do limite, não afirme o limite em reais nem conclua direito a partir do resultado (ativo 'Calcule a renda por pessoa da família': regra ('criterios.renda_per_capita') sem fonte de emissor comprovado cujo escopo cubra a jurisdição do conteúdo; fonte de subdivisão não prova regra do país; ativo 'Calcule a renda por pessoa da família': valor_vigente ('criterios.salario_minimo_vigente') sem valor vigente em 2026, com data e abrangência explícitas, de fonte oficial ou reputada)
- `research_p3`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 5 fato(s) verificado(s) do dossiê cc429d677a39
- `dossie_p3`: OK (tentativas=0, modelo=ready)
- `research_p4`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 7 fato(s) verificado(s) do dossiê cc429d677a39
- `dossie_p4`: OK (tentativas=0, modelo=ready)
- `research_p5`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 4 fato(s) verificado(s) do dossiê cc429d677a39
- `dossie_p5`: OK (tentativas=0, modelo=review)
  - [revisao_humana_por_evidencia] requisito da promessa central sem evidência: a página é escrita, mas não publica sem decisão humana
  - [evidencia_unavailable] saida_oficial: não há canal oficial verificado agora: não ponha link oficial nem endereço; diga ao leitor para procurar o canal oficial pelo nome do órgão responsável
  - [desativado] saida_oficial 'link oficial': nenhum canal oficial verificado para a página
  - [desativado] bloco 'Como confirmar a situação com a empresa da conta?': prova oficial sem canal oficial verificado
- `research_p6`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 4 fato(s) verificado(s) do dossiê cc429d677a39
- `dossie_p6`: OK (tentativas=0, modelo=ready)
- `research_p7`: OK (tentativas=0, modelo=dossie)
  - [fatos_do_dossie] 5 fato(s) verificado(s) do dossiê cc429d677a39
- `dossie_p7`: OK (tentativas=0, modelo=ready)
- `dossie`: OK (tentativas=4, modelo=gpt-6.1-sol)
  - [dossie_consolidado] páginas {'ready': 4, 'review': 3}; 33 fato(s); 1 complementação(ões) sob demanda; 0 lacuna(s) deduplicada(s); 0 reaproveitada(s) do cache; 0 conflito(s); sha256 73a6cf5b2e46
- `dossie_complemento_lote`: OK (tentativas=0, modelo=n/a)
  - [complemento_lote] {"lacunas": 8, "pesquisadas": 7, "resolvidas": 4, "restantes": 4, "defeito": ""}
- `widgets_do_funil`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
  - [widgets_do_funil] {"paginas": [3, 4, 5, 6, 7], "prontas": [3, 4, 5, 6, 7], "recusadas": {}}
- `ctas_do_funil`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
  - [ctas_do_funil] {"arestas": 14, "pedidas": 14, "aplicadas": 14, "reaproveitadas": 0, "primeira_dobra": true, "entregas_ajustadas": [2], "recusas": {}}
- `delta_de_entrega`: OK (tentativas=0, modelo=n/a)
  - [entrega_ajustada] {"pagina": 2, "entrega_original": "O acesso depende de hipóteses legais e dados cadastrais vigentes. Ter NIS, receber Bolsa Família, ser aposentado ou ter 60 anos, isoladamente, não confirma o direito.", "entrega": "Apresenta as hipóteses de acesso e uma conta informativa da renda por pessoa, sem confirmar a composição legal dessa renda nem o valor vigente do salário-mínimo em reais.", "o_que_sai": "A definição da renda considerada no cálculo e a conversão do limite para reais.", "requisitos_sem_lastro": ["criterios.renda_per_capita", "criterios.salario_minimo_vigente"]}
- `screenshot_p3`: OK (tentativas=1, modelo=n/a)
- `screenshot_p5`: OK (tentativas=1, modelo=n/a)
- `screenshot_p6`: OK (tentativas=1, modelo=n/a)
- `screenshot_p7`: OK (tentativas=1, modelo=n/a)
- `delta_de_esqueleto`: OK (tentativas=0, modelo=n/a)
  - [continuidade_p4] {"pagina": 4, "proxima_duvida": {"antes": "", "depois": "confirmar_aplicacao"}, "motivo": "a página terminava sem saída; depois de falar com a distribuidora, a dúvida seguinte é conferir o desconto na fatura (p5)"}
- `briefing_p1`: OK (tentativas=0, modelo=n/a)
- `write_p1`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
- `seo_p1`: OK (tentativas=0, modelo=n/a)
- `revisor_p1`: OK (tentativas=0, modelo=chatgpt/gpt-6.1-sol)
- `build_p1`: OK (tentativas=1, modelo=n/a)
- `content_gate_p1`: OK (tentativas=1, modelo=n/a)
- `briefing_p2`: OK (tentativas=0, modelo=n/a)
- `write_p2`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
- `widget_p2`: OK (tentativas=0, modelo=n/a)
  - [ferramenta_pronta_do_pacote] Ferramenta preparada antes da redação; sem chamada ao modelo: calculo
- `seo_p2`: OK (tentativas=0, modelo=n/a)
- `briefing_p3`: OK (tentativas=0, modelo=n/a)
- `write_p3`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
- `widget_p3`: OK (tentativas=0, modelo=n/a)
  - [ferramenta_pronta_do_pacote] Ferramenta preparada antes da redação; sem chamada ao modelo: orientacao
- `seo_p3`: OK (tentativas=0, modelo=n/a)
- `revisor_p3`: OK (tentativas=0, modelo=chatgpt/gpt-6.1-sol)
- `build_p3`: OK (tentativas=1, modelo=n/a)
- `content_gate_p3`: OK (tentativas=1, modelo=n/a)
- `briefing_p4`: OK (tentativas=0, modelo=n/a)
- `write_p4`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
- `widget_p4`: OK (tentativas=0, modelo=n/a)
  - [ferramenta_pronta_do_pacote] Ferramenta preparada antes da redação; sem chamada ao modelo: orientacao
- `seo_p4`: OK (tentativas=0, modelo=n/a)
- `revisor_p4`: OK (tentativas=0, modelo=chatgpt/gpt-6.1-sol)
- `screenshot_p4`: OK (tentativas=1, modelo=n/a)
- `build_p4`: OK (tentativas=1, modelo=n/a)
- `content_gate_p4`: OK (tentativas=1, modelo=n/a)
- `briefing_p5`: OK (tentativas=0, modelo=n/a)
- `write_p5`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
- `widget_p5`: OK (tentativas=0, modelo=n/a)
  - [ferramenta_pronta_do_pacote] Ferramenta preparada antes da redação; sem chamada ao modelo: orientacao
- `seo_p5`: OK (tentativas=0, modelo=n/a)
- `revisor_p5`: OK (tentativas=0, modelo=chatgpt/gpt-6.1-sol)
- `build_p5`: OK (tentativas=1, modelo=n/a)
- `content_gate_p5`: OK (tentativas=1, modelo=n/a)
- `briefing_p6`: OK (tentativas=0, modelo=n/a)
- `write_p6`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
- `widget_p6`: OK (tentativas=0, modelo=n/a)
  - [ferramenta_pronta_do_pacote] Ferramenta preparada antes da redação; sem chamada ao modelo: orientacao
- `seo_p6`: OK (tentativas=0, modelo=n/a)
- `briefing_p7`: OK (tentativas=0, modelo=n/a)
- `write_p7`: OK (tentativas=1, modelo=chatgpt/gpt-6-sol)
- `widget_p7`: OK (tentativas=0, modelo=n/a)
  - [ferramenta_pronta_do_pacote] Ferramenta preparada antes da redação; sem chamada ao modelo: orientacao
- `seo_p7`: OK (tentativas=0, modelo=n/a)
- `revisor_p7`: OK (tentativas=0, modelo=chatgpt/gpt-6.1-sol)
- `build_p7`: OK (tentativas=1, modelo=n/a)
- `content_gate_p7`: OK (tentativas=1, modelo=n/a)
- `revisor_lote`: OK (tentativas=1, modelo=chatgpt/gpt-6.1-sol)
- `paginas_paralelas`: OK (tentativas=0, modelo=n/a)
  - [paralelo] workers=3; páginas=7; redigidas=7; acabadas=7; chamadas=7; pico_de_chamadas_em_voo=3; parede_s=277.933; soma_das_paginas_s=296.086; teto_do_run=não; dossie=cc429d677a39
- `revisao_global`: OK (tentativas=0, modelo=n/a)
  - [saida_oficial_ausente] [p5 confirmar_aplicacao] (aviso) corpo inteiro: a saída oficial boa prevista não aparece no rascunho → Conferir o canal oficial que a pesquisa trouxe.
- `revisor_p6`: OK (tentativas=0, modelo=chatgpt/gpt-6.1-sol)
- `build_p6`: OK (tentativas=1, modelo=n/a)
- `content_gate_p6`: OK (tentativas=1, modelo=n/a)
- `revisor_p2`: OK (tentativas=0, modelo=chatgpt/gpt-6.1-sol)
- `build_p2`: OK (tentativas=1, modelo=n/a)
- `content_gate_p2`: OK (tentativas=1, modelo=n/a)

## Custos e telemetria (COGS)
- Custo total (USD): 0.000000
- Teto por run/página (USD): 1.00 / 0.60
- Gasto debitado do teto (USD): 0.000000
- Tokens prompt/completion: 202139/29855
- Páginas alcançáveis no grafo: 7
- Páginas por sessão: não medidas (nenhum evento de sessão neste relatório).
- Passos no plano ChatGPT (uso do plano, sem custo de API): 18 — o custo em USD acima é só o faturado por API.

### Custo por página

| Página | Slug | Custo USD | % do run | Tokens | Situação |
|---|---|---|---|---|---|
| p1 | tarifa-social-energia-eletrica | 0.000000 | 0.0% | 11321 | gerada (sem publish) |
| p2 | quem-tem-direito-tarifa-social-pr | 0.000000 | 0.0% | 16242 | gerada (sem publish) |
| p3 | como-obter-tarifa-social-p1 | 0.000000 | 0.0% | 14808 | gerada (sem publish) |
| p4 | tarifa-social-por-distribuidora-p2 | 0.000000 | 0.0% | 14136 | gerada (sem publish) |
| p5 | como-saber-se-tarifa-social-esta-na-conta-p3 | 0.000000 | 0.0% | 12556 | gerada (sem publish) |
| p6 | quanto-paga-tarifa-social-p4 | 0.000000 | 0.0% | 13258 | gerada (sem publish) |
| p7 | desconto-social-conta-de-luz-p5 | 0.000000 | 0.0% | 13446 | gerada (sem publish) |

### Custo por tipo de passo

| Tipo | Chamadas | Custo USD | % do run |
|---|---|---|---|
| inteligencia | 1 | 0.000000 | 0.0% |
| extract | 1 | 0.000000 | 0.0% |
| revisao_esqueleto | 1 | 0.000000 | 0.0% |
| research | 7 | 0.000000 | 0.0% |
| dossie | 8 | 0.000000 | 0.0% |
| dossie_complemento_lote | 1 | 0.000000 | 0.0% |
| widgets_do_funil | 1 | 0.000000 | 0.0% |
| ctas_do_funil | 1 | 0.000000 | 0.0% |
| delta_de_entrega | 1 | 0.000000 | 0.0% |
| screenshot | 5 | 0.000000 | 0.0% |
| delta_de_esqueleto | 1 | 0.000000 | 0.0% |
| briefing | 7 | 0.000000 | 0.0% |
| write | 7 | 0.000000 | 0.0% |
| seo | 7 | 0.000000 | 0.0% |
| revisor | 7 | 0.000000 | 0.0% |
| build | 7 | 0.000000 | 0.0% |
| content_gate | 7 | 0.000000 | 0.0% |
| widget | 6 | 0.000000 | 0.0% |
| revisor_lote | 1 | 0.000000 | 0.0% |
| paginas_paralelas | 1 | 0.000000 | 0.0% |
| revisao_global | 1 | 0.000000 | 0.0% |

### Desperdício e custo por página útil

- Gasto em páginas REPROVADAS: US$ 0.000000 (0.0% do run) — nenhuma
- Custo médio por página que sobreviveu: US$ 0.000000

### Verificação de URL (ao vivo)

- URLs visitadas: 0 · visitas evitadas pelo cache: 0
- Verificadas OK: 0 · recusadas: 0 · inconclusivas (bloqueio/timeout): 0

| Passo | Prompt tok | Completion tok | Custo USD | Latência ms |
|---|---|---|---|---|
| inteligencia | 0 | 0 | 0.000000 | 0 |
| extract | 0 | 0 | 0.000000 | 0 |
| revisao_esqueleto | 0 | 0 | 0.000000 | 0 |
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
| research_p6 | 0 | 0 | 0.000000 | 0 |
| dossie_p6 | 0 | 0 | 0.000000 | 0 |
| research_p7 | 0 | 0 | 0.000000 | 0 |
| dossie_p7 | 0 | 0 | 0.000000 | 0 |
| dossie | 86553 | 9891 | 0.000000 | 187372 |
| dossie_complemento_lote | 0 | 0 | 0.000000 | 0 |
| widgets_do_funil | 3132 | 3579 | 0.000000 | 66772 |
| ctas_do_funil | 4954 | 1640 | 0.000000 | 32630 |
| delta_de_entrega | 0 | 0 | 0.000000 | 0 |
| screenshot_p3 | 0 | 0 | 0.000000 | 0 |
| screenshot_p5 | 0 | 0 | 0.000000 | 0 |
| screenshot_p6 | 0 | 0 | 0.000000 | 0 |
| screenshot_p7 | 0 | 0 | 0.000000 | 0 |
| delta_de_esqueleto | 0 | 0 | 0.000000 | 0 |
| briefing_p1 | 0 | 0 | 0.000000 | 0 |
| write_p1 | 9720 | 1601 | 0.000000 | 30941 |
| seo_p1 | 0 | 0 | 0.000000 | 0 |
| revisor_p1 | 0 | 0 | 0.000000 | 0 |
| build_p1 | 0 | 0 | 0.000000 | 0 |
| content_gate_p1 | 0 | 0 | 0.000000 | 0 |
| briefing_p2 | 0 | 0 | 0.000000 | 0 |
| write_p2 | 13996 | 2246 | 0.000000 | 43317 |
| widget_p2 | 0 | 0 | 0.000000 | 0 |
| seo_p2 | 0 | 0 | 0.000000 | 0 |
| briefing_p3 | 0 | 0 | 0.000000 | 0 |
| write_p3 | 12600 | 2208 | 0.000000 | 42315 |
| widget_p3 | 0 | 0 | 0.000000 | 0 |
| seo_p3 | 0 | 0 | 0.000000 | 0 |
| revisor_p3 | 0 | 0 | 0.000000 | 0 |
| build_p3 | 0 | 0 | 0.000000 | 0 |
| content_gate_p3 | 0 | 0 | 0.000000 | 0 |
| briefing_p4 | 0 | 0 | 0.000000 | 0 |
| write_p4 | 12222 | 1914 | 0.000000 | 36714 |
| widget_p4 | 0 | 0 | 0.000000 | 0 |
| seo_p4 | 0 | 0 | 0.000000 | 0 |
| revisor_p4 | 0 | 0 | 0.000000 | 0 |
| screenshot_p4 | 0 | 0 | 0.000000 | 0 |
| build_p4 | 0 | 0 | 0.000000 | 0 |
| content_gate_p4 | 0 | 0 | 0.000000 | 0 |
| briefing_p5 | 0 | 0 | 0.000000 | 0 |
| write_p5 | 11294 | 1262 | 0.000000 | 25660 |
| widget_p5 | 0 | 0 | 0.000000 | 0 |
| seo_p5 | 0 | 0 | 0.000000 | 0 |
| revisor_p5 | 0 | 0 | 0.000000 | 0 |
| build_p5 | 0 | 0 | 0.000000 | 0 |
| content_gate_p5 | 0 | 0 | 0.000000 | 0 |
| briefing_p6 | 0 | 0 | 0.000000 | 0 |
| write_p6 | 11367 | 1891 | 0.000000 | 35878 |
| widget_p6 | 0 | 0 | 0.000000 | 0 |
| seo_p6 | 0 | 0 | 0.000000 | 0 |
| briefing_p7 | 0 | 0 | 0.000000 | 0 |
| write_p7 | 11278 | 2168 | 0.000000 | 40736 |
| widget_p7 | 0 | 0 | 0.000000 | 0 |
| seo_p7 | 0 | 0 | 0.000000 | 0 |
| revisor_p7 | 0 | 0 | 0.000000 | 0 |
| build_p7 | 0 | 0 | 0.000000 | 0 |
| content_gate_p7 | 0 | 0 | 0.000000 | 0 |
| revisor_lote | 25023 | 1455 | 0.000000 | 35310 |
| paginas_paralelas | 0 | 0 | 0.000000 | 277933 |
| revisao_global | 0 | 0 | 0.000000 | 0 |
| revisor_p6 | 0 | 0 | 0.000000 | 0 |
| build_p6 | 0 | 0 | 0.000000 | 0 |
| content_gate_p6 | 0 | 0 | 0.000000 | 0 |
| revisor_p2 | 0 | 0 | 0.000000 | 0 |
| build_p2 | 0 | 0 | 0.000000 | 0 |
| content_gate_p2 | 0 | 0 | 0.000000 | 0 |

## Jornada do leitor

- Revisão do esqueleto (antes do gasto): aprovada, 9 aviso(s).
- Revisão global do funil pronto: avisos_para_humano — 0 achado(s) material(is), 1 aviso(s). Nenhum texto alterado.
- Saídas oficiais: tarifa_social=nao_aplicavel, quem_tem_direito=nao_aplicavel, como_obter=boa, por_distribuidora=boa, confirmar_aplicacao=boa, quanto_paga=nao_aplicavel, desconto_social=boa
- Contrato de medição: medicao.json (45 sinais previstos, 0 observação(ões) real(is)). Proposta de nova versão exige aprovação humana; nada é publicado ou reescrito por código.
