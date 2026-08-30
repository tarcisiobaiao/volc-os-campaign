# ADR — Runtime do ORAKUL, workers e scheduler

- **Estado:** proposto (missão Fable 5, 2026-08-28). Nada deste ADR foi provisionado.
- **Decisores:** dono do VOLC O.S. (pendente). Este documento recomenda; não autoriza.
- **Contexto de missão:** investigação read-only; nenhuma migration aplicada, nenhum
  deploy executado, `FORGE_PERMITIR_ESCRITA` ausente (verificado: `env | grep -c` → 0).

## Pergunta

Onde devem rodar (1) a API síncrona de projeção/decisão, (2) o worker ORAKUL
(coleta → features → políticas → proposta → shadow) e (3) o scheduler, quando o
Decision Intelligence Lab sair do dataset sintético para shadow e depois canário —
sem entregar a propriedade intelectual da regra ao n8n e sem criar um segundo ledger.

## Fatos levantados (evidência, 2026-08-28)

| Fato | Evidência |
|---|---|
| O único Supabase operacional é self-hosted no Hetzner `178.156.196.149` (Ashburn), 3 vCPU, 3,8 GB RAM (~1,6 GB disponíveis), 34 GB livres, 13 containers saudáveis há 3 semanas | `ssh … free -m; df -h; docker ps` (leitura direta desta missão) |
| O backend FastAPI roda apenas em dev local (uvicorn :8010 via `start-dev.sh`); não há Dockerfile nem projeto Vercel para ele | `start-dev.sh:78,117`; ausência de `backend/Dockerfile`/`backend/vercel.json` |
| O frontend + Express (`api/`) já são Vercel (projeto `webgo`) | `CLAUDE.md` §Deploy; `vercel.json` |
| O n8n legado roda em VPS Hostinger `n8n.srv860769.hstgr.cloud`; o único executor de mutação ativo é um webhook n8n sem autenticação (snapshot inventariado) | `inventario-n8n/flows/atuacao-apply-bidding-webhook-v2.json` (`active:true`, `credentials:null`) |
| A inteligência legada é 100 % Python determinístico embutido em Code nodes (BEAST 1.678 linhas; motores Lance/Insights ~12 k chars cada); nenhum LLM participa da decisão | leitura direta dos 5 flows da missão |
| O kernel novo (`volc_ads/inteligencia_decisao/`) é Python puro, hermético, sem I/O — roda em qualquer runtime com CPython 3.12+ | `pipeline.py` (0 imports de rede) |
| O ledger-alvo (v10_01/v10_02) é Postgres puro com gatilhos; **não aplicado** | `supabase/migrations/README.md:510-516` |
| Volume de trabalho projetado: dezenas de contas, coleta 1–2×/dia por conta, jobs de segundos a poucos minutos — não é big data | contagens vivas: 84 campanhas em `trafego_campanha`, 86 tabelas |

## Opções avaliadas

### 1. Vercel (funções serverless)
- **A favor:** já é o runtime do front; zero servidor novo.
- **Contra (eliminatório para o worker):** timeout de função (padrão 10–60 s; máx.
  800 s em planos pagos) incompatível com coleta+shadow multi-conta; Python é
  segunda classe no projeto atual (o `api/` é Node); sem processo residente para
  locks/fila; cron da Vercel dispara HTTP, não supervisiona; cold start
  imprevisível para janela de coleta; segredos do Google Ads passariam a viver
  num terceiro provedor.
- **Veredito:** aceitável só para a *projeção de leitura* que o front já consome;
  **rejeitado** para worker/scheduler.

### 2. Railway
- **A favor:** deploy simples de container Python, cron nativo, logs razoáveis.
- **Contra:** terceiro provedor novo (Vercel + Hetzner + Hostinger já existem);
  custo fixo (~US$ 5–20/mês) sem ganho sobre um VPS que já existe; o Postgres
  continua em Ashburn — mesma latência WAN de qualquer forma; sem rede privada
  com o Supabase.
- **Veredito:** plano B legítimo se o time quiser PaaS; não recomendado agora.

### 3. Cloud Run (jobs + service)
- **A favor:** jobs com timeout de horas, retries nativos, escala a zero,
  observabilidade GCP, proximidade natural com Google Ads API; `us-east4` fica
  geograficamente perto de Ashburn.
- **Contra:** conta GCP nova para operar (billing, IAM, Artifact Registry);
  segredos em mais um cofre; rede até o Postgres self-hosted é pública (exigiria
  IP allowlist ou túnel); complexidade de deploy maior que a fase atual precisa.
- **Veredito:** **arquitetura-alvo para escala** (quando houver dezenas de contas
  ativas e canário T2 rotineiro), não para a fase 1.

### 4. Worker/cron em VPS existente (Hetzner, o mesmo box do Supabase)
- **A favor:** rede local com o Postgres (latência ~0, sem exposição extra);
  segredos já vivem ali (`/root/supabase/docker/.env`); custo zero incremental;
  docker compose já é o padrão do host; systemd timers dão scheduler supervisionado
  sem serviço novo; o worker de fase 1 (shadow read-only) cabe em 256–512 MB.
- **Contra:** box com 3,8 GB RAM já hospeda 13 containers (~1,6 GB livres) — exige
  `mem_limit` e disciplina; acoplamento de falha (se o box cai, cai banco e worker
  — mitigado pelo fato de que sem banco o worker não teria o que fazer); CPU 3
  vCPU compartilhada.
- **Veredito:** **recomendado para a fase 1**, com gatilhos de saída explícitos.

### 5. n8n
- **A favor:** já agenda coisas hoje; UI de execução.
- **Contra (eliminatório):** é exatamente o anti-padrão que esta missão veio
  desfazer — regra de negócio de 1.678 linhas dentro de Code node, sem versão, sem
  teste, sem code review, com segredos inline (P10-T08) e executor de mutação sem
  autenticação. O n8n agendar um processo não pode voltar a significar o n8n ser
  o dono intelectual da regra.
- **Veredito:** **rejeitado** como runtime de decisão/execução. Permitido apenas
  como *gatilho de conveniência* (chamar `POST /jobs/...` autenticado) e como
  canal de notificação, durante a transição.

### 6. Híbrido (recomendação)
API de leitura onde já está; worker ao lado do banco; scheduler no host; fila no
Postgres; n8n rebaixado a gatilho/notificação até ser aposentado dessas rotas.

## Decisão recomendada

### Fase 1 — "shadow ao lado do banco" (implementável já, custo ~zero)

| Papel | Escolha | Detalhe |
|---|---|---|
| **Runtime da API** | FastAPI existente, container `volc-backend` no box Hetzner, atrás do Kong (rota `/trafego/*`) | Kong já termina TLS em `database.agenciavolc.com.br`; front continua na Vercel |
| **Runtime do worker** | Container `volc-worker` (mesma imagem do backend, entrypoint diferente) no mesmo box, `mem_limit: 512m`, `cpus: 1` | Executa: coleta GAQL read-only → normalização → kernel `volc_ads.inteligencia_decisao` → persistência de evidência/diagnóstico/proposta no ledger (quando v10 for aplicada) → shadow |
| **Scheduler** | systemd timers no host (`volc-worker-coleta.timer` 2×/dia por conta; `volc-worker-shadow.timer`) chamando `docker compose run --rm` | Supervisão, jitter e journal nativos; nada de cron dentro de container |
| **Fila** | Tabela Postgres `trafego_job` com `FOR UPDATE SKIP LOCKED` (migration proposta na SPEC; **não aplicada nesta missão**) | Volume é de dezenas de jobs/dia; Redis/RabbitMQ seria complexidade sem carga |
| **Locks** | `pg_advisory_xact_lock(hash(customer_id))` por conta | Impede duas execuções simultâneas sobre a mesma conta |
| **Armazenamento** | Somente o ledger v9/v10 no Supabase oficial; recibo de arquivo (`volc_ads/dados/recibos/`) vira espelho secundário até a v10_01 ser aplicada — nunca um segundo ledger | evita o split-brain já observado no legado |
| **Observabilidade** | `trafego_evento` (append-only, já aplicado) + heartbeat por rotina (P02-T04) + logs JSON do container no journald; alerta de rotina parada via `alertas.py` | o Ads Health Monitor mínimo (P06-T06) consome o heartbeat |
| **Segredos** | `.env` root-only no host (padrão já existente); zero segredo em n8n Code node; zero segredo em browser | P10-T08 |
| **Deploy/rollback** | build da imagem por tag git + `docker compose up -d`; rollback = tag anterior; imagem anterior mantida | sem pipeline novo obrigatório na fase 1 |
| **Fallback** | Se o box degradar (RAM disponível < 1 GB sustentado), mover `volc-worker` para um CX22/CPX11 dedicado (~€4–6/mês) na mesma região, acesso ao Postgres via rede privada Hetzner (vSwitch) | gatilho objetivo, medível |

### Arquitetura-alvo — escala (não provisionar agora)

- **Worker:** Cloud Run Jobs (`us-east4`), uma execução por conta, retries nativos,
  Workload Identity; imagem única compartilhada com a fase 1.
- **Scheduler:** Cloud Scheduler.
- **Fila:** continua Postgres (`SKIP LOCKED`) enquanto < ~10 k jobs/dia; Pub/Sub só
  se surgir fan-out real.
- **Rede:** IP allowlist do egress do Cloud Run no firewall Hetzner **ou** túnel
  WireGuard; nunca abrir o Postgres ao mundo.
- **Gatilhos para migrar:** (a) > ~20 contas ativas com coleta 2×/dia ficando
  > 30 min de janela; (b) canário T2 rotineiro exigindo isolamento de falha do
  box do banco; (c) necessidade de concorrência > 3 workers simultâneos.

### O que morre

- Mutação por webhook n8n sem autenticação: **desativar** (decisão operacional do
  dono; esta missão não editou workflow).
- Regra de negócio em Code node: congelada como memória (P14-T01); toda régua
  nova nasce em `volc_ads/` com versão, owner e teste.
- Escrita de orientação no Supabase legado `txvvzpstquqmbhljudfn.supabase.co`:
  rota condenada; o produtor ativo hoje viola o ADR de autoridade do Supabase.

## Custos (ordem de grandeza)

| Cenário | Custo mensal incremental |
|---|---|
| Fase 1 (mesmo box) | ~R$ 0 (usa folga do VPS atual) |
| Fase 1b (box dedicado ao worker) | €4–6 |
| Railway (plano B) | US$ 5–20 |
| Cloud Run alvo | ~US$ 0–10 em baixa escala (jobs curtos, escala a zero) + operação GCP |

## Consequências

- A regra sai do n8n sem big bang: o BEAST não é reativado; suas réguas úteis são
  reimplementadas como `RegraDeOtimizacao` versionada com teste dourado
  (P09-T08), provadas em shadow (P09-T09) antes de qualquer T2.
- Nenhuma recomendação vira mutação por acidente: o único caminho de escrita
  passa a ser o executor com `FORGE_PERMITIR_ESCRITA` + aprovação humana
  (v10_02: `trafego_aplicacao` exige FK de `trafego_aprovacao` com
  `decisao='aprovada'`).
- O box do banco ganha um vizinho: mitigado por `mem_limit`, `cpus` e gatilho de
  evacuação medível.

## Pendências que este ADR não resolve

1. Aplicar v10_01/v10_02 (decisão do dono; migrations prontas, bloqueadas por
   protocolo).
2. Autorizar o deploy do backend FastAPI atrás do Kong (hoje ele nem está em
   produção).
3. Desativar/blindar o webhook de mutação legado no n8n vivo.
4. Escolher a conta/projeto GCP se e quando os gatilhos de escala dispararem.
