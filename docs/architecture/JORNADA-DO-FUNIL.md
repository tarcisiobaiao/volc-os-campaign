# Jornada do funil — contrato, portões e medição (07/10/2026)

O funil deixou de ser um conjunto de páginas com links e passou a carregar a
JORNADA do leitor: `intenção → entrada → resposta imediata → qualificação →
próxima dúvida ainda aberta → solução/saída oficial → monetização → medição →
nova versão`. A mudança estende o que existia (contrato `editorial`, portão de
grafo, revisão V2) e não cria uma segunda plataforma.

## Fontes que motivaram (evidência, não instrução)

- *Tomada de Decisão Baseada em Dados* (Pubx 2026, apresentação visual):
  conteúdo é produto; IA produz, pessoa decide; uma intenção → uma solução,
  resposta rápida com profundidade; a campanha é ferramenta de descoberta
  (hipótese ≠ realidade); volume sem intenção econômica não é vitória;
  monetização faz parte do desenho; o ciclo construir → medir → decidir →
  modificar. As taxas do slide "taxa de conversão" (≥50% Search, ≥30–35%
  Display) são ilustrativas e **não** viraram limiar em lugar nenhum.
- *Relatório MiroFish Creditoup/SENAC*: **simulação qualitativa, 0/29
  entrevistas de agentes com transcrição**. Os achados (CTA de renda universal,
  ciclos renda ↔ curso e estado ↔ inscrição, página do estado como checkpoint,
  saída oficial boa x prematura, LP que só roteia) viraram contratos e casos de
  teste — nunca métrica observada.

## O contrato

`Page.jornada` (`JornadaDaPagina`) e `FunnelPlan.jornada` (`JornadaDoFunil`),
em `funnelforge-migracao/engine/src/funnelforge/domain/models.py`. Opcionais e
aditivos: card sem jornada roda exatamente como antes.

- Referências entre páginas usam `duvida_id`, nunca slug (o sufixo de posição
  `-pr`/`-pN` não as afeta).
- Por página: pergunta principal, trabalho do leitor, resposta imediata,
  coortes de entrada, `ja_resolvido`, `proxima_duvida`, condição terminal,
  `entrada_direta` (autocontida | depende_de_contexto), saída oficial
  (esperada, classificação, condição, justificativa), monetização (papel,
  restrições), `retornos_justificados`, hipótese de medição, evidências com
  natureza (`hipotese` | `simulacao` | `observacao_real`).
- Por funil: intenção principal, solução principal, checkpoint, coortes
  (canal, entrada, promessa, profundidade, próximo passo), hipótese, evidências.
- Destinos priorizados com motivo continuam em `editorial.links` (fonte única
  das arestas). A jornada fica fora do `editorial` de propósito: o dump do
  `editorial` vai cru para os prompts do ramo V1, cujo ouro é byte a byte.

Fluxo: prompt do arquiteto (`backend/app/n8n_prompts/funnel_builder.py`) →
revisor do arquiteto (preserva, aponta) → `page_factory` (`writer_briefing.
jornada`) → ponte do motor (`adapters/briefing_volc.py`, jornada inválida falha
na carga, antes de qualquer gasto).

## Os portões

| Momento | Onde | O que | Custo |
|---|---|---|---|
| Antes da 1ª chamada paga | `pipeline/jornada.revisar_esqueleto` → `routing.validate_funnel_graph` → `funnel_graph` | bloqueia: jornada incompleta, dúvida duplicada, referência inexistente, LP que só roteia, resposta imediata ausente, `/rec` dependente de contexto, próxima dúvida sem destino, CTA para dúvida já resolvida, ciclo sem ganho de informação, beco sem saída, entrada sem caminho até conclusão, próximo passo de coorte fora do mapa. Avisa: saída oficial prematura/divergente, coorte fria guiada, mesma promessa para busca paga e tráfego frio, message match fraco | zero |
| Roteamento | `routing._contextual_routes` | o CTA principal (hero) é o destino da próxima dúvida, não a ordem do card. O fan-out "para todas as soluções restantes" sobrevive só como fallback de card sem `editorial` | zero |
| Redação | `prompts/jornada_da_pagina.jinja` incluído no contrato do leitor (V1 e V2), no juiz, no briefing e no revisor | pergunta, promessa da primeira dobra, o que já foi resolvido, próxima dúvida, destino principal, classificação da saída oficial, limites de monetização | — |
| Funil pronto | `pipeline/jornada.revisar_funil_pronto` → `state.revisao_global`, `revisao_global.json` | uma passada: promessa fora da primeira dobra (antes do 1º slot do Ad Inserter), CTA repetido, loop no texto real, saída oficial na LP ou antes da próxima dúvida, saída boa ausente, órfã, beco, CTA universal, message match. Só propõe; `microajustes_aplicados: 0` | zero |

Ordem corrigida no caminho: o classificador de `engajamento` (chamada paga)
passou a rodar DEPOIS do portão de grafo; funil quebrado não paga nem ele.

## Saída oficial: boa ou prematura

`classificar_saida_oficial`: sem saída esperada → `nao_aplicavel`;
justificativa explícita → `boa`; na LP → `prematura`; com condição terminal
declarada → `boa`; senão → `prematura`.

## Contrato de medição

`domain/medicao.py` + `jornada.contrato_de_medicao` → `medicao.json` no run
(só quando o grafo passou). Sinais previstos com escopo e contrato de origem:
chegada por coorte, escolha de ramo, progressão, resolução, saída oficial
boa/prematura, loop/revisita, abandono, receita por sessão, RPM/valor de sessão
e Core Web Vitals. Nenhum tracking novo foi implantado; o campo `coleta` diz o
que já existe (parcial, P08-T02/P08-T07) e o que não existe.

A separação de natureza é estrutural: `observacao_real` recusa fonte
`simulacao:*` e exige valor, janela e amostra; `simulacao`/`hipotese` recusam
número (só faixa). `PropostaDeNovaVersao` tem `requer_aprovacao_humana: True`
e `publicacao_automatica: False` como literais.

## Provas

`engine/tests/test_jornada_senac.py` (casos C1–C12 sobre a fixture
`tests/fixtures/jornada_senac/arquitetura.json`), `test_jornada_redator.py`,
`test_benchmark_modelos.py`, ouro V1 `test_editorial_v2_flag_off_identico.py`
intacto, `backend/tests/test_jornada_arquiteto.py`.

## O que não foi feito

Sem UI, sem tracking, sem LLM no revisor global (julgamento de sentido continua
no juiz/revisor por página), sem estado pessoal. CTA condicional por sessão (a
recomendação do MiroFish) exige estado de visita: fora deste contrato.
