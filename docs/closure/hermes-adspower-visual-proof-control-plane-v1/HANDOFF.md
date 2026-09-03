# Handoff — Secure AdsPower Broker + Visual Proof Control Plane V1

**Data:** 2026-09-02  
**Branch:** `sprint/hermes-adspower-visual-proof-control-plane-v1`  
**Base:** `382c5d4c67fc521d5e6739f8e76d1c36a96fdb53`  
**Modo de conclusão:** `BIA_TAKEOVER_POS_EXECUTOR` após Claude Code encerrar por `error_max_turns` na sessão `3bc63e8f-e15e-4a63-a5ab-b460009337bd`.

## Status

`LOCAL_ADSPOWER_VISUAL_PROOF_SPINE_CANDIDATE`

Este pacote fecha a espinha **local e hermética** entre Cofre/Asset Vault, referência lógica de credencial, broker AdsPower em loopback, fake AdsPower HTTP, VisualProofJob/Receipt e prontidão visual no Asset Vault.

Não declara:

- `REAL_ADSPOWER_PROVEN`;
- `REAL_PAGE_ONBOARDED`;
- `REAL_VISUAL_QA_PROVEN`;
- `PRODUCTION_READY`.

## Entregue

- Domínio `backend/app/visual_proof/` com `BrowserProfileReference`, `AdsPowerBrokerRequest`, `AdsPowerBrokerReceipt`, `VisualProofJob`, `VisualProofArtifact`, `VisualProofVerdict` e política de URL/SSRF.
- Plano de controle local com idempotência, lease em memória, owner isolation, timeout e vereditos honestos.
- Broker em `tools/adspower-broker/broker/` com bind loopback, Bearer próprio, allowlist de operação/perfil, resolução efêmera por referência e recibo sanitizado.
- Fake AdsPower HTTP em `tools/adspower-broker/fake/`, usado em E2E hermético com sockets reais em `127.0.0.1:0`.
- Integração read-only no Asset Vault: `GET /api/cofre/ativos/{ativo_id}/prontidao-visual`.
- Frontend mínimo no Asset Vault para distinguir bloqueado, pronto para peça, pronto para QA, QA em execução, corrigir, indeterminado e aprovado.
- Script estrutural `scripts/provar_visual_proof_hermetico.py` para provar ausência textual de AdsPower real, driver real, Supabase oficial write, Postiz/publicação, segredo/sentinela escapada, migrations e invasão de ownership.

## Não entregue por design

- Nenhum perfil AdsPower real iniciado.
- Nenhuma navegação/screenshot real.
- Nenhuma escrita no Supabase oficial.
- Nenhuma migration oficial aplicada.
- Nenhum Postiz/publicação/n8n/deploy.
- Nenhuma edição em Roadmap, curadoria ou grafo.

## Para Terminal 2 / PublicationJob

A capacidade consumível é o contrato de prontidão e o futuro `VisualProofJob`, não uma chamada direta ao broker. Terminal 2 deve depender de:

1. ativo real cadastrado no Cofre;
2. referência de credencial verificada;
3. perfil AdsPower lógico relacionado;
4. broker configurado;
5. job de QA visual persistido/executado;
6. aprovação humana quando requerida.

Enquanto `qa_visual.estado` for `nao_persistido`, `nao_executado`, `em_execucao` ou `indeterminado`, PublicationJob não deve pintar o portão como verde.
