# SUPERSESSÃO — candidato de broker do Cofre

**Pacote:** `docs/closure/hermes-asset-vault-organic-access-v1/`
**Adjudicação:** 2026-09-03, feature `sprint/asset-vault-operator-experience-v2`
**Veredito:** `CANDIDATO NÃO INTEGRADO/SUPERADO`

Este pacote descreve, em 02/09/2026, um sidecar candidato em
`backend/app/asset_vault/broker/` apresentado como entrega de P03-T11.
Esse pacote **não está na árvore final**. Foi removido na adjudicação de
autoridade única. **Não transplante** `inventario_perfis` / `inventario_grupos`
a partir desta evidência.

## Autoridade canônica única (P03-T11)

`tools/adspower-broker/`

Já possui servidor loopback autenticado, `POST /v1/operacoes`, `GET /v1/saude`,
resolução efêmera pelo 1Password, allowlist, idempotência, integração com
`VisualProofJob`, consumidor real `BrokerHttp` e operações
`estado` / `abrir` / `capturar` / `fechar`.

`backend/app/visual_proof/infraestrutura.py` é cliente do broker VOLC, nunca
da AdsPower Local API.

## O que neste pacote continua verdadeiro

- prontidão operacional (`backend/app/asset_vault/prontidao.py` e rotas);
- lista mínima de campos da Página (`CAMPOS-QUE-FALTAM.md`);
- zero escrita externa da missão original;
- P03-T11 permanece `partial`: AdsPower real e resolução real não foram exercitados;
- inventário real de perfis/grupos **não está implementado**;
- interface pronta **não** significa Cofre povoado.

## O que neste pacote está superado

Qualquer afirmação de que `backend/app/asset_vault/broker/` existe na árvore
final, é autoridade de P03-T11, ou já inventaria perfis/grupos ao vivo.
