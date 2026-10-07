# Jornada do funil — contrato, portões e medição

Atualizado em 07/10/2026 (2ª rodada, lapidação). O funil carrega a JORNADA do
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
| Antes da 1ª chamada paga | `jornada/esqueleto.py` → `routing.validate_funnel_graph` → `funnel_graph`; `revisao_esqueleto` FAILED quando reprova | jornada incompleta, dúvida duplicada, referência inexistente, `valor` ausente ou incompleto, fusão necessária, LP que só roteia, `/rec` dependente, próxima dúvida sem destino, reoferta de dúvida resolvida em todo caminho, ciclo sem ganho, beco, entrada sem conclusão, bloco visual fora da função ou sem entrega, ferramenta sem ativo | zero |
| Roteamento | `routing` + `jornada/contexto.politica_da_saida_oficial` | CTA principal = próxima dúvida; saída oficial `nao_aplicavel` não é obrigada; `boa` vem primeiro; `prematura` depois dos CTAs internos; sem fonte comprovada, fail-closed | zero |
| Redação | `jornada_da_pagina.jinja` (V1 e V2, condicional), `escrita_natural.jinja` (V2) | pergunta, promessa, o que está certo e o que é talvez resolvido, destinos (principal/secundário), saída oficial, valor, plano visual, ativos; escrita natural sem perder fato, número, link ou SEO | — |
| Revisão por página (V2) | `revisao.py` | categoria `naturalidade` (padrão Humanizer), sempre ajuste, patch na MESMA chamada; o código recusa patch que perde número ou toca link | — |
| Funil pronto | `jornada/revisao_global.py`, antes de qualquer publicação, só páginas aprovadas | bloqueio só com prova estrutural (CTA para dúvida resolvida em todo caminho, ciclo real, link oficial na LP, saída prematura antes da próxima dúvida, beco); proxy de termo é aviso | zero |
| Widget | `steps.step_widget` | ativo do arquiteto só com a fonte da regra no lastro da pesquisa da página; sem isso, nenhuma chamada | zero |
| Print oficial | `steps.proveniencia_do_print` | URL, data, título, trecho que comprova, legenda ("Reprodução... pertence ao site de origem"), alt, recorte, sha256 e estado; sem isso não é embutido | zero |
| Metadados | `pipeline/metadados.py`, `state.metadados`, `metadados_pN.json` | title, description, canonical (previsto/publicado), robots, OG, Twitter, breadcrumb, autor, datas, fontes, tipo; JSON-LD só com o que o texto mostra (FAQPage com perguntas visíveis, HowTo com passos reais, ItemList com checklist) | zero |

## Dossiê factual pré-redação (`run.dossie_factual`)

Com jornada e grafo aprovado, ANTES de qualquer briefing ou redação:

1. uma pesquisa do funil inteiro (`steps.dossie`, modelo exato, sem fallback;
   com `gemini/gemini-3.8-flash` + Google Search via `GEMINI_API_KEY`,
   `auth_mode api_key`). Modelo servido diferente do pedido bloqueia o funil;
2. fontes = SÓ as citações do `groundingMetadata` do provedor, com
   redirecionamento resolvido; URL que o modelo digitou sem a busca ter
   aberto é `unverified`;
3. verificação ao vivo de cada fonte (`url_verifier`); número, prazo, data e
   mudança exigem `valor` e `vigente_desde`; duas fontes com valor diferente
   para o mesmo requisito viram `conflict` e nenhuma das duas sustenta texto;
4. portão de cobertura determinístico por página: cada `RequisitoFactual`
   (`JornadaDaPagina.requisitos`, ou um derivado da resposta principal) com
   fato `verified`; saída oficial exigida com canal verificado; cálculo com
   fato numérico; ferramenta com a fonte da regra no lastro;
5. até 2 rodadas de complementação, dirigidas só ao que faltou;
6. `dossie_factual.json` (`domain/dossie.py`: FunnelDossier → PageDossier →
   fatos → CoverageResult), congelado por SHA-256 do conteúdo. Página sem
   cobertura fica `dossie_pN`/`blocked_pN` FAILED e não gasta nada depois.
   Um resume reaproveita o mesmo dossiê; hash divergente bloqueia tudo.

O redator, o juiz, o briefing e o revisor recebem a MESMA projeção da página
(`projecao_para_o_prompt`), só com fatos verificados dela. O grounding é
cobrado por consulta: o orçamento debita tokens + consultas × preço de tabela
do LiteLLM (teto conservador), e a telemetria registra as duas parcelas.

## Redação paralela segura (`run.page_workers`, 1 a 3)

`1` é o laço serial de sempre (`_processar_pagina`, byte a byte). `>1` exige
`dossie_factual` (erro de configuração sem ele) e só roda com o dossiê
congelado — a pesquisa faturada já aconteceu, serial. Duas fases, ambas com
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
