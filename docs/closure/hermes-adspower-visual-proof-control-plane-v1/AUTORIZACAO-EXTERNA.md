# Checkpoint único de autorização externa

Este bloco é o pedido único para uma etapa futura real. Nada abaixo foi executado nesta missão.

## 1. Dados mínimos da página real

- nome público;
- URL pública HTTPS;
- plataforma;
- owner/sub;
- finalidade;
- estado;
- Business Portfolio, se aplicável;
- identificador externo conforme política;
- próximo uso esperado.

## 2. Referências lógicas necessárias no 1Password

- nome lógico da credencial da página;
- referência lógica do AdsPower API key para o broker;
- ambas sem valor secreto e sem caminho completo exibido em relatório público.

## 3. Referência do perfil AdsPower

- `perfil_logico` estável;
- owner;
- ativo relacionado;
- finalidade;
- estado;
- host/broker lógico;
- nome lógico da credencial;
- domínios permitidos;
- operações permitidas.

## 4. Chamada read-only proposta ao AdsPower

Primeiro checkpoint permitido futuro: saúde/estado de perfil allowlisted via broker local, endpoint loopback, Bearer próprio, sem navegar e sem screenshot.

## 5. Migration proposta

Se a operação precisar persistir histórico real de QA visual: criar migration nova para `VisualProofJob`/receipt com RLS forçada, append-only onde necessário, ownership, idempotência, anti-segredo, rollback e prova em PostgreSQL descartável antes de qualquer Supabase oficial.

## 6. Escrita governada no Cofre

Somente após input humano e autorização literal: cadastrar página real e relacionar perfil AdsPower lógico. Sem cookie, proxy bruto, senha, token, API key ou localizador completo em payload público.

## 7. Primeira URL segura para QA

A URL deve ser HTTPS pública, resolver somente para IPs públicos, pertencer ao domínio esperado e não redirecionar para rede privada/metadata.

## 8. Comando exato futuro

A definir após preencher allowlist privada 0600 no host AdsPower. Deve usar broker loopback, Bearer próprio e operação allowlisted. Não deve chamar AdsPower diretamente do app VOLC.

## 9. Rollback

- parar broker local;
- remover allowlist privada do host isolado se criada;
- remover artefatos privados de teste real;
- rollback de migration apenas se ela tiver sido aplicada em ambiente controlado.

## 10. Riscos

- `user_id` AdsPower abre sessão autenticada se vazar;
- screenshots podem conter dados pessoais;
- DNS/redirect podem mudar entre autorização e execução;
- falha técnica do AdsPower não deve virar reprovação editorial.

## 11. Continua explicitamente proibido sem nova autorização

AdsPower real, perfil real iniciado, navegação real, screenshot real, segredo impresso, Supabase oficial write, migration oficial, Postiz, publicação, Meta/Facebook write, n8n, deploy, merge, Roadmap/grafo e push fora da feature branch.
