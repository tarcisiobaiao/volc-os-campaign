# AUDITORIA GEMINI — FECHAMENTO

> Você respondeu "NÃO" à pergunta sobre haver algo além de refinamento de
> prompt, e concordamos. Isto não abre rodada nova. É o registro do que entrou
> no código, do que foi recusado, e de um achado que apareceu ao rodar — que
> derruba uma peça que você e nós dávamos por boa. Se houver réplica a ele, é a
> única coisa que ainda vale ser escrita.

---

## 1 · O QUE ENTROU, POR SUA CAUSA

Aplicado, 97 testes passam, `tsc` e `build` limpos.

**`trechos_citados` com verificação de substring.** Cada contagem cita o recorte
da própria `resposta_literal`. O programa confere se o trecho está mesmo lá.
Medido na primeira rodada real: **100% de 16 citações conferiram** em duas
entidades — acima do seu limiar de 90%, então a trava pode ser ligada.

**Sua normalização, integral.** NFD com descarte de categoria `Mn`, minúsculas,
pontuação para espaço, colapso de espaços. Com uma exceção declarada: **ordem de
palavras não se dobra**, porque reordenar frase é reescrever, e reescrita é a
paráfrase que a conferência existe para pegar.

**Três passadas com unanimidade.** Custo de uma chamada a mais por lote.

**`regra_mudou_recentemente` exige âncora textual** — sem citação, cai para
`false` sozinho.

**Sua blindagem do `stake` (5.E), integral.** `stake=true` com `stake_qual` nulo
ou genérico não rebaixa nada: marca `stake_sem_prova` e força `limitrofe`.
Fecha a brecha sem reintroduzir o falso-kill.

**Seu teste de sobrejetividade (5.C item 1), como pytest.** Varre todo o espaço
de observáveis e falha se qualquer nível de qualquer escala ficar órfão. Teria
pego os três erros — o seu `ramos_de_acao` da rodada 1, os seus três observáveis
da rodada 2, e o item do 5.D abaixo.

---

## 2 · O QUE FOI RECUSADO, E É UM DEFEITO NOVO NO SEU 5.D

Você propôs, para contagens cuja citação falhe: *"rebaixar a contagem para o
piso (0 ou 1)"*.

`ramos_de_acao = 1` com `decisao_apos_resposta = false` **é o portão**. Rebaixar
`ramos_de_acao` ao piso por erro de citação **mata o tema** — exatamente o
falso-kill que você proíbe três parágrafos depois, no 5.E, com o argumento certo.

É a terceira ocorrência do mesmo padrão: mudar a derivação sem varrer a
consequência. E o item 1 do seu próprio checklist, aplicado antes de entregar,
teria pego.

Recusado, com teste que guarda a fronteira: **citação reprovada nunca mexe em
contagem.** Ela marca, e o marcado pode virar `limitrofe`. Nunca valor.

---

## 3 · O ACHADO DA RODADA REAL — E ELE DERRUBA O VEREDITO DE TRÊS ESTADOS

Rodamos ponta a ponta, 4 entidades, 3 passadas, PAA em cache.

```
Registrato   shares 0,75 · 1,00 · 1,00   rótulos: limitrofe, portao, portao
FGTS         shares 0,50 · 0,25 · 0,50   limitrofe, sem_portao, limitrofe
Cesantías    shares 0,25 · 0,50 · 0,50   sem_portao, limitrofe, limitrofe
```

**As quatro saíram `limitrofe`.** Fomos ver por quê, e não é o modelo.

A medição é estável: as três leituras ficam dentro de **uma pergunta** de
diferença em todos os casos. O **rótulo** é que pula. Com 4 perguntas do PAA o
share só assume 5 valores, uma pergunta virando o move 0,25, e os limiares (0,5
e 1,0) caem dentro dessa banda:

```
share  rótulo       se UMA pergunta virar
0,00   sem_portao   [sem_portao]
0,25   sem_portao   [sem_portao, limitrofe]   ← cruza
0,50   limitrofe    [sem_portao, limitrofe]   ← cruza
0,75   limitrofe    [limitrofe, portao]       ← cruza
1,00   portao       [limitrofe]               ← cruza

4 de 8 movimentos de uma única pergunta trocam o rótulo = 50%
```

O veredito de três estados é frágil **por aritmética**, não por instabilidade do
instrumento. É a mesma classe de defeito que já aposentou a escala de cinco
níveis de `engajamento`: distinção que a medição não paga.

**O que mudou por causa disso:**

A unanimidade passou a morar no **share**, não no rótulo, e cada desfecho
automático exige unanimidade do lado que o protege do próprio erro:

```python
min(shares) >= 1,0   ->  portao       esgotou tudo em TODA leitura
max(shares) <  0,5   ->  sem_portao   nem na pior leitura chegou à metade
qualquer outra coisa ->  limitrofe    o humano lê o número e decide
```

`sem_portao` **não** exige share zero — toda entidade rica tem uma pergunta de
lookup no PAA, e exigir zero mandaria toda entidade boa para revisão, que é o
mesmo erro na direção contrária.

E a tela inverteu: **o número lidera, o rótulo virou chip pequeno.** Onde havia
`⛔ NÃO CONSTRUA` em caixa alta, agora há `3 de 4 perguntas se esgotam` com as
três leituras marcadas numa faixa de 0 a 1, os limiares desenhados, e a banda
entre a menor e a maior leitura sombreada. Ver o limiar cair dentro da banda é o
argumento inteiro, e ele fica visível sem precisar de legenda.

---

## 4 · O QUE FICOU RESOLVIDO SOBRE O PARADOXO DO DADO PRÓPRIO

Você, o painel e nós convergimos em "puxe o GAM". O operador apontou o furo, e
ele é real: **o motor existe para entrar em nicho e país onde ele nunca rodou.**
Lá não existe dado próprio por definição. Dado próprio calibra o QUANTO; ele não
decide o SE de um mercado onde não se esteve.

A saída estava num eixo ambíguo que já existia. `nivel_vacuo` devolve `virgem`
(valor 1,00, o topo) quando a SERP é da fonte oficial e quase não há portal — e
`virgem` comporta duas leituras opostas. Elas se separam por **estrutura de
mercado**, que é pública, não usa LLM e não usa histórico:

```
virgem + há leilão + nenhum publisher com tráfego  ->  DESCOBERTA
        alguém PAGA por essa atenção e ninguém montou conteúdo em cima
virgem + NÃO há leilão                             ->  DESERTO
        ninguém paga: o topo do eixo é miragem, não é espaço livre
virgem + publisher COM tráfego real                ->  OCUPADO
        alguém já vive disso; a pergunta muda de "existe?" para "eu ganho dele?"
```

Está no código como `leitura_do_vazio()`, **reportando e não decidindo** — a
ligação entre "há leilão" e "a página monetiza" é plausível e não foi medida.

---

## 5 · A SEQUÊNCIA, E ELA NÃO PASSA MAIS POR LLM

1. Publicar o primeiro funil e gravar a predição do motor **antes** do desfecho,
   com data e hash do commit.
2. Anexar RPM de sessão e CPC realizado quando existirem.
3. Rodar o motor nos ~15 vencedores históricos, com a sua regra escrita antes:
   matar 1 ou mais reprova o portão; matar 0 passa no filtro de verossimilhança
   (`P(X=0 | p=0,20) = 0,035`) — o que **não é validação, é ausência de
   refutação**.

---

## 6 · A ÚNICA COISA QUE AINDA VALE VOCÊ ESCREVER

Não responda o documento inteiro. Se houver réplica, que seja a **um** destes:

**A** — A regra de unanimidade da seção 3 (`min >= 1,0` mata, `max < 0,5`
aprova) está certa, ou existe assimetria melhor? Note que ela é deliberadamente
frouxa para aprovar e apertada para matar.

**B** — Com 4 perguntas do PAA a grade do share é grossa demais para três
estados. Pedir mais perguntas ao PAA (5, 6) refinaria a grade — ou traria cauda
que não muda distribuição e só encarece?

**C** — O `leitura_do_vazio` da seção 4: a ligação entre "há leilão na SERP" e
"a página monetiza" é defensável como indício público, ou é a mesma classe de
salto que os 9 temas do mesmo arquétipo?

Se nenhum dos três merecer réplica, responda apenas isso. Encerrar limpo vale
mais que uma rodada de aparência produtiva, e você já mostrou saber fazer isso.
