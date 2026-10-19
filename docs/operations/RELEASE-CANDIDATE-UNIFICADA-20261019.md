# Release candidate unificada — 19/10/2026

Estado: **candidata local, não publicada**.

Branch: `integration/release-candidate-20261019`  
Base: `6e924fed` (`lab/data-foundation-20261016`)  
SHA antes da reconciliação operacional: `7eef6c8b`

## O que foi unificado

- Fundação Data Intelligence, Item 5 e kernel econômico de viabilidade V2.
- Measurement/GTM v36, Sensor v3.1, WEBS Wrapper v2, `event_seq`, verificador e `volc-ingest`.
- Bia/Hermes: gateway FastAPI, widget web, streaming, anexos, comandos governados e migration candidata.
- W13: shadow de portfólio com um experimento por campanha, sem autoridade de escrita.
- D1 sobre o Design System V2 existente, preservando o shell D3 e a semântica honesta de ausência.

## Decisões de integração

- Arquivos gerados e autoridades compartilhadas não foram aceitos cegamente de branches antigas; Roadmap, curadoria e grafo são reconciliados uma vez nesta candidata.
- W13 permaneceu `ADMIN`-only e preservou expiração individual e conferência byte/hash dos artefatos.
- O D1 não reintroduziu os cartões antigos da home nem sobrescreveu o `PonteDeComando` do D3.
- A ausência de `hypothesis` em `backend/requirements-dev.txt` foi corrigida porque impedia a coleta obrigatória do W14.
- Nenhuma migration, publicação GTM, deploy, push, mudança de campanha, gasto ou escrita em produção foi executada nesta integração.

## Provas

| Gate | Resultado |
|---|---:|
| Measurement focado | 5 passed |
| Bia backend | 176 passed, 4 skipped |
| Bia frontend | 50 passed, 1 skipped |
| W13 backend | 33 passed |
| W13 freedom-lab | 55 passed |
| W13 frontend | 27 passed |
| Agenda W13 em Linux com `flock` | 17 passed, 1 skipped |
| Inventário/laboratório/sombra integrado | 352 passed |
| Data Intelligence completa | 1287 passed, 3 skipped |
| TypeScript | verde |
| Build Vite de produção | verde |
| Gate bancada fora do bundle | verde |
| Autoridade Supabase | `https://database.agenciavolc.com.br` confirmada |

### Suítes globais e dívida herdada

- Frontend completo com configuração hermética: **2530 passed, 8 skipped, 44 failed em 6 suítes Meta**. As áreas desta integração passam; os 44 casos são dívida do conjunto Meta anterior, em grande parte timeouts sob carga e expectativas anteriores ao accordion.
- Backend completo na candidata: **6748 passed, 125 skipped, 35 failed**.
- Backend completo na base, com o mesmo interpretador e dependências: **6559 passed, 121 skipped, os mesmos 35 failed**.
- Portanto, a candidata acrescenta 189 provas backend verdes e não introduz uma nova falha backend; os 35 casos continuam como dívida explícita de canário/golden/toolchain/SQL Meta e configuração hermética.

## Segurança e limitações

- `gitleaks` sobre todo o histórico encontra achados preexistentes; no delta da candidata há dois padrões em commits intermediários, ambos fixtures/fingerprints documentados, não credenciais operacionais. A árvore final também contém fixtures que o scanner genérico reconhece como tokens sintéticos.
- A varredura não autoriza publicar. O cutover precisa de revisão por área e rollback nomeado.
- O Sensor v3.1 continua descartando o `campaign.id` numérico como possível PII. A fonte foi integrada para não se perder, mas P08-T11 permanece aberta até correção, publicação autorizada e canário de sete dias.
- Data Intelligence continua laboratório sem autoridade financeira. W13 continua shadow sem botão de execução.
- Bia permanece `partial`: código e provas existem, mas merge/deploy/migration/QA autenticado não fazem parte desta integração.

## Memória operacional afetada

- `P08-T11` — código da medição preservado; risco do campaign.id segue aberto.
- `P09-T04` — Bia promovida de `todo` para `partial`, sem alegar deploy.
- `P14-T02` — Data Intelligence e W13 registrados como candidata/shadow, ainda `partial`.
- Nós: `cap_behavior`, `risk:sensor_campaign_id_pii_filter`, `cap_bia_copilot`, `system:hermes`, `concept:campaign_shadow_recommendation`, `concept:data_intelligence_lab`.

## Próxima fronteira segura

1. Revisar e publicar a branch candidata remota sem avançar `main`.
2. Fazer QA autenticado do frontend e da Bia.
3. Fechar a dívida Meta global ou registrar baseline aprovado antes do cutover.
4. Corrigir P08-T11 em nova mudança pequena e publicar GTM com rollback nomeado.
5. Só depois separar migrations/deploys por domínio, cada um com canário e recibo.

