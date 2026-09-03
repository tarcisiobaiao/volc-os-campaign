/**
 * Recibos de portão para teste — a FORMA exata que `recibo.emitir` produz.
 *
 * ⚠️ Não é um mock livre. Os campos, os nomes e os tipos são copiados de
 * `backend/app/landing_policy/recibo.py`; se o backend mudar a forma, estes
 * arquivos precisam falhar junto. Um fixture inventado testaria o adaptador
 * contra um contrato que não existe, que é a forma mais cara de ter cobertura
 * verde e produção quebrada.
 */

export interface ReciboDeTeste extends Record<string, unknown> {
  schema: string;
}

/** Um recibo APTO: sem bloqueio, sem desconhecido, no ponto de campanha. */
export function reciboApto(
  over: Record<string, unknown> = {},
  { agora_epoch = 1_756_900_000 }: { agora_epoch?: number } = {},
): ReciboDeTeste {
  return {
    schema: 'LandingPolicyGateReceipt',
    schema_version: 'landing_policy_gate_receipt.v2',
    gate_point: 'campaign_destination_eligibility',
    role: 'paid_destination',
    role_declared: 'paid_destination',
    url: 'https://creditoup.com.br/cartao-para-negativado',
    content_sha256: 'a'.repeat(64),
    content_fingerprint: 'b'.repeat(64),
    observed_at: '2026-09-03T09:00:00Z',
    observed_at_epoch: agora_epoch - 60,
    freshness_window_s: 86400,
    policy_contract_version: 'paid_destination_policy_spine.v2',
    policy_source_version: 'c'.repeat(64),
    gate_point_requires: ['live_drift', 'approval_receipt', 'redirect_chain'],
    verdict: 'approved',
    evidence_completeness: {
      conclusive: ['claims', 'identity', 'links', 'live_drift'],
      inconclusive: [],
      required_here: ['live_drift', 'approval_receipt', 'redirect_chain'],
      ratio: '10/10',
    },
    readiness: {
      volc_gate: 'ready',
      live_verified: true,
      google_approval: 'unknown',
      google_approval_note:
        'Este portão lê HTML; ele não lê a decisão do revisor do Google.',
    },
    paid_destination_ready: true,
    not_ready_reasons: [],
    blockers: [],
    risks: [],
    observations: [],
    unknowns: [],
    evidence_refs: ['inventario/links.json'],
    external_mutation: {
      google_ads_mutate: false,
      wordpress_write: false,
      appeal_submitted: false,
      deploy: false,
    },
    ...over,
  };
}

/** O portador: o dict que o backend já trafega, com o recibo dentro dele. */
export function portadorApto(
  over: Record<string, unknown> = {},
  opcoes?: { agora_epoch?: number },
): Record<string, unknown> {
  return {
    post_id: 2152,
    slug: 'cartao-para-negativado',
    url_wp: 'https://creditoup.com.br/cartao-para-negativado',
    status_wp: 'publish',
    landing_policy_receipt: reciboApto(over, opcoes),
  };
}
