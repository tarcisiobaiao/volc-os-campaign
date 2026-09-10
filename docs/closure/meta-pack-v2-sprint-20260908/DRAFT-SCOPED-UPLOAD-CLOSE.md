# Fechamento da autorização de mídia por rascunho

09/09/2026. Branch operacional existente; sem novo checkout, commit, push ou deploy.

## Concluído

- Migration `20260909070930_meta_draft_media_authorization.sql` aplicada em transação no Supabase oficial `https://database.agenciavolc.com.br`.
- Uma autorização administrativa, limitada ao rascunho previamente autorizado, sua conta e uma imagem selecionada. Prazo: 10/09/2026 às 04:23:31 (America/Sao_Paulo). Não se renova automaticamente.
- Hash dos bytes congelado na autorização. Propriedade resolvida pelo job do master. A seleção precisa continuar salva num conjunto existente do mesmo rascunho.
- Tabela de autorizações privada, RLS forçada, sem acesso de escrita do service_role nem de usuários. RPC pública SECURITY INVOKER, implementação privada SECURITY DEFINER; chamada apenas pelo backend service_role.
- Backend confere escopo antes da inspeção e novamente antes de obter a credencial/enviar. A presença de draft_ref impede fallback para autorização geral da conta.
- Frontend envia o mesmo draft_ref na consulta da autorização e no registro. Trocar rascunho/conta/seleção invalida respostas antigas; liberação restrita aparece explicitamente. Aprovação humana, inspeção e publicação continuam atos distintos.
- Recuperadas pela versão HEAD 40 dependências rastreadas ausentes (código/testes/start-dev), sem sobrescrever arquivos existentes. Documentos históricos ausentes não foram recuperados nesta intervenção.

## Provas

- 143 testes backend/SQL passaram: rascunhos/CAS, mídia, catálogos e nova autorização.
- Teste SQL usa UUID para dono do job/pack e text no rascunho, conforme catálogo oficial. Apply/reapply; dono/conta/rascunho incorretos, imagem duplicada, remoção de seleção/conjunto, arquivo arquivado/hash alterado, expiração e revogação negados.
- RPC oficial conferida pelo cliente real do backend: seleção atual permitida; outro rascunho e outro dono negados; autorização geral da conta continua falsa.
- 12 testes do componente passaram, incluindo propagação do rascunho até o envio e exigência de segundo clique.
- Build Vite passou. Typecheck global segue com falhas fora do escopo desta alteração; não é gate verde global.
- Chrome isolado: seis combinações 375/768/1440 × claro/escuro, teclado, carregamento, resultado e estado bloqueado; zero erro JS/overflow. APIs simuladas e rede externa bloqueada. Não equivale a sessão autenticada ou upload real.
- Frontend 8080 e backend 8010 responderam HTTP 200.

## Ainda não concluído

O rascunho persistido mantém uma URL de teste e nenhuma fonte de mensuração selecionada. O evento escolhido é CONTENT_VIEW. A URL final e qual pixel/dataset usar foram solicitados ao operador; nenhuma escolha foi inventada.

Não houve upload Meta, criação de campanha ou ativação nesta janela. Faltam envio pelo fluxo autenticado, montagem/retomada dos anúncios com recibo real, validação atual do plano, condições de destino, autorização de execução restrita e canário PAUSED com read-back. A autorização de upload NÃO libera essas outras etapas.

P11-T07 registra o encerramento específico da autorização de mídia. P11-T02 e P11-T05 continuam partial até suas provas de ponta a ponta. Nós afetados: cap_meta_ads e cap_bancada_criativa.

## Revogação

O operador do banco pode preencher `revoked_at` da autorização específica. Não apagar packs, masters, seleções ou recibos para revogar. Não ampliar prazo/escopo automaticamente nem ligar flags gerais para contornar uma recusa.
