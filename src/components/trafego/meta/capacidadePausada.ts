import type { CapacidadePausadaMeta } from '@/lib/pautadorApi';

/** Presentation only. Dispatch still requires current server capabilities,
 * exact-plan validation, human approval and destination proof. Historical
 * `criar_liberado` is deliberately not interpreted as a current feature flag. */
export function fluxoPausadoImplementado(item: {
  capacidade_pausada?: CapacidadePausadaMeta;
} | null | undefined): boolean {
  const capacidade = item?.capacidade_pausada;
  return capacidade?.implementada === true
    && capacidade.fluxo === 'VALIDAR_APROVAR_CRIAR_PAUSADA'
    && capacidade.estado_ao_nascer === 'PAUSED'
    && capacidade.autoriza_ativacao === false;
}
