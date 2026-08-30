/**
 * As regras da decisão de aprovação.
 *
 * `ajuste_solicitado` e `rejeitado` sem motivo são a mesma coisa na prática:
 * alguém recebe a peça de volta e não sabe o que corrigir. O campo obrigatório
 * não é burocracia, é o que faz a decisão ser acionável pela pessoa seguinte.
 */
import type { DecisaoDeAprovacao } from '@/types/criativos';

export const DECISOES: readonly DecisaoDeAprovacao[] = [
  'aprovado',
  'ajuste_solicitado',
  'rejeitado',
] as const;

export function motivoObrigatorio(decisao: DecisaoDeAprovacao): boolean {
  return decisao === 'ajuste_solicitado' || decisao === 'rejeitado';
}
