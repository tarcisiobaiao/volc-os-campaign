# GEMINI — O PORTÃO QUE VOCÊ DEFENDEU NÃO ERA O PORTÃO

> Você respondeu bem sobre a arquitetura do roteador (4.E), e a resposta foi
> adotada. Só que ela protegia um portão que **quase nunca dispara**, enquanto
> outro — que ninguém nomeou em cinco rodadas — zerava o índice sozinho.
> Um painel adversarial encontrou, e nós reproduzimos no código vivo.

---

## 1 · O DEFEITO, REPRODUZIDO

```
entidade que RAMIFICA em 3 das 4 perguntas do PAA
uma delas tem forma de calculadora (1 ramo, 3 condições pessoais)

  share_dado_unico ......... 0,25          1 de 4 esgota
  veredito_do_portao ....... sem_portao    ← 3 passadas, unanimidade
  pergunta eleita .......... "Como calculo o valor?"
  eixo engajamento ......... dado_unico    ← 1 pergunta, 1 passada
  índice ................... 0,0
  perfil ................... descartar
```

**Dois portões no mesmo card, discordando.**

`agregar()` fazia `niveis = derivados[pergunta_mais_rica]`: os três eixos da
entidade saíam de UMA pergunta, eleita por
`carga_de_leitura = ramos + condicoes + 2·decisao`.

O `veredito` — que blindamos com três passadas e unanimidade, e que você e nós
passamos cinco rodadas discutindo — governava **uma string na tela**. Quem zerava
o índice era o eixo, tirado de uma pergunta, de uma passada, num eixo de AC1
0,64 e sem réplica.

**E a eleição é enviesada CONTRA a calculadora**, porque `carga_de_leitura` soma
`condicoes_pessoais`. Quanto mais a pergunta parece ferramenta, mais provável ela
vencer a eleição e carimbar a entidade inteira de `dado_unico`.

Medido em 200 mil entidades sintéticas de 4 perguntas: **93% dos disparos do eixo
acontecem com share < 1,00** — invisíveis ao veredito — e em **metade deles a
pergunta eleita é ela mesma a candidata a ferramenta**.

É o `DIRPF` morrendo de novo, uma camada abaixo de onde foi consertado.

---

## 2 · O QUE ISSO FAZ COM A SUA RESPOSTA 4.E

Sua arquitetura estava certa: **o portão continua zerando, o formato vira
metadado.** Ela foi adotada e não mudou.

O que mudou é o alvo. Você escreveu *"o portão `dado_unico` continua ZERANDO O
ÍNDICE — isso protege o capital do operador"*. Correto sobre o portão que você
tinha na mão. Mas o `veredito_do_portao` exige `min(shares) >= 1,0` nas três
passadas, e as três entidades reais medidas no repositório saem **todas
`limitrofe`**, nenhuma `portao`:

```
Registrato  0,75 · 1,00 · 1,00  ->  limitrofe
FGTS        0,50 · 0,25 · 0,50  ->  limitrofe
Cesantías   0,25 · 0,50 · 0,50  ->  limitrofe
```

Ou seja, o roteador que você desenhou converteria `PORTAO -> LIMITROFE` num
estado que o arquétipo do próprio motor não alcança. O mecanismo real de morte
estava no eixo, não no veredito.

---

## 3 · O CONSERTO, JÁ APLICADO

Nível que mata vem da DISTRIBUIÇÃO, nunca de uma pergunta eleita:

```python
engajamento   share >= 1,0 E n >= 3        ->  dado_unico
ignorancia    NENHUMA pergunta tem stake   ->  nao_preciso_de_nada
opacidade     não carrega portão           ->  segue vindo da representativa
```

Medido depois do conserto:

```
ramifica em 3 de 4      índice 0,000 -> 0,821    era o bug
lookup puro             índice 0,000             continua morrendo
curiosidade pura        índice 0,000             continua morrendo
uma sem stake, 3 com    índice 0,704             não morre mais por uma
n=1 abaixo do piso      não declara portão
```

**A evidência está intacta.** Os 9 temas dos R$ 138.814 são consulta de registro
pessoal e esgotam em TODAS as perguntas (share 1,0): seguem em 0,000.

Travado por um teste que varre todas as distribuições de 1 a 6 perguntas e falha
se os dois portões voltarem a discordar. 100 testes passam.

---

## 4 · AS TRÊS PERGUNTAS

**4.A — Você reconhece o defeito, e ele muda alguma coisa na sua 4.E?**
A arquitetura (portão zera, formato é metadado) sobrevive intacta ou precisa de
ajuste agora que se sabe onde a morte acontecia?

**4.B — O discriminador de ferramenta tem um vazamento medido. Como fechar?**
`condicoes_pessoais` conta **dimensão de seleção**, não entrada calculável — e o
exemplo é do próprio prompt: *"o valor do IPVA depende do estado e do ano do
veículo"* → 2. Logo `ramos <= 1 + condicoes >= 2 + NÃO oficial_fecha_sozinho`
rotearia **"consultar IPVA pela placa" para FERRAMENTA**, quando é consulta no
portal do estado.

Existe observável que separe **dimensão de seleção** (consulta uma tabela) de
**entrada de cálculo** (alimenta uma fórmula)? Ou o discriminador precisa de um
nono observável — e nesse caso, qual, e ele é contável sobre o texto da resposta
como os outros oito?

**4.C — Quantos formatos, agora que o resgate mudou de lugar?**
O painel voltou dividido: uma lente disse **2** (`artigo` ·
`artigo_com_ferramenta`, argumentando que o roteador é no fundo um booleano —
"a página tem entrada que ela manipula, ou não tem"), outra disse **5**, e os
dois críticos convergiram em **3 que se produzem + 1 que não**. Um dos críticos
observou que checklist, tabela e comparador são o **mesmo artefato** (2-3 campos
+ função + painel de saída) e que o que os distingue é o rótulo da saída — uma
frase no prompt do redator, não um formato.

Você disse 3 na rodada anterior. Mantém, com esse argumento na mesa?

---

## 5 · REGRAS

- **Português do Brasil.** Numere (4.A a 4.C). Três respostas, nada além.
- **Não reabra o que está fechado.** Isto é sobre o defeito e suas consequências.
- **Estimativa vem rotulada como estimativa.**
- **"Não sei" é resposta**, especialmente em 4.B — pode não existir observável
  que separe seleção de cálculo, e dizer isso vale mais que inventar um.
- **Não capitule por educação.** Se a 4.E não precisa de ajuste nenhum, diga.
