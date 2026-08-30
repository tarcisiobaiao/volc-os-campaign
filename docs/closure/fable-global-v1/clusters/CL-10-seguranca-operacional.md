# CL-10 · Segurança operacional pré-lançamento

**Horizonte**: A (gate de lançamento) · **Resultado**: nenhuma superfície
privilegiada aberta; credenciais rotacionadas; smoke anônimo prova zero escrita.

## Estado factual (F017, F021)

- Webhook de mutação n8n `apply-bidding` ATIVO e sem autenticação (**a maior
  contradição operacional viva**) — mutação Google Ads fora de governança.
- Endpoints `/api/supabase/*` sem autenticação carregando service_role, CORS *.
- Credenciais no histórico git (904cb0b); anon key demo; v8_02-07 não
  aplicadas (public.users sem RLS); seis tabelas operacionais sem REVOKE/RLS
  fechados (P02-T05 risk — único `risk` do roadmap).
- Rotação/reemissão de credenciais é bloqueador pré-lançamento declarado.

## Missões

| ID | O quê | Onda | Portão |
|---|---|---|---|
| M-W2-05 | Inventário executável + scripts prontos: REVOKE/RLS das seis tabelas, plano de rotação, fechamento dos endpoints, smoke anônimo — TUDO escrito e provado em cluster descartável, NADA aplicado | 2 | nenhum |
| M-W3-13 | Janela de aplicação: desativar/blindar webhook (**D10**), aplicar REVOKE/RLS, rotacionar credenciais (**D4**), rodar smoke anônimo em produção | 3 | D4 + D10 |

## Regra dura

Nenhum valor sensível em doc/commit/prompt; o registro guarda localização e
classe do achado, nunca o valor (regra do P10-T08). A missão M-W2-05 não toca
n8n nem banco — produz o pacote executável para a janela humana.
