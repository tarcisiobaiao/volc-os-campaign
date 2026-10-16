# VOLC Measurement v3 — ativação controlada

Data: 15/10/2026  
Site: `creditoup.com.br`  
Supabase operacional: `https://database.agenciavolc.com.br`

## Resultado

A inteligência comportamental voltou a operar por uma fronteira única e
auditável. Foram ativadas apenas as substituições seguras do wrapper editorial e
do sensor. As tags legadas que escreviam direto no REST do Supabase ou poderiam
duplicar conversões permaneceram pausadas.

Fluxo efetivo:

`GTM-N4KS27ZV (v35) -> volc-ingest -> public.raw_events`

Rollback de GTM: publicar novamente a versão 34. O backup anterior da Edge
Function foi preservado no host operacional com permissão restrita.

## Alterações aplicadas

- `VOLC Sensor v3.0`: ativo em DOM Ready; exige `analytics_storage` no GTM;
  envia apenas eventos e campos allowlisted para `volc-ingest`.
- `WEBS Wrapper v2`: ativo na inicialização; exige `analytics_storage` e
  `ad_storage`; normaliza origem, mídia, campanha e slug sem escrever no banco.
- `volc-ingest`: limita origem, método, tamanho, lote, idade, host, path, nomes
  de evento e campos; erros internos não são devolvidos ao navegador.
- `raw_events`: RLS habilitada e forçada; `anon` e `authenticated` sem acesso;
  `service_role` limitado nominalmente a `SELECT` e `INSERT`.
- OAuth de publicação: token separado e restrito ao escopo
  `tagmanager.publish`; nenhum segredo foi versionado.

## Provas

- GTM live relido como versão 35, sem conflito de workspace.
- Origem permitida: HTTP 200 e inserção confirmada.
- Origem não permitida: HTTP 403 (`origin_not_allowed`).
- Evento fora do contrato: HTTP 422 (`no_valid_events`).
- `OPTIONS` permitido: HTTP 204.
- REST anônimo de `raw_events`: HTTP 401 / PostgreSQL 42501.
- REST com `service_role`: leitura HTTP 200.
- Smoke público em Chrome isolado, com redes de anúncio bloqueadas para não
  fabricar impressão: wrapper e sensor carregados, UTMs persistidas e uma única
  requisição ao endpoint.
- Linha real confirmada no banco: `volc_sensor_ready`, versão 3.0, path
  `/r/guia-cursos-senac/`, payload sanitizado e host preenchido.

## Consentimento

Esta rodada não alterou o mecanismo de consentimento do WordPress. O site já
envia um estado padrão `granted` antes da escolha do visitante e depois atualiza
o estado pelo banner. As tags novas declaram os tipos de consentimento exigidos;
portanto seguem o estado que o site fornece ao GTM. Esse comportamento existente
deve passar por revisão jurídica/privacidade própria; não deve ser confundido com
prova de manifestação individual do visitante.

## Limites honestos

- O smoke automatizado bloqueou redes publicitárias; os eventos GPT/ad view do
  wrapper não foram exercitados nessa prova para evitar tráfego artificial.
- A camada externa ainda apresenta `Access-Control-Allow-Origin: *`, aparentemente
  acrescentado pelo gateway. A validação server-side recusou origem indevida,
  mas o cabeçalho do gateway deve ser endurecido em missão separada.
- Não há ainda inventário completo nem detecção de drift de GA4/GTM; esta entrega
  é a primeira peça operacional do Tracking Control Plane.
- Os fatos históricos com host/path vazios não foram retroativamente corrigidos.

## Atualização v3.1 — 16/10/2026

A versão 36 do container publicou `VOLC Sensor v3.1` em workspace isolado, sem
alterar as tags de conversão. O envelope ganhou `seq`, monotônico por pageview,
e `raw_events` ganhou `event_seq`; a chave de idempotência passou a ser
`(sid, pid, event_name, ts_sec, event_seq)`. Isso preserva eventos legítimos do
mesmo tipo no mesmo segundo sem perder a deduplicação de um envelope repetido.

Provas da implantação:

- migration aplicada pelo owner real `supabase_admin`, em transação;
- backup prévio do DDL e do `volc-ingest` preservado no host;
- banco descartável reteve dois scrolls no mesmo segundo e recusou rollback
  destrutivo;
- Edge Function v3.1 aceitou três eventos, com sequências 1, 2 e 3;
- workspace GTM 37: zero conflito, uma mudança, quick preview sem erro;
- versão 36 criada e publicada sem erro de compilação;
- versão 35 continua sendo rollback imediato da tag; a coluna aditiva pode
  permanecer sem prejudicar envelopes v3.0, que recebem `event_seq = 0`.

