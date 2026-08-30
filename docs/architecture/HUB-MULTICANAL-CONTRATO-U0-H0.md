# Hub multicanal: contrato de integração U0 + H0

Status: congelado para implementação paralela em 26/08/2026  
Owner de integração: Codex  
Fontes: `PRODUCT.md`, `docs/DESIGN.md`, PRD/SPEC/ADRs de Tráfego e grafo híbrido no commit `43130af`

## 1. Objetivo da fatia

U0 corrige a verdade operacional que já está na tela. H0 cria o menor contrato
capaz de receber Google Ads e Meta Ads sem transformar o núcleo do Hub em código
específico de uma plataforma.

A fatia só termina quando:

1. o inventário padrão separa operação corrente de histórico removido;
2. FGTS e Maquininha são reconhecidas como campanhas existentes sem hardcode;
3. a reconciliação impede duplicidade silenciosa;
4. plataforma, canal, nível de entidade e capacidade de ação têm vocabulário único;
5. o frontend consome o contrato real ou um único adapter temporário declarado;
6. nenhuma ação privilegiada parte do navegador.

## 2. Fontes de verdade

| pergunta | autoridade |
|---|---|
| A campanha existe e qual é seu estado? | conta da plataforma, refletida no inventário com frescor |
| O que a VOLC pretendia criar? | campanha declarada, linhagem e evento operacional |
| A qual funil/oportunidade pertence? | vínculo confirmado e auditável |
| O vínculo ainda não foi confirmado? | sugestão de reconciliação, nunca fato |
| O que está gastando e performando? | snapshot de plataforma + ingestão de custo/receita, com janela e frescor |
| O que pode ser alterado? | manifesto de capacidades + autorização + portão de escrita |

Uma tabela legada isolada nunca decide que uma oportunidade está livre para
lançamento. Nome de campanha nunca é identidade.

## 3. Vocabulário canônico

### Plataforma

```text
GOOGLE_ADS
META_ADS
```

### Canal Google

```text
SEARCH
DISPLAY
DEMAND_GEN
PERFORMANCE_MAX
```

`PMAX` pode existir somente como alias de entrada legado, traduzido numa única
fronteira e nunca persistido ou devolvido pela API canônica.

### Estado de reconciliação

```text
vinculada
correspondencia_provavel
conflito
sem_campanha
somente_historico
```

Semântica:

- `vinculada`: vínculo humano confirmado e campanha presente.
- `correspondencia_provavel`: sinais suficientes para revisão, insuficientes
  para afirmar o vínculo.
- `conflito`: mais de uma candidata plausível ou sinais incompatíveis.
- `sem_campanha`: nenhuma candidata depois da prova somente leitura.
- `somente_historico`: existem apenas instâncias removidas; relançamento exige
  motivo declarado e nova linhagem/instância conforme a decisão operacional.

### Presença operacional

`REMOVED` é histórico por padrão. Não é apagado, não é atenção e não compete na
lista operacional.

## 4. Contrato do inventário

### Entrada

O parâmetro canônico é conceitualmente:

```text
incluir_historico=false
```

O nome final pode seguir a convenção já adotada pela API, mas o default e a
semântica não podem mudar.

Filtros e busca operam no servidor antes de contagem, ordenação e paginação.
O cursor é opaco e determinístico.

### Totais

O envelope precisa distinguir, sem derivação no frontend:

```text
operacionais
historicas
geral
atencao
contas
```

`geral` não substitui `operacionais`. O rótulo principal da aba Campanhas usa
o universo operacional.

### Ordenação padrão

1. campanha que pede atenção;
2. ligada;
3. pausada;
4. demais estados presentes;
5. histórico, apenas quando solicitado.

Dentro do mesmo grupo, a ordenação deve ser estável e documentada para não
quebrar o cursor.

## 5. Contrato de reconciliação

A sugestão considera, nesta ordem de força:

1. mesma conta/plataforma e URL final normalizada;
2. vínculo/linhagem já registrados;
3. projeto, oportunidade e funil compatíveis;
4. sinais auxiliares explícitos e versionados.

Nome pode ser exibido como evidência auxiliar, mas não autoriza decisão.

A reconciliação devolve:

- estado;
- candidatas e seus IDs estáveis;
- sinais que sustentam cada candidata;
- sinais ausentes ou conflitantes;
- ação permitida;
- necessidade de confirmação humana;
- frescor da prova.

Uma campanha ativa provável bloqueia novo lançamento até revisão. Uma campanha
somente histórica não bloqueia relançamento, mas exige motivo declarado.

## 6. Modelo extensível de canal

`ChannelProfile` declara apresentação e capacidades. `ChannelAdapter` traduz o
núcleo para a API externa.

O perfil declara:

- plataforma e canal;
- níveis da hierarquia;
- painéis disponíveis;
- campos do pedido;
- capacidades de leitura;
- capacidades de proposta;
- capacidades de escrita;
- provas obrigatórias;
- estados vazios e indisponibilidades conhecidas.

O núcleo não importa `keyword`, `placement`, `asset_group`, `listing_group` ou
`ad_set`. Esses conceitos pertencem ao perfil/adaptador.

Hierarquias iniciais:

| perfil | hierarquia operacional |
|---|---|
| Google Search | campanha → grupo → anúncio/keyword |
| Google Display | campanha → grupo → anúncio/asset |
| Google Demand Gen | campanha → grupo → anúncio/asset |
| Google Performance Max | campanha → asset group → asset |
| Meta Ads | campanha → conjunto → anúncio → criativo |

## 7. Arquitetura de informação

```text
Tráfego
├── Rede: Google Ads | Meta Ads
├── Tarefa: Campanhas | Preparar | Atenção
├── Google, canal: Todos | Search | Performance Max | Demand Gen | Display
└── Meta, nível: Campanhas | Conjuntos | Anúncios | Criativos
```

Rede, tarefa, canal e nível são eixos diferentes. O estado relevante deve ser
serializável na URL.

Rota canônica de detalhe:

```text
/trafego/campanhas/:volcCampaignId
```

A página deriva plataforma, canal e painéis do perfil. A rota legada só
redireciona quando a identidade interna puder ser resolvida sem ambiguidade.

## 8. Escrita blindada

Toda atuação futura segue:

```text
fato observado
→ proposta versionada
→ diff antes/depois
→ validação da plataforma
→ autorização humana
→ execução idempotente no backend
→ recibo
→ releitura
→ verificação final
```

U0/H0 não autoriza mutate em Google ou Meta. Também não autoriza webhook
privilegiado, segredo ou `service_role` no navegador.

## 9. Ownership paralelo

### Claude

- backend, domínio, persistência, contratos compartilhados e testes;
- reconciliação e proteção contra duplicidade;
- nenhum acabamento visual;
- não atualiza o grafo.

### Grok

- páginas, componentes, hooks, estilos e testes frontend;
- consome o contrato compartilhado sem redefini-lo;
- nenhum backend, SQL, migration ou segredo;
- não atualiza o grafo.

### Codex

- reconcilia os dois handoffs;
- revisa contratos e diffs;
- executa gates integrados e validação visual com dados reais;
- atualiza a curadoria humana e reconstrói o grafo após convergência.

## 10. Gates de integração

- nenhum `git add .` ou formatação global;
- mudanças preexistentes preservadas;
- nenhum hardcode de FGTS, Maquininha, contagens ou IDs;
- nenhum zero inventado para ausência;
- nenhum token privilegiado no bundle;
- nenhum mutate durante leitura/render/testes U0/H0;
- histórico oculto por default e acessível explicitamente;
- cursor, filtros e totais coerentes;
- FGTS e Maquininha reconhecidas pela mesma regra geral;
- conflito impede montagem;
- somente histórico permite relançamento declarado;
- claro, escuro, mobile, teclado e foco verificados;
- testes frontend, backend, `volc_ads`, tipos e build proporcionais ao delta;
- grafo reconstruído sem `--reuse-technical` quando código/schema mudar.

## 11. Pendências de curadoria após a integração

Somente depois da validação final:

1. reconciliar `cap_inventario_trafego=implemented` com `wave:P0-T` e
   `concept:multichannel_inventory`, hoje ainda marcados como `todo`;
2. registrar Meta Ads, Estúdio Criativo, contrato, hipótese, versão criativa,
   aprovação, asset, experimento e aprendizado;
3. ligar os motores existentes de imagem/vídeo ao núcleo de assets sem afirmar
   integração ainda não comprovada;
4. registrar as capacidades reais de cada perfil Google com evidência de código
   e documentação oficial atual.

## 12. Baseline anterior às frentes paralelas

Medido em 26/08/2026 antes dos handoffs de Claude e Grok:

- frontend do Hub: 12 arquivos, 247 testes verdes;
- backend de inventário/sincronização/alertas: 113 testes verdes e 1 ignorado;
- persistência em PostgreSQL descartável: 26 testes verdes e 1 ignorado;
- build Vite de produção: verde;
- HEAD: `43130af`;
- grafo: `built_at_commit=43130af`, com árvore suja já declarada pelo pipeline.

Nota de ambiente: o PostgreSQL descartável não inicializa dentro do sandbox por
restrição a memória compartilhada SysV (`shmget: Operation not permitted`). A
mesma suíte executada fora do sandbox passou integralmente. Isso é limitação do
harness, não falha do schema.

## 13. Costuras concretas para a integração

Este mapa foi levantado depois do congelamento do contrato. Ele delimita onde os
handoffs precisam se encontrar e evita que a integração seja feita por busca de
texto ou por reescrita global.

### Oportunidades e duplicidade

- `backend/app/routers/trafego.py` ainda monta `campanhas_lancadas` a partir de
  runs legados e entrega a contagem usada pelo quadro de oportunidades.
- `src/pages/trafego/NovaCampanhaPage.tsx` e
  `src/components/trafego/oportunidades/` consomem essa projeção.
- As provas de sincronia e incorporação estão em
  `src/pages/trafego/__tests__/sincronia-do-lancado.test.tsx` e
  `src/components/trafego/inventario/__tests__/oportunidades-embutiveis.test.tsx`.

Resolução esperada: a reconciliação canônica substitui a decisão binária legada.
O frontend recebe estado, evidências, candidatas e ação permitida. Ele não
reconstrói vínculo por nome, URL ou contagem.

### Rota e detalhe de campanha

- `src/App.tsx` mantém `/dashboard/campaign/:campaignId` como detalhe atual e
  ainda não registra `/trafego/campanhas/:volcCampaignId`.
- Links antigos partem de dashboard, configurações, relatórios e paleta de
  comandos.

Resolução esperada: criar primeiro a rota interna e o resolvedor de identidade.
O redirecionamento legado só entra onde conta + plataforma + ID externo levam a
uma única identidade interna. Não fazer substituição global de links antes dessa
prova.

### Escrita privilegiada no detalhe antigo

- `src/components/campaign/BiddingActionBox.tsx` possui chamada direta a um
  webhook n8n público e atuação iniciada pelo navegador.
- `src/pages/CampaignDetailDashboard.tsx` incorpora esse componente.

Resolução esperada: o novo shell pode reaproveitar leitura e apresentação, mas
não herda essa fronteira de escrita. Qualquer ação mutável futura atravessa o
backend, o manifesto de capacidades, autorização, idempotência e recibo. A
remoção ou migração do caminho antigo é uma fatia própria, depois de existir
substituto verificável.

### Vocabulário de canal

- `src/types/trafego.ts` ainda declara `PMAX`.
- filtros e o backend já usam `PERFORMANCE_MAX`;
- `backend/app/trafego/dominio.py`, `backend/app/trafego/inventario.py` e
  `volc_ads/campanha/` já tratam o alias na fronteira.

Resolução esperada: o contrato compartilhado devolve somente
`PERFORMANCE_MAX`. `PMAX` fica restrito a normalização de entrada legada e não
aparece em filtros, URLs, persistência ou respostas novas.

### Capacidade real por canal

O backend e `volc_ads` já reconhecem os quatro canais, mas isso não significa
que os quatro possuam builder de campanha. Search é a capacidade de construção
comprovada hoje; Display e Demand Gen têm superfícies parciais; Performance Max
é inventário/perfil até existir evidência de builder seguro.

Resolução esperada: o frontend deriva cada CTA do manifesto de capacidades. Não
mostrar “criar” por simetria visual quando o adaptador só sabe ler, diagnosticar
ou preparar.

### Grafo e encerramento

Hoje `cap_inventario_trafego` está `implemented`, enquanto `wave:P0-T` e
`concept:multichannel_inventory` continuam `todo`. Esse desalinhamento será
corrigido somente após os handoffs convergirem, junto dos novos nós Meta e dos
estados reais de capacidade Google. Até lá, o grafo continua válido para
navegação histórica, mas não deve ser usado para afirmar que U0/H0 já terminou.
