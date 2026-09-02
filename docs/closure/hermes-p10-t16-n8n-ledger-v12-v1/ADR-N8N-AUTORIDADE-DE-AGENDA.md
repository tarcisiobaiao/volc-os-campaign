# ADR — o n8n é a única autoridade de agenda da ingestão Google Ads

**Estado:** proposta aceita nesta lane · **aplicação pendente de autorização**
**Data:** 01/09/2026
**Escopo:** ingestão contínua Google Ads → Supabase oficial (família campanha-dia
D0/D-1 e, por consequência, a cadência do coletor de inteligência)
**Tarefa:** P10-T16 · **Base:** `b6e226ab2f6d339d2c7c899b83b05ff4a95ebcac`

---

## Contexto

Duas rotinas concorriam pelo mesmo trabalho, e nenhuma estava ligada.

De um lado, os **workflows n8n D0/D-1** (`hN15qFAVOqH0135q`, `tKUItcd0AoD9mozV`),
que são o plano de orquestração da operação vigente: eles já rodavam a ingestão
de custo Google Ads antes desta tarefa, foram adaptados em 28/08/2026 (API v25,
dedupe por `customer_id + campaign_id`, `Merge` antes de o cursor andar) e ficaram
**inativos** aguardando decisão.

Do outro, o **pacote systemd** de `deploy/google-intelligence/`: um serviço
`oneshot` e dois timers (a cada 4 h e diário às 06:15), versionados e nunca
instalados, que agendariam `scripts/coletar_google_inteligencia.py`.

A `SPEC-GOOGLE-ADS-INTELLIGENCE-COLLECTOR.md` já dizia o que ninguém tinha
decidido: *"Só uma agenda pode permanecer ativa."* O critério de pronto do
cluster CL-04 repete: *"uma única autoridade de agenda ativa, sem sobreposição
entre n8n e systemd."*

## Decisão

**O n8n é a única autoridade de agenda da ingestão contínua Google Ads.**

Consequências diretas, todas verificáveis:

1. **A agenda vive no n8n.** Dois workflows, dois papéis: D0 às 06:00, 12:00,
   18:00 e 23:00 (`America/Sao_Paulo`) e D-1 às 06:00, sobre a janela fechada do
   dia anterior.
2. **O coletor Python continua existindo, e não agenda nada.** Ele permanece como
   biblioteca de domínio, execução one-shot, caminho de diagnóstico e *fallback*
   manual. `scripts/coletar_google_inteligencia.py --modo …` e o caminho por alvo
   nomeado de P09-T14 seguem operacionais e são a rota de recuperação quando o
   n8n estiver fora do ar.
3. **Os timers systemd ficam desinstalados e inativos.** O pacote continua
   versionado como alternativa declarada — apagá-lo destruiria a única descrição
   de como o worker seria operado —, com esta ADR como condição de aposentadoria:
   ele só volta à mesa se a decisão for revertida por outra ADR.
4. **Nenhuma segunda agenda executa a família.** Nem cron, nem Vercel cron, nem
   um segundo workflow n8n. O gate `scripts/gate_agenda_unica_gads.py` mede isso
   a cada rodada.
5. **O n8n orquestra; o banco decide.** Identidade, idempotência, precedência
   D0 × D-1, reconciliação e projeção de compatibilidade ficam na RPC
   `volc_registrar_gads_campanha_dia`. O fluxo não tem permissão de escrita
   direta — `service_role` não possui `INSERT`/`UPDATE`/`DELETE` nas tabelas.

Registro operacional: **`N8N_IS_SCHEDULE_AUTHORITY`**.

## Por que o n8n, e não o worker

A instrução operacional já apontava o n8n salvo incompatibilidade técnica
reproduzida. Nenhuma apareceu — e vale registrar o que foi conferido, porque
"nenhuma incompatibilidade" é uma alegação, não um fato, até alguém medir:

| Exigência | n8n | Verificação |
|---|---|---|
| Paginação sem descartar linha | laço explícito com token no item | 3 páginas → 3 lotes contíguos, 7 linhas, nenhuma perdida (simulador) |
| Lote/batch com saída `done` correta | `SplitInBatches` v3 | `main[0]` fecha, `main[1]` itera; validador confere elo a elo |
| Retry com teto | `retryOnFail` + `maxTries: 3` + espera | declarado no nó e conferido pelo validador |
| Idempotência | chave por passada + lote | mesma passada repetida devolve o recibo guardado |
| Estados semânticos | `ok`/`parcial`/`falhou` + vazio confirmado | 65 provas no simulador |
| Segredo fora do artefato | credencial referenciada por id/nome | varredura no JSON, zero achados |
| Zero mutação Google | GAQL `SELECT`, sem `:mutate` | varredura + campos conferidos no SDK v25 |

Contra o worker pesavam três fatos, e nenhum deles é preferência:

- a instalação exige **copiar uma credencial OAuth** (`google-ads.yaml`) para o
  servidor oficial, ou seja, aumentar a superfície de segredo em produção para
  resolver um problema de agendamento;
- o n8n **já é o plano de orquestração vivo** da operação — trocar de plano
  significaria migrar também o que já funciona, não só o que falta;
- o worker não elimina o n8n: ele **acrescenta** uma segunda autoridade, que é
  exatamente o defeito que P10-T16 existe para fechar.

## O que esta ADR **não** decide

- **Não** aposenta o coletor Python. Ele continua sendo onde a inteligência
  Google Ads (diagnóstico, recomendações, simulações, forecast, PMax) é lida, e
  essa família **não** foi migrada para o n8n aqui. Esta ADR trata da autoridade
  de AGENDA; a cadência daquela família, quando for ligada, também passa a ser do
  n8n, e isso exige outra entrega.
- **Não** liga nada. Os dois workflows continuam inativos e a migration continua
  não aplicada. A sequência de ativação está em `AUTORIZACAO-ATIVACAO.md`.
- **Não** migra os 13 flows do núcleo que ainda escrevem no Supabase hospedado
  legado (F018). Isso é o cluster CL-11, e não se resolve por troca cega de URL.

## O risco que fica aberto, dito sem rodeio

O inventário sanitizado de **19/08/2026** registra cinco workflows da família
Google Ads com gatilho de agenda e `ativo: true` na instância viva:
`custo-gads-report`, `custo-gads-report-d1`, `custo-gads-placements-display`,
`custo-gads-placements-display-d1` e `criacao-gads-factory-v3`.

Esta lane **não conseguiu ler a instância viva** (`REAL_N8N_READ_NOT_PROVEN`:
não há credencial de n8n disponível no ambiente). Logo, não é possível afirmar
daqui que só uma agenda ficará ativa — apenas que **nenhuma das agendas desta
entrega está ligada**, o que torna a sobreposição impossível hoje e obrigatória
de conferir antes de ligar. Por isso o primeiro passo da autorização é humano e
no painel: identificar os dois workflows por ID, confirmar seu estado, e
desativar o que for duplicata antes de ativar o par novo.

## Como esta decisão é revertida

Uma ADR sucessora que:

1. registre a incompatibilidade técnica **reproduzida** que motivou a troca;
2. desative os dois workflows n8n **antes** de instalar qualquer timer;
3. prove, com `systemctl` e com o painel, que só uma agenda ficou de pé;
4. preserve a projeção de compatibilidade e a RPC — o worker também escreveria
   por ela, porque a autoridade de dados não muda com a autoridade de agenda.
