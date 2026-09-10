# Confirmação do anunciante e persistência do rascunho

Estado: correção local e de banco verificada; canário Meta completo pendente.

## Causa e correção

O frontend/Pydantic aceitavam regulatoryIdentityRef, mas a função SQL oficial de salvar rascunhos ainda possuía uma lista fechada sem esse campo. Ela recusava o payload; a rota escondia essa validação como indisponibilidade genérica.

Migration 20260909112458_meta_draft_regulatory_identity.sql aplicada exclusivamente no Supabase operacional database.agenciavolc.com.br. SHA256 84f9853e704c8b9c86ee89d7908b6c6ab70cd68e05ee48bfc0c7de04719ee822. Altera somente a cláusula da função existente, com guarda de fonte e regex para referência opaca; preserva proprietário, CAS, grants, arquivamento e ausência de autoridade de lançamento. Seleção vazia normalizada para ausência antes de enviar ao banco. Erros conhecidos de validação retornam 422 sem detalhes privados.

## Identidade sem confusão com conjuntos

O catálogo identifica pares regulatórios presentes na própria conta; os nomes agora vêm de GET direto dos objetos de identidade, não de nomes de campanhas nem do Business. Na conta consultada, anunciante e pagador retornaram o mesmo nome real. O campo advertiser_verification_status na conta foi recusado pela API atual; não é usado como prova. Verificação do Business não é promovida a verificação atual do anunciante.

A resposta pública tem allowlist explícita e não inclui IDs regulatórios brutos ou nomes de conjuntos. A interface mostra Anunciante/Pagador e confirmação humana. Não copia objetos, configurações ou público. Descoberta dos IDs ainda usa histórico da própria conta porque um catálogo direto de todas as identidades elegíveis não foi demonstrado; isso permanece uma limitação, especialmente para contas sem histórico. Consulta do nome pode falhar sem inventar nome ou estado verificado.

## Provas

- 55 testes focais backend, incluindo PostgreSQL local real, reaplicação, save/read/clear, owner e entradas inválidas.
- 33 testes frontend focais passaram.
- No Supabase oficial: probe sintético com service_role salvou, recuperou, limpou seleção e confirmou isolamento de proprietário; ROLLBACK integral. Nenhum rascunho real foi excluído ou alterado nesta prova.
- Catálogo real completo retornou nomes dos objetos de identidade e nenhuma referência nominal a conjuntos antigos.
- Chrome isolado em 375/768/1440 claro/escuro: teclado, confirmação explícita, independência entre conjuntos e nenhuma falha/overflow. Não é sessão autenticada ponta a ponta.
- Build passou; frontend HTTP200; backend protege nova rota com HTTP401 sem sessão.

## Limites e próximo teste

Nenhuma campanha ou conjunto criado/deletado nesta correção. A exclusão no Gerenciador é ato do operador, não foi executada aqui. Para uma intenção nova, usar novo rascunho e nome distinto da tentativa anterior; não apagar registros duráveis para contornar proteção contra duplicação. Confirmar identidade, salvar, validar e aprovar o plano antes de criar PAUSED. Aceitação remota de todos os objetos continua pendente; ativação proibida.

P11-T11 e cap_meta_ads permanecem partial.
