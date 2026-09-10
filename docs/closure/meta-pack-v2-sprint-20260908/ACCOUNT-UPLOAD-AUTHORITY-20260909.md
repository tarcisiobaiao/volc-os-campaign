# Autorização de mídia por conta — 09/09/2026

P11-T12 concluído no escopo de autorização, não de publicação ponta a ponta.

O operador autorizou envio para todos os seus rascunhos na conta selecionada. A antiga concessão era restrita a um rascunho e hashes; novos rascunhos não a herdavam.

Migration oficial: `supabase/migrations/20260909114432_meta_account_draft_upload_authority.sql`.
SHA256: `701a79d4ccaeca55ac761df0f76348ce049d765bf233f8c1c99df126febb9464`.
Aplicada em `https://database.agenciavolc.com.br`; concessão owner/conta registrada por operador, sem expiração automática, revogável. Não permite autoconcessão pelo cliente ou service_role.

O verificador exige rascunho ativo do proprietário na conta, seleção persistida em conjunto existente, masters próprios e não arquivados. Aprovação humana e aprovação final do plano continuam obrigatórias. Não concede ativação. A autorização antiga por rascunho continua como alternativa.

## Provas

- 18 testes SQL/autoridade passaram, incluindo migração repetida, novo rascunho próprio, isolamento de conta/proprietário, seleção inválida, arquivamento, revogação e proibição de autoconcessão.
- Handler real consultado com identidade e seleção atuais, usando RPCs do banco oficial: `registro_de_imagem=ENABLED`, `registro_duravel_disponivel=true`, `escopo_do_envio=ACCOUNT_OWNED_DRAFTS`, `motivo=null`, `aprovacao_final_exigida=true`.
- Configuração efetiva a partir do diretório do backend: validação habilitada e nenhuma flag de criação ausente.
- Nenhum upload, criação ou ativação Meta nesta rodada. A prova do handler não substitui teste autenticado no navegador nem aceite remoto da campanha; P11-T09/P11-T11 continuam parciais.
