# Decisões que exigem o dono — fechamento global VOLC O.S.

Estas decisões NÃO podem ser tomadas por agente nenhum, de nenhum tier. Cada
missão que esbarra numa delas para no portão e registra o estado, em vez de
inventar autorização. Ordenadas por impacto no Horizonte A.

## D1 · Aplicar v10_01/v10_02 (ledger decisório) no Supabase oficial
- **O que é**: as migrações do ledger de decisão (intenção, proposta,
  aprovação, aplicação, rollback — 19 tabelas provadas em cluster descartável)
  ainda não foram aplicadas no banco oficial (P09-T01/P09-T02 `partial`).
- **Por que é do dono**: mutação de schema em produção; o protocolo exige
  backup conferido + autorização explícita.
- **O que destrava**: fechamento do ciclo proposta→aprovação→recibo (P05-T06,
  P05-T11), executor por porta única (P09-T03).
- **Caminho conservador enquanto não decidido**: writers e UI continuam
  apontando para contrato tipado com adapter local; nenhuma missão finge que o
  ledger existe em produção.

## D2 · Instalar credencial OAuth no servidor e ativar a rotina contínua de coleta
- **O que é**: a coleta de inteligência Google Ads v3 provou 10 recibos reais
  em execução manual; a rotina contínua aguarda instalação de credencial e
  ativação de timers/agenda (P05-T07, P09-T14).
- **Por que é do dono**: credencial de produção + processo permanente no
  servidor.
- **O que destrava**: frescor contínuo do diagnóstico Search; deixa de haver
  "coleta como evento" e passa a haver "coleta como operação".

## D3 · Autoridade de agenda: n8n ou worker (systemd)
- **O que é**: existem dois candidatos a orquestrador da coleta (workflows n8n
  D0/D-1 legados + pacote systemd versionado não instalado). P10-T16 exige
  decidir UM e registrar ADR; dois coletores concorrentes são proibidos.
- **Por que é do dono**: define onde vive a operação (n8n é a prática vigente;
  worker muda o plano de operação).
- **Recomendação registrada no roadmap**: preferencialmente n8n chamando o
  coletor/RPC canônico — a proposta desta análise segue essa preferência.

## D4 · Fechar grants/RLS e rotacionar credenciais antes de qualquer lançamento
- **O que é**: P02-T05 (`risk`) mantém como bloqueadores pré-lançamento a
  rotação/reemissão de credenciais e REVOKE/RLS das seis tabelas operacionais,
  com smoke anônimo provando zero escrita.
- **Por que é do dono**: rotação de credencial derruba consumidores que o
  inventário ainda não fechou; é uma janela de manutenção, não um commit.
- **Consequência**: nenhuma missão pode declarar "lançável" antes de D4 —
  o plano marca isso como gate humano do cluster Search lançável.

## D5 · Autorizar validate_only/upload real por conta (Display e afins)
- **O que é**: P04-T04/P04-T05 estão a uma prova real de `done`; essa prova
  toca a conta Google Ads real (mesmo sem gasto) e o protocolo exige
  autorização explícita por ato.
- **Por que é do dono**: envolve conta real; a fronteira "engenharia na conta
  laboratório, dinheiro na conta financeira" é decisão de negócio.

## D6 · Aplicar v11_03 (runtime criativo) no Supabase oficial
- **O que é**: migração + rollback provados 129/129 em cluster descartável;
  produção tem zero tabela `criativo_render_*` (P17-T03 `todo`, com
  "nenhuma aplicação sem autorização explícita" no aceite).
- **Horizonte**: B — não bloqueia o caixa; decidir quando o Estúdio subir de
  prioridade.

## D7 · Destino das branches de integração concorrentes
- **O que é**: existem múltiplas linhas de integração vivas
  (`integration/global-convergence-20260829`,
  `integration/autonomous-closure-20260829`, `integration/volc-unificado-20260827`,
  `integration/qg-v3-redator`, `integration/estudio-criativo-c0-c1-c3`, etc.).
  O ledger de integração propõe ordem e decisão por item, mas a escolha da
  linha-tronco de convergência é do dono se houver conflito de estratégia.
- **Caminho conservador**: a proposta trata a `main` como única verdade e cada
  integração como missão pequena com gates; nada é mesclado nesta missão.

## D8 · Quatro perguntas abertas da missão SPEC+PRD de arbitragem
- **O que é**: a memória do projeto registra que o diagnóstico SPEC+PRD foi
  entregue com decisões anunciadas e quatro perguntas ao dono ainda sem
  resposta (fonte: memória de sessão `volc-spec-prd-arbitragem`). Não foram
  reencontradas respondidas em documento nesta varredura.
- **Ação**: o dono confirma se já respondeu (e onde) ou se as perguntas
  seguem abertas; até lá a matriz mantém `NÃO_CONFIRMADO`.

## D9 · Destino do backup remoto da main (URGENTE — risco existencial)
- **O que é**: `origin/main` só tem o Initial commit; a main local está 411
  commits à frente e com história divergente. Fev-ago/2026 existe só neste
  disco (F002).
- **Por que é do dono**: escolher o remoto (novo repositório privado próprio;
  NUNCA o upstream webgo) e autorizar o push (provavelmente
  `--force-with-lease`).
- **Custo**: ~10 minutos. É a decisão de melhor razão risco/benefício de toda
  esta análise.

## D10 · Desativar/blindar o webhook n8n de mutação `apply-bidding`
- **O que é**: o workflow T2Lr1MD33w4aZFJY está ATIVO e SEM autenticação,
  podendo mutar lances Google Ads fora de qualquer governança — violando o
  ADR de porta única (F017). O ADR de runtime já o lista em "o que morre".
- **Por que é do dono**: desativar um workflow n8n de produção é mutação
  externa; pode haver dependência operacional não mapeada.
- **Caminho conservador**: M-W2-05 entrega o inventário do que o webhook faz
  e quem o chama; a desativação em si acontece na janela D4/D10 (M-W3-13).

## D11 · Modelo de câmbio (04 bloqueada vs `update_all_revenue_conversions`)
- **O que é**: a migração 04 do volc-sync está vetada por 2 defeitos
  destrutivos e conflita com a função existente; hoje duas regras de conversão
  concorrem no legado (mais a disputa de triggers em `revenue_converted`).
- **Por que é do dono**: é decisão de produto (taxa por data vs taxa mensal
  fixada; quem reconstrói o histórico).
- **Bloqueia**: a reativação de receita (P06-T03/T04) — Horizonte B.

## D12 · Deploy do backend FastAPI + regra de colocação de cargas no box do banco
- **O que é**: o ADR de runtime ORAKUL (PROPOSTO) recomenda FastAPI + worker
  no box Hetzner do Supabase; o ADR do Remotion decreta "nunca na caixa do
  Supabase" para render. Falta a regra única de que carga pode morar com o
  banco (F040), e o backend não está em produção (F024).
- **Por que é do dono**: provisionar produção + aceitar o risco de colocation.
- **Bloqueia**: operação fora do localhost; shadow→canário do ORAKUL runtime.

## D13 · Intervenção nos supervisores vivos
- **O que é**: às 23:21Z de 29/08, demand-gen e orakul rodavam a attempt 2
  fadadas ao mesmo FileNotFoundError dos gates (F011); creative-s0 e
  pytest-ratchet já estão blocked; o supervisor-contínuo v0 morreu por
  wall_budget com candidato pronto.
- **Opções**: (a) deixar as tentativas morrerem e colher via M-W2-06 +
  reativar após M-W1-05 (conservador, recomendado); (b) criar o
  `backend/.venv` no clone agora para salvar as tentativas em curso (mexe no
  ambiente de processos vivos — só com o dono ciente).
- **Recomendação registrada**: (a). Nenhum processo foi tocado nesta missão.

## H1 · Ação de operador (5 minutos): confirmar os vínculos
- P05-T04 está a um clique de `done`: abrir a UI autenticada e confirmar os
  vínculos Maquininha→funil 74 e FGTS→funil 65 (`trafego_vinculo` sai de zero
  linhas). Não é decisão — é a menor ação humana com maior efeito no roadmap.
