# Growth Engine — a frente

**Agente F** · 26/08/2026 · escopo `src/**`
Registro **product** (`PRODUCT.md`), sistema visual de `docs/DESIGN.md`.

---

## 1 · O brief (shape)

### O que é

Nove superfícies que continuam o Hub de Tráfego. O Hub responde *o que existe e
em que estado está*. Estas respondem as três perguntas seguintes:

| pergunta | superfície |
|---|---|
| por que esta campanha não entrega? | escada de entrega |
| o que deveria mudar, e com que evidência? | caixa de propostas · diff · portão |
| quem autorizou, e o que exatamente saiu? | aprovação · recibo · lote |
| e o que dá para criar aqui? | conversa de criação · criativos · canal |

### Ação primária

Ler um diagnóstico com a evidência colada e **decidir** se aprova uma mudança
específica. Não é acompanhar: é decidir, com o antes e o depois na frente.

### Direção visual

**Restrained** — o piso de `DESIGN.md`, e o teto aqui. Cor semântica é o
inventário inteiro de energia visual, e ela está toda comprometida com estado.

**Cena que decide o tema:** já escrita em `DESIGN.md` — o operador conferindo às
três da tarde, monitor de 27", perto de uma janela, se a campanha de ontem está
entregando. Claro por padrão, escuro completo. Nenhum token novo foi criado:
tudo sai de `--foreground`, `--muted-foreground`, `--border`, `--success`,
`--warning`, `--destructive`, `--info`.

**Âncoras:** a página de disputa da Stripe (evidência → veredito → quem
decidiu), o detalhe de issue do Linear (denso, teclado, sem moldura), e o
diagnóstico "por que meu anúncio não aparece" do Google Ads — como
anti-referência pela vagueza, e como referência positiva por `primary_status_
reasons` ser a palavra da própria conta.

**Checagem de reflexo de categoria.** Primeira ordem: "ferramenta de anúncio →
escuro azul-marinho com número grande de gasto e gráfico de linha". Recusado —
claro por padrão, zero hero metric, zero gráfico. Segunda ordem: "ferramenta de
anúncio que não é dashboard escuro → relatório editorial com muito branco".
Também recusado: isto é ferramenta densa de conferência, e espaço em branco como
luxo custaria linhas. O que sobrou é a forma que a informação já tinha: uma
**escada causal**, lista ordenada, hairline e recuo, sem cartão nenhum.

### A ideia estrutural

Uma campanha que não entrega falha em **um** degrau, e o degrau de baixo torna
os de cima irrelevantes. Nove degraus, em ordem causal:

```
conta → campanha → orçamento → grupo → anúncio → keyword → segmentação → conversão → leilão
```

Uma grade de nove medições lado a lado daria nove candidatos com o mesmo peso, e
o operador escolheria o mais familiar — lance ou verba — quando a causa era
cobrança da conta. A ordem **é** a estrutura da tela.

O veredito é uma união, e não um campo anulável:

```ts
type VereditoDaEscada =
  | { tipo: 'bloqueada';       eixo }
  | { tipo: 'limitada';        eixo }
  | { tipo: 'sem_impedimento' }
  | { tipo: 'nao_apurado';     eixo }
```

Modelar como `primeiro_bloqueio: Eixo | null` deixaria "nada bloqueia" e "nada
foi apurado" com a mesma representação — e o consumidor escolheria a leitura
otimista. É o mesmo defeito de `reconciliacao: null` virando `?? 0`, um andar
acima. A união o torna impossível de escrever.

E há a consequência que quase sempre falta: um degrau **não apurado interrompe a
leitura**. Os degraus acima dele continuam na tela, sob a frase *"a leitura para
aqui"* — esconder perderia informação, exibir como conclusão afirmaria o que não
se provou.

---

## 2 · O que foi implementado

### Contrato

| arquivo | o quê |
|---|---|
| `src/types/diagnostico.ts` | o contrato inteiro: escada, proposta, diff, aprovação, recibo, lote, etapas, criativo, capacidade de canal, e o envelope `RespostaDoDiagnostico` |
| `src/lib/diagnostico/evidencia.ts` | a forma REAL do `evidencia.json` do Agente B, com leitura defensiva |

### Domínio puro (`src/lib/diagnostico/`)

| arquivo | o quê |
|---|---|
| `escada.ts` | veredito, ordem causal, corte de leitura suspensa |
| `derivar.ts` | **ponte declarada**: `evidencia.json` → `DiagnosticoDeEntrega`, nove degraus |
| `propor.ts` | escada → caixa de propostas, herdando a causalidade |
| `fixtureDeEvidencia.ts` | fixture com a forma exata do runner, duas campanhas Search reais |

### Superfícies

| arquivo | o quê |
|---|---|
| `components/trafego/diagnostico/EscadaDeEntrega.tsx` | a escada, com evidência expansível inline e "copiar evidência" |
| `components/trafego/diagnostico/CaixaDePropostas.tsx` | a fila, com origem, confiança, janela e amostra |
| `components/trafego/hub/PropostaDeAcao.tsx` | **estendido**: diff multi-linha, dependência real, portão de aprovação |
| `components/trafego/recibos/` | `recibo.ts` (leitura tolerante) + `CartaoDeRecibo.tsx` |
| `components/trafego/lote/` | `lote.ts` (resumo) + `QuadroDoLote.tsx` |
| `components/trafego/criacao/` | `conversa.ts` (máquina de 13 etapas) + `ConversaDeCriacao.tsx` |
| `components/trafego/criativos/BibliotecaDeCriativos.tsx` | tabela com procedência, impressão, validação por canal e uso |
| `components/trafego/canal/` | `capacidades.ts` + `VisaoDoCanal.tsx`, derivados do manifesto |

### Ligação

`/trafego/campanhas/:volcCampaignId` já monta escada, caixa e visão do canal, via
`useDiagnosticoDeEntrega` → `pautadorApi.diagnosticoDeEntrega()`. `404`/`501`
rendem a frase *"este servidor ainda não apura diagnóstico"* — a ausência é da
capacidade, e a tela diz isso em vez de sumir com a seção.

### Por que `PropostaDeAcao` foi estendido, e não duplicado

A doutrina dele já estava certa e a forma era pequena: um antes e um depois
soltos, uma explicação enlatada por tipo de ação, e um botão sempre desligado. As
três superfícies novas pedem a mesma ideia com mais matéria. Todas as props novas
são opcionais, a chamada antiga continua válida, e há teste provando. Um segundo
componente para "ação que gasta dinheiro" é como duas telas passam a discordar
sobre o que é seguro.

---

## 3 · As decisões que carregam peso

**A exceção do zero medido.** O runner serializa com
`always_print_fields_with_no_presence=False`. Em proto3 sem presença isso **omite
o valor padrão**: uma métrica de `impressions: 0` não aparece na linha. Dentro de
uma linha que veio, campo ausente significa **zero medido**, não "não sei". A
regra mora numa função só, `zeroMedido()`, com nome próprio para a exceção ser
visível na chamada em vez de virar um `?? 0` distraído. Fora dali, ausência
continua sendo ausência em todo o repositório.

**A impressão amarra aprovação e recibo.** `Aprovacao.impressao` é o mesmo campo
que o recibo carrega. Um portão que grava só quem e quando autoriza uma pessoa a
assinar uma proposta e outra a alterá-la depois, com o carimbo intacto.
`conferirImpressao()` responde `confere`, `difere` ou `nao_da_para_conferir` — e
nunca `confere` por falta de dado.

**Amostra pequena aparece, e não é escondida.** `insuficiente: true` põe a
ressalva na tela e mantém a proposta na fila. Esconder seria decidir por quem
opera.

**Confiança não reusa `SinalDeReconciliacao.forca`.** Aquele mede força de um
sinal de identidade; este mede quão bem a evidência sustenta uma mudança. São
perguntas diferentes e ficaram com vocabulários diferentes, com o porquê escrito
no tipo.

**`indeterminado` não é `falhou`.** No lote, `falhou` AFIRMA que nada foi criado
e essa afirmação autoriza reenviar; `indeterminado` diz que a chamada saiu e não
se sabe o desfecho. Somados, viram um número que autoriza reenviar — e reenviar
um indeterminado cria a segunda campanha real disputando o mesmo leilão contra a
primeira. Baldes separados, glifos separados, e o botão de retomar fica fechado
enquanto houver um indeterminado ou uma duplicidade no lote.

**O vocabulário do lote é o do backend.** Os estados vêm de `ESTADOS_DO_ITEM`
(`backend/app/trafego/lote.py`) e a `proxima_acao` de cada item vem **decidida do
servidor**. Ela já tem duas definições — o `CASE` da view `trafego_item_situacao`
e a função Python — comparadas contra um Postgres real por
`scripts/provar-ciclo-v10.sh`. Uma terceira, em TypeScript, seria justamente a
que ninguém compara, e a divergência apareceria como a tela oferecendo "criar"
para um item que o executor considera em voo.

**Criar e ligar são duas etapas.** `criacao` cria pausada; `ativacao` é o gesto
que faz gastar. Elas ficam separadas mesmo quando a intenção óbvia é subir e
ligar — a separação é o lugar de conferir o que foi criado antes de custar.

**Trava não lida nunca é trava aberta.** `travaAberta: null` bloqueia a criação
com a frase que diz que o estado não foi lido.

---

## 4 · Provas

```
npm test -- --run                                    56 arquivos · 734 testes · 0 falhas
npx tsc --noEmit -p tsconfig.app.json | grep -c TS    76
npm run build                                        verde
```

Baseline de partida: 44 arquivos · 574 testes · 77 erros de tipo. Os 12 arquivos
e 160 testes novos são deste lote; o 77º erro caiu com a limpeza das quatro
cópias de Drive (`inventario/formato 2.tsx`, `Selos 2.tsx`,
`EstadosDoInventario 2.tsx`, `hooks/useInventario 2.ts` — todas não rastreadas e
com zero imports, conferidas com `rg` antes de sair).

Duas provas são o portão do lote, em
`components/trafego/diagnostico/__tests__/seguranca-growth-engine.test.tsx`:

- **zero chamada ao Google Ads no render** — varredura estática de todos os
  arquivos novos *mais* uma sonda que renderiza as oito superfícies com `fetch`,
  `XMLHttpRequest`, `WebSocket`, `EventSource` e `sendBeacon` trocados por dublês
  que explodem se chamados;
- **zero credencial e zero mutação** — a varredura entra por pasta, então
  arquivo novo cai dentro dela sozinho, em vez de depender de uma lista que
  envelhece.

---

## 5 · O que falta ligar — dependências de contrato

### 5.1 · A rota que a tela já chama

```
GET /api/trafego/campanhas/{volc_campaign_id}/diagnostico
→ RespostaDoDiagnostico { versao, diagnostico, propostas }
```

Só identidade **interna**, como a rota canônica. Leitura de projeção: nada de
Google Ads em tempo de render. Diagnóstico e propostas vêm **no mesmo envelope**
de propósito — duas rotas produziriam o dia em que a tela mostra a escada de
agora ao lado de propostas de meia hora atrás, sem nada dizendo isso.

Códigos: `404`/`501` = capacidade não ligada · `503` = indisponível · `403` = sem
papel.

### 5.2 · Para o Agente B

O `evidencia.json` ainda não existia quando este lote fechou, e a fixture foi
construída contra a **forma que `rodar.py` emite**. Duas coisas:

1. o tipo `EvidenciaDeDiagnostico` já está escrito e é o contrato esperado — o
   arquivo real entra no lugar da fixture sem tocar em componente nenhum;
2. **considere `always_print_fields_with_no_presence=True`**. Com `False`, campo
   ausente numa linha é "zero medido" e o consumidor precisa saber disso. Com
   `True`, ausência volta a significar ausência, e a exceção documentada acima
   deixa de existir.

### 5.3 · Rotas que ainda não existem

| superfície | precisa de |
|---|---|
| recibos | `GET /api/trafego/campanhas/{id}/recibos → Recibo[]` |
| lote | `GET /api/trafego/lotes/{id}` · `POST .../retomar` · `POST .../cancelar` (com motivo). O payload precisa trazer `proxima_acao`, `recibo_em_voo` e `encontradas_na_conta` por item — a tela não recalcula nenhum dos três |
| aprovação | `POST /api/trafego/propostas/{id}/aprovar` — **`por` sai do token**, nunca do corpo, como em `confirmarVinculo` |
| criativos | `GET /api/trafego/criativos` — com `uso: null` distinto de `uso: []` |
| conversa | `manifesto.campos_do_pedido` com os nomes reais; hoje a etapa de conversão é decidida por heurística sobre esse array |

⚠️ **A impressão do pedido é calculada no servidor.** O browser não monta o grafo
de operações e portanto não pode carimbá-lo. Enquanto a aprovação chegar sem
`impressao`, a tela mostra a ressalva de que nada amarra o que foi aprovado ao
que vai sair — há teste para isso.

### 5.4 · Convergência já feita com o lote do backend

O `backend/app/trafego/lote.py` e a migração `v10_01_intencao_e_lote.sql` apareceram
na árvore durante este lote, vindos de outro agente. Os tipos da frente foram
**realinhados ao vocabulário deles** antes de fechar: treze estados de item, onze
de lote, e as oito ações de `proxima_acao`. O que a frente ganhou nessa
convergência foi o estado `indeterminado`, que não estava no desenho original
daqui e é o mais importante da lista.

O que ainda não bate: `DESFECHOS_DE_RECIBO` do backend (`em_voo`, `sucesso`,
`erro`, `sem_resposta`) descreve o **desfecho de uma chamada**, enquanto
`Recibo.estado` daqui (`ACEITO`) descreve o **arquivo** que `volc_ads` grava em
`dados/recibos/`. São dois artefatos diferentes com o mesmo nome; se forem
unificados, o campo de arquivo é que deve ceder.

### 5.5 · Prontos e ainda não montados em rota

`QuadroDoLote`, `ConversaDeCriacao`, `BibliotecaDeCriativos` e `CartaoDeRecibo`
estão implementados e provados, e ainda não têm tela própria. Montá-los é decisão
de produto além de endpoint: a criação já tem `NovaCampanhaPage` em
`/trafego/nova/:opportunityId`, e enxertar um segundo fluxo ao lado do existente
criaria dois vocabulários para criar campanha — exatamente o que o resto deste
documento recusa. A conversa foi desenhada para **substituir** aquele miolo
quando a decisão for tomada, não para conviver com ele.

---

## 6 · Acabamento

- **Mobile e desktop** — alvo de toque `min-h-11` (44 px), `md:min-h-9` no
  desktop; a tabela de criativos rola dentro do próprio contêiner
  (`overflow-x-auto` + `min-w`), o corpo da página nunca rola na horizontal; toda
  `dl` empilha no telefone e vira duas colunas a partir de `sm`.
- **Claro e escuro** — nenhuma cor literal. Só tokens do `index.css`.
- **Acessibilidade** — glifo + palavra + descrição em todo estado, com a
  descrição em `sr-only` além do `title`; `aria-expanded` + `aria-controls` nas
  linhas que abrem inline (nunca modal); `aria-current="step"` na etapa corrente;
  `aria-describedby` ligando cada botão indisponível à frase que explica a
  dependência; foco visível com anel de 2 px em todo `outline-none`;
  `motion-reduce` nos dois únicos movimentos da tela.
- **Vocabulário** — nada de "GAQL", "payload" ou "snapshot" na leitura normal. O
  nome de máquina do campo existe só na evidência expandida, que é o texto que o
  operador **copia** quando pede ajuda.
