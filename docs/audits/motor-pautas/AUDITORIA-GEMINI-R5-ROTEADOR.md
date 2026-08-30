# GEMINI — REABERTURA POR PREMISSA FALSA

> Auditoria datada: evidência de revisão, não contrato de runtime.

> Encerramos a auditoria e você respondeu "NÃO há mais nada além de refinamento
> de prompt". Isto não contradiz aquilo: um FATO que nós te demos estava errado,
> e ele é justamente o que fez você matar a sua própria melhor contribuição.

---

## 1 · O FATO ERRADO, E ele era nosso

Na rodada 1, item 7.2, você escreveu a melhor frase de todas as auditorias que
rodamos: que quem lucra com consulta de registro pessoal opera com **ferramentas
interativas / widgets de captura** ou fluxos de múltiplos passos, e que em artigo
de texto puro o portão detecta *"uma incompatibilidade fatal entre a intenção do
usuário e o formato do publisher"*.

Nós desenvolvemos isso na rodada 2 e você **matou**, com esta justificativa:

> *"O operador possui 1 site, capacidade para 2 a 3 publicações por mês e **zero
> engenheiros de software dedicados a desenvolver widgets interativos ou
> calculadoras personalizadas por tópico**. Se a Etapa 2 recomendar 'faça uma
> calculadora' para um tema dado_unico, o operador não terá como executar a
> recomendação (...). O ROTEADOR É FANTASIA OPERACIONAL."*

**O operador produz widget.** O agente redator dele já coloca widgets HTML —
calculadoras, simuladores — nas páginas de solução do funil. A restrição que
você usou para matar o roteador não existe.

O erro é nosso: o dossiê descrevia a operação como quem só publica artigo
estático. Você raciocinou corretamente sobre um fato falso. Por isso a
reabertura é de UM ponto, não da auditoria.

---

## 2 · O QUE ISSO REABRE

Dois estados negativos do motor assumem em silêncio que **a página é um artigo
de texto**, e a premissa nunca foi declarada:

**O portão `dado_unico`** — dispara quando `ramos_de_acao <= 1` e não sobra
decisão. "A resposta esgota em segundos." Zera o índice do tema.

**O perfil `mercado_rico_sem_leitura`** — economia alta, demanda humana baixa.
Na tela ele lia *"paga bem e não pagina"*, o que o operador interpretou, com
razão, como veto.

Se o formato pode mudar, os dois deixam de ser vereditos sobre o ASSUNTO e
passam a ser vereditos sobre **assunto × formato**. E o motor tem uma decisão a
mais para tomar, não uma a menos.

---

## 3 · A HIPÓTESE QUE ESTAMOS DESENHANDO

Que a discriminação já está nos 8 observáveis, sem medição nova:

```
ramos <= 1  +  condicoes_pessoais >= 2  +  NÃO oficial_fecha_sozinho
    -> a resposta é um CÁLCULO sobre os dados dela, e o canal oficial não
       resolve. É FERRAMENTA. "Quanto vou receber de FGTS?" esgota como artigo
       (um número) e é uma calculadora perfeita.

ramos <= 1  +  condicoes_pessoais >= 2  +  oficial_fecha_sozinho
    -> o balcão oficial já faz a conta. Sua ferramenta não adiciona nada. Morte.

ramos <= 1  +  condicoes_pessoais <= 1
    -> a resposta é a mesma para todo mundo. Lookup puro. Morte.
```

Os 8 observáveis, para você não precisar reabrir os arquivos:

```
condicoes_pessoais        0-3   quantos fatos da situação DELA a resposta exige
ramos_de_acao             1-3   quantos caminhos levam a AÇÕES diferentes
fontes_oficiais           1-3   quantos órgãos/sistemas distintos a resposta cita
decisao_apos_resposta     bool  sobra decisão real depois de responder?
oficial_fecha_sozinho     bool  o canal oficial resolve a pergunta inteira?
regra_mudou_recentemente  bool  mudança de regra/prazo nos últimos 12 meses
stake                     bool  há algo concreto em jogo?
descobre_que_existe       bool  ela descobre NESTA página que a coisa existe?
```

---

## 4 · AS PERGUNTAS

**4.A — Você retira a sentença "o roteador é fantasia operacional"?**
Diga sim ou não. Se retirar, diga o que muda na sua recomendação de 5.C/5.D.
Se mantiver, o argumento tem de ser outro que não a capacidade de produção —
essa caiu.

**4.B — A economia do formato se sustenta?**
Esta é a pergunta em que você é insubstituível, e ela é mais difícil do que a
narrativa sugere. Você descreveu: artigo sobre resposta seca → o leitor sai em
1,5s, sem Active View (50% dos pixels por 1s), sem refresh (30s in-view), RPM de
sessão perto de zero, mais Smart Pricing rebaixando o domínio. E widget → 25-40s
de interação, refresh disparado, impressão viewable, Quality Score melhor
baixando o CPC de compra.

Mas: **uma calculadora prende 30 segundos e gera UMA pageview. Um artigo
comparativo gera três pageviews de 10 segundos.** Qual ganha em **RPM de
SESSÃO**, que é o numerador do negócio? Ad refresh compensa a pageview perdida,
ou o inventário por sessão cai mesmo assim? Responda com o que você sabe da
mecânica de GAM/AdSense, não com plausibilidade.

**4.C — Quantos formatos, e quais?**
Cada formato a mais é custo real de produção. Qual é o conjunto MÍNIMO que muda
a ação do operador na segunda-feira? Nomeie-os e diga qual observável discrimina
cada um. Suspeite de qualquer taxonomia elegante que colapse em dois na prática.

**4.D — Existe o meio-termo?**
Entre artigo de texto e calculadora funcional há tabela consultável, checklist
com estados, comparador lado a lado, passo a passo com progresso. Algum deles dá
a maior parte do ganho de retenção com uma fração do risco? Note que calculadora
errada sobre benefício do INSS é problema sério — retenção comprada com
imprecisão é passivo, não ativo.

**4.E — O risco que nos incomoda, e queremos que você o defenda contra nós.**
O portão `dado_unico` carrega a ÚNICA evidência empírica do motor: 9 temas do
mesmo arquétipo, R$ 138.814, prejuízo líquido. Transformá-lo em roteador
**afrouxa a única proteção medida que existe**, e troca evidência por elegância —
que é o pior negócio possível aqui.

Existe desenho que abra a porta do formato **sem** afrouxar a proteção? Por
exemplo: o portão continua zerando, e o roteador só muda o TEXTO na tela e a
instrução que desce para a Etapa 4, sem tocar no índice. Isso é covardia ou é a
resposta certa?

---

## 5 · REGRAS

- **Português do Brasil.** Numere as respostas (4.A a 4.E).
- **Não reabra o resto.** As outras conclusões da rodada 4 estão fechadas e
  implementadas. Este documento é sobre um ponto só.
- **Nenhum número sem procedência.** Você já entregou coeficientes estimados sem
  rótulo uma vez; aqui, estimativa vem escrita como estimativa.
- **"Não sei" é resposta.** Especialmente em 4.B, onde plausibilidade é fácil e
  a mecânica de leilão é específica.
- **Não capitule por educação.** Se depois de saber que o operador produz widget
  você ainda achar que o roteador não vale, o valor está em você sustentar isso.
