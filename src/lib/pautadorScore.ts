// ============================================
// PAUTADOR PRO — preview client-side da nota de arbitragem.
// ESPELHO de backend/app/scoring.py (fonte da verdade). Usado apenas para
// PREVIEW instantâneo no formulário de adição manual; quando a oportunidade
// é persistida, o backend recalcula a nota autoritativa.
// ============================================

import type { Competition, Qual4, Tier } from '@/types/pautador';

const VOLUME_SCORE: Record<string, number> = { very_high: 100, high: 75, medium: 50, low: 25 };
const RPM_SCORE = VOLUME_SCORE;
const COMPETITION_SCORE: Record<string, number> = { low: 100, medium: 50, high: 25 };
const CONFIDENCE_SCORE: Record<string, number> = { very_high: 1.0, high: 0.85, medium: 0.7, low: 0.5 };
const TIER_WEIGHT: Record<string, number> = { S: 1.5, A: 1.2, B: 1.0, EXPERIMENTAL: 0.9 };

export function calcArbitrageScore(
  volume?: Qual4 | null,
  rpm?: Qual4 | null,
  competition?: Competition | null,
  confidence?: Qual4 | null,
  tier?: Tier | null,
): number {
  const vol = VOLUME_SCORE[volume ?? ''] ?? 25;
  const r = RPM_SCORE[rpm ?? ''] ?? 25;
  const comp = COMPETITION_SCORE[competition ?? ''] ?? 50;
  const conf = CONFIDENCE_SCORE[confidence ?? ''] ?? 0.7;
  const tierMult = TIER_WEIGHT[tier ?? ''] ?? 1.0;
  const base = vol * 0.25 + r * 0.4 + comp * 0.35;
  // Math.round = half-up, igual ao backend
  return Math.round(base * conf * tierMult * 100) / 100;
}
