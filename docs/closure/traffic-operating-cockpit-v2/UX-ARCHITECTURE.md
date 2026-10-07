# UX-ARCHITECTURE — a experiência de tráfego, e o que a governa

## O princípio que decidiu tudo

> **A tela nunca decide. Ela lê o veredito e não o perde no caminho.**

Não é slogan: é o que separa este domínio de um painel administrativo. Autorização
calculada no navegador é a falha que `contrato_canais.py` foi escrito para
impedir — um `capacidades.google_mutate && manifesto.sabe_criar` em TypeScript
pareceria correto e estaria errado, porque a janela do canário recusa Display com
as duas verdadeiras.

## As duas perguntas que não são a mesma

Esta distinção organiza a aba Criar inteira:

```
manifesto  →  "este canal SABE criar?"        propriedade do CANAL
portão     →  "e EU posso criar nele AGORA,   propriedade da SESSÃO,
               e se não, por quê?"             do SERVIDOR e da POLÍTICA
```

Display responde `sabe_criar: true` **e** `criavel_pausada: BLOQUEADO`. As duas
são verdade. Uma tela que lesse só a primeira ofereceria o botão e o servidor
recusaria no clique — depois de o operador montar o pedido inteiro.

## A arquitetura da aba Criar, de cima para baixo

```
┌ EstudioLigado ───────────────────────────────────────────────────┐
│  lê: /capacidades  /inventario/vocabulario  /trava  /canais      │
│                                                                   │
│  ┌ EstudioMulticanal ────────── o CANAL, e o que ele é ────────┐ │
│  │  chips dos canais · papel · limites declarados · CTA        │ │
│  │  ⚠️ o CTA agora sabe que a porta monta Search               │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌ JornadaDoCanal ───────────── o VEREDITO, e o caminho ───────┐ │
│  │                                                              │ │
│  │  1. ESCADA DOS QUATRO PORTÕES        ← do servidor           │ │
│  │     planejável · validável · criável pausada · ativável      │ │
│  │     cada um: estado · pergunta que responde                  │ │
│  │     cada bloqueio: causa (como o servidor escreveu)          │ │
│  │                    origem → A QUEM PEDIR                     │ │
│  │                    revalidação · observado em                │ │
│  │                                                              │ │
│  │  2. AS TREZE ETAPAS                  ← a máquina pura        │ │
│  │     objetivo → conta → destino → conversão → segmentação     │ │
│  │     → orçamento → criativos → revisão                        │ │
│  │     → validação local → PROVA → APROVAÇÃO → CRIAÇÃO PAUSADA  │ │
│  │     → ATIVAÇÃO                                               │ │
│  │     ⚠️ as três últimas obedecem aos portões, não à regra local│ │
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

### Por que a escada vem antes das etapas

O operador usa isto poucas vezes por semana. A primeira pergunta dele não é "por
onde começo", é **"dá para fazer alguma coisa aqui hoje?"**. A escada responde em
quatro linhas. As treze etapas respondem "quanto trabalho é", e essa é a segunda
pergunta.

### Por que as treze etapas aparecem sem respostas

Elas mostram o **tamanho e a forma** do trabalho: quais perguntas este canal faz,
quais não faz (`não se aplica`, riscado — Display não pede conversão), e onde o
caminho fecha por papel ou por manifesto. A tela diz isso com todas as letras,
porque um trilho todo pendente se leria como uma sessão travada.

## Os cinco atos, e por que continuam separados

`validação local` · `prova` · `aprovação` · `criação pausada` · `ativação`

Juntar `criação` e `ativação` num botão é o que transforma gasto em clique. A
separação existe para haver um lugar onde conferir o que foi criado **antes** de
começar a custar.

⚠️ **`ativação` nunca vira ato.** `_portao_ativavel` devolve `BLOQUEADO` em todos
os ramos, para os quatro canais, nos quatro perfis de sessão medidos
(`CHANNEL-CAPABILITY-MATRIX.json` = 16 células). Não existe rota de ativação
entre os 32 endpoints. Ela aparece como **degrau** — saber que o caminho termina
ali é informação — nunca como botão.

E ela não pode fechar por sequência. Fechava com "não há campanha criada para
ligar", o que prometia o degrau seguinte. Agora fecha pela causa do servidor.

## A gramática de estados, e o que ela custa perder

| estado | tom | o que pede |
|---|---|---|
| `PERMITIDO` | verde | seguir |
| `BLOQUEADO` | vermelho | alguém liberar ou consertar |
| `INDETERMINADO` | **âmbar** | uma leitura que ninguém fez |
| `NAO_APLICAVEL` | neutro | nada — a pergunta não existe aqui |

⚠️ `INDETERMINADO` **nunca** é vermelho. As duas pedem atos opostos, e pintar
ignorância de recusa ensina o operador a ignorar o vermelho — que é a cor que
não pode ser ignorada.

Fora dos quatro: **portão ausente** (o servidor não mandou) é uma quinta coisa, e
diz "não veio". **BLOQUEADO sem bloqueador** é declarado como lacuna do contrato,
nunca como permissão.

## A origem do bloqueio decide A QUEM PEDIR

Um botão cinza sem origem faz "peça a quem administra", "peça a quem escreve o
motor" e "peça ao dono" virarem a mesma frustração.

| origem | a quem pedir |
|---|---|
| `produto` / `politica` | decisão registrada, com data e reversão |
| `servidor` / `operador` | quem administra o sistema · o papel da sessão |
| `construtor` / `manifesto` | o sistema aprender a montar o canal |
| `mensuracao` / `observabilidade` | medição comprovada · conseguir reler depois |

## O que NÃO foi construído, e por quê

**A varredura de evidência (§8.4).** `POST /provar` é UMA requisição. Não há
sub-fases observáveis. Animar nove fases sobre uma chamada seria o "loader falso"
que o próprio briefing proíbe. Uma varredura honesta precisa encadear atos
realmente sequenciais — e isso é uma sprint própria, não um efeito.

**Um formulário multicanal.** `campos_do_pedido` é vazio para PMax, e o caminho
HTTP de Display não carrega imagens. Desenhar campos por simetria montaria um
pedido que o backend não sabe receber.
