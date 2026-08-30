# Segunda revisão externa — a unidade de análise

> Auditoria datada: evidência de revisão, não contrato de runtime.

Cole tudo abaixo da linha.

---

Preciso de uma revisão adversarial. Já rodei uma com outro modelo, apliquei os cinco defeitos que ele achou, e o que sobrou é um problema que não sei se é conserto ou parede. Quero saber se estou perseguindo algo que não existe.

**Não quero validação.** Se a conclusão for "pare", diga.

# 1 · A OPERAÇÃO

Arbitragem de tráfego como publisher. Compro clique no Google Ads e monetizo com display (AdSense/AdX/GAM) em portais que **explicam** serviços, benefícios e documentos. Não vendo nada, não capturo dado. A receita é RPM da página menos CPC do clique.

Mês medido (jun–jul/2026, Brasil + LATAM):

```
investido  R$ 461.364   ·   receita  R$ 592.080
ROAS do que consigo parear  1,463   (60.581 pares campanha × dia × placement)
```

Um funil = 1 landing page + 1 hub + 3 páginas de solução, grafo tipado e acíclico, ~8 mil palavras, pipeline automatizado. **Errar o tema custa uma quinzena de produção e verba de teste.**

# 2 · O MODELO

`motor_pautas/espaco.py` — Python puro, stdlib, 63 testes.

Cada tema é um ponto em **10 eixos, 3 famílias**, combinados por média geométrica ponderada, com **portões** que são pares `(eixo, nível)` e zeram o índice.

```
DEMANDA HUMANA   ignorancia · engajamento · opacidade · reposicao
ECONOMIA         volume · spread (RPM÷CPC) · densidade · formato_consumo
POSIÇÃO          vacuo · producao

PORTÕES  (engajamento, dado_unico) · (ignorancia, nao_preciso_de_nada)
         (formato_consumo, video_social|voz_ou_humano)
         (spread, ruim) · (volume, residual)   ← só com dado MEDIDO
```

Cinco dos dez eixos são **declarados por um agente** (leitura, julgamento); cinco são **medidos** (DataForSEO, GAM). Os pesos são priores declarados; há um `_CALIBRACAO` vazio com teste garantindo que continue vazio.

# 3 · O QUE JÁ FOI TESTADO E REJEITADO — com números

Não proponha nenhuma destas sem derrubar a medição.

**Modelo ajustado nos 237 temas da operação.** AUC fora da amostra 0,689. Morreu porque **`spend` sozinho prevê o alvo (`lucro > R$3.000`) com AUC 0,971** — aprendeu em que a equipe decidiu investir. Spend mediano dos "vencedores" R$12.430, dos "perdedores" R$483.

**Pressão psicológica ordenada por persistência:** correlação +0,017. Reordenando por **ignorância**: +0,194.

**Kahneman como prior:** literatura prevê perda ~2× ganho; medido 1,06× e 0,69×. Prospect Theory descreve escolha sob risco; aqui se mede leitura.

**Loewenstein (U invertido):** medido monotônico decrescente, pico no hiato máximo.

**IAB como feature:** piorou o AUC (−0,011 a −0,013).

**Limite da base:** n=235, erro padrão da correlação 0,065 — diferenças abaixo de ~0,13 são ruído.

**A objeção da primeira revisão, que aceitei:** aposentei a regressão por contaminação de `spend` e continuei medindo tudo contra o mesmo alvo contaminado. Sobrevive um achado — `(engajamento, dado_unico)` — porque aqueles 9 temas gastaram **acima da mediana dos vencedores** e perderam assim mesmo, então o viés de seleção não os alcança.

# 4 · O PROBLEMA DE AGORA

Integrei os três eixos de julgamento (`ignorancia`, `engajamento`, `opacidade`) na descoberta de entidades: um LLM classifica cada entidade, e `(engajamento, dado_unico)` barraria a entidade antes de gastar com mineração de keywords.

Para combater o modelo rotular o *tema* em vez da pergunta, exigi que ele **escrevesse a resposta da dúvida em uma frase ANTES de rotular**. Isso funcionou — eliminou uma classe inteira de erro, verificada.

Depois rodei o teste de estabilidade (mesma configuração, duas rodadas):

```
rótulo igual entre rodadas   2 de 6   (acaso, com 5 valores, = 20%)
os dois portões dispararam em entidades DIFERENTES
```

Tentei estabilizar pedindo **três frases** por entidade e tomando a **moda**:

```
rótulo igual entre rodadas   6 de 12   (critério definido antes: >= 83%)
```

E aí apareceu a medida que reenquadra tudo:

> **Das 43 entidades das duas rodadas, apenas 2 tiveram as três frases concordando entre si.**

```
CDB                 [comparativo, condicional, sequencial]
Seguro Residencial  [dado_unico, dado_unico, sequencial]  → barrou numa rodada, não na outra
Financiamento Solar [comparativo, dado_unico, condicional]
```

**As três frases estão corretamente rotuladas cada uma.** O CDB tem legitimamente uma pergunta comparativa, uma condicional e uma de dado único.

A instabilidade não está entre rodadas — está **dentro de uma única classificação**. Não é um classificador ruidoso: é um classificador cuja **unidade de análise não existe**. "O engajamento do CDB" não é uma quantidade.

# 5 · A HIPÓTESE QUE QUERO QUE VOCÊ ATAQUE

Se a entidade tem N perguntas legítimas e a página responde UMA, então o eixo é **indefinido no nível da entidade e definido no nível da página** — e as três frases do CDB são, literalmente, três páginas de um funil.

Consequência: a descoberta não deveria devolver **um rótulo** por entidade. Deveria devolver **o conjunto de perguntas** — que é a arquitetura do funil.

Isto já funciona no outro extremo do pipeline: o gerador de funil declara `engajamento` por página de solução, e o rótulo escolhe qual ferramenta HTML interativa a página recebe (roteador de elegibilidade, navegador de jornada, diagnóstico de recusa…). Lá a unidade é a página e não há ambiguidade.

# 6 · O QUE QUERO DE VOCÊ

**1. A hipótese do §5 procede?** Se sim, qual é a consequência que eu não estou vendo? Se não, onde ela falha?

**2. Existe alguma quantidade honesta no nível da entidade?** Ou toda métrica de "forma da pergunta" é necessariamente por-pergunta? Se existir, qual — com dado obtenível.

**3. O portão morreu?** Barrar antes de minerar era a economia concreta do subsistema. Se a decisão é por-pergunta e a mineração é por-entidade, existe algum portão legítimo no nível da entidade, ou a economia tem que vir de outro lugar?

**4. O que você deletaria do modelo de 10 eixos?** Um modelo com menos eixos que decide igual é melhor. Diga qual eixo não paga o próprio custo de declaração, e por quê.

**5. Estou perseguindo algo que não existe?** O dono desta operação está cansado deste ciclo e desconfia de estar andando em círculos. Se a leitura honesta é "pare e volte quando tiver desfecho medido", diga isso — vale mais que uma sugestão de conserto.

## Regras da resposta

- **Elogio só com especificidade.** "A abordagem é sólida" não serve.
- **Se discordar da minha leitura de um número, diga.** Já li errado a minha própria medição quatro vezes neste projeto.
- **Prefira estar errado e específico a estar seguro e vago.**
- Se a resposta for "pare", diga em quantas linhas precisar, mas diga primeiro.
