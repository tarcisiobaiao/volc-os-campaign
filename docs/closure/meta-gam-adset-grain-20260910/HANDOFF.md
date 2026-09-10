# Fechamento — atribuição GAM no grão de conjunto Meta

Data: 10/09/2026
Estado: **PARTIAL operacional** — contrato, schema oficial e testes concluídos; primeira linha real Meta+GAM e workflow n8n remoto ainda não foram provados.

## Problema confirmado

`gam_metrics.utm_campaign_value` não é uma identidade universal de campanha. No legado Google ele resolve uma campanha; no nascimento Meta o template grava `{{adset.id}}`. O trigger anterior tratava os dois namespaces como campanha e podia:

- deixar a receita Meta sem correspondência com a hierarquia;
- criar uma linha sintética de campanha em `daily_campaign_metrics` usando um ID de conjunto;
- misturar namespaces quando um mesmo texto existisse em Google e Meta;
- esconder ausência de vínculo projeto↔conta Meta.

## Contrato final

1. O GAM continua sendo o registro bruto de receita e preserva `utm_campaign_value`.
2. Para Meta, `utm_campaign_value = adset_id` e a atribuição canônica é conjunto/dia.
3. A campanha Meta soma exclusivamente seus conjuntos filhos; não recebe uma segunda receita em nível de campanha.
4. Anúncios carregam `utm_content={{ad.id}}` para diagnóstico, mas a receita não é repetida por anúncio.
5. `daily_campaign_metrics` continua sendo compatibilidade de campanha/dia. O trigger só projeta nela quando existe exatamente uma campanha legada compatível com o projeto.
6. Meta conhecida, chave desconhecida, colisão de namespace ou ambiguidade nunca criam campanha sintética.

Fluxo esperado:

```text
Meta hierarchy sync -> ad_account/campaign/adset
                         |
project binding ----------+
                         |
GAM raw row (project_id + date + utm_campaign=adset_id)
                         |
vw_trafego_meta_financeiro_conjunto_dia_gam
                         |
SUM dos conjuntos filhos
                         |
vw_trafego_meta_financeiro_campanha_dia_gam
```

## Implementação

- `supabase/migrations/20260910143000_gam_attribution_grain_router.sql`
  - classificador `vw_gam_attribution_route`;
  - trigger legado refeito com roteamento fail-closed;
  - índices de resolução por conjunto, projeto, UTM e data;
  - views financeiras Meta escopadas pelo vínculo ativo da conta ao projeto;
  - receita ambígua vira `NULL` com status nomeado, nunca fan-out.
- `src/sql/update_sync_gam_function.sql`
  - instalador legado alinhado ao mesmo contrato;
  - removida a criação de campanha desconhecida;
  - atualização Google preserva métricas de entrega já existentes.
- `n8n/gerar_flows_meta_ledger.py` e `n8n/volc_meta_insights_dia_d1.json`
  - nomenclatura corrigida para conjunto/dia;
  - coleta Meta continua em `level=adset`.
- `backend/tests/test_gam_attribution_grain_router_sql.py`
  - prova comportamental em PostgreSQL descartável, não apenas inspeção textual.

## Banco oficial

Destino: `https://database.agenciavolc.com.br`.

Backup anterior ao DDL:

- arquivo operacional: `/root/backups/pre_meta_gam_adset_grain_20260910_1345.dump`;
- SHA-256: `b1a0c5f3d618c8ec1e676685e7bab460b9dc6330bde10110b956a2465b12b5a7`;
- tamanho aproximado: 2,8 MB.

Aplicadas, em ordem:

1. `v15_02_meta_ads_insights.sql`;
2. `20260907210000_meta_read_model_consistency.sql`;
3. `20260908000000_meta_insights_escopo.sql`;
4. `20260908120000_meta_financeiro_conjunto_dia.sql`;
5. `20260910143000_gam_attribution_grain_router.sql`.

Pós-condições relidas no catálogo oficial:

- fatos e views de Insights Meta presentes;
- views financeiras por conjunto e campanha presentes;
- classificador de rota GAM presente;
- exatamente um trigger de sincronização instalado;
- 99 linhas legadas de `daily_campaign_metrics` preservadas;
- zero grant de leitura das novas views para browser (`anon`/`authenticated`);
- padrão antigo que criava campanha desconhecida ausente.

As tabelas Meta e `gam_metrics` estavam vazias no momento da aplicação. Nenhum histórico foi inventado ou migrado.

## Provas

- suite integrada de atribuição/tracking/workflows: **144 passed**, 0 failed;
- validador isolado dos workflows n8n: **279 passed**, 0 failed e 1 integração pulada por módulo fora do `PYTHONPATH`;
- migration reexecutável e trigger único;
- Google compatível projeta receita;
- Meta adset não cria linha falsa em `daily_campaign_metrics`;
- desconhecido, colisão e projeto divergente falham fechados;
- total de campanha Meta é soma dos filhos;
- `security_invoker` e grants mínimos conferidos.

## Lacunas reais

- O workflow remoto `9jOsfVPGrFOQAcUR` não foi aberto, editado nem executado nesta rodada: o conector disponível retornou erro e não houve autorização para sondar credenciais antigas locais. O artefato canônico versionado está correto, mas a instância remota ainda precisa ser reconciliada/importada.
- Ainda falta a primeira prova com hierarquia Meta real, vínculo de projeto, linha de Insights por conjunto e linha GAM do mesmo dia/ID.
- Se o workflow remoto escrever diretamente em `daily_campaign_metrics`, ele precisa ser substituído. O guardião do banco cobre toda escrita que passa por `gam_metrics`, não uma escrita direta arbitrária na tabela legada.

Não houve chamada à Meta Ads, ativação de campanha, custo de mídia nem chamada paga de IA nesta correção.
