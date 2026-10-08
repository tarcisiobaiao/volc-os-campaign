# Jornada do funil — contrato, portões e medição

Atualizado em 08/10/2026 (lucro por visita); 2ª rodada de lapidação em 07/10/2026. O funil carrega a JORNADA do
leitor: `intenção → entrada → resposta imediata → qualificação → próxima dúvida
ainda aberta → solução/saída oficial → monetização → medição → nova versão`. A
mudança estende o que existia (contrato `editorial`, portão de grafo, revisão
V2, prints, widgets, SEO) e não cria uma segunda plataforma.

## Fontes que motivaram (evidência, não instrução)

- *Tomada de Decisão Baseada em Dados* (Pubx 2026): conteúdo é produto; IA
  produz, pessoa decide; uma intenção → uma solução, resposta rápida com
  profundidade; campanha é descoberta (hipótese ≠ realidade); volume sem
  intenção econômica não é vitória; monetização faz parte do desenho. As taxas
  do slide de conversão são ilustrativas e não viraram limiar.
- *Relatório MiroFish Creditoup/SENAC*: **simulação qualitativa, 0/29
  entrevistas transcritas**. Os achados viraram contratos e casos de teste.
- Skill *Humanizer* (35 padrões de escrita artificial, base Wikipedia "Signs of
  AI writing"): doutrina de escrita natural do redator e do revisor V2.

## O contrato (`domain/models.py`)

`Page.jornada` (`JornadaDaPagina`) e `FunnelPlan.jornada` (`JornadaDoFunil`),
opcionais e aditivos. Referências entre páginas são por `duvida_id`.

- Pergunta principal, resposta imediata, coortes de entrada, `ja_resolvido`
  (o caminho PLANEJADO), próxima dúvida, condição terminal, entrada direta,
  saída oficial, monetização, retornos justificados, hipótese, evidências.
- `valor` (obrigatório no portão): problema, informação nova, evidência, o que
  o leitor consegue fazer depois, por que não fundir, e `entregas` (resposta
  direta, passo a passo, comparação, exemplo, checklist, cálculo, tabela, fonte
  oficial explicada, ferramenta, decisão prática, próximo passo concreto).
- `plano_visual`: o mesmo vocabulário do `visual_plan` do briefing, ampliado
  (cards, timeline, decisão, próximos passos, citação útil, cálculo,
  ferramenta, prova oficial, imagem editorial), com função editorial e posição
  (nunca entre a pergunta e a resposta).
- `ativos`: widget pedido pelo arquiteto, com pergunta, entradas, lógica,
  resultado, fonte da regra, fallback sem JS, acessibilidade, evento e custo.
- Evidência com natureza `hipotese` | `simulacao` | `observacao_real`.
  Observação real exige fonte, data de coleta e referência verificável; a
  guarda `fonte_nao_observada` (a mesma em `domain/medicao.py`) recusa MiroFish
  e "simulação" com qualquer caixa, acento ou espaço.

### Lucro por visita: o contrato mínimo da página (08/10/2026)

Norte: **maior lucro esperado por visita** dentro de quatro limites — intenção,
valor real em cada página, progressão honesta e congruente, política/fatos.
Princípio da página: **entrega + tensão residual** (`promessa → resposta
imediata → aprofundamento útil → consequência ou nova dúvida → CTA
específico`). Só dois campos novos; o resto já existia:

| Conceito | Campo |
|---|---|
| intenção de entrada | `jornada.coortes_de_entrada`, `trabalho_do_leitor` |
| estado mental, dor/desejo predominante | `Page.emotional_objective` (estado ao chegar + ganho, não lista do que evitar) |
| pergunta central / promessa / entrega imediata | `pergunta_principal`, `resposta_imediata` |
| informação exclusiva | `valor.informacao_nova`, `valor.por_que_nao_fundir` |
| **tensão residual legítima** | **`jornada.tensao_residual`** (novo) |
| próxima pergunta / encerramento | `proxima_duvida`, `condicao_terminal` |
| **CTA principal desta origem** | **`editorial.links[].cta`** (novo; vazio = `cta_label` do destino) |
| destino / entrega prometida no destino | `links[].target` + `useful_delivery`/`resposta_imediata` do destino |
| função na monetização | `jornada.monetizacao` |
| condição de entrada direta | `entrada_direta` |

Os dois campos novos saem do dump quando vazios (`exclude_if`): pacotes
congelados e estados antigos conferem byte a byte. O Pautador chega ao
arquiteto pelo contrato REAL da validação: `contexto_de_leitura.tensao`, as
dores mineradas da entidade (`pains`) e `concrete_pain` viram
`brief.dores_observadas`; `perguntas_paa` viram demanda (antes o motor lia
chaves que ninguém escrevia e `dores_observadas` saía sempre vazio).

O que mudou no motor existente (sem engine, revisor ou caminho novos):

- **arquiteto** (`funnel_builder.py`): alvo de lucro por visita; página existe
  quando tem intenção, entrega exclusiva, próxima pergunta e entrada direta (não
  minimizar páginas); pré-sell existe quando ajuda a se reconhecer e escolher;
  formas permitidas (hub por intenção, jornada progressiva, diagnóstico sem dado
  sensível, sequencial); `cta` por link com a fórmula dor/desejo + próxima
  resposta + consequência; caiu "rótulo igual para entrega igual é correto";
- **redator** (`jornada_da_pagina.jinja`, `reader_contract_v2.jinja`): ordem
  entrega + tensão, emoção permitida e proibida, todo parágrafo responde,
  esclarece, exemplifica, antecipa objeção ou prepara o próximo passo; a
  abertura responde e o corpo avança; caiu "um destino com a mesma entrega pode
  manter o mesmo rótulo" (os templates V1 não mudaram);
- **saída oficial**: `boa` só abre a página (hero) quando não resta
  `proxima_duvida`; com dúvida aberta continua obrigatória e visível, depois do
  CTA interno;
- **esqueleto**: `ctas_iguais` (destinos diferentes com o mesmo texto) bloqueia;
  `cta_generico` (lista única em `copy_contract.cta_generico`: saiba mais,
  continuar, próximo, ver conteúdo, ver guia, clique aqui, acessar, confira…),
  `cta_sem_correspondencia_no_destino`, `tensao_residual_ausente` e
  `presell_sem_escolha` são aviso; o CTA principal genérico no caminho do brief
  continua bloqueante;
- **revisor V2**: nota baixa válida em `cta_discipline`/`useful_delivery` vira
  `nota_baixa_so_aviso` no recibo e não segura a página. Continuam travando:
  `compliance`, `destination_relevance`, nota ausente/fora do contrato, achado
  bloqueante (fato, política, destino, identidade), afirmação sem fato, HTML
  inválido. Uma revisão, um microajuste, sem laço.

A/B enxuto real no Gás do Povo (10 chamadas, sem publicação): melhora
estrutural clara, ganho percebido pequeno (juiz cego 73 × 70); ver
`docs/audits/FUNNELFORGE-LUCRO-POR-VISITA-AB-2026-10-08.md`.

### Estado do leitor por caminho

`ja_resolvido` não é verdade absoluta. `jornada.estado_do_leitor` calcula, no
grafo, o que está resolvido em TODO caminho de qualquer entrada até a página
(`certamente`), em algum caminho (`possivelmente`) e por entrada/coorte. Uma
página que é entrada direta tem `certamente` vazio. A reoferta de CTA só
bloqueia com `certamente`; com `possivelmente` vira CTA secundário e condicional.

## Do arquiteto ao motor (backend)

`backend/app/agents/funnel_pro/jornada_contrato.py`, puro:
- `preservar_jornada`: merge por página e por campo depois do revisor do
  arquiteto. Campo protegido (coortes, evidências, monetização, hipótese,
  condição terminal, valor, plano visual, ativos, retornos) nunca é apagado
  por omissão ou valor vazio.
- `normalizar_arquitetura`: aliases e variação cosmética viram valor canônico
  ("Google Ads Search" → `paid_search`, "MiroFish" → `simulacao:mirofish`);
  campo de rota/portão desconhecido é ERRO com campo e motivo; campo
  descritivo cosmético vira aviso. Roda logo depois do arquiteto e de novo
  depois do revisor. O relatório vai a `revisao_arquitetura.jornada`; nunca há
  fallback silencioso para "sem jornada" (a ponte do motor recusa o card com o
  campo).
- Telemetria do arquiteto e do revisor (tokens, latência, modelo pedido e
  servido) vai a `revisao_arquitetura.telemetria`.

## Os portões

| Momento | Onde | O que | Custo |
|---|---|---|---|
| Antes da 1ª chamada paga | `jornada/esqueleto.py` → `routing.validate_funnel_graph` → `funnel_graph`; `revisao_esqueleto` FAILED quando reprova | jornada incompleta, dúvida duplicada, referência inexistente, `valor` ausente ou incompleto, fusão necessária, LP que só roteia, `/rec` dependente, próxima dúvida sem destino, reoferta de dúvida resolvida em todo caminho, ciclo sem ganho, beco, entrada sem conclusão, bloco visual fora da função, ferramenta sem ativo, dois destinos com o mesmo botão (`ctas_iguais`); avisos: CTA genérico, CTA sem eco no destino, tensão residual ausente, pré-sell sem escolha | zero |
| Roteamento | `routing` + `jornada/contexto.politica_da_saida_oficial` | CTA principal = próxima dúvida, com o `cta` do link quando declarado; saída oficial `nao_aplicavel` não é obrigada; `boa` vem primeiro só sem `proxima_duvida` (estágio de agir), senão depois do CTA interno; `prematura` depois dos CTAs internos; sem fonte comprovada, fail-closed | zero |
| Redação | `jornada_da_pagina.jinja` (V1 e V2, condicional), `escrita_natural.jinja` (V2) | pergunta, promessa, o que está certo e o que é talvez resolvido, destinos (principal/secundário), saída oficial, valor, plano visual, ativos; escrita natural sem perder fato, número, link ou SEO | — |
| Revisão por página (V2) | `revisao.py` | categoria `naturalidade` (padrão Humanizer), sempre ajuste, patch na MESMA chamada; o código recusa patch que perde número ou toca link | — |
| Funil pronto | `jornada/revisao_global.py`, antes de qualquer publicação, só páginas aprovadas | bloqueio só com prova estrutural (CTA para dúvida resolvida em todo caminho, ciclo real, link oficial na LP, saída prematura antes da próxima dúvida, beco); proxy de termo é aviso | zero |
| Widget | `steps.step_widget` | ativo do arquiteto só com a fonte da regra no lastro da pesquisa da página; sem isso, nenhuma chamada | zero |
| Print oficial | `steps.proveniencia_do_print` | URL, data, título, trecho que comprova, legenda ("Reprodução... pertence ao site de origem"), alt, recorte, sha256 e estado; sem isso não é embutido | zero |
| Metadados | `pipeline/metadados.py`, `state.metadados`, `metadados_pN.json` | title, description, canonical (previsto/publicado), robots, OG, Twitter, breadcrumb, autor, datas, fontes, tipo; JSON-LD só com o que o texto mostra (FAQPage com perguntas visíveis, HowTo com passos reais, ItemList com checklist) | zero |

## Dossiê factual: memória compartilhada, não portão global (`run.dossie_factual`)

O dossiê (`pipeline/dossie.py`, `CompiladorDeDossie`) é o CACHE factual do
funil. Vale para qualquer tema, nicho, idioma e país: nenhuma lista fixa de
domínios decide autoridade.

**Estado de cada requisito** (`CoberturaDoRequisito.estado`):

| Estado | Quando | O que a página faz |
|---|---|---|
| `verified` | evidência suficiente e coerente | usa |
| `derived` | conta determinística de premissas verificadas | usa, como conta |
| `unavailable` | fonte ou transporte falhou (WAF, timeout, UA recusado) — não é falso | tenta alternativa; senão retira/generaliza |
| `unsupported` | pesquisa feita, evidência insuficiente | omite; se é a promessa central, revisão |
| `conflicting` | fontes confiáveis divergem | bloqueia a afirmação; na promessa central, bloqueia SÓ a página |

**Estado da página**: `ready`, `degraded` (detalhe omitido, bloco ou ferramenta
desativados, canal oficial ausente → sem link oficial), `review` (promessa
central sem evidência: escrita, não publica sem decisão humana) e `blocked`
(só conflito material na promessa central). Nada bloqueia o funil inteiro;
pesquisa que falha não entra fato e deixa os requisitos `unavailable`.

**Fluxo**: uma pesquisa GLOBAL (`steps.dossie`, modelo exato, sem fallback);
cada página `ready` escreve logo; página com lacuna faz UMA busca dirigida por
lacuna no próprio worker (`complementar_pagina`), deduplicada entre páginas
(a segunda espera a primeira), registrada no cache sob trava e validada antes
de qualquer prosa. No fim, consolidação determinística (fatos por `fact_id`,
SHA novo); revisão global e publicação continuam esperando o conjunto.

**Evidência**: fonte só da citação do provedor (`url_citation` ancorada) ou de
hint do operador conferido no documento; verificação ao vivo com UA honesto
(nunca se passa por navegador). Risco alto (dinheiro, elegibilidade, prazo,
data, direito, legislação) exige evidência FORTE: emissor oficial comprovado,
canal oficial da jornada, derivado, ou duas fontes reputadas independentes
(publicadores diferentes) que concordam. Recuperação de `unavailable`: leitura
direta → outra publicação oficial equivalente → citação ancorada do provedor
de fonte do canal oficial (registrada como `citacao_do_provedor`) → duas
fontes independentes → remoção ou generalização.

**Proveniência genérica** (`pipeline/proveniencia.py`): a estruturação declara
emissor, tipo de emissor, escopo e jurisdição (ISO 3166); só valem quando a
frase do emissor está no cabeçalho ou título do documento. Escopo do país
prova regra do país e de suas partes; escopo de subdivisão, só dela
(`FunnelPlan.jornada.jurisdicao`). Ferramenta (`AtivoInterativo`) declara a
necessidade por requisito (`rule_source_fact_id`, `current_value_source_fact_id`);
sem vínculo, SÓ a ferramenta sai. Derivado só pela operação declarada no
requisito (`multiplicacao`), premissas oficiais verificadas, mesma
jurisdição, `Decimal` sem arredondamento, linhagem e recálculo a cada
compilação.

**Degradação no texto**: o redator recebe "O QUE NÃO PODE SER AFIRMADO" com a
instrução por requisito (sem valor, prazo ou precisão; formulação perene;
onde o leitor confere), e blocos/ferramentas desativados saem do pedido.

## Redação paralela segura (`run.page_workers`, 1 a 3)

`1` é o laço serial de sempre (`_processar_pagina`, byte a byte). `>1` exige
`dossie_factual` (erro de configuração sem ele): a pesquisa global acontece
antes, e cada worker só complementa as lacunas da própria página. Duas fases, ambas com
`ThreadPoolExecutor`, consolidação serial em ordem de página entre elas:

- **A — redação:** portão, briefing, redação. Cada worker tem cópia profunda
  do estado, `RunnerDaPagina` (orçamento da página, `checkpoint` sem efeito,
  log e prompts em `<run>/paginas/pN/`), e devolve um `DeltaDaPagina` com o
  que mudou nas chaves DELE; mudança fora da página é violação, não é
  aplicada e bloqueia a página. Depois, a unicidade entre as páginas do lote
  é conferida como no serial (cada uma contra as anteriores).
- **B — acabamento:** SEO, widget, revisor, build e gate, cada revisor já
  vendo os rascunhos das páginas de origem (o rótulo que o botão de lá
  prometeu — `_rotulo_publicado`).

Logs e prompts das páginas entram no run no fim, em ordem de página; os passos
novos ficam na ordem do serial. A publicação continua serial, depois da
revisão global. Diferença conhecida: no serial a unicidade reprova DENTRO da
redação (validador com rascunhos anteriores, com retentativa); no paralelo, na
consolidação, sem retentativa. A condenação é a mesma (teste
`test_15_unicidade_*`). Browser e sitemap ficam atrás de uma trava única.
Limite honesto: com N workers o teto do run pode ser ultrapassado em até N-1
chamadas que já estavam no ar — por isso o gasto faturado (pesquisa) é serial.

## Caminho de produção (após c168168)

O caminho de qualidade é um só: editorial V2 com dossiê e até 3 workers
(preset `completo_chatgpt`; `rapido_chatgpt` é alias legado de cards gravados). `run.perfil: rapido` ficou
como rótulo inerte e `revisao_rapida.py` não existe mais. No caminho
pré-redação (`--card-pre-arquitetura`), a revisão é UMA chamada em lote
(`inteligencia.revisar_lote`) com as mesmas políticas, notas e patcher do
revisor V2.

Histórico (commit 4575ea0, antes da unificação): canário de 08/10/2026, card
#65 (FGTS), 6/6 páginas, 13 chamadas, pico de 3 simultâneas, cerca de 5m45s.

## Contrato de medição

`jornada/medicao.py` → `medicao.json`. Todo sinal nasce `nao_implantada`:
nenhum coletor desta lista foi provado ativo para as URLs do funil. A proposta
de nova versão exige aprovação humana por literal.

## O que não foi feito

Sem UI, sem tracking, sem coletor, sem passagem extra de humanização (só a
revisão existente), sem envio do JSON-LD ao WordPress e sem cache por hash
(registrados como pendência). Sem ADC/Vertex na pesquisa do dossiê (exigiria
projeto GCP que não se presume). CTA condicional por visita exige estado de
sessão: fora do contrato.
