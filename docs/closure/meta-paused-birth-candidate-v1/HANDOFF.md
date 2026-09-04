# Meta PAUSED birth — candidato local v1

## Veredito

`META_PAUSED_BIRTH_ENGINE_LOCAL_CANDIDATE`

Este pacote implementa o compilador e o executor hermético da primeira receita
Meta de tráfego para site. Ele **não** monta rota HTTP, não resolve credencial,
não aplica schema e não chama a Meta nesta entrega.

## Receita fechada

1. Campaign `OUTCOME_TRAFFIC`, `AUCTION`, `PAUSED`.
2. Ad Set com budget diário em minor units, `LANDING_PAGE_VIEWS`, cobrança por
   `IMPRESSIONS`, `LOWEST_COST_WITHOUT_CAP`, destino `WEBSITE`, targeting BR e
   `PAUSED`.
3. Creative link-image com Page e `image_hash` já existentes. Creative não
   recebe `status`, pois não é objeto de veiculação.
4. Ad ligado ao Ad Set e ao Creative, `PAUSED`.

Receitas diferentes — Sales/custom conversion, Advantage Audience explícito,
placements manuais, upload de asset, vídeo e campaign budget — falham com código
nomeado em vez de alterar silenciosamente o pedido.

## Segurança operacional materializada

- plano determinístico e aprovação presa ao SHA-256 exato;
- capabilities separadas para `validate_only` e `create_paused`;
- `validate_only` nas raízes independentes e, na saga, antes de cada POST real;
- recibo durável obrigatório e commitado antes de cada POST de criação;
- retomada de passo já criado lê o objeto e não repete o POST;
- timeout é ambíguo, marca reconciliação e nunca permite retry cego;
- read-back acontece após cada degrau e precisa confirmar nome, parentes,
  objetivo/configuração econômica e `PAUSED` nos objetos veiculáveis;
- token, IDs externos, Page ID e image hash não entram na projeção pública;
- Graph API fixada em `v26.0` e host fixado em `graph.facebook.com`.

## Arquivos

- `backend/app/trafego/meta_execucao/contrato.py`
- `backend/app/trafego/meta_execucao/compilador.py`
- `backend/app/trafego/meta_execucao/registro.py`
- `backend/app/trafego/meta_execucao/executor.py`
- `backend/tests/test_meta_paused_birth.py`

## Decisão arquitetural

O executor não foi encaixado em `app.trafego.ledger`. O fechamento atual é
Google-shaped e presume uma única chamada bem-sucedida; uma criação Meta possui
quatro efeitos parcialmente falháveis. O pacote define uma porta própria de
saga/recibo. A integração produtiva deve implementar essa porta em schema
aditivo provider-neutral, sem inserir objetos Meta na tabela Google v9 e sem
usar o read model v15 como write-side.

## O que falta para liberar um canário real

1. integrar o SHA da Bia e este candidato numa única branch operacional;
2. criar/aplicar, sob autorização separada, o schema de aprovação, execução e
   recibo por passo;
3. implementar o adapter Supabase da porta `RegistroSagaMeta`;
4. montar rota autenticada com capability exata `META_CREATE_PAUSED`;
5. ligar o blueprint controlado da UI, referência opaca de conta/Page/asset e
   confirmação explícita das categorias especiais;
6. provar `validate_only` real no macOS após clique do operador;
7. somente em autorização posterior, criar um único canário PAUSED e conferir
   os quatro objetos por read-back.

Nenhum item do Roadmap deve virar `done` por este candidato isolado.
