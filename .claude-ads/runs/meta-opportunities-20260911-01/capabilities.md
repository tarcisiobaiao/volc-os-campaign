# Pacote técnico revisado pelo lead — 2026-09-11

Fonte: worktree operacional, base 0f48c25. Consulta inicial ao grafo híbrido e
verificação de digest: current=true. Inventário abaixo é amostral, não prova de
ausência global. Nenhuma conta de anúncios ou banco foi consultado nesta rodada.

## Presentes em código

- Jornada conta/Página/LP/mensuração/conjuntos/criativos/revisão, rascunhos, packs,
  biblioteca e copy IA. `src/pages/trafego/MetaCriacaoPage.tsx` e
  `src/components/trafego/meta/MetaCampaignReadView.tsx`.
- Dashboard com campanha/conjuntos/anúncios/criativos. Read model hierárquico;
  propostas de gestão não equivalem a executor de mutações remoto provado.
  `MetaCampaignReadView.tsx:943-1214`; roadmap P11-T06 permanece partial.
- Financeiro em `backend/app/trafego/meta/financeiro.py`: gasto adset/dia, GAM por
  utm_campaign_value=adset_id, campanha soma conjuntos, nível campaign reconcilia
  gasto sem somá-lo de novo; moeda/fuso/completude explícitos. Não há evidência
  fornecida de lucro líquido após revshare, impostos e todos os custos operacionais.
- `backend/app/trafego/meta/desempenho_anuncios.py`: insights por anúncio observados,
  sem ratear receita/gasto do conjunto; ausente não vira zero. `_METRICAS` enumera
  spend, impressions, clicks, ctr, cpc, cpm. Não afirmar que clicks é outbound_clicks.
- `backend/app/trafego/meta/sincronizador.py`: inventário/sync idempotente e registro.
  Roadmap P11-T20: schema do roteador Meta/GAM aplicado; primeira cadeia real no novo
  roteador e alinhamento do workflow remoto ainda pendentes. Não concluir que toda
  mensuração anterior inexiste; são escopos e provas diferentes.
- `backend/app/trafego/meta_execucao/compilador.py:765-822`: reuso de post estático
  verifica Página, imagem, destino, copy e ID. Recusa assumir equivalência de post
  flexível. FLEXIBLE_IMAGES gera creative_asset_groups_spec no AD; pool explícito
  de textos combina imagens/textos dentro do conjunto, não entre conjuntos.
- `backend/app/trafego/meta_execucao/executor.py`: executor PAUSED, ledger,
  dependências e readback inclusive creative_asset_groups_spec. Existência do código
  não prova aceite remoto completo para toda receita/conta.
- `backend/app/trafego/meta/copy_context.py:152-245`: contexto resolvido de seleção,
  pack, master, run; fatos referenciados, assunto, desejo, motivações como hipóteses,
  ângulo, big idea, cena e copy. Valida destino e origem. Já evita pedir novo briefing.
- `backend/app/criativo/contexto_pagina.py`, `studio/spec_visual.py`, `execucao.py`,
  `packs.py`: fluxo LP→briefing/spec→geração→assets→pack. Qualidade criativa e ganho
  de CTR não provados por testes. Usuário quer menos panfleto e mais congruência e
  apelo; não tratar estética subjetiva como ganho financeiro demonstrado.
- Últimos tickets Gemini implementados: recuperação de preview de copy após retry
  e foco ao adicionar/remover texto flexível. 38 testes focais passaram. São polimentos
  locais, NÃO um estudo amplo de oportunidades de arbitragem.

## Lacunas/provas a obter

- P11-T21 refino geral partial; P11-T23 dois tickets locais done; P11-T19 contexto
  copy e revisão técnica partial; P11-T06 dashboard e gestão remota partial.
- Sem export atual de performance, janela madura, dados de sessões/ad requests,
  custos líquidos, consentimento/eventos, histórico de experimentos ou recursos
  liberados para a conta. Prioridades propostas não são diagnóstico da conta.
- Busca focal em backend/app/trafego/meta* não localizou creative_fatigue ou
  ad_recommendations. Isso é pista para inventariar, não prova de ausência global.
- Não foi comprovado feedback automático de resultado econômico para seleção de
  ângulos no briefing; se sugerir, faça ticket de inventário/contrato antes de duplicar.
