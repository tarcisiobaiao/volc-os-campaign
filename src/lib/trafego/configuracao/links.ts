/**
 * Os links que levam à Bancada JÁ COM O CANAL.
 *
 * Até 08/10/2026 nenhum link da interface punha `?canal=`: a Bancada abria em
 * Search, e Display, Demand Gen e PMax só existiam para quem digitasse a URL.
 * Toda navegação para `/trafego/nova/:id` passa por aqui.
 */
import { CANAIS_COM_MANIFESTO, canalCanonico } from '@/types/trafego';
import type { CanalComManifesto } from '@/types/trafego';

/** Os quatro canais que a Bancada monta, na ordem em que a tela os oferece. */
export const CANAIS_DA_BANCADA: readonly CanalComManifesto[] = CANAIS_COM_MANIFESTO;

export const ROTULO_DO_CANAL_NA_BANCADA: Record<CanalComManifesto, string> = {
  SEARCH: 'Search',
  DISPLAY: 'Display',
  DEMAND_GEN: 'Demand Gen',
  PERFORMANCE_MAX: 'Performance Max',
};

/** Um valor de URL (inclusive o apelido `PMAX`) → canal da Bancada, ou `null`. */
export function canalDaBancadaOuNulo(bruto: string | null | undefined): CanalComManifesto | null {
  const c = canalCanonico(bruto ?? '');
  return c && (CANAIS_COM_MANIFESTO as readonly string[]).includes(c)
    ? (c as CanalComManifesto)
    : null;
}

export function hrefDaBancada(
  opportunityId: number,
  canal: CanalComManifesto,
  opcoes: { runId?: number | null; relancar?: boolean } = {},
): string {
  const q = new URLSearchParams();
  if (opcoes.runId != null) q.set('run', String(opcoes.runId));
  q.set('canal', canal);
  if (opcoes.relancar) q.set('relancar', '1');
  return `/trafego/nova/${opportunityId}?${q.toString()}`;
}

/** Da Visão Multicanal para a aba de oportunidades, com o canal escolhido —
 *  a Bancada exige uma oportunidade, e é lá que o operador a escolhe. */
export function hrefDasOportunidadesDoCanal(canal: CanalComManifesto): string {
  return `/trafego?aba=preparar&canal=${canal}`;
}
