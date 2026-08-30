# AUDITORIA GEMINI — RODADA 3 · TRÉPLICA

> Auditoria datada: evidência de revisão, não contrato de runtime.

> Sua rodada 2 foi conferida linha a linha contra o código e contra os dados
> brutos. Este documento diz o que se confirmou, o que se aplicou, o que se
> recusou, e por quê. Depois faz cinco perguntas.

---

## 0 · O QUE JÁ ESTÁ NO CÓDIGO, POR SUA CAUSA

Aplicado, testado (94 testes passam), `tsc` limpo:

1. **`trechos_citados`** — cada contagem cita o recorte da própria
   `resposta_literal` que a justifica. **Com um acréscimo que você não propôs:**
   o programa confere se o trecho está mesmo no texto, por busca de substring.
   Citação que não aparece na resposta é fabricação detectável.
2. **Unanimidade de 3 passadas** — o veredito só é aceito quando as três
   concordam; qualquer divergência vira `limitrofe`. Custo: uma chamada a mais
   por lote, US$ 0,01.
3. **Concordância por pergunta gravada em toda evidência** — porque o veredito
   da entidade pode bater por compensação (duas perguntas trocando de lado
   mantêm o share), e aí a instabilidade fica escondida.
4. **`regra_mudou_recentemente` exige âncora textual** — sem citação, o programa
   rebaixa para `false` sozinho.
5. **PAA vazio gravado como sinal**, com a hipótese declarada como **não medida**
   e sem poder de decisão.

O que **não** foi aplicado está nas seções 2 e 3.

---

## 1 · OS SEUS COEFICIENTES ERAM INVENTADOS

Você entregou `AC1` de Gwet e `alpha` de Krippendorff com dois decimais. Você
nunca recebeu os dados brutos — só as tabelas-resumo da rodada 1. Não havia como
computar nenhum dos dois.

Calculamos. 42 perguntas, 3 execuções, input fixo:

| eixo | **AC1 real** | você alegou | erro |
|---|---|---|---|
| ignorância | **0,81** | α ≈ 0,64 | −0,17 |
| tensão | **0,76** | AC1 ≈ 0,62 | −0,14 |
| opacidade | **0,64** | α ≈ 0,68 | +0,04 |
| engajamento binário | **0,64** | AC1 ≈ 0,59 | −0,05 |
| engajamento 5 níveis | **0,53** | — | — |

Duas coisas ao mesmo tempo, e as duas importam:

**Você acertou a conclusão.** A tensão tem 0,76 e é o segundo eixo mais
confiável. Sua retratação (1.B) estava certa. O paradoxo do kappa era real: o
binário é 0,64 sob AC1, não 0,41 sob kappa — a nossa tabela subestimava, como
você disse.

**E o ranking que você produziu está invertido no topo.** Você colocou opacidade
em 1º e tensão em 3º. O real é ignorância 1º, tensão 2º, opacidade empatada em
último. **O seu "DNA Mínimo" foi construído sobre esse ranking invertido.**

Também resolve a disputa que abrimos: o colapso de 5 para 2 estados foi de
**0,53 para 0,64**. Ganho real de 0,11 — nem os 28 pontos que a concordância
crua sugeria, nem o 0,01 que o kappa sugeria.

---

## 2 · O SEU CÓDIGO DERRUBOU OS DOIS MELHORES EIXOS

Varremos todas as entradas possíveis do seu prompt contra a escala declarada em
`espaco.py`. Sua derivação deixa **4 de 12 níveis inalcançáveis**:

```
IGNORANCIA     4 de 6 alcançáveis
   nao_sei_se_existe        valor 1,00   ✖ INALCANÇÁVEL   ← o topo
   sei_o_que_fazer          valor 0,30   ✖ INALCANÇÁVEL

OPACIDADE      2 de 4 alcançáveis
   regra_mudou              valor 1,00   ✖ INALCANÇÁVEL   ← o topo
   clara                    valor 0,10   ✖ INALCANÇÁVEL   ← o piso
```

`opacidade` vira um eixo de dois níveis numa faixa de 0,85 a 0,60 — some
exatamente a dispersão que, na rodada 1, você mesmo apontou como o melhor
comportamento do motor. E `ignorância`, que é **o eixo mais confiável que
existe aqui** (AC1 0,81), perde o estado de maior valor.

Você removeu `oficial_fecha_sozinho`, `regra_mudou_recentemente` e
`descobre_que_existe` — e cada um deles era a **única** porta para um nível.

**O diagnóstico que motivou a remoção era bom.** Esses três de fato não eram
verificáveis por citação. Mas a receita estava errada: a solução é **ancorar**,
não apagar. Foi o que fizemos com `regra_mudou_recentemente`.

**E é a segunda vez.** Na rodada 1 você removeu `ramos_de_acao` sem ver que o
portão era derivado dele. Na rodada 2, removeu três observáveis sem ver que cada
um sustentava um nível de escala. Mesmo defeito, duas rodadas: mudar a derivação
sem varrer a consequência.

---

## 3 · O SEU `de_json` REINTRODUZ DOIS BUGS JÁ CORRIGIDOS

**3.1** — `bool(d.get("escolha_pendente_no_texto", False))`. Em Python,
`bool("false")` é `True`. O código atual recusa a ficha inteira quando um
booleano não vem como booleano JSON, e isso existe porque a ficha seria lida ao
contrário, em silêncio.

**3.2** — `max(1, min(3, int(...)))` aceita lixo em silêncio onde hoje se recusa.

Uma nuance que descobrimos ao escrever o teste, e que vale registrar porque
contradiz nossa própria documentação: os dois casos **não são simétricos**.
`int("2")` devolve `2` — o valor certo, mal embrulhado; recusar aí jogaria fora
medição boa por questão de aspas. `bool("false")` devolve `True` — o valor
**invertido**. Então número em string passa, booleano em string derruba. Estava
certo no código e estava errado no comentário; o comentário foi corrigido.

---

## 4 · O QUE VOCÊ ACERTOU, VERIFICADO

- **`CUSTO_TAREFA_GOOGLE_ADS = 0.09`** existe em `sensores/dataforseo.py:517`.
  Nossa dúvida era infundada e seu argumento de mover o endpoint para a Etapa 3
  procede.
- **O paradoxo do kappa.** Você estava certo contra nós, e agora está medido.
- **A retratação sobre a tensão** — certa, e pelo motivo certo.
- **`5.C/5.D`** — você argumentou contra a sua própria melhor ideia porque o
  operador não tem como executá-la. Foi a resposta mais honesta das três
  auditorias externas que rodamos.
- **`6.E`** — rejeitar o Transparency Center na Etapa 2. Aceito.
- **`3.B`** — o enquadramento do teste com n=15 como filtro de verossimilhança,
  com `P(X=0 | p=0,20) = 0,035`, é matematicamente correto e honesto sobre o que
  não pode concluir. Adotado.

**Um erro factual que sobrou:** seu teste de custo zero para o PAA (4.3) manda
filtrar "as 96 medições de SERP armazenadas em `dfs_result.json`". O arquivo real
é `volc_ads/dados/dataforseo-96-medicoes.json` e contém **6 descrições de sonda
de endpoint** — não 96 SERPs. O teste não é executável como descrito.

---

## 5 · AS CINCO PERGUNTAS DA TRÉPLICA

**5.A · Como você produziu coeficientes com dois decimais sem os dados?**
Não é retórica. Os erros são de −0,17 a +0,04, o que é próximo demais para ser
acaso e longe demais para ser cálculo. Se você estimou a partir dos números
crus, isso era uma estimativa e deveria ter vindo rotulada como tal. Diga o que
de fato aconteceu — a resposta muda quanto vale o resto do que você escreveu.

**5.B · Com o ranking real, o seu DNA Mínimo muda?**
Você o construiu com opacidade em 1º. O real é ignorância 0,81 · tensão 0,76 ·
opacidade 0,64 · engajamento 0,64. Refaça o corte, ou defenda o corte original
apesar do ranking.

**5.C · Duas rodadas, o mesmo defeito. Qual é a regra que te impede na terceira?**
Você derrubou `ramos_de_acao` na rodada 1 e três observáveis na rodada 2, e nas
duas vezes não viu que estava tornando níveis inalcançáveis. Não queremos um
pedido de desculpas: queremos **o procedimento** que, aplicado antes de entregar,
teria pego os dois. Escreva-o como checklist executável.

**5.D · A conferência de citação deve virar trava, e quando?**
Hoje ela mede: a taxa de citações que de fato aparecem no texto vai gravada em
toda evidência, e não barra nada. O raciocínio foi que normalização (acento,
reticências, aspas curvas) produz falso negativo, e ligar a trava antes de medir
o falso negativo reprovaria ficha boa em silêncio. Qual taxa observada
justificaria ligar a trava? E qual normalização você aplicaria para não reprovar
citação honesta?

**5.E · A assimetria que introduzimos aguenta ataque?**
`regra_mudou_recentemente` sem citação cai para `false` (é o topo de `opacidade`;
rebaixar é conservador). `stake` **não** cai por falta de citação, porque
`stake=false` é o portão `nao_preciso_de_nada` que zera o índice — rebaixar por
ausência de prova mataria o tema, e ausência de prova não é prova. Ataque isso.
Se houver caso em que a assimetria produz o erro que ela tenta evitar, nomeie.

---

## 6 · COMO SEGUIMOS, E O QUE ISSO SIGNIFICA PARA VOCÊ

Depois desta tréplica, **encerramos a auditoria por LLM.** Não é desprezo: é que
o instrumento já está medido em AC1 de 0,64 a 0,81, e isso deixou de ser o
gargalo. O que falta não é opinião melhor, é desfecho — e nenhuma rodada
adicional produz desfecho.

A sequência é:

1. **Puxar do GAM e do Google Ads os 24 temas de desfecho conhecido**, com as
   métricas que você nomeou (Active View % viewable, ad requests vs. matched
   impressions, eCPM por sessão, páginas/sessão). Custo R$ 0. É o único passo que
   testa o **mecanismo** do portão com dado próprio em vez de por proxy.
2. **Rodar o motor nos ~15 vencedores**, com a sua regra escrita antes: matar 1
   ou mais reprova o portão; matar 0 passa no filtro de verossimilhança — o que
   **não é validação, é ausência de refutação**.
3. **Log prospectivo** a partir do próximo funil: predição gravada com data e
   hash do commit, desfecho anexado depois.

**Sua última pergunta, e responda-a com franqueza:** existe alguma coisa que
você ainda tenha a dizer que **não** seja refinamento de prompt? Se a resposta
honesta for "não, o próximo ganho está nos dados dele e não em mim", diga isso.
Encerrar bem vale mais que uma rodada 4 de aparência produtiva.

---

## 7 · REGRAS

- **Português do Brasil.** Numere as respostas (5.A a 5.E).
- **Nenhum número sem procedência.** Se for estimativa, escreva "estimativa".
  Depois da seção 1, um coeficiente não rotulado será tratado como invenção.
- **Não reescreva o prompt de novo** a menos que a resposta de 5.B exija, e nesse
  caso entregue também a varredura de alcançabilidade dos níveis.
- **Não capitule por educação.** Três dos itens da seção 4 são pontos em que você
  estava certo contra nós; se algum item das seções 1 a 3 também estiver errado,
  o valor está em você mostrar.
