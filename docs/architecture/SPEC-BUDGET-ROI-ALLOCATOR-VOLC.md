# VOLC Budget-ROI Allocator

Status: especificação de pesquisa; zero autoridade de escrita  
Fonte principal: *Multi-channel Autobidding with Budget and ROI Constraints* (Deng et al., arXiv:2302.01523)  
Escopo inicial: Google Ads e, depois, portfólio multicanal de mídia  
Fora do escopo inicial: corrigir campanha sem entrega, definir lance por leilão ou executar mudança sem aprovação

## 1. Decisão

O artigo fundamenta uma capacidade nova no VOLC O.S.: recomendar como repartir um orçamento global entre unidades elegíveis de mídia quando suas curvas orçamento → valor são desconhecidas.

Essa capacidade se chama **VOLC Budget-ROI Allocator**. Ela nasce em replay e shadow mode. Não substitui Smart Bidding, ORAKUL, Bola de Cristal, Meridian nem o executor canônico.

O primeiro uso correto é publicidade digital. A tradução da ideia para canais de arbitragem, apostas ou outras carteiras é apenas uma analogia futura e exige outro contrato econômico.

## 2. O que o paper realmente demonstra

Para canais `j = 1..M`, o trabalho maximiza valor/conversão total, sujeito a:

- ROI agregado mínimo: `sum(valor_j) >= gamma * sum(gasto_j)`;
- orçamento total: `sum(gasto_j) <= rho`.

O anunciante escolhe orçamento e target ROI por canal; cada canal é uma caixa-preta que decide os leilões internos. No modelo do artigo:

1. targets ROI isolados podem ser arbitrariamente subótimos;
2. orçamentos por canal são suficientes para atingir o ótimo global;
3. com orçamentos otimizados, os targets ROI tornam-se redundantes no ótimo matemático;
4. um algoritmo SGD-UCB pode aprender a alocação com feedback bandit, discretizando orçamentos em braços e usando multiplicadores duais para as restrições globais.

Isso **não** significa desligar tCPA/tROAS, nem prova que o orçamento é sempre a melhor alavanca em uma conta real do Google Ads.

## 3. Hipóteses que impedem cópia literal

O allocator deve declarar `inelegivel` quando uma destas premissas não puder ser defendida:

- o orçamento atribuído não é consumido; o paper assume orçamento vinculante;
- a janela de conversão ainda não fechou ou foi revisada;
- custo e valor não estão na mesma moeda e janela;
- tracking, policy, aprovação, volume ou lance impedem entrega;
- houve mudança estrutural recente ou learning period;
- não existe amostra mínima por braço;
- há canibalização/interferência material entre unidades;
- o valor econômico é atribuído, mas não incremental;
- o ambiente mudou o suficiente para invalidar a hipótese estacionária.

As campanhas Search atuais da Crédito Up, que quase não gastam, são **inelegíveis**. Antes do allocator vem o diagnóstico de entrega.

## 4. Correção da leitura da Bia

A Bia acertou ao recomendar modo offline, controle global de ROI, exploração controlada e confirmação humana.

O score proposto por ela — `profit + 0.5*EV + 1000*CLV + 50*execution_rate - 200*error_rate - 0.5*drawdown` — não vem do paper. Ele mistura unidades e pesos não calibrados. Fica preservado somente como `bia_score_v0_candidate`, hipótese histórica não publicável.

No VOLC:

- valor econômico deve ser uma medida única, por exemplo contribuição líquida;
- gasto de mídia permanece separado;
- risco, drawdown, concentração e erro são restrições/guardrails explícitos;
- confiança exige amostra, cobertura dos braços e intervalo; não nasce de uma linha agregada;
- a Bia pode explicar a proposta, nunca calcular a autoridade econômica nem aprová-la.

## 5. Lugar na arquitetura

```text
Google Ads + receita + custos + frescor
                  |
                  v
        ledger econômico canônico
                  |
                  v
       gate de elegibilidade do allocator
                  |
                  v
  estimadores orçamento -> valor + SGD-UCB
                  |
                  v
         proposta tipada em shadow
                  |
                  v
       árbitro de políticas ORAKUL
                  |
                  v
       aprovação humana contextual
                  |
                  v
 executor canônico com teto, recibo e rollback
```

Fronteiras:

- **Smart Bidding:** decide dentro do leilão; o allocator decide envelopes de orçamento.
- **ORAKUL:** avalia maturidade, histerese, políticas, conflitos e se a proposta pode seguir.
- **Bola de Cristal:** produz previsões; não aloca nem autoriza.
- **Meridian:** informa contribuição incremental, saturação e priors estratégicos em cadência lenta; não controla a operação intradiária.
- **Decision Intelligence Lab:** oferece normalização, replay, linhagem, suficiência, comparação e superfície de proposta.
- **Executor:** é a única porta futura de mutação; o allocator nunca chama Google Ads diretamente.

## 6. Unidade de alocação

O contrato não deve chamar tudo de “canal”. Cada rodada declara `allocation_unit_kind`:

- `platform` — Google Ads, Meta;
- `account` — conta de anúncio;
- `channel` — Search, Display, Demand Gen, Performance Max;
- `portfolio` — carteira explicitamente definida;
- `campaign` — somente quando interferência e comparabilidade forem avaliadas.

Misturar tipos na mesma otimização é proibido. A chave inclui tenant, moeda, objetivo econômico, janela e versão da taxonomia.

## 7. Contrato mínimo de entrada

Por unidade e período:

- identidade e tipo da unidade;
- orçamento autorizado e efetivamente aplicado;
- gasto observado;
- conversão ou valor econômico observado;
- moeda e definição de valor;
- instante da fotografia e fechamento da atribuição;
- atraso de conversão conhecido;
- estado de entrega, policy, tracking e learning;
- mudanças estruturais recentes;
- braço de orçamento e número de observações;
- fonte, versão e cobertura de cada campo;
- sinais de interferência e concentração.

`null` nunca vira zero. Gasto abaixo do orçamento não vira resposta ao braço; vira violação de premissa.

## 8. Contrato de saída

Cada recomendação contém:

- `allocator_run_id`, versão de algoritmo e dataset fingerprint;
- unidade, orçamento atual e orçamento recomendado;
- modo `hold | reduce | increase | explore | ineligible`;
- objetivo global e restrições verificadas;
- braço, observações, estimativa, intervalo e incerteza;
- razões e contraprovas;
- premissas satisfeitas e violadas;
- delta máximo, cooldown, teto de exploração e rollback proposto;
- estado `shadow`, sem autoridade de execução.

O resultado entra como proposta T1 na timeline. Nunca como aplicação.

## 9. Spike offline

### A0 — reprodução matemática

- implementar uma versão pequena e determinística do SGD-UCB;
- reproduzir cenários sintéticos do paper sem alegar equivalência ao Google Ads;
- testar limites, parada segura, discretização e restrições.

### A1 — bancada comparativa

Comparar:

1. orçamento atual/estático;
2. proporcional;
3. greedy por retorno histórico;
4. SGD-UCB inspirado no paper.

Medir valor, ROI global, violações, regret contra baseline, turnover, concentração, estabilidade e cobertura de braços.

### A2 — replay histórico as-of

- nenhuma informação futura;
- atribuição fechada;
- campanhas inelegíveis excluídas com motivo;
- intervalos e resultados posteriores separados;
- zero Google mutate.

### A3 — shadow real

- somente após o ledger econômico fechar custo, receita e frescor;
- proposta humana na Bancada de Decisão;
- ORAKUL pode bloquear, mas não reescrever silenciosamente;
- Bia explica em linguagem operacional;
- nenhuma exploração com dinheiro real.

### A4 — canário humano, futuro

Exige ADR específica, allowlist, teto total e por unidade, cooldown, rollback, recibo, verificação posterior e autorização nominal. Não está autorizado por esta SPEC.

## 10. Critérios de aceite do spike

- implementação reproduzível por seed e dataset fingerprint;
- provas que falham se futuro vazar, `null` virar zero ou orçamento não gasto for tratado como braço observado;
- restrições globais verificadas independentemente do algoritmo;
- baseline simples lado a lado;
- nenhum ganho declarado sem intervalo e tamanho de amostra;
- nenhuma confiança inventada;
- exploração desativada fora do laboratório;
- nenhuma dependência de LLM no cálculo;
- zero mutação externa;
- saída compatível com proposta, timeline e revisão humana existentes.

## 11. Ordem prática

Esta frente não bloqueia a prioridade imediata de lançar e destravar campanhas. A ordem correta é:

1. fazer campanhas elegíveis entregarem e fechar medição econômica;
2. extrair o kernel ORAKUL e consolidar o ledger;
3. construir/reproduzir o spike offline;
4. executar replay histórico;
5. somente então iniciar shadow real.

## 12. Perguntas que os próximos insights da Google Ads API devem responder

- quais campos permitem distinguir budget limited de underdelivery por lance, policy, aprovação ou volume;
- que cadência e atraso existem para custo, conversão e conversion value;
- como observar mudanças de budget, bidding e learning sem reconstruir o passado;
- quais níveis podem ser tratados como unidades comparáveis sem canibalização;
- como representar shared budgets e portfolio bidding;
- como separar valor atribuído de valor incremental;
- quais recomendações/experimentos da API podem informar o allocator sem se tornarem autoridade.

