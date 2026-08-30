# SPEC — Data Manager API e copiloto contextual do Google Ads

**Estado:** proposta factual para incorporação ao Roadmap Vivo e ao grafo após a convergência das frentes em execução  
**Data da pesquisa:** 27/08/2026  
**Autoridade de dados do VOLC O.S.:** Supabase self-hosted em `database.agenciavolc.com.br`  
**Princípio:** navegador não recebe credencial Google, não consulta a conta diretamente e não executa mutação.

## 1. Decisão em uma página

São três peças diferentes e elas não devem ser misturadas.

| Peça | Papel correto no VOLC | Decisão |
|---|---|---|
| Google Ads API Developer Assistant | Ferramenta de engenharia para Claude Code/Antigravity: inspecionar schemas, validar GAQL, gerar código e diagnosticar integrações | Instalar no ambiente dos agentes; **não** embutir como chatbot do produto |
| Google Ads MCP server | Ponte read-only entre um agente e dados atuais da conta Google Ads | Candidato a ferramenta da Bia, sempre atrás do backend; não é autoridade de escrita |
| Data Manager API | Porta oficial para enviar conversões, eventos e, depois, audiências first-party | Tornar a autoridade de ingestão do novo loop de conversões do VOLC |

O widget flutuante nas páginas de campanha deve ser a **Bia**, executada pelo Hermes. O Developer Assistant não é um serviço de chat para produto e a documentação o descreve explicitamente como sistema de missão para engenharia. A Bia poderá usar fatos já persistidos no VOLC e, quando necessário, uma ferramenta read-only controlada, como o Google Ads MCP ou endpoints canônicos do próprio backend.

## 2. Fatos oficiais que mudam o roadmap

1. A Data Manager API está disponível em v1, em disponibilidade geral, e recebe eventos por `POST /v1/events:ingest`.
2. A versão 1.2 adicionou conversões offline e enhanced conversions for leads para Google Ads; a 1.3 adicionou diagnósticos por `request_id`.
3. Para novas integrações de conversão offline, o caminho atual é Data Manager API. Desde 15/06/2026, `UploadClickConversion` pode falhar para developer tokens que não o utilizavam anteriormente.
4. A Data Manager API não usa developer token da Google Ads API. Ela usa Google Cloud + OAuth/ADC com o scope `https://www.googleapis.com/auth/datamanager`.
5. A mesma credencial local pode receber também o scope `adwords`, mas cada runtime deve continuar com o menor privilégio necessário.
6. Eventos podem carregar `gclid`, `gbraid`, `wbraid`, session attributes ou user data. Dados pessoais exigem normalização, hash/criptografia e consentimento aplicável.
7. `transactionId` deduplica eventos da mesma ação de conversão enviados por fontes diferentes.
8. `validateOnly=true` valida sem ingerir. Uma ingestão aceita devolve `requestId`; o status posterior precisa ser consultado até `SUCCESS`, `PARTIAL_SUCCESS` ou `FAILURE`.
9. O primeiro diagnóstico deve ocorrer após aproximadamente 30 minutos, com backoff e jitter, por até 24 horas.
10. Cada `IngestEventsRequest` aceita até 2.000 eventos e 10 destinos; o projeto tem cota de 100.000 requisições/dia e 300/min para ingestão.

## 3. Estado comprovado do VOLC

- O cliente oficial Python do Google Ads já está integrado: `google-ads>=25.0` no ambiente de worker/dev.
- `volc_ads/gads/client.py` fixa a API v25, usa `GoogleAdsClient.load_from_storage()` e separa as contas pelo `login_customer_id`.
- A aplicação serverless não carrega o SDK Google Ads de propósito. Chamadas Google pertencem ao worker/engine, não ao Vite nem ao backend da Vercel.
- O banco já registrou 9.468 visitas, 9.407 com GCLID, mas todas permaneceram pendentes.
- `conversion_queue` e `conversion_batches` existem como intenção estrutural e permanecem vazias; não há job produtor nem job de envio.
- `niche_conversion_mappings` está vazia.
- O roadmap já contém P07 — “Fechar o loop de conversão offline” — mas o PRD antigo ainda aponta `UPLOAD_CLICKS` pela Google Ads API.
- A Bia/Hermes já está curada no grafo como runtime vivo e capacidade `todo`; gateway, widget e contratos faltam.

**Limitação da leitura do grafo:** o snapshot consultado foi gerado no commit `f4cf128`, enquanto o repositório já estava em `b1f4661`. Os fatos operacionais acima foram reconfirmados na curadoria, no Roadmap Vivo e no código atual.

## 4. Correções de conceito antes de escrever código

### 4.1 O evento não é uma compra

O desenho antigo cria `adviewinterstitial` como `PURCHASE`. Isso é semanticamente falso quando não houve compra.

Antes do primeiro envio, o dono do produto precisa aceitar um contrato de evento real, por exemplo:

- `monetized_session`: sessão em que pelo menos uma impressão publicitária válida foi observada;
- `qualified_monetized_session`: sessão que superou critérios declarados de qualidade e monetização;
- `publisher_value_realized`: valor efetivamente reconciliado com uma fonte de receita.

A categoria Google deve representar a ação real — provavelmente `ENGAGEMENT` ou outra categoria comprovadamente compatível — e não `PURCHASE`. A primeira ação nasce **secundária/observação**, sem participar do Smart Bidding. Ela só pode virar primária depois de qualidade, atraso, cobertura, deduplicação e correlação com receita serem medidos.

### 4.2 “Valor estimado” e “receita observada” não são iguais

O evento precisa carregar:

- `value_kind`: `observed`, `estimated` ou `unknown`;
- fórmula e versão, se estimado;
- moeda;
- fonte de receita;
- instante do fato e instante da reconciliação;
- evidência de atribuição à sessão/campanha.

Um valor desconhecido não vira zero. Um valor estimado não pode ser apresentado como receita realizada.

### 4.3 Os 9.407 GCLIDs são evidência, não uma fila pronta

Não fazer backfill em massa. O material histórico está envelhecido, sem valor calculado e foi produzido antes do contrato novo. O canário começa numa data de corte nova. O legado só entra depois de uma auditoria explícita de elegibilidade, janela, semântica e deduplicação.

### 4.4 `AW-id/label` deixa de bloquear o envio offline

Na Data Manager API, o destino Google Ads usa o **ID numérico da ação de conversão** como `productDestinationId`. O `AW-id/label` continua relevante para tags online, mas não deve bloquear o job de eventos offline.

## 5. Arquitetura-alvo

```text
Site/GTM/sensor
    │ fato de sessão + identificadores + consentimento
    ▼
Supabase self-hosted
    site_visits / raw_events / fatos de monetização
    │ produtor determinístico
    ▼
conversion_queue
    │ agrupador idempotente (até 2.000 eventos)
    ▼
conversion_batches
    │ validateOnly ou ingestão autorizada
    ▼
Data Manager API
    │ requestId
    ▼
diagnóstico assíncrono (30 min → backoff → até 24 h)
    │
    ├── recibo imutável + contagens + warnings/errors
    ├── cockpit da campanha
    └── somente após aceite: sinal primário para bidding
```

### 5.1 Módulos propostos

Criar sob `volc_ads/datamanager/`, sem acoplar ao frontend:

- `contrato.py`: evento canônico, destino, consentimento, valor e recibo;
- `formatacao.py`: timestamps, moeda, identificadores e hash sem persistir PII em log;
- `cliente.py`: cliente `google-ads-datamanager`, ADC e retry tipado;
- `destinos.py`: conta operacional, conta de login e conversion action ID;
- `produtor.py`: transforma fatos elegíveis em fila, sem I/O externo;
- `lotes.py`: agrupa, sela e deduplica;
- `envio.py`: `validateOnly`/ingestão e captura de `requestId`/warnings;
- `diagnostico.py`: `RetrieveRequestStatus` com backoff, jitter e prazo;
- `worker.py`: agenda o ciclo sem depender do n8n;
- `politica.py`: autorização `UPLOAD_CONVERSAO`, kill switch, idade máxima e limites.

Dependências pertencem ao runtime do worker, não a `backend/requirements.txt` da Vercel:

- `google-ads-datamanager`;
- opcionalmente `google-ads-datamanager-util==0.2.0` para formatação/criptografia.

### 5.2 Contratos persistidos mínimos

Reaproveitar as tabelas existentes, migrando-as somente após prova em cluster descartável.

`conversion_queue` precisa distinguir:

- identidade interna e `source_event_id` único;
- conta operacional, conta de login e conversion action ID;
- tipo e versão do evento;
- `event_timestamp` e `transaction_id` estável;
- presença de `gclid`/`gbraid`/`wbraid`/session attributes, sem expor valores na UI;
- estado e origem do consentimento;
- valor, moeda, `value_kind` e versão da fórmula;
- estado `eligible → queued → validated → sent → reconciled`, ou falha nomeada;
- idempotency key e hash do payload sanitizado.

`conversion_batches` precisa guardar:

- lote, janela e destinos;
- `validate_only`;
- request fingerprint;
- `request_id` do Google;
- contagens de aceitos, rejeitados, pendentes e avisos;
- tentativas, próxima consulta e prazo máximo;
- resposta sanitizada, autorização, executor e recibo.

Nenhuma tabela deve guardar token, segredo ou user data em texto puro.

## 6. Bia nas páginas de campanha

### 6.1 Primeira versão

Widget flutuante autenticado, read-only/suggest-only:

- “Explique por que esta campanha não entrega”;
- “Compare com a última leitura boa”;
- “Quais dados faltam antes de mexer no lance?”;
- “Explique os avisos do último lote de conversões”;
- “Gere uma proposta de próxima ação”, sem executá-la.

O frontend envia apenas a pergunta e um identificador de contexto. O backend resolve os fatos e envia ao Hermes um envelope sanitizado:

- usuário, papel e autorização;
- rota, campanha interna, conta e canal;
- snapshot e frescor;
- métricas e período;
- vínculos, alertas e recibos;
- fontes consultadas e campos ausentes.

### 6.2 Ferramentas da Bia

Ordem de autoridade:

1. snapshots e recibos persistidos no VOLC;
2. endpoints canônicos read-only do backend;
3. Google Ads MCP read-only para pergunta ad hoc autorizada;
4. documentação/schema para explicação técnica.

O Google Ads MCP atual é read-only e expõe descoberta de contas, `search` GAQL e metadados. Se o Hermes não falar MCP nativamente, criar um gateway interno com ferramentas equivalentes; não expor MCP, OAuth ou developer token ao navegador.

O Developer Assistant permanece fora do runtime: ele ajuda os agentes a construir e testar essas ferramentas.

## 7. Roadmap executável

### D0 — Preflight de acesso, sem envio

- identificar o Google Cloud Project correto;
- habilitar Data Manager API;
- decidir usuário OAuth versus service account com impersonation;
- conceder acesso desse principal ao MCC/contas corretas;
- gerar ADC com scope `datamanager` e, se realmente necessário, `adwords`;
- provar chamada de descoberta/metadata sem expor token.

**Aceite:** autenticação provada e nenhum dado de cliente transmitido.

### D1 — Contrato do evento e governança

- escolher o nome e a categoria semanticamente verdadeiros;
- declarar evento primário/secundário;
- definir valor observado/estimado, moeda, idade máxima e consentimento;
- definir transaction ID e idempotência;
- documentar dados proibidos e retenção.

**Aceite:** uma fixture completa e fixtures de ausência recusadas por testes puros.

### D2 — Fila e lote em cluster descartável

- evoluir `conversion_queue`/`conversion_batches`;
- implementar produtor, lote e recibo;
- provar concorrência, retomada, duplicidade e falha parcial;
- provar RLS e ausência de PII em logs.

**Aceite:** o mesmo fato executado duas vezes gera um evento e um payload.

### D3 — `validateOnly` controlado

- instalar cliente no worker;
- montar destino com conversion action ID numérico;
- enviar um lote mínimo com `validateOnly=true` após autorização para transmissão;
- registrar erros de campo de forma sanitizada.

**Aceite:** validação 200, sem ingestão e com recibo local completo.

### D4 — Canário real secundário

- selecionar uma conta e uma ação secundária;
- enviar 1–10 eventos novos, nunca o backlog inteiro;
- guardar `requestId`;
- consultar diagnóstico após 30 minutos até estado terminal;
- conferir Google Ads e comparar contagens.

**Aceite:** `SUCCESS` ou `PARTIAL_SUCCESS` explicado, nenhuma duplicidade e rollback operacional por desligamento da autorização.

### D5 — Cockpit e observabilidade

- mostrar última fila, lote, request ID mascarado, status, avisos, erros e frescor;
- alertar job parado, backlog crescente, baixa taxa de aceite e valor ausente;
- ligar explicação da Bia aos recibos, não a memória da LLM.

**Aceite:** o operador entende “o que aconteceu, quando, com quantos eventos e o que fazer”.

### D6 — Graduação para bidding

- medir cobertura, atraso, aceitação, deduplicação e relação com receita;
- manter ação secundária até o owner aceitar critérios objetivos;
- propor mudança para primária com antes/depois, teto, janela e rollback.

**Aceite:** nenhuma ação de conversão vira biddable por convenção ou entusiasmo.

### B0 — Developer Assistant no harness

- instalar/pinar o plugin em Claude Code;
- registrar o codebase com `context_dir`;
- usar `/validate-gaql`, `/inspect-object`, `/troubleshoot-conversions`, `/get-cids` e `/pmax-filter` como gates auxiliares;
- revisar qualquer código gerado antes de integrar.

### B1 — Bia read-only na campanha

- `/api/bia/chat` no backend;
- contexto resolvido por IDs, não JSON livre do navegador;
- streaming opcional;
- memória por conversa com TTL e auditoria;
- zero ação externa.

### B2 — Google Ads MCP como ferramenta opcional

- provar suporte MCP do Hermes ou implementar gateway;
- allowlist de consultas/recursos e limites por usuário;
- timeout, custo, redaction e cache;
- registrar a consulta e a fonte usada na resposta.

## 8. Prioridade recomendada

1. **D1 — contrato do evento**: sem ele, o sistema pode otimizar para uma mentira.
2. **D0 — acesso Data Manager**: valida a dependência externa.
3. **D2/D3 — fila idempotente + validateOnly**.
4. **D4/D5 — canário e cockpit**.
5. **B0 — Developer Assistant no harness**, em paralelo por ser isolado e reversível.
6. **B1 — Bia read-only** depois que o cockpit tem fatos confiáveis.
7. **B2 — MCP** apenas se reduzir trabalho sem criar uma segunda autoridade de dados.
8. **Audiências/Customer Match** ficam para uma fase posterior: exigem first-party data legítimo, consentimento, política de privacidade, elegibilidade da conta e volume útil.

## 9. Delta proposto para o Roadmap Vivo e o grafo

Não aplicar enquanto outras frentes editam a curadoria.

- manter `cap_offline_conversion`, mas trocar a evidência futura de “Google Ads UploadClickConversion” para “Data Manager IngestEvents + diagnostics”;
- ligar `cap_offline_conversion` a um novo sistema `system:google_data_manager`;
- adicionar conceito `concept:first_party_data_contract`;
- conectar `cap_bia_copilot` ao `Hub de Controle de Mídia`, `Cockpit de campanha`, `cap_offline_conversion` e, opcionalmente, `system:google_ads_mcp`;
- P07-T02: definir evento, valor, consentimento e ação secundária;
- P07-T03: fila/lotes idempotentes para Data Manager;
- P07-T04: `validateOnly`, canário, `requestId` e diagnóstico;
- P07-T05: cockpit + Bia explicando recibos;
- criar tarefa de dívida: remover `AW-id/label` como bloqueador do upload offline, preservando-o apenas para tag online quando aplicável;
- registrar o Developer Assistant como ferramenta de engenharia, não como capacidade do produto.

## 10. Fontes oficiais

- Google Ads API Developer Assistant: <https://developers.google.com/google-ads/api/docs/developer-toolkit/ai-assistant>
- Conceito do Developer Assistant: <https://developers.google.com/google-ads/api/docs/developer-toolkit/what-is-developer-assistant>
- Google Ads MCP server: <https://developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server>
- Client libraries Google Ads: <https://developers.google.com/google-ads/api/docs/client-libs/python/>
- Data Manager API: <https://developers.google.com/data-manager/api>
- Acesso e autenticação: <https://developers.google.com/data-manager/api/devguides/quickstart/set-up-access>
- Bibliotecas cliente: <https://developers.google.com/data-manager/api/devguides/quickstart/install-library>
- Envio de eventos: <https://developers.google.com/data-manager/api/devguides/events/send-events>
- Diagnósticos: <https://developers.google.com/data-manager/api/devguides/diagnostics>
- Limites: <https://developers.google.com/data-manager/api/devguides/limits>
- Categorias de conversão: <https://developers.google.com/google-ads/api/docs/conversions/categories>
- Políticas de Customer Match: <https://support.google.com/google-ads/answer/6299717>

