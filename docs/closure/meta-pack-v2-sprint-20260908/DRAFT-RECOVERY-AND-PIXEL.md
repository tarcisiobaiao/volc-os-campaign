# Rascunhos recuperáveis e catálogo de pixels

## Entrega

- Criador Meta: botão Rascunhos permanente, contador, resumo/data, indicação Em edição, paginação e Continuar. Salva a montagem atual antes de navegar; falha não descarta trabalho. Demonstração não consulta dados reais.
- GET autenticado /api/trafego/meta/drafts usa proprietário da sessão, cache no-store e resumos sem conteúdo dos anúncios. Erro não vira lista vazia. Retomada reabre a página para não reutilizar identidade/state do editor anterior.
- Migration 20260909013856_meta_campaign_draft_list.sql aplicada no Supabase oficial. Apenas schema privado e duas funções de leitura; nenhuma alteração de dados, grant de tabela ou autorização de publicação. Função pública SECURITY INVOKER encaminha para função privada SECURITY DEFINER, restritas a service_role. Tabela permanece fechada inclusive ao SELECT direto service_role.
- AdsPixel retornado pela edge tipada adspixels pode ser classificado como PIXEL sem discriminador redundante. Discriminador explícito desconhecido, estado inválido e indisponibilidade continuam tratados. Nenhuma inferência de elegibilidade por nome ou de DATASET pela nomenclatura do Business Manager.
- Ajuda de mensuração distingue atribuição ao usuário do sistema de vínculo do dataset à conta de anúncios. ViewContent continua sendo evento padrão.

## Evidências

- Backend/SQL: 70 testes passando; apply/reapply em PostgreSQL descartável, paginação, owner isolado, anon/authenticated recusados e tabela sem SELECT direto.
- Frontend: 63 testes passando em cinco arquivos (11 draft/hook + 52 criador/eventos).
- Build passou. TSC mantém erros globais herdados, sem erro nos arquivos desta alteração.
- Chrome isolado com APIs simuladas: 375/768/1440, light/dark, abertura por teclado, Escape devolvendo foco, retomada e ausência de overflow/erro JS. Não equivale a QA autenticado da campanha real.
- Prova por RPC no Supabase oficial: 2 rascunhos encontrados no proprietário do rascunho indicado, somente resumo; proprietário inexistente retornou vazio. Nenhum conteúdo ou identificador bruto registrado aqui.
- Nenhuma chamada Meta real, upload, geração paga ou criação de campanha nesta rodada. Permissões atuais do System User ainda dependem da conferência do operador.

## Fontes e decisão

SDK oficial Meta, get_ads_pixels: target_class=AdsPixel na edge /adspixels:
https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adaccount.py

Grants, RLS e schema privado (docs consultadas em 09/09/2026 UTC):
https://supabase.com/docs/guides/api/securing-your-api

Business Manager exige sessão; nomes exatos dos menus podem variar. Não foi alegada inspeção autenticada dessa interface.

## Estado e reversão

P11-T02/P11-T05 permanecem partial: canário PAUSED, destino definitivo, fonte/evento selecionados e elegibilidade real ainda pendentes. Nós cap_meta_ads/cap_bancada_criativa recebem esta evidência.
Para desabilitar a listagem, revogar EXECUTE da função pública para service_role; isso preserva todos os rascunhos e os RPCs anteriores de salvar/ler. Nenhum rollback foi aplicado.
