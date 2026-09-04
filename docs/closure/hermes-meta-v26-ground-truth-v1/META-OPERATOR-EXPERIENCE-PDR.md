# Meta Operator Experience PDR

Canonical entry: `/trafego?rede=meta`. `/trafego?plataforma=meta` is an input-only compatibility alias and must normalize once to the canonical URL.

## Hub Meta
Surfaces: account selector, Campaigns, Ad Sets, Ads, Creatives, Insights, Alerts, History, freshness, provenance, next action, editability, receipt.

Every number shows source + read time. Failed read is not zero. Not configured is not empty inventory.

## Wizard
1. Conta e projeto — backend account binding/readiness.
2. Objetivo e mensuração — allowed objectives/goals from contract.
3. Destino e compliance — website/app/Special Ad Category.
4. Estratégia criativa — typed copilot outputs and human approval.
5. ZIP/assets — manifest and local validation.
6. Público e placements — v26 rules; no Explore Feed; HEC-F advantage_audience explicit.
7. Orçamento, lance e agenda — operator declared; no silent default spend.
8. Revisão do payload — normalized blueprint, diff, risk.
9. Validação — local first; remote only if authorized.
10. Criação em PAUSED e read-back — future separate mission.

Frontend never decides: token readiness, account access, objective/goal compatibility, Special Ad Category omission, placement compatibility, monetary caps, approval state, idempotency, read-back success.

The complete field ownership, conditional requirements, states and endpoints are normative in `META-UI-FIELD-CONTRACT.json` and `META-UI-API-BINDING.json`.
