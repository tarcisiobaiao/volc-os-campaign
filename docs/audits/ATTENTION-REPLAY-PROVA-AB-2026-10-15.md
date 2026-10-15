# Attention Engine: histórico reaproveitado e prova curta

Data: 15/10/2026. Experimento encerrado; sem mudança de modelo padrão, cron, campanha ou banco.

## Decisão

1. Aproveitar o histórico mensal já comprado é viável, sem nova API. O replay separa as próximas janelas dos temas perenes, sem excluir estes últimos nem usar CPC para ordená-los.
2. Recuar `date_to` em um dia funcionou para as duas tarefas testadas. É uma mitigação comprovada nessa amostra, não uma demonstração da causa única nem uma correção já incorporada ao motor canônico.
3. **Manter o raciocínio padrão.** O modo baixo economizou tempo e tokens, mas descartou um serviço potencialmente útil por inventar um requisito de demanda massiva. Não adotá-lo globalmente.
4. HTTP 200 e domínio oficial não comprovam uma data. As duas fontes testadas não permitiram confirmar a afirmação; não converter indisponibilidade em fato falso nem paralisar todos os outros temas.

## Histórico, sem APIs

Fonte: `../producao/attention-rodada-unica-20261014/`, preservada.

- 176 resultados de keywords, 175 combinações distintas país/keyword.
- 161 resultados com histórico mensal preenchido; 86 das 94 entidades ligadas a algum histórico mensal.
- Ordenação por mês/ano; valor ausente não vira zero.
- Filas consultivas: em janela, próximas janelas, perenes/outros sem janela e janela passada. Nenhum card canônico foi substituído.
- Exemplo: Bolsa Família reaparece entre as próximas janelas, enquanto Escala 6x1 continua na fila sem calendário. Datas herdadas continuam identificadas como **não reverificadas**.
- Cesantías: média escalar anterior 720, pico mensal reportado 2.900 em fevereiro/2026. O corte pela média esconderia esse pico. Isso não comprova oportunidade lucrativa atual.
- PTU México: pico mensal reportado em maio, não confirmação da janela diária aprendida para outubro. Histórico mensal é contexto; não valida automaticamente o backtest.
- Um único ano não prova sazonalidade anual recorrente. Dados não foram usados para reescrever o histórico nem para alegar previsão prospectiva.

## Prova pequena de Trends

Uma tarefa por país; mesmas keywords, localização, idioma e amplitude de 250 dias. Data final mudou de 15/10 para 14/10, com a inicial recuada igualmente. Sem retentativas.

| País | Antes | Agora | Dados úteis |
| --- | --- | --- | --- |
| RO | `40501 Invalid Field: date_to` | `20000`, 251 pontos | apenas 1 ponto não ausente e positivo |
| TH | `40501 Invalid Field: date_to` | `20000`, 251 pontos | 92 pontos não ausentes e positivos |

Custo DataForSEO informado: US$ 0,011 por consulta, US$ 0,022 total.

A execução também ocorreu em horário diferente: não há controle simultâneo do pedido antigo, portanto não se atribui causalidade exclusiva ao fuso ou à data. A [documentação do endpoint](https://docs.dataforseo.com/v3/keywords_data-google-trends-explore-live/) inclusive descreve a data atual como padrão quando `date_to` é omitido. A baixa densidade de RO continua sendo uma limitação, apesar do aceite técnico.

## A/B de raciocínio real

- Modelo pedido e servido em todas as quatro chamadas: `gemini-3.8-flash`.
- Dois pares, BR e TH, 20 sinais por país. Amostra histórica enriquecida para incluir decisões positivas/monitoradas, não estimativa da prevalência da população.
- Mesmos prompts, contexto histórico, temperatura e limite de 8.192 tokens nos dois braços. Somente `thinkingConfig.thinkingLevel=LOW` diferencia o tratamento.
- Ordem contrabalançada: BR padrão→baixo; TH baixo→padrão. Não elimina aleatoriedade ou efeitos de servidor/cache.
- Todas as respostas terminaram em STOP e cobriram os IDs esperados, sem duplicações. Nenhuma busca de modelo ou retentativa.

| Métrica, dois lotes | Padrão | Baixo | Redução |
| --- | --- | --- | --- |
| Soma da latência das chamadas | 41,944 s | 24,792 s | 40,89% |
| Tokens de entrada | 5.104 | 5.104 | 0% |
| Tokens totais | 11.613 | 9.314 | 19,80% |
| Saída + raciocínio reportado | 6.509 | 4.210 | 35,32% |
| Custo estimado | US$ 0,02823675 | US$ 0,01961550 | 30,53% |

O provedor não retornou `thoughtsTokenCount` no braço baixo; não se afirma que houve literalmente zero raciocínio interno. Valores de custo são estimados pela [tabela oficial](https://ai.google.dev/gemini-api/docs/pricing), US$ 0,75/M de entrada e US$ 3,75/M de saída incluindo raciocínio, consultada nesta data; a fatura real não foi retornada.

**Qualidade:** 39/40 decisões iguais e 40/40 vínculos de entidade iguais. Mas o padrão promoveu descarte de eletroeletrônicos nos Correios; o baixo descartou por ser um serviço “sem demanda massiva de utilidade”. O prompt exigia utilidade prática, não demanda massiva. Consideramos uma perda potencial material, não prova de lucro perdido.

A revisão dos 40 itens foi feita pelo próprio assistente, não por humano independente e não é avaliação cega certificada. Há também um possível erro compartilhado: ambos descartaram aviso de restrição temporária de voo de drones, que pode gerar dúvida prática regional. Concordância não equivale a acurácia. Não há recall ou ROI medidos.

## Duas fontes oficiais, GET público sem API

- INSS: URL anteriormente fornecida pela pesquisa terminou em uma página de login com HTTP 200. Não comprovou o calendário.
- SSA: HTTP 403. Não comprovou o calendário.

Recibos preservam URL final, hash e texto. Nenhuma data foi promovida a verificada por conter um domínio oficial ou um número de dia. Nenhuma tentativa de contornar os bloqueios foi feita.

## Custo, segurança e escopo

- Seis chamadas pagas: duas DataForSEO, quatro Gemini. Duas leituras públicas adicionais, sem API paga.
- Total contabilizado: **US$ 0,06985225**, sendo US$ 0,022 informados pelo DataForSEO e US$ 0,04785225 estimados do Gemini. Teto pré-registrado: US$ 0,50.
- Fase paga de aproximadamente **94,292 segundos**, além do preparo e análise offline. Não representa o tempo de uma rodada completa de sete países.
- Seis testes locais focados passaram. Entradas dos pares conferidas por igualdade estrutural; 164 arquivos originais conferidos por SHA-256 e intactos.
- Scripts recusam repetição implícita da fase paga. Respostas brutas gravadas antes da interpretação. Sem segredos nos recibos.
- Nenhuma alteração no código canônico, default de modelo, WordPress, Supabase, Ads ou deploy; sem notificações ou scheduler. Sem commit/push desta rodada.

## Evidências e continuidade

Pasta: `/Users/mac/Desktop/VOLC-OS-CAMPAIGN/producao/attention-fechamento-20261015/`.

- `validar.py`, `test_validar.py`, `protocolo.json`: replay, teto e execução delimitada.
- `replay-historico.json`: histórico por entidade e filas completas.
- `prova-trends.json`, `prova-fontes.json`: duas provas pequenas.
- `comparacao-ab.json`: decisões lado a lado e revisão dos 40 itens.
- `chamadas.json`, `execucao.json`, `raw/`: custos, uso e respostas sem cabeçalhos de autenticação.
- `integridade.json`, `originais-sha256.json`: preservação do run anterior.

**Experimento solicitado concluído. P08-T06 e `concept:topic_radar` permanecem partial:** essa tarefa é mais ampla que o experimento; integração operacional, precisão independente, backtest sem lookahead e retorno econômico continuam sem homologação. Não autoriza uma nova corrida para tentar obter uma conclusão mais favorável.
