# O que foi tentado e rejeitado — com os números

Este arquivo existe porque as ideias abaixo **vão voltar**. São plausíveis, soam
sofisticadas, e três delas eu mesmo propus com convicção antes de medir. Sem o
registro, alguém — provavelmente eu — reintroduz cada uma daqui a alguns meses.

---

## 1 · Um modelo ajustado nos 237 temas da operação-exemplo

**O que era.** Regressão logística L2 em numpy, alvo `lucro > R$ 3.000`, seis
variáveis, k-fold estratificado. AUC dentro 0,716, **fora da amostra 0,689**,
lift de 2,79× no decil superior. Cuidados reais: RPM de arquétipo leave-one-out,
temas agregados por nome antes de tudo, L2 obrigatório com 46 positivos.

**Por que caiu.** Uma revisão externa mediu o que eu não tinha medido:

```
AUC de `spend` sozinho contra o alvo ....... 0,971
spend mediano dos "vencedores" ............. R$ 12.430
spend mediano dos "perdedores" ............. R$    483
```

O modelo não aprendeu o que é um bom tema — aprendeu **em que aquela equipe
decidiu investir**. A maioria dos "perdedores" não perdeu: foi descartada antes
de ser testada.

Para um motor que existe para SUGERIR pauta, isso é fatal. Um sniper que
recomenda o que você já faz não vale nada.

**Outros três defeitos, todos verificados por mim:**

- **Não generalizava para arquétipo novo.** k-fold por tema: 0,689. Deixando um
  arquétipo inteiro fora do treino: **0,605**. Previa tema novo dentro de
  categoria conhecida — o oposto do que descoberta exige.
- **Dependia de uma lista regional.** A variável de maior peso (+0,600) era um
  regex com siglas latino-americanas. Sem ela, AUC caía para **0,561**. Não era
  princípio; era lookup.
- **A camada de dimensões era dead code.** 488 linhas, validadas em teste cego
  com 237 temas em duas rodadas, e **nunca chamadas** pelo caminho de pontuação.

**A regra que fica.** Se algum dia houver calibração, o alvo tem que ser **tempo
de atenção por sessão**, não lucro. Lucro embute decisão de verba. `_CALIBRACAO`
em `espaco.py` está vazio e há teste garantindo que continue.

**A amostra, para quem for tentar de novo:** 237 temas distintos, 100% LATAM,
só pt/es, um nicho, uma equipe, um período, e **8 temas somam 44% do lucro**.

---

## 2 · Ordenar a pressão psicológica por persistência

**O que era.** Seis níveis de pressão ordenados por quanto tempo a aflição
sobrevive sem ser resolvida, com `compulsao` no topo.

**Por que caiu.** Teste cego em 237 temas, duas rodadas independentes:

```
correlação com desfecho ..... +0,017      (nada)

direito_latente ... 33% de vitória, 1,68× a base, n=52
compulsao ......... 11% de vitória, 0,58× a base, n=53
```

Três vezes de diferença com amostras equilibradas. Reordenando por **ignorância**
— quanto o leitor não sabe ao chegar —, a correlação foi para **+0,194**.

**O mecanismo.** O que faz virar página não é a força que empurrou, é o tamanho
do buraco de conhecimento. Quem precisa renovar a carteira de motorista sabe
exatamente o que fazer e quer executar: não lê. Quem não sabe se tem dinheiro
parado lê tudo.

---

## 3 · Teoria da Perspectiva (Kahneman) como prior de peso

**O que era.** Uma revisão externa apontou que `dinheiro_esquecido` e
`medo_de_perder` são aversão à perda, e que a literatura diz que perda pesa ~2×
o ganho. Ideia: usar 2,0× como prior com literatura, no lugar de número inventado.

**Por que caiu.** Agrupando as sete tensões por enquadramento e medindo:

```
rodada 1 ... razão perda/ganho = 1,06×
rodada 2 ... razão perda/ganho = 0,69×   (invertido)
Kahneman prevê ~2,0×
```

**O motivo é conceitual, não amostral.** Prospect Theory descreve **escolha sob
risco** — qual opção você prefere. Aqui se mede **leitura** — quanto tempo você
gasta se informando. São comportamentos diferentes, e o mesmo vale para o Fogg
Behavior Model, que descreve *agir*, não *ler*.

---

## 4 · Teoria do hiato de informação (Loewenstein) como curva

**O que era.** Loewenstein prevê que a curiosidade tem **U invertido**: pico no
hiato moderado, porque quem não sabe nada não sente falta e quem sabe quase tudo
não precisa.

**Por que caiu.** Nas duas rodadas o pico está no hiato **máximo**:

```
                        r1      r2
nao_sei_se_existe      1,68×   1,52×   ← pico
nao_sei_se_sirvo       0,99×   1,26×
so_falta_um_dado       0,52×   0,53×
sei_o_que_fazer        0,58×   0,99×
```

Monotônico decrescente, não U invertido.

**Mas testar essa teoria produziu o achado mais limpo da base:**
`curiosidade pura` deu **0% de vitória nas duas rodadas** — zero em 4 e zero em 7.
Isso expôs que a escala colapsava dois conceitos: quem busca uma novela tem hiato
**máximo** e não paga, porque não há nada em jogo. Hiato e interesse são
ortogonais, e a curiosidade virou portão.

---

## 5 · IAB como feature do modelo

**O que era.** Três variáveis derivadas da taxonomia IAB — RPM médio do Tier-1,
flag de órfão, vetor de propósito — como preditores.

**Por que caiu.** Todas pioram o AUC fora da amostra:

```
modelo sem IAB ......... 0,6885
+ iab_rpm_tier1 ........ 0,6775   (−0,0110)
+ iab_orfao ............ 0,6757   (−0,0129)
+ as três .............. 0,6767   (−0,0118)
```

`iab_rpm_tier1` é versão mais grossa do RPM de arquétipo que o modelo já tinha;
`iab_orfao` é colinear com "arquétipo desconhecido". Proxy pior de coisa já
medida só injeta ruído.

**O que ficou.** IAB é camada de **classificação e interoperabilidade**, não de
pontuação: id para key-value do GAM, ponte de arquétipo entre idiomas, e o vetor
de propósito. Há teste garantindo que nenhuma feature IAB volte ao modelo.

**Hipótese testada junto e refutada:** granularidade da taxonomia ≈ densidade de
demanda publicitária. Pearson **−0,140**. Automotive tem 41 subcategorias e RPM
21; Careers tem 9 e RPM 55.

---

## 6 · `spread` como média nacional

**O que era.** RPM do país ÷ CPC do país, com faixas por mercado.

**Por que caiu.** Testado contra os cinco mercados com resultado medido:
**Pearson −0,266** — levemente negativo. Limpando o maior outlier: **−0,280**.

**A correção.** Média de país dilui o nicho no run-of-network. O RPM de uma
página de subsídio habitacional não é o RPM médio da Colômbia, e o CPC de
`cesantias` não é o CPC médio de lá. A unidade correta é **arquétipo × país**, e
o `keywords_data/google_ads/search_volume` do DataForSEO entrega o CPC da
keyword por seis centésimos de centavo.

---

## 7 · `formato_consumo` como peso

**O que era.** Novo eixo, entrando na média ponderada como os outros.

**Por que caiu.** Não pegava o caso para o qual foi criado. Varredura de prior:

```
prior 0,65 → video_social perde 1,17× para texto_busca
prior 1,20 → perde 1,29×
```

Diluído numa média de dez eixos. **Peso é para o que troca com outra dimensão;
disponibilidade de canal não troca com volume.** Promovido a portão — e aí
`jaminan hari tua bpjs`, que tem a melhor economia da tabela (0,946), cai de
primeiro para sexto.

---

## 8 · A trava de concordância entre declarações

**O que era.** Duas declarações independentes por tema, e o motor só pontua onde
concordam. A evidência era boa:

```
                onde CONCORDAM     onde DISCORDAM
pressao         r = +0,135         r = −0,032
opacidade       r = +0,176         r = +0,068
```

**Por que não foi implementada.** Revisão externa confirmou os três riscos que eu
já suspeitava: concordância pode medir apenas **facilidade do item** (tema óbvio
gera concordância e também é o mais explorado, logo o menos lucrativo); selecionar
por concordância **encolhe a amostra e infla correlação** por acaso; e dois
agentes do mesmo modelo **não são independentes de verdade**.

Fica como motivo para marcar "olha isso com atenção", nunca como gate.

---

## O limite de resolução desta base

Com n=235, o erro padrão da correlação é **0,065**. Diferenças menores que ~0,13
são indistinguíveis de ruído, e quase toda hipótese testada aqui vive abaixo
disso. Continuar afinando contra esses 237 temas é ajustar ruído.

O caminho não é mais tuning. São dados novos, com alvo de tempo de atenção — e
até lá os pesos são **priores declarados**, e o código diz isso em voz alta.

---

## 9 · A revisão externa de 2026-08-10 — cinco bugs, todos reproduzidos

Diferente das oito anteriores, esta seção **não** registra ideias rejeitadas.
Registra defeitos que estavam no código e foram corrigidos. Reproduzi cada um
no próprio módulo antes de aceitar; nenhum era exagero.

**1 · O portão não era portão.** `base *= g.valor` aplicava força de portão a
QUALQUER nível dos três eixos. Medido:

```
diagnostico -> comparativo   x0,60    um passo banal na forma da pergunta
spread excelente -> ruim     x0,80    a margem real do negócio
```

**O rótulo declarado por um agente movia a nota mais que o dinheiro.** Portão
virou par `(eixo, nível)`, binário, que zera; qualquer outro nível entra na
média.

**2 · Margem negativa saía como alvo.** `spread=ruim` com todo o resto perfeito
dava **0,802 e perfil `"alvo"`** — prejuízo por construção rotulado como "lê e
paga", a decisão exata que o modelo existe para não errar. `(spread, ruim)` e
`(volume, residual)` viraram portões.

**3 · Índice e perfil se contradiziam.** `dado_unico` + resto perfeito dava
índice 0,05 e perfil `"alvo"`. `perfil()` agora consulta os portões primeiro.

**4 · O silêncio pagava mais que a honestidade.** Portão não declarado valia
0,70 — número inventado que fazia calar render **1,08x** mais que declarar
`misto`. Contradizia o princípio que o próprio módulo enuncia. Agora o eixo
não declarado simplesmente não entra, e um alerta distingue *"nenhum portão
fechou"* de *"ninguém olhou"*.

**5 · A escala de ignorância contrariava a própria medição.** As duas rodadas
cegas mediram `sei_o_que_fazer` (0,58 · 0,99) acima de `so_falta_um_dado`
(0,52 · 0,53); o código codificava 0,25 contra 0,35. Empatados em 0,30 —
inverter seria trocar um sobreajuste por outro, com erro padrão de 0,065.

### A objeção que não é bug, e é a mais séria

> *"Você aposentou a logística e manteve o desfecho."*

Rejeitamos a regressão porque `spend` prevê `lucro > R$3.000` com AUC 0,971.
**E medimos a escada de ignorância, os portões e as refutações de Kahneman e
Loewenstein contra esse mesmo alvo.** Régua contaminada contamina tudo que se
mede com ela.

Sobrevive **um** achado: `(engajamento, dado_unico)`. Os 9 temas somaram
R$ 138.814, ~R$15k cada — **acima da mediana dos vencedores**. Passaram pelo
filtro de verba e perderam assim mesmo, então o viés de seleção não os alcança.

E cai uma pretensão minha: `curiosidade pura = 0%` é **0 de 11**, IC de Wilson
até 0,26, p≈0,09 contra base de ~20%. Chamei de "o achado mais limpo da base"
o que é indício. Continua como portão pela plausibilidade do mecanismo, e o
código diz isso.

**O que fica pendente:** calibrar contra uma RAZÃO — segundos de anúncio
visível por real de clique, ou RPC/CPC — em vez de lucro. `spend` não pode
prever razão por construção, e é a única saída de raiz da circularidade.

### O que eu acrescentei à revisão

A trava de **proveniência**. Os portões de `spread` e `volume` só disparam com
dado MEDIDO. Na fase de descoberta os dois são palpite de LLM, e deixar um
número inventado matar um tema é o mesmo erro, do outro lado.

---

## 10 · A segunda revisão externa — PARE, e três motivos independentes

Veredito: **REJECT**. Não do modelo inteiro — do **rótulo intrínseco por
entidade** e do afinamento do índice de dez eixos. O roteamento de widget por
página fica.

### 1 · O construto não existe, e estávamos EM CIMA do acaso

Eu reportei "33% contra 20% de acaso". Os 20% são o **piso**, válido só se os
cinco rótulos fossem uniformes. Com a distribuição observada, o acaso é `Σpᵢ²`:

```
comparativo 0,45 · condicional 0,35 · sequencial 0,10 · dado_unico 0,05 · diagnostico 0,05
acaso esperado ......... 34,0%
medido entre rodadas ... 33,3%
três frases concordando  4,7%  (acaso 4,0%)
```

**Zero informação, medido duas vezes.** A minha régua fez um resultado nulo
parecer sinal fraco.

E o limiar de 83% não foi só "não atingido": com estabilidade real de 83%,
P(X≤6 em 12) ≈ 0,0088. É evidência contra, não ausência de evidência a favor.

### 2 · A justificativa econômica era falsa, e o número estava neste repositório

O portão existia para poupar mineração. `sensores/dataforseo.py:15` documenta:

```
Google Ads volume + CPC   $0,06/tarefa, até 1000 keywords
                          → $0,00006 por keyword    (~$0,25 por ciclo)
```

**Um falso negativo custa uma oportunidade de quinze dias; minerar custa vinte
e cinco centavos.** Argumentei por várias rodadas que barrar antes de minerar
era economia direta, contra um número que estava no nosso próprio arquivo. Não
era preciso teste nenhum — bastava ler.

A economia legítima fica **entre a sondagem e os quinze dias de produção**,
nunca antes da sondagem.

### 3 · Dois eixos estavam documentados como medidos e não são

`densidade` sai de `_DENSIDADE_POR_BAIRRO`, tabela de onze categorias IAB
escrita à mão em `grafo/prescrever.py`. `formato_consumo` sai de um mapa de
país. Os dois apareciam do lado "medido pelo DataForSEO" no README e no
ARQUITETURA — proxy manual com prior 0,70, o mesmo do `spread` observado.
Corrigido: os dois saíram das duas colunas.

### O erro de unidade que eu quase repeti

`nivel_spread(cpc_usd, rpm_usd)` calculava `rpm_usd / cpc_usd`. A intenção era
receita por SESSÃO — os testes usavam 0,30 contra 0,10 —, mas **RPM, por
convenção, é receita por MIL**, que é o número que o GAM mostra. Quem ligasse o
RPM do Ad Manager produziria spread **mil vezes maior**, e todo tema pareceria
excelente. O parâmetro virou `receita_por_sessao_usd`, com teto de sanidade que
levanta `ValueError`. Erro silencioso por natureza: produzia número plausível.

### Outra correção minha, aceita

Escrevi que "spend não pode prever uma razão por construção". **Errado.** Ele
não entra algebricamente na razão, mas orçamento e parada adaptativos dependem
dos resultados iniciais — então spend prevê a razão de qualquer forma. Alvo em
razão **não** é imune; precisa de exposição inicial comum ou regra sequencial
fixada antes.

### O que sobrevive, nomeadamente

- **"responda antes de rotular"** — resolve um erro real, mas só onde o objeto
  já está definido: a PÁGINA. Está no lugar certo em
  `funnel-forge/.../declarador_engajamento.jinja`.
- **A trava de proveniência** de `spread` e `volume` — impede palpite de matar tema.
- **`_CALIBRACAO` vazio** — não fingir precisão enquanto o alvo é inadequado.

### A regra de retomada

Só volta com **desfecho medido na unidade certa**, que não é a entidade nem a
página isolada: é **cluster de consulta × página × país × período**.

1. Registrar consulta/cluster, página, clique pago, CPC, pageviews, impressões
   viewable e receita.
2. **Exposição inicial comum** — mesmo número de cliques, ou regra sequencial
   fixada antes — para o spend parar de codificar a decisão da equipe.
3. Avaliar **receita por clique ÷ custo por clique** e **segundos viewable por
   clique**, em holdout de entidades. Nunca lucro absoluto.
4. Só então testar se `share_dado_unico` acrescenta algo além de CPC, RPM e volume.
5. Só promover a portão com replicação **fora** dos nove temas originais.
