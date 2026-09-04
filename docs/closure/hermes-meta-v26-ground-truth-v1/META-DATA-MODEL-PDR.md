# PDR — modelo de dados Meta v26

Status: contrato confirmado com precondições. Este documento não aplica schema.

## Decisão

Adotar a opção C: manter a identidade v9 intocada e usar um read model Meta isolado. O slice `v15_01_meta_ads_read_model.sql` materializa Business → Ad Account → Campaign → Ad Set → Ad → Creative e recibo de sync; ele não contém Insights, upload ou plano de mutação. O seam reutilizável do v10 é intenção → blueprint → lote → item → validação → recibo, respeitando os nomes, chaves e relações que realmente existem na migration.

## Autoridades reutilizadas

- `criativo_master` (v11) continua sendo o mestre imutável de mídia. `trafego_meta_asset_upload` apenas associa um mestre ao hash de imagem ou ID de vídeo obtido numa conta Meta.
- `meta_business_portfolio`, `meta_ad_account` e `cofre_credencial_referencia` (v13) continuam sendo a autoridade de onboarding e referência de segredo.
- O locator de credencial não cruza a API de UI. Um broker privilegiado resolve a referência somente no servidor e mantém o segredo em memória pelo menor tempo possível.

## Identidade e tenancy

Uma identidade Meta é sempre resolvida dentro da conta ou do pai do objeto; ela não ocupa `customer_id`/`campaign_id` de v9. `project_id` é resolvido pelo binding ativo e validado no servidor. O read model v15 mantém exatamente uma associação de projeto aberta por ad account.

## Insights

O fato diário tem grão explícito por provider, conta, nível (`ACCOUNT`, `CAMPAIGN`, `ADSET`, `AD`), objeto, período, janela de atribuição e conjunto de breakdowns. Métricas ausentes permanecem `NULL`. Actions e action values ficam em tabela filha por tipo e janela; não são achatadas em uma coluna ambígua.

## Temporalidade

O binding projeto/conta usa `confirmado_em` → `desfeito_em` e índice parcial no registro aberto. Já `trafego_meta_ad_creative_binding` em v15 é uma associação corrente observada, com `ausente_desde`; não deve ser apresentada como histórico temporal. Se histórico de troca de criativo for necessário, uma migration NEXT cria intervalos `iniciado_em`/`encerrado_em` e índice único parcial no vínculo aberto.

## Gates antes de migration

1. Revisar/aprovar o slice v15 e provar que Google continua lendo e escrevendo os mesmos IDs.
2. Provar isolamento entre projetos e contas Meta e o contrato do broker de segredo.
3. Conferir novamente campos e permissões exatos na versão Graph API fixada.
4. Criar migrations NEXT separadas para Insights/upload e, se aprovado, histórico temporal.
5. Validar RLS, grants, índices, retenção e rollback antes de qualquer apply.

O inventário detalhado e as formas propostas estão em `META-DATA-MODEL.json`.
