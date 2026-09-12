# Descoberta de oportunidades Meta para arbitragem

Data: 11/09/2026. Estado: **análise concluída; propostas provisórias, não implementadas**.
O refino global P11-T21 continua partial. Esta rodada responde à lacuna de ideias
de produto/performance; não é continuação automática dos tickets de código anteriores.

## O que realmente rodou

- Google ADK do harness existente, modelo efetivo `gemini-3.8-flash`, HIGH.
- Pesquisador público: search grounding com queries e 43 chunks. Algumas fontes
  secundárias apareceram apesar da instrução; grounding não prova todas as frases.
- Estrategista: HTTP 400 ao enviar schema nativo; sem usage retornado.
- Última chamada: reaproveitou pesquisa, pacote técnico e correções do lead. Entregou
  nove propostas estruturadas, validadas pelo host. Não houve crítico independente
  Gemini na recuperação; revisão final foi feita pelo lead.
- Limite respeitado: **3 despachos, 2 respostas, 36.883 tokens informados**. Custo
  faturado não retornado. Nenhuma chamada repetida de pesquisa.
- Zero escritas Meta/DB, zero geração de mídia, zero mudanças na aplicação ou ativação.
  Apenas harness, prompts e documentação local foram alterados.

## Resultado que vale usar

Autoridade: [OPPORTUNITIES.json](OPPORTUNITIES.json), nove oportunidades revisadas.
O `discovery.json` bruto é registro de pesquisa, **não uma fila aprovada de execução**.

| Ordem | Oportunidade | O que muda para o operador |
| --- | --- | --- |
| 1 | Diagnóstico anúncio → visita → monetização | Saber se investigar criativo, LP ou tag, usando métricas compatíveis. |
| 2 | Contribuição estimada + confiança | Decidir com custos e revisão dos dados visíveis; não apenas CTR/ROAS bruto. |
| 3 | Memória de hipóteses criativas | Novos briefings aproveitam aprendizados de tema/ângulo/cena/LP, sem inventar atribuição. |
| Depois | Fábrica de experimentos | Escolher o que testar e receber matriz pré-preenchida; flexível não é A/B. |
| Depois | Preparar ABO → CBO | Reusar a origem em novo rascunho, preservando post quando elegível e sem remontagem. |
| Depois | Congruência no preview | Enxergar promessa versus entrega da LP sem outro detector bloqueante. |
| Condicional | Posicionamentos, sinais de fadiga e telemetria da LP | Abrir novas investigações depois de comprovar campos, infraestrutura e elegibilidade. |

Cada item no JSON tem owner funcional, primeiro ticket, aceite, experimento,
confundidores, dependências e condição de parada/rollback. A implementação começa
por inventariar o que já existe, não por criar tabelas/compiladores duplicados.

## Onde o lead corrigiu o Gemini

- `financeiro.py` **já** tem `provisorio`, frescor e completude. A alegação contrária
  era errada. O incremento é histórico de revisão e custos, não novas flags iguais.
- Requisições GAM não equivalem a visitas: múltiplos slots/refresh invalidam a
  proposta de chamar requests/LPV de retenção. Coortes/denominadores precisam casar.
- Eliminados thresholds percentuais e janelas fixas sem dado, incluindo “maduro D+3”.
- Famílias mistas não podem receber cada uma toda a receita do mesmo conjunto.
- `contexto_pagina.py` lê a LP, não publica template WordPress. Tags exigem owner do site.
- Rejeitados novos bloqueios editoriais por palavras, atribuição de IVT a rejeição
  da LP e confusão entre assinatura de webhook e `appsecret_proof`.
- O [campo GPT trafficSource](https://developers.google.com/publisher-tag/reference#googletag.PrivacySettingsConfig.trafficSource)
  foi confirmado como opcional/reportável. Não existe nessa fonte prova de punição
  automática pela ausência; nem cabe ocultar origem para tentar elevar eCPM.
- [Receita estimada](https://support.google.com/admanager/answer/12958957?hl=en) e
  [ajustes posteriores](https://support.google.com/admanager/answer/6053295?hl=en)
  foram confirmados. Não justificam desconto exato por adset sem granularidade.
- As páginas Meta abertas diretamente pelo lead retornaram erro de acesso. Campos,
  limites, endpoints e elegibilidade citados pelo pesquisador permanecem candidatos
  a reverificação antes de qualquer mudança. Não se afirmou pesquisa Meta integralmente validada.

## Reprodutibilidade e limites

Prompt específico: `tools/meta-adk-review/OPPORTUNITIES.md`.
Runner: `tools/meta-adk-review/discover.py`; não expõe shell, banco ou edição ao modelo.
Pacote técnico, manifest, respostas e correções: `.claude-ads/runs/meta-opportunities-20260911-01/`.
O runner recusa sobrescrever run paga, limita três despachos e permite uma recuperação
explícita reaproveitando pesquisa; todo resultado permanece provisório até revisão humana.
Schema complexo foi retirado do parâmetro API após o HTTP 400; JSON continua validado
localmente, inclusive unicidade e referências das prioridades.

Testes locais: 30 testes do harness passaram (24 existentes + 6 de discovery).
Validação do artefato: nove IDs únicos, referências de fonte válidas e três prioridades.
Sem teste de performance da conta: faltam métricas recentes, custos, lag e elegibilidade.
A skill Ads orientou a separação entre hipótese e prova; a skill Gemini orientou SDK,
grounding e controle da execução. Nenhuma delas é evidência de melhoria de performance.

Memória operacional: P11-T24 registra esta descoberta, P11-T21 permanece partial.
Nó: `doc:meta_adk_refinement_loop` → `cap_meta_ads`. Frescor é conferido pelo comando
`scripts/atualizar_grafo_volc_os.py --check`, não por igualdade de commit.

Fechamento: reconstrução técnica/operacional executada; `--check` retornou
`current=true`, 2.122 insumos, digest
`1f348d642d66498cded408276ff7d2baca26b73d90d9de472913f07af6da37ee`.
Scanner sem padrões fortes de segredo e `git diff --check` aprovado. Sem commit/push
nesta rodada; alterações anteriores de inventário não foram descartadas.
