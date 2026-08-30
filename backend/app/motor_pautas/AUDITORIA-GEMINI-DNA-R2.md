# AUDITORIA GEMINI — RODADA 2

> Continuação direta da rodada 1. Você já leu os arquivos; eles não mudaram.
> Este documento contesta a sua resposta.

---

## 0 · O QUE MUDOU DESDE A SUA RESPOSTA

Sua resposta foi a melhor das três auditorias externas, e por um motivo
específico: foi a única que trouxe **mecanismo com número** (Active View 50%/1s,
refresh 30s in-view, Smart Pricing atacando os dois lados da razão). Isso não vai
se repetir abaixo, então registre agora, porque o resto deste documento é ataque.

Três coisas aconteceram:

1. **Um dos números que te entregamos estava mal comparado, e ele é justamente o
   que sustenta a sua recomendação central.** Seção 1.
2. **O prompt que você escreveu quebra o motor que ele deveria alimentar.**
   Seção 2.
3. **Uma fonte de dados nova entrou na mesa.** Seção 6.

Você não está sendo convidado a concordar. Se a seção 1 estiver errada, diga que
está errada e mostre por quê — capitular a uma correção sem checá-la seria o
mesmo defeito que você acusou neste projeto.

---

## 1 · A CORREÇÃO QUE DERRUBA A SUA RECOMENDAÇÃO CENTRAL

Você recomendou **eliminar a taxonomia de tensões da Etapa 2** e movê-la para a
Etapa 4. O argumento foi a baixa confiabilidade: 63%, com moda migrando.

Aquele 63% era **concordância crua**, e comparava escalas de tamanhos diferentes.
Uma escala binária enviesada concorda consigo mesma por sorte quase metade do
tempo; uma escala de 8 valores espalhados, quase nunca. Refizemos a conta
descontando o acaso (concordância esperada = probabilidade de 3 sorteios
independentes caírem no mesmo valor, usando as marginais observadas).

**3 execuções independentes, input fixo (mesmo PAA em cache, mesmo prompt),
42 perguntas comparáveis:**

| eixo | nº de níveis | concordância crua | esperada por acaso | **kappa** |
|---|---|---|---|---|
| engajamento, 5 níveis | 5 | 45% | 9% | 0,40 |
| engajamento, colapsado | 2 | 67% | 43% | **0,41** |
| ignorância | 6 | 74% | 38% | 0,58 |
| opacidade | 4 | 60% | 10% | 0,55 |
| **tensão** | 8 | 74% | **4%** | **0,73** |

Três consequências:

**1.1** — **A tensão é o traço MAIS confiável do motor**, não o menos. A sua
recomendação de matá-la da Etapa 2 estava apoiada numa comparação injusta que
**nós** te entregamos.

**1.2** — **O colapso de 5 níveis para 2 comprou quase nada.** Kappa foi de 0,40
para 0,41. A concordância crua subiu 22 pontos porque a escala ficou degenerada,
não porque ficou confiável.

**1.3** — Mas há um contra-argumento, e você tem de julgá-lo em vez de aceitar a
tabela: **o paradoxo do kappa**. Kappa castiga marginais enviesadas por
construção, e um portão **deve** ser enviesado — ele dispara em ~20% dos casos
por desenho. Então 0,41 provavelmente subestima o binário, e comparar kappa entre
escalas de 2 e de 8 níveis pode ser tão injusto quanto comparar concordância crua,
só que na direção contrária.

**RESSALVA DE AMOSTRA, e ela é séria:** estas são 3 execuções NOVAS. Nas 3
execuções anteriores, os mesmos eixos deram 51% / 79% / 77% / 65% / 63% de
concordância crua. O binário caiu de 79% para 67% e a tensão subiu de 63% para
74% **só trocando as execuções**. Com n≈42, a própria estimativa de
confiabilidade tem barra de erro larga.

### PERGUNTAS 1.A a 1.D — responda uma a uma

**1.A** — Kappa é a métrica certa para comparar estes cinco eixos entre si? Se
não é, qual é, e refaça o ranking com ela. Se a resposta correta for "nenhuma
métrica única compara escalas de tamanhos diferentes", diga isso e proponha como
decidir sem ranking.

**1.B** — Com a correção na mesa, você **mantém ou retira** a recomendação de
eliminar a tensão da Etapa 2? Retirar não é vergonha; manter sem enfrentar a
tabela é.

**1.C** — Quantas execuções e quantas perguntas seriam necessárias para estimar
essa confiabilidade com precisão suficiente para decidir? Dê o número, e o custo
em chamadas de LLM.

**1.D** — Existe um desenho de medição que **contorne** o problema em vez de
resolvê-lo? Por exemplo: em vez de exigir que o eixo seja estável, exigir que a
DECISÃO seja estável (rodar 3× e usar só o que 3/3 concordam, tratando o resto
como abstenção). Isso troca cobertura por confiabilidade. Vale a troca aqui?

---

## 2 · O PROMPT QUE VOCÊ ESCREVEU QUEBRA O MOTOR

Dois defeitos, e o primeiro é fatal.

**2.1 · Você removeu `ramos_de_acao`, e o portão é derivado dele.**

A regra do portão colapsado, em `ficha.py`:

```python
if f.ramos_de_acao <= 1 and not f.decisao_apos_resposta:
    return "dado_unico"        # PORTÃO — zera o índice
return "sustenta"
```

Seu prompt entrega `condicoes_pessoais`, `decisao_apos_resposta` e
`sobra_acao_editorial`. Sem `ramos_de_acao`, a regra cujo 79% (agora 67%) você
citou como aceitável **não pode ser computada**. Você propôs um prompt que não
produz o número em que se apoiou.

**2.2 · `sobra_acao_editorial` é juízo, não contagem.**

Você escreveu: *"Existe algum desdobramento explicativo **necessário** após o dado
principal?"*. Necessidade é julgamento. O princípio central deste desenho é
**contar, não julgar** — e ele existe porque a versão anterior, que pedia
julgamento, mediu 67% de estabilidade e foi aposentada. Você reintroduziu
exatamente a classe de coisa que o desenho existe para impedir.

### PERGUNTAS 2.A a 2.C

**2.A** — Reescreva o prompt **de novo**, agora com uma regra dura: todo campo
tem de ser respondível apontando para um trecho literal da `resposta_literal`. Se
um observável não passa nesse teste, ele não entra. Diga quais dos observáveis
atuais reprovam.

**2.B** — Se o corte de 8 observáveis para 3 exige mudar a regra de derivação do
portão, **escreva a nova regra em Python**, e diga o que se perde. Não deixe o
motor sem portão computável.

**2.C** — Você propôs `sobra_acao_editorial` para capturar alguma coisa. Que
coisa? Existe versão dela que seja contagem verificável em vez de juízo?

---

## 3 · O SEU TESTE NÃO PODE DECIDIR NADA

Você propôs: rodar nos 9 perdedores e 9 vencedores; refutado se não sinalizar
parada em ≥8 dos 9 perdedores E aprovar ≥7 dos 9 vencedores.

Dois problemas, já identificados por outra auditoria antes de você:

**3.1 · Circularidade.** O portão foi **derivado** dos 9 perdedores. Acertá-los é
tautológico. A única amostra que traz informação nova são os vencedores.

**3.2 · Potência.** Com ~15 vencedores e uma taxa real de falso-kill de 10%, o
resultado "0 de 15" ocorre em 21% das rodadas por acaso. O desfecho **mais
provável** do seu teste é indistinguível de ruído, e seria lido como validação.

### PERGUNTAS 3.A e 3.B

**3.A** — Redesenhe o teste com potência declarada. Diga: qual hipótese, qual n
mínimo, qual a regra de decisão, e **qual resultado seria compatível com o acaso**
e portanto não autoriza conclusão nenhuma.

**3.B** — Se n=15 não paga nenhuma conclusão forte, o teste retrospectivo deve
ser rodado mesmo assim? Argumente pelos dois lados. Se sim, com que leitura
permitida?

---

## 4 · COISAS QUE VOCÊ AFIRMOU E TEM DE VERIFICAR OU RETIRAR

**4.1** — Você citou **US$ 0,09 por chamada** do `ad_traffic_by_keywords`. Não
conseguimos confirmar esse preço. Ele é a base inteira do seu argumento de mover
o endpoint para a Etapa 3. Confirme, corrija ou marque como não verificado — e
diga se o argumento sobrevive caso o preço seja outro.

**4.2** — Você abriu o veredito com **"corta 73% do custo da API"**. O operador
faz 2 a 3 funis por mês. Custo por card nunca foi restrição — economizar sete
milésimos de dólar por card não decide nada. Por que essa métrica liderou a sua
resposta? Se foi reflexo, diga; se há um argumento, faça-o.

**4.3** — Você afirmou que o PAA volta vazio em consultas navegacionais porque o
Google entende que a pessoa quer um destino. **Qual é o teste mais barato que
confirma ou refuta isso com dado que se possa coletar hoje?** Ele é a base do
traço R2 que você propôs, e no momento é asserção.

---

## 5 · O QUE VOCÊ ENTERROU E É A SUA MELHOR CONTRIBUIÇÃO

No meio da resposta 7.2 você escreveu que quem lucra com consulta de registro
pessoal no Brasil opera com **ferramentas interativas / widgets de captura** ou
**fluxos de múltiplos passos** — e que em página de artigo em texto puro o portão
detecta *"uma incompatibilidade fatal entre a intenção do usuário e o formato do
publisher"*.

Isso reenquadra o portão inteiro. Ele não detecta **assunto ruim**. Detecta
**formato errado para aquela intenção**. Dado que este operador publica artigo, o
portão está certo; se ele construísse a ferramenta, estaria errado.

E isso muda o **produto**, não só o motor: a Etapa 2 poderia deixar de responder
"aprovar / rejeitar" e passar a responder **"qual formato este tópico exige"**.

### PERGUNTAS 5.A a 5.D

**5.A** — Desenvolva. Quais são os formatos possíveis (artigo longo, ferramenta
interativa, calculadora, tabela consultável, passo a passo com estados,
comparador), e **qual observável da ficha discrimina entre eles**?

**5.B** — A economia muda com o formato? Uma calculadora sobre um tópico
`Know Simple` monetiza melhor que um artigo sobre o mesmo tópico — e se sim, por
qual mecanismo exato (mais pageviews? mais tempo in-view? mais refresh de
anúncio? mais ad requests por sessão)?

**5.C** — Se a Etapa 2 passar a recomendar formato em vez de vetar tópico, o que
acontece com o portão? Ele vira um roteador em vez de um veto? Argumente contra
essa ideia antes de argumentar a favor — o operador tem capacidade de produzir 2
a 3 páginas por mês e não tem equipe de produto para construir ferramentas.

**5.D** — Se a resposta honesta for "ele só sabe fazer artigo, então o veto está
certo e o roteador é fantasia", diga isso. É uma resposta válida.

---

## 6 · FONTE NOVA — GOOGLE ADS TRANSPARENCY CENTER

O operador quer usar o **Google Ads Transparency Center** (adstransparency.
google.com), acessado via um scraper do Apify, para ter "uma prévia da
concorrência e da oportunidade de um tópico".

**Nossa leitura, que pode estar errada e que você deve corrigir:** o Transparency
Center é centrado em **anunciante**, não em keyword. Busca-se um anunciante ou
domínio e veem-se os criativos dele, por região e período. Ele não responde "quem
dá lance nesta palavra-chave" — o que faria da premissa do operador o mesmo tipo
de erro que ele cometeu com o `ad_traffic_by_keywords`.

Mas há valor numa direção diferente da imaginada: **criativo que roda há seis
meses é campanha lucrativa** — ninguém sustenta anúncio perdedor. Persistência de
criativo seria sinal de profundidade de monetização do vertical, ou seja, o lado
do **RPM**, não do CPC.

### PERGUNTAS 6.A a 6.E

**6.A** — Nossa leitura do Transparency Center está correta? O que exatamente ele
permite consultar, e o que **não** permite? Seja específico sobre os filtros
disponíveis.

**6.B** — Dá para chegar de uma **keyword** a uma lista de anunciantes por esse
caminho, ou só o inverso (de anunciante para criativos)? Se só o inverso, existe
uma ponte prática — por exemplo, colher os domínios dos resultados pagos da SERP
e depois consultar cada um no Transparency Center?

**6.C** — **Persistência de criativo é mesmo sinal de lucratividade?** Quais são
os falsos positivos (campanha de marca que roda por brand awareness sem ROI
direto, teste de longa duração, anunciante grande com verba insensível)?

**6.D** — Para arbitragem, densidade de anunciante é **ambígua por natureza**:
muito anunciante encarece o clique que se compra e enriquece o leilão que paga a
página. O Transparency Center ajuda a separar esses dois efeitos, ou os confunde?
Se ajuda, como?

**6.E** — **Vale a pena?** Compare com o que já se tem: contagem de resultados
pagos na SERP (já coletada, custo zero adicional) e `competition_index` do
Google Ads (0-100, já disponível). O Transparency Center adiciona sinal ou
adiciona trabalho? Se a resposta for "adiciona trabalho", diga.

---

## 7 · O QUE SERÁ FEITO INDEPENDENTEMENTE DA SUA RESPOSTA

Não reproponha estes; eles já estão decididos. Estão aqui para você não gastar
resposta neles e para poder contestá-los se achar que estão errados.

- **Puxar do GAM e do Google Ads os 24 temas de desfecho conhecido**, com Active
  View % viewable impressions, ad requests vs. matched impressions, eCPM por
  sessão e páginas/sessão. Três auditorias independentes convergiram nisso.
- **Tirar o índice escalar da superfície de decisão.**
- **Manter o log de predição→desfecho** a partir do próximo funil.
- **PAA vazio não deriva eixo** (já corrigido; era abstenção). Sua contribuição
  de tratá-lo também como **sinal próprio** será incorporada.

---

## 8 · FORMATO DA RESPOSTA

Responda **numerado, na ordem das perguntas** (1.A, 1.B, ... 6.E). Sem
preâmbulo, sem resumo, sem elogio, sem plano de implementação por semanas.

Ao final, três blocos:

**A · O PROMPT** — `ficha_de_resposta.md` reescrito de novo, corrigindo 2.1 e
2.2, pronto para colar. Se a sua conclusão da seção 1 for que a tensão volta, ela
tem de estar nele.

**B · A REGRA EM PYTHON** — a derivação dos eixos a partir dos observáveis do seu
prompt. Código, não descrição.

**C · A MUDANÇA DE IDEIA** — liste explicitamente o que você afirmou na rodada 1
e agora retira, e o que você **mantém apesar da contestação**, com o motivo. Se
não houver nada nas duas listas, você não leu este documento.

---

## 9 · REGRAS

- **Português do Brasil.**
- **Não capitule por educação.** Se a seção 1 estiver errada, o valor está em
  você mostrar isso, não em concordar. Uma auditoria que muda de opinião a cada
  empurrão não vale nada.
- **"Não sei" é resposta aceita.** Plausibilidade inventada não é.
- **Não proponha nada que dependa de dado que não existe.** Não há log de
  desfecho por tema. Proposta que dependa disso é proposta para daqui a seis
  meses, e tem de vir marcada assim.
- **Não some com o que você acertou.** O mecanismo do portão (7.2), o
  `Know Simple` das Quality Rater Guidelines (7.3) e o PAA vazio como sinal (7.1)
  foram as três melhores contribuições da rodada 1. Se você as abandonar agora
  para acomodar as críticas, terá piorado.
