# Motor de pautas

Decide **o que escrever, em qual país, e por quê** — não como escrever, que é
trabalho do Pautador.

Autocontido: só stdlib, nenhuma dependência de `forge/`, e nada em `forge/`
depende daqui. A separação é deliberada, para que o trabalho de campanha e o de
pauta evoluam sem se derrubar.

```bash
python -m motor_pautas.cli --eixos        # os 10 eixos e níveis válidos
python -m motor_pautas.cli --espaco       # smoke test da pontuação
python -m motor_pautas.cli --grafo        # estado do grafo
python -m motor_pautas.cli --prescrever   # a prescrição do dia
python -m pytest motor_pautas/testes -q   # 54 testes
```

## A ideia em uma linha

```
o que está acontecendo no mundo  ×  como o ser humano reage  =  pauta agora
        (muda todo dia)                 (não muda nunca)
```

O lado direito é o ativo, e é o que este motor guarda. O lado esquerdo é fluxo
que qualquer um compra.

## O que ele NÃO faz

Não decide verba, não sobe campanha, não tem stop-loss. **Sugere pauta.** Quem
decide é o operador, e por isso a saída é *posição no espaço com motivo*, nunca
probabilidade calibrada — o que serve a quem decide é saber por que um tema está
bem ou mal colocado.

## Os dez eixos

Cada tema é um ponto num espaço de dez eixos em três famílias. Combinação por
**média geométrica ponderada**, porque a economia é multiplicativa: um eixo perto
de zero derruba o produto.

### A · DEMANDA HUMANA — por que ela busca, e sobretudo por que ela LÊ

| eixo | o que mede |
|---|---|
| `ignorancia` | o buraco de conhecimento que ela carrega ao chegar |
| `engajamento` | quanto tempo de atenção a resposta EXIGE |
| `opacidade` | o quanto a instituição esconde |
| `reposicao` | entra gente nova na condição, ou é a mesma voltando? |

### B · ECONOMIA — quanto a atenção vale e quanto custa comprá-la

| eixo | o que mede |
|---|---|
| `volume` | quantas pessoas por mês |
| `spread` | RPM ÷ CPC, no nível arquétipo × país |
| `densidade` | quantos setores pagariam para falar com essa pessoa |
| `formato_consumo` | naquele país, "como fazer" acontece em texto ou em vídeo? |

### C · POSIÇÃO — dá para entrar, e a que custo

| eixo | o que mede |
|---|---|
| `vacuo` | quantos já explicaram bem |
| `producao` | custo de manter a página viva |

## Os três portões

Portão **multiplica** o resultado inteiro. Não é peso — descreve pré-condição, e
pré-condição não negocia com outra dimensão.

```
engajamento = dado_unico        a resposta esgota em segundos, o anúncio não
                                chega a ficar visível
ignorancia  = nao_preciso...    não há nada em jogo
formato_consumo = video_social  o "como fazer" acontece em vídeo e mensageria;
                  ou voz        o funil de texto não fecha
```

Peso alto **não** é a mesma coisa que portão. Com dez eixos, mesmo o maior peso
vale ~15% da influência: um tema de `dado_unico` com todo o resto perfeito ainda
pontuava 0,546 antes da correção. E `formato_consumo` entrou primeiro como peso —
mesmo com prior 1,20, um país de `video_social` só perdia 1,29× para um de
`texto_busca`. Foi teste que mostrou que ambos eram portão.

## Os quadrantes

O rótulo orienta a ação; a nota, não.

```
alvo                       lê e o mercado paga
audiencia_pobre            lê muito, mercado não paga
mercado_rico_sem_leitura   paga bem, mas a página não segura
descartar                  nenhum dos dois
```

Um índice escalar esconderia a decisão: `alto volume × spread ruim` e
`baixo volume × spread ótimo` dão nota parecida e pedem ações opostas.

## O grafo

```
TENSÃO       dinheiro_esquecido
   │
ARQUÉTIPO    fundo_verba_trabalhista
   │
   ├── BR ── FGTS        ● explorado
   ├── CO ── Cesantias   ● explorado
   ├── PE ── CTS         ● explorado
   ├── CL ── ?           ○ VAZIO
   └── CA ── ?           ○ VAZIO
```

**O arquétipo é o invariante; a entidade é a pele local.** `FGTS`, `Cesantias` e
`CTS` não compartilham uma letra — compartilham a pergunta *"tem dinheiro meu
parado que eu não sei sacar?"*.

**As arestas ausentes são o produto.** Hoje: 462 células, 404 vazias, 123 delas
em arquétipos já provados em dois ou mais países.

## O ciclo diário

```
1 · CONSTRUIR    5 fontes → grafo
2 · PRESCREVER   células vazias → perguntas FECHADAS
3 · HARNESS LLM  responde as perguntas com busca        ← grafo/harness.md
4 · INTEGRAR     novas acendem · conhecidas não repetem
5 · MEDIR        DataForSEO preenche 5 dos 10 eixos     ← sensores/dataforseo.py
6 · PONTUAR      Python puro, sem LLM
7 · EMITIR       teto por ação, ou silêncio
```

A pergunta que a LLM recebe **não é** "descubra oportunidades" — é *"qual é o
nome local de `fundo_verba_trabalhista` em CA-FR?"*. Fechada, verificável, e
nunca repete porque a célula fica marcada. É isso que impede o sentinela de
devolver a mesma lista todo dia e morrer de tédio na segunda semana.

## Medido × declarado

| medido pelo DataForSEO | declarado pelo agente |
|---|---|
| `volume` · `spread` · `vacuo` · `reposicao` | `ignorancia` · `engajamento` · `opacidade` · `producao` |

⚠️ **`densidade` e `formato_consumo` não pertencem a nenhuma das duas colunas.**
Ambos saem de tabela escrita à mão — `densidade` de onze categorias IAB em
`grafo/prescrever.py::_DENSIDADE_POR_BAIRRO`, `formato_consumo` de um mapa de
país. Estavam listados como MEDIDOS, e uma revisão externa apontou: proxy
manual com peso igual ao da economia observada.

Os **três portões estão todos do lado do julgamento**. A API mede o que é
contável; o agente decide o que mata. A divisão não foi planejada — caiu assim.

Custo do ciclo diário medido com preços reais: **US$ 0,69/dia**.

## Estrutura

```
espaco.py        os 10 eixos, os 3 portões, os quadrantes
psique.py        as 7 tensões — a biblioteca de padrões, estável
iab.py           taxonomia IAB: arquétipo → categoria, vetor de propósito
cli_espaco.py    smoke test da pontuação
cli.py           ponto de entrada

grafo/
  modelo.py      nós, arestas, células, mermaid
  construir.py   monta o grafo a partir de dados/
  prescrever.py  células vazias → transpor | ativar
  harness.md     o prompt do ciclo diário

sensores/
  dataforseo.py  cliente + mapeadores resposta → nível de eixo
  fontes_br.py   fontes oficiais brasileiras (D2)

dados/           os JSONs que o grafo consome
testes/          54 testes
```

Ver [ARQUITETURA.md](ARQUITETURA.md) para o raciocínio e
[DECISOES.md](DECISOES.md) para o que foi tentado e rejeitado, com os números.
