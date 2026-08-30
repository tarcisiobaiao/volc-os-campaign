# Ações de segurança

## P0 — revogar chave legada exposta

Durante a onda zero de higiene, `run_refresh.cjs` foi identificado com uma chave
`service_role` hardcoded de uma instância Supabase hospedada antiga. O script também
continha deleção e aplicação dinâmica de SQL.

### Contenção já aplicada

- segredo removido do working tree;
- script substituído por stub bloqueado em `scripts/archive/campaign-highlights/`;
- JWTs encontrados em dois runbooks legados de deploy também foram redigidos;
- scanner local sem vazamento de valores adicionado ao pipeline do Mapa Vivo.

### Ação externa obrigatória

1. identificar a instância hospedada antiga;
2. revogar/rotacionar a chave `service_role` exposta;
3. verificar logs e último uso da credencial;
4. decidir se o histórico Git será reescrito em uma janela coordenada;
5. confirmar que n8n e serviços atuais usam apenas a fonte self-hosted governada.

Reescrever histórico afeta clones e branches; não deve ser feito como efeito colateral
de uma reorganização. Até a rotação, trate a chave antiga como comprometida.
