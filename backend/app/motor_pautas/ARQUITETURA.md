# Arquitetura — o raciocínio por trás de cada peça

Complementa o [README](README.md), que descreve o **quê**. Aqui está o **porquê**,
e o que fica pendente para quem retomar.

---

## O princípio que organiza tudo

```
o que está acontecendo no mundo  ×  como o ser humano reage  =  pauta agora
        (muda todo dia)                 (não muda nunca)
```

O lado esquerdo é commodity: DOU, calendário, Trends, News — qualquer um compra.
O lado direito é o ativo, e ele não roda: **existe**. Sete tensões, dez eixos,
uma taxonomia de arquétipos.

Um motor que só tivesse o lado esquerdo seria um leitor de notícias. Um que só
tivesse o direito seria um ensaio. O valor está no cruzamento.

---

## Três camadas, e o papel de cada uma mudou durante a construção

### `psique.py` — a biblioteca de padrões

Sete tensões destiladas dos vencedores medidos. **Descobriu-se que não é camada
de pontuação, é de transferência.**

`Cesantias` e `saque aniversário FGTS` não compartilham uma letra, mas
compartilham a pergunta *"tem dinheiro meu parado que eu não sei sacar?"*. É a
pergunta que atravessa o idioma, não o substantivo. Por isso os marcadores são
**formas interrogativas**, não palavras: `quando cai` / `cuándo cobro` /
`when do I get paid` são o mesmo objeto mental.

Medição da transferência: **93% de precisão quando lê, 1% de erro, silêncio em
80% dos nomes nus.** O silêncio é comportamento correto — nome próprio sozinho
não carrega pergunta, e a tensão precisa da descrição.

### `espaco.py` — os dez eixos

Cada eixo responde a uma pergunta sobre o mundo, não sobre uma planilha. Nenhum
menciona país, idioma ou instituição.

**Combinação geométrica, não aritmética.** Um tema com pressão máxima e resposta
que se esgota em segundos não vale a média dos dois — vale quase nada, porque a
economia é multiplicativa.

**Dimensão desconhecida fica fora da conta, nunca vira 0,5.** Preencher buraco
com meio-termo é inventar informação, e num motor de decisão isso é a falha mais
cara que existe. Abaixo de três eixos legíveis, ele recusa dar índice.

**Os pesos são priores de princípio, declarados como tal.** `_CALIBRACAO` está
vazio e há teste garantindo. Ver [DECISOES.md](DECISOES.md) §1 para por que
calibrar contra a operação-exemplo foi o erro que originou esta versão.

### `iab.py` — a ponte com quem compra

Não pontua. Ver [DECISOES.md](DECISOES.md) §5. O que ela entrega:

- **arquétipo independente de idioma** — regex é preso a uma língua; id IAB não
- **o vetor de propósito**, que já codifica a armadilha de lookup:
  `Informational → Instructional` são as páginas que ganham,
  `Utility/Online Tool` é a que responde e some
- **os órfãos** — dois arquétipos que funcionam bem não têm nó nas 704
  categorias. Nenhum comprador mira porque não há como pedir, e ninguém compete
  porque ninguém nomeou. É fosso, e com prazo: acaba no dia em que o IAB criar o nó

---

## O grafo, e por que não é tabela

Uma tabela mostra célula vazia como falta de dado. O grafo mostra como
oportunidade — e mostra a **propagação**: quando um evento acende um nó, dá para
ver quais outros países têm a mesma tensão sem ninguém atendendo.

```
nós      tensao · arquetipo · pais · entidade · evento
arestas  aciona · instancia · habita · explora · ativa
```

`explora` é a aresta que interessa: **existir ou não é o produto**.

A força de um arquétipo é medida por **presença** — em quantos países já se
provou, com nomes locais diferentes —, nunca por lucro. Presença é fato sobre o
mundo; lucro era fato sobre uma equipe.

`forca_minima=2` é deliberado: um país só pode ser sorte ou execução; dois
países com nomes diferentes é evidência de que a tensão atravessa fronteira.

---

## Por que o ciclo não roda do zero

Se todo dia uma LLM buscasse oportunidades do zero, devolveria a mesma lista —
não por ser burra, mas porque o mundo não muda tanto em 24 horas. No terceiro dia
ninguém lê, e o sentinela morreu.

O motor tem memória. A LLM só toca o **delta**, e recebe pergunta fechada:

> *"Qual é o nome local de `fundo_verba_trabalhista` em CA-FR? Equivalentes
> conhecidos: CO:cesantias · PE:cts"*

Verificável, e nunca repete porque a célula fica marcada. `sem_equivalente` é
resposta válida e fecha a célula.

**A LLM não busca oportunidade — declara eixos.** Buscar é tarefa aberta e ela
alucina; declarar é tarefa fechada com rubrica e ela acerta. Isso foi medido: a
primeira rodada de declaração falhou por concentração (`evergreen_reposicao` em
149 de 235 casos), e a rubrica ancorada da segunda tirou `densidade` de −0,035
para **+0,208**.

O que fez a diferença, e está em `grafo/harness.md`:

- **teste literal antes do rótulo** — escrever a resposta da dúvida antes de
  classificar `engajamento`. O caso canônico (`Simit`, consulta de multa) saiu
  `sequencial` na rodada 1 e `dado_unico` na 2
- **nomear antes de rotular** — escrever os setores antes de declarar `densidade`
- **o teste da gente-nova** — *"amanhã haveria pessoas novas que nunca tiveram
  essa necessidade?"* separa perene de recorrente
- **auto-verificação de distribuição** antes de entregar

---

## Medido × declarado, e por que a divisão caiu bem

| medido (DataForSEO) | declarado (agente) |
|---|---|
| `volume` `spread` `vacuo` `reposicao` | `ignorancia` `engajamento` `opacidade` `producao` |

⚠️ `densidade` e `formato_consumo` ficam FORA das duas colunas: os dois vêm de
tabela à mão, não de medição nem de julgamento ancorado. Ver DECISOES.md §10.

**Os três portões estão todos do lado do julgamento.** A API mede o que é
contável; o agente decide o que mata. Não foi planejado.

`sensores/dataforseo.py` traduz resposta em nível de eixo. Os mapeadores são
funções puras, testáveis sem rede — quem depende de rede é a borda, não a lógica.

⚠️ **As funções de rede nunca foram exercitadas contra a API real** — não havia
credencial. Os mapeadores foram testados com respostas montadas a partir da
documentação. Tratar a primeira execução real como validação, não rotina.

---

## O que fica pendente

**A ponte com o Pautador.** É o próximo passo e o que faz tudo isto entrar no
fluxo real. O contrato: um JSON com `arquetipo`, `tensao`, `entidade`, `pais`,
`eixos`, `ferramenta_sugerida` e `porque`, que o Pautador consome no lugar do
`arbitrage_score` atual.

O cabo mais direto é o `engajamento` → **qual ferramenta HTML gerar**:

```
condicional   "depende de A, B, C"     → checador de elegibilidade
sequencial    "passo 1 ao 7"           → acompanhador de etapas
diagnostico   "por que não funcionou"  → simulador de causa
comparativo   "qual opção"             → comparador
dado_unico    a resposta é um número   → não construa o funil
```

**Três endpoints que convertem palpite em medição** (do SerpApi, fornecedor
diferente do DataForSEO):

- **Related Questions (PAA)** — mede `engajamento`, que hoje é julgamento. É o
  Google dizendo como a pergunta ramifica, e é o portão mais importante
- **AI Overview** — se a Overview responde inteiro, o clique não acontece.
  Vira portão novo, e testa a crítica mais séria que o motor recebeu
- **YouTube Search** — mede `formato_consumo` por termo, em vez da tabela de
  país que eu escrevi à mão. É o eixo mais frágil e virou portão, o que torna a
  fragilidade cara

**Limitações conhecidas, para não serem redescobertas:**

- O motor assume **Google** como buscador. Na Coreia é Naver, na Rússia Yandex,
  na China Baidu. Transpor arquétipo para lá mede o leilão errado.
- Cobertura de tensão em pt/es/en. Fora disso o motor **se abstém** — e a
  abstenção é honesta, mas larga.
- `formato_consumo` por país vem de tabela escrita à mão em
  `grafo/construir.py::FORMATO_PAIS`. É estimativa, não medição.
- O grafo lê a taxonomia de arquétipos de `dados/familias_rpm.json`, mas **só os
  nomes e as regras** — há teste garantindo que o `rpm_familia` não entre.
